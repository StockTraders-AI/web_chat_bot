import asyncio
import importlib
import inspect
import os
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

try:
    import socketio
except Exception as exc:  # pragma: no cover - depends on optional runtime package
    socketio = None
    SOCKETIO_IMPORT_ERROR = exc
else:
    SOCKETIO_IMPORT_ERROR = None


def _ensure_socketio():
    global socketio, SOCKETIO_IMPORT_ERROR

    if socketio is not None:
        return socketio

    try:
        socketio = importlib.import_module("socketio")
    except Exception as exc:  # pragma: no cover - depends on optional runtime package
        SOCKETIO_IMPORT_ERROR = exc
        return None

    SOCKETIO_IMPORT_ERROR = None
    return socketio


REALTIME_CORE_URL = os.getenv(
    "REALTIME_CORE_URL",
    "http://112.213.91.235:3005/realtime",
).strip()
REALTIME_NAMESPACE = os.getenv("REALTIME_NAMESPACE", "/realtime").strip() or "/realtime"
REALTIME_WAVE_ENABLED = os.getenv("REALTIME_WAVE_ENABLED", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
_wave_cache = {
    "payload": None,
    "rows": [],
    "sent_at": "",
    "received_at": "",
}
_socket_task: asyncio.Task | None = None
_socket_client = None
_wave_listeners = []
_last_socket_error = ""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_date(row: dict) -> str:
    return str(
        row.get("date")
        or row.get("tradingDate")
        or row.get("time")
        or row.get("createdAt")
        or ""
    )[:10]


def _extract_wave_rows(data) -> list[dict]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]

    if not isinstance(data, dict):
        return []

    for key in (
        "waveDatas",
        "stockWaveDatas",
        "items",
        "records",
        "result",
        "results",
    ):
        value = data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    nested = data.get("data")
    if isinstance(nested, list):
        return [item for item in nested if isinstance(item, dict)]
    if isinstance(nested, dict):
        rows = _extract_wave_rows(nested)
        if rows:
            return rows

    if any(key in data for key in ("waitbuy", "waitBuy", "wait_buy", "cho_mua")):
        return [data]

    return []


def clear_wave_cache():
    _wave_cache["payload"] = None
    _wave_cache["rows"] = []
    _wave_cache["sent_at"] = ""
    _wave_cache["received_at"] = ""


def update_wave_payload(payload) -> bool:
    if not isinstance(payload, dict):
        return False

    channel = payload.get("channel")
    if channel and channel != "wave":
        return False

    data = payload.get("data") if "data" in payload else payload
    rows = _extract_wave_rows(data)

    sent_at = str(payload.get("sentAt") or payload.get("sent_at") or "")
    if sent_at and rows:
        sent_date = sent_at[:10]
        for row in rows:
            if not _row_date(row) and sent_date:
                row.setdefault("date", sent_date)

    _wave_cache["payload"] = data
    _wave_cache["rows"] = rows
    _wave_cache["sent_at"] = sent_at
    _wave_cache["received_at"] = _utc_now()
    return True


def latest_wave_snapshot(date: str | None = None) -> dict | None:
    rows = [row for row in _wave_cache["rows"] if isinstance(row, dict)]
    if not rows:
        return None

    requested_date = str(date or "")[:10]
    selected_rows = rows
    fallback_date = ""

    if requested_date:
        selected_rows = [row for row in rows if _row_date(row) == requested_date]
        if not selected_rows:
            dated_rows = [row for row in rows if _row_date(row)]
            if dated_rows:
                fallback_date = max(_row_date(row) for row in dated_rows)
                selected_rows = [row for row in dated_rows if _row_date(row) == fallback_date]
            else:
                selected_rows = rows

    selected_rows = sorted(selected_rows, key=_row_date)

    return {
        "name": "ALL",
        "waveDatas": selected_rows,
        "_source": "realtime_wave",
        "_sentAt": _wave_cache["sent_at"],
        "_receivedAt": _wave_cache["received_at"],
        "_requestedDate": requested_date,
        "_fallbackDate": fallback_date,
        "_usedFallbackLatest": bool(fallback_date),
    }

def wave_status() -> dict:
    _ensure_socketio()
    latest = latest_wave_snapshot()
    rows = _wave_cache["rows"]
    task_done = bool(_socket_task and _socket_task.done())
    return {
        "enabled": REALTIME_WAVE_ENABLED,
        "has_socketio": socketio is not None,
        "connected": bool(_socket_client and getattr(_socket_client, "connected", False)),
        "task_running": bool(_socket_task and not _socket_task.done()),
        "task_done": task_done,
        "row_count": len(rows),
        "latest_date": _row_date((latest or {}).get("waveDatas", [{}])[-1]) if latest else "",
        "sent_at": _wave_cache["sent_at"],
        "received_at": _wave_cache["received_at"],
        "import_error": str(SOCKETIO_IMPORT_ERROR) if SOCKETIO_IMPORT_ERROR else "",
        "last_error": _last_socket_error,
        "url": _socket_connect_url(),
        "namespace": REALTIME_NAMESPACE,
    }




def wave_debug_snapshot(date: str | None = None, sample_limit: int = 5) -> dict:
    status = wave_status()
    rows = [row for row in _wave_cache["rows"] if isinstance(row, dict)]
    sample_limit = max(1, min(int(sample_limit or 5), 20))
    snapshot = latest_wave_snapshot(date)
    payload = _wave_cache["payload"]

    if isinstance(payload, dict):
        payload_type = "dict"
        payload_keys = list(payload.keys())[:30]
    elif isinstance(payload, list):
        payload_type = "list"
        payload_keys = []
    elif payload is None:
        payload_type = "none"
        payload_keys = []
    else:
        payload_type = type(payload).__name__
        payload_keys = []

    return {
        **status,
        "debug": {
            "requested_date": str(date or "")[:10],
            "payload_type": payload_type,
            "payload_keys": payload_keys,
            "sample_rows": rows[:sample_limit],
            "latest_rows": rows[-sample_limit:],
            "snapshot_row_count": len((snapshot or {}).get("waveDatas", [])),
            "snapshot_rows": (snapshot or {}).get("waveDatas", [])[:sample_limit],
            "snapshot_requested_date": (snapshot or {}).get("_requestedDate", ""),
            "snapshot_fallback_date": (snapshot or {}).get("_fallbackDate", ""),
            "snapshot_used_fallback_latest": bool((snapshot or {}).get("_usedFallbackLatest")),
        },
    }

def add_wave_listener(listener):
    if listener not in _wave_listeners:
        _wave_listeners.append(listener)


def _dispatch_wave_payload(payload):
    for listener in list(_wave_listeners):
        try:
            result = listener(payload)
            if inspect.isawaitable(result):
                asyncio.create_task(_run_wave_listener(result))
        except Exception:
            pass


async def _run_wave_listener(awaitable):
    try:
        await awaitable
    except Exception:
        pass


def _socket_connect_url() -> str:
    parsed = urlsplit(REALTIME_CORE_URL)
    if parsed.path.rstrip("/") == REALTIME_NAMESPACE:
        return urlunsplit((parsed.scheme, parsed.netloc, "", parsed.query, parsed.fragment))
    return REALTIME_CORE_URL


async def _run_realtime_wave_client():
    global _last_socket_error, _socket_client

    socketio_module = _ensure_socketio()
    if socketio_module is None:
        return

    while REALTIME_WAVE_ENABLED:
        client = socketio_module.AsyncClient(
            reconnection=False,
            logger=False,
            engineio_logger=False,
        )
        _socket_client = client

        @client.event(namespace=REALTIME_NAMESPACE)
        async def connect():
            global _last_socket_error
            _last_socket_error = ""
            await client.emit(
                "message",
                {
                    "action": "subscribe",
                    "channels": ["wave"],
                },
                namespace=REALTIME_NAMESPACE,
            )

        @client.event(namespace=REALTIME_NAMESPACE)
        async def disconnect():
            pass

        @client.event(namespace=REALTIME_NAMESPACE)
        async def connect_error(data):
            global _last_socket_error
            _last_socket_error = f"connect_error: {data!r}"

        @client.on("message", namespace=REALTIME_NAMESPACE)
        async def on_message(payload):
            if update_wave_payload(payload):
                _dispatch_wave_payload(payload)

        try:
            await client.connect(
                _socket_connect_url(),
                transports=["websocket"],
                namespaces=[REALTIME_NAMESPACE],
                wait_timeout=10,
            )
            await client.wait()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _last_socket_error = str(exc)
        finally:
            if client.connected:
                await client.disconnect()

        await asyncio.sleep(5)


def start_realtime_wave_client():
    global _socket_task

    if not REALTIME_WAVE_ENABLED:
        return None

    if _ensure_socketio() is None:
        return None

    if _socket_task and not _socket_task.done():
        return _socket_task

    _socket_task = asyncio.create_task(_run_realtime_wave_client())
    return _socket_task


def _should_restart_stale_socket(status: dict) -> bool:
    return (
        bool(status.get("task_running"))
        and not bool(status.get("connected"))
        and bool(status.get("last_error"))
    )


async def ensure_realtime_wave_client(timeout: float = 5.0, restart_stale: bool = True):
    task = start_realtime_wave_client()
    if not task:
        return wave_status()

    loop = asyncio.get_running_loop()
    deadline = loop.time() + max(0.0, timeout)

    while loop.time() < deadline:
        status = wave_status()
        if status["connected"] or status["task_done"]:
            return status
        await asyncio.sleep(0.1)

    status = wave_status()
    if restart_stale and _should_restart_stale_socket(status):
        await stop_realtime_wave_client()
        task = start_realtime_wave_client()
        if not task:
            return wave_status()

        deadline = loop.time() + max(0.0, timeout)
        while loop.time() < deadline:
            status = wave_status()
            if status["connected"] or status["task_done"]:
                return status
            await asyncio.sleep(0.1)

    return wave_status()


async def stop_realtime_wave_client():
    global _socket_task

    if _socket_client and getattr(_socket_client, "connected", False):
        await _socket_client.disconnect()

    if _socket_task and not _socket_task.done():
        _socket_task.cancel()
        try:
            await _socket_task
        except asyncio.CancelledError:
            pass

    _socket_task = None

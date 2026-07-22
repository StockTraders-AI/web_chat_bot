import asyncio
import importlib
import inspect
import os
from collections import deque
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
_socket_events = deque(maxlen=50)
_wave_messages = deque(maxlen=20)


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


def _payload_channel(payload) -> str:
    return str(payload.get("channel") or "") if isinstance(payload, dict) else ""


def _summarize_wave_payload(payload) -> dict:
    data = payload.get("data") if isinstance(payload, dict) and "data" in payload else payload
    rows = _extract_wave_rows(data)
    sample = rows[0] if rows else data
    return {
        "channel": _payload_channel(payload),
        "row_count": len(rows),
        "sent_at": str(payload.get("sentAt") or payload.get("sent_at") or "") if isinstance(payload, dict) else "",
        "received_at": _utc_now(),
        "sample": sample,
    }


def _record_socket_event(kind: str, **data):
    event = {
        "kind": kind,
        "at": _utc_now(),
        **data,
    }
    _socket_events.append(event)
    return event


def clear_wave_cache():
    _wave_cache["payload"] = None
    _wave_cache["rows"] = []
    _wave_cache["sent_at"] = ""
    _wave_cache["received_at"] = ""
    _wave_messages.clear()


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
    _wave_messages.append(_summarize_wave_payload(payload))
    return True


def latest_wave_snapshot(date: str | None = None) -> dict | None:
    rows = [row for row in _wave_cache["rows"] if isinstance(row, dict)]
    if not rows:
        return None

    requested_date = str(date or "")[:10]
    selected_rows = rows

    if requested_date:
        selected_rows = [row for row in rows if _row_date(row) == requested_date]
        if not selected_rows:
            return None

    selected_rows = sorted(selected_rows, key=_row_date)

    return {
        "name": "ALL",
        "waveDatas": selected_rows,
        "_source": "realtime_wave",
        "_sentAt": _wave_cache["sent_at"],
        "_receivedAt": _wave_cache["received_at"],
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
        "message_count": len(_wave_messages),
        "last_messages": list(_wave_messages),
        "events": list(_socket_events)[-10:],
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
        except Exception as exc:
            print("REALTIME_WAVE_LISTENER_ERROR:", exc)


async def _run_wave_listener(awaitable):
    try:
        await awaitable
    except Exception as exc:
        print("REALTIME_WAVE_LISTENER_ERROR:", exc)


def _socket_connect_url() -> str:
    parsed = urlsplit(REALTIME_CORE_URL)
    if parsed.path.rstrip("/") == REALTIME_NAMESPACE:
        return urlunsplit((parsed.scheme, parsed.netloc, "", parsed.query, parsed.fragment))
    return REALTIME_CORE_URL


async def _run_realtime_wave_client():
    global _last_socket_error, _socket_client

    socketio_module = _ensure_socketio()
    if socketio_module is None:
        print(f"REALTIME_WAVE_SOCKET_DISABLED: {SOCKETIO_IMPORT_ERROR}")
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
            _record_socket_event("connect", url=_socket_connect_url(), namespace=REALTIME_NAMESPACE)
            await client.emit(
                "message",
                {
                    "action": "subscribe",
                    "channels": ["wave"],
                },
                namespace=REALTIME_NAMESPACE,
            )
            _record_socket_event("subscribe", channels=["wave"])
            print("REALTIME_WAVE_SOCKET_CONNECTED")

        @client.event(namespace=REALTIME_NAMESPACE)
        async def disconnect():
            _record_socket_event("disconnect")
            print("REALTIME_WAVE_SOCKET_DISCONNECTED")

        @client.event(namespace=REALTIME_NAMESPACE)
        async def connect_error(data):
            global _last_socket_error
            _last_socket_error = f"connect_error: {data!r}"
            _record_socket_event("connect_error", data=repr(data))
            print("REALTIME_WAVE_SOCKET_CONNECT_ERROR:", data)

        @client.on("message", namespace=REALTIME_NAMESPACE)
        async def on_message(payload):
            summary = _summarize_wave_payload(payload)
            _record_socket_event("message", **{key: value for key, value in summary.items() if key != "sample"})
            print(
                "REALTIME_WAVE_RAW_MESSAGE:",
                f"channel={summary['channel']}",
                f"rows={summary['row_count']}",
                f"sent_at={summary['sent_at']}",
            )
            if update_wave_payload(payload):
                status = wave_status()
                print(
                    "REALTIME_WAVE_MESSAGE:",
                    f"rows={status['row_count']}",
                    f"latest_date={status['latest_date']}",
                )
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
            _record_socket_event("error", error=str(exc))
            print("REALTIME_WAVE_SOCKET_ERROR:", exc)
        finally:
            if client.connected:
                await client.disconnect()

        await asyncio.sleep(5)
        print("REALTIME_WAVE_SOCKET_RETRYING")


async def probe_realtime_wave_connection(timeout: float = 20.0) -> dict:
    socketio_module = _ensure_socketio()
    started_at = _utc_now()

    if socketio_module is None:
        return {
            "ok": False,
            "connected": False,
            "subscribed": False,
            "received_message": False,
            "started_at": started_at,
            "error": str(SOCKETIO_IMPORT_ERROR),
        }

    client = socketio_module.AsyncClient(
        reconnection=False,
        logger=False,
        engineio_logger=False,
    )
    message_event = asyncio.Event()
    events = []
    message_summary = None
    error_text = ""

    def record(kind: str, **data):
        item = {"kind": kind, "at": _utc_now(), **data}
        events.append(item)
        print("REALTIME_WAVE_PROBE:", item)

    @client.event(namespace=REALTIME_NAMESPACE)
    async def connect():
        record("connect", url=_socket_connect_url(), namespace=REALTIME_NAMESPACE)
        await client.emit(
            "message",
            {
                "action": "subscribe",
                "channels": ["wave"],
            },
            namespace=REALTIME_NAMESPACE,
        )
        record("subscribe", channels=["wave"])

    @client.event(namespace=REALTIME_NAMESPACE)
    async def disconnect():
        record("disconnect")

    @client.event(namespace=REALTIME_NAMESPACE)
    async def connect_error(data):
        record("connect_error", data=repr(data))

    @client.on("message", namespace=REALTIME_NAMESPACE)
    async def on_message(payload):
        nonlocal message_summary
        message_summary = _summarize_wave_payload(payload)
        record(
            "message",
            channel=message_summary["channel"],
            row_count=message_summary["row_count"],
            sent_at=message_summary["sent_at"],
        )
        update_wave_payload(payload)
        message_event.set()

    try:
        await client.connect(
            _socket_connect_url(),
            transports=["websocket"],
            namespaces=[REALTIME_NAMESPACE],
            wait_timeout=10,
        )
        try:
            await asyncio.wait_for(message_event.wait(), timeout=max(0.0, timeout))
        except asyncio.TimeoutError:
            record("message_timeout", timeout=timeout)
    except Exception as exc:
        error_text = str(exc)
        record("error", error=error_text)
    finally:
        if client.connected:
            await client.disconnect()

    return {
        "ok": not error_text,
        "connected": any(event["kind"] == "connect" for event in events),
        "subscribed": any(event["kind"] == "subscribe" for event in events),
        "received_message": message_summary is not None,
        "started_at": started_at,
        "finished_at": _utc_now(),
        "url": _socket_connect_url(),
        "namespace": REALTIME_NAMESPACE,
        "timeout": timeout,
        "error": error_text,
        "message": message_summary,
        "events": events,
        "cache_status": wave_status(),
    }


def start_realtime_wave_client():
    global _socket_task

    if not REALTIME_WAVE_ENABLED:
        print("REALTIME_WAVE_SOCKET_DISABLED: REALTIME_WAVE_ENABLED=false")
        return None

    if _ensure_socketio() is None:
        print(f"REALTIME_WAVE_SOCKET_DISABLED: {SOCKETIO_IMPORT_ERROR}")
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
        _record_socket_event("auto_restart", reason=status.get("last_error") or "stale_disconnected")
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

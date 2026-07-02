import requests
import json
import sys
from typing import Any, Dict
from core.tool_engine import ToolRegistry
from services.branch_map import extract_branch_path
from services.branch_tickers import BRANCH_DATA
from services.chan_song_client import get_chan_song
from services.stock_4key_evaluator import Stock4KeyError, evaluate_stock_4key
from services.ticker_policy import invalid_api_ticker, sanitize_api_result

DEBUG_API = True

def _configure_console_encoding():
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="backslashreplace")
            except Exception:
                pass


def _safe_console(value: Any) -> str:
    return str(value)


def _escaped_console(value: Any) -> str:
    return str(value).encode("ascii", errors="backslashreplace").decode("ascii")


def log(*args):
    if not DEBUG_API:
        return
    try:
        print(*(_safe_console(arg) for arg in args))
    except UnicodeEncodeError:
        print(*(_escaped_console(arg) for arg in args))


_configure_console_encoding()


def get_branch_path_by_ticker(ticker: str):

    if not ticker:
        return None

    ticker = ticker.upper()

    for b in BRANCH_DATA:
        if ticker in b["tickers"]:
            return b["path"]

    return None
# ============================================================
# API EXECUTOR
# ============================================================

class APIExecutor:

    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    def _apply_special_branch_alias(self, args: Dict[str, Any]) -> Dict[str, Any]:
        real_estate_branch = "B\\u1ea5t \\u0111\\u1ed9ng s\\u1ea3n d\\u00e2n c\\u01b0".encode("ascii").decode("unicode_escape")
        special_branch_map = {
            "BDS": real_estate_branch,
            "B\\u0110S".encode("ascii").decode("unicode_escape"): real_estate_branch,
        }
        ticker = args.get("ticker")
        if not ticker:
            return args

        value = str(ticker).upper().strip()
        if value not in special_branch_map:
            return args

        log("DETECTED BRANCH KEYWORD:", value)
        args = dict(args)
        args.pop("ticker", None)
        args["keyName"] = special_branch_map[value]
        return args

    def _looks_like_branch_path(self, value: Any) -> bool:
        text = str(value or "").strip()
        return bool(text) and all(ch.isdigit() or ch == "-" for ch in text) and "-" in text

    def _resolve_branch_path(self, *values: Any) -> str | None:
        for value in values:
            if not value:
                continue
            if self._looks_like_branch_path(value):
                return str(value).strip()
            branch_path = extract_branch_path(str(value))
            if branch_path:
                return branch_path
        return None

    def _normalize_args(self, operation_id: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize GPT tool arguments per API, avoiding global side effects."""
        args = self._apply_special_branch_alias(dict(args or {}))

        ticker = args.get("ticker")
        if ticker and "branch_path" not in args and operation_id == "getPerformance":
            branch_path = get_branch_path_by_ticker(str(ticker))
            if branch_path:
                log("BACKEND FOUND BRANCH PATH:", branch_path)
                args["branch_path"] = branch_path

        if operation_id == "getSMDTBranch":
            branch_value = args.get("branch") or args.get("keyName") or args.get("name")
            branch_path = self._resolve_branch_path(
                args.get("path"),
                args.get("branch_path"),
                branch_value,
            )
            if branch_path:
                log("NORMALIZED getSMDTBranch TO PATH:", branch_path)
                args["path"] = branch_path
                for key in ("branch_path", "branch", "keyName", "name"):
                    args.pop(key, None)
            return args

        if operation_id == "getBranchSMDTTickers":
            if "date" in args and "from_date" not in args:
                args["from_date"] = args.pop("date")

            branch_value = args.get("branch") or args.get("keyName") or args.get("name")
            branch_path = self._resolve_branch_path(
                args.get("path"),
                args.get("branch_path"),
                branch_value,
            )
            if branch_value and "branch" not in args:
                args["branch"] = branch_value
            if branch_path:
                args["path"] = branch_path
            for key in ("branch_path", "keyName", "name"):
                args.pop(key, None)
            return args

        if operation_id == "getPerformance":
            if args.get("branch") and not args.get("branch_path"):
                branch_path = self._resolve_branch_path(args.get("branch"))
                if branch_path:
                    args["branch_path"] = branch_path
            return args

        if operation_id == "getSMDTLastN":
            branch_path = (
                args.get("path")
                or args.get("branch_path")
                or args.get("brand_path")
                or self._resolve_branch_path(args.get("branch"), args.get("keyName"), args.get("name"))
            )
            if branch_path:
                args["path"] = branch_path
            for key in ("branch_path", "brand_path", "branch", "name"):
                args.pop(key, None)
            return args

        branch_path_operations = {
            "getCashFlowBranch",
            "getSMDTBranchCross",
            "getSMDTBranchDrop",
            "getBranchStrongSMDTWithPrice",
        }
        if operation_id in branch_path_operations:
            branch_value = args.get("branch") or args.get("keyName") or args.get("name")
            branch_path = self._resolve_branch_path(
                args.get("path"),
                args.get("branch_path"),
                branch_value,
            )
            if branch_path:
                args["path"] = branch_path
            if args.get("branch") and not args.get("name") and operation_id == "getCashFlowBranch":
                args["name"] = args["branch"]
            for key in ("branch_path", "branch"):
                args.pop(key, None)
            return args

        return args
    # ============================================================
    # MAIN TOOL CALL
    # ============================================================

    def call(self, operation_id: str, args: Dict[str, Any], doc_name: str = None) -> Any:

        log("\n================ API CALL ================")
        log("OPERATION:", operation_id)
        log("ARGS FROM GPT:", args)
        args = self._normalize_args(operation_id, args)

        if invalid_api_ticker(operation_id, args):
            log("BLOCKED TICKER OUTSIDE PROJECT ALLOWLIST")
            return {
                "error": "Ticker is not supported by this system",
                "unsupported_ticker": True,
            }

        if operation_id == "getChanSong":
            try:
                return sanitize_api_result(operation_id, get_chan_song())
            except Exception as e:
                log("CHAN SONG API EXCEPTION:", str(e))
                return {"error": str(e)}

        if operation_id == "getStock4KeyEvaluation":
            try:
                return evaluate_stock_4key(
                    lambda child_operation, child_args: self.call(child_operation, child_args, doc_name=doc_name),
                    args,
                )
            except Stock4KeyError as e:
                log("4KEY EVALUATION ERROR:", str(e))
                return {"ok": False, "error": str(e)}
            except Exception as e:
                log("4KEY EVALUATION EXCEPTION:", str(e))
                return {"ok": False, "error": str(e)}

        month_only_docs = {
            r"C\u00e2u h\u1ecfi v\u1ec1 x\u00e1c nh\u1eadn ch\u00e2n s\u00f3ng, [th\u00e1ng, n\u0103m] l\u00e0 s\u00f3ng l\u1edbn hay s\u00f3ng h\u1ed3i.txt".encode("ascii").decode("unicode_escape"),
            r"C\u00e2u h\u1ecfi v\u1ec1 [th\u00e1ng, n\u0103m] l\u00e0 s\u00f3ng l\u1edbn hay s\u00f3ng h\u1ed3i.txt".encode("ascii").decode("unicode_escape"),
        }
        date = args.get("date")
        if doc_name in month_only_docs and isinstance(date, str):
            if len(date) == 10 and date.count("-") == 2:
                log("DOC RULE NORMALIZE DATE:", date, "->", date[:7])
                args["date"] = date[:7]

        op = self.registry.operations.get(operation_id)

        if not op:
            log("❌ UNKNOWN OPERATION:", operation_id)
            return {"error": f"Unknown operationId: {operation_id}"}

        url = self.registry.server_url + op["path"]
        method = op["method"]

        log("URL:", url)
        log("METHOD:", method)

        # ============================================================
        # EXTRACT BRANCH NAME
        # ============================================================

        branch_name = args.get("keyName") or args.get("name")

        # ============================================================
        # CALL API WITH KEYNAME FIRST
        # ============================================================

        try:

            response = self._execute_with_retry(
                url,
                method,
                args
            )

            log("STATUS:", response.status_code)

            # ============================================================
            # FALLBACK KEYNAME -> PATH
            # ============================================================

            data = self._safe_parse_json(response)

            def is_empty_data(d):
                if d is None:
                    return True
                if isinstance(d, list):
                    return len(d) == 0
                if isinstance(d, dict):
                    return d == {} or d.get("data") in [None, []]
                return False

            if (not response.ok or is_empty_data(data)) and branch_name:

                log("⚠️ KEYNAME FAILED -> TRY PATH")

                branch_path = extract_branch_path(str(branch_name))

                if branch_path:

                    log("🧠 BACKEND RESOLVED PATH:", branch_path)

                    args2 = args.copy()
                    args2["path"] = branch_path
                    args2.pop("keyName", None)
                    args2.pop("name", None)

                    if "date" in args:
                        args2["date"] = args["date"]

                    log("🔁 RETRY WITH PATH:", args2)

                    response = self._execute_with_retry(
                        url,
                        method,
                        args2
                    )

                    log("STATUS AFTER PATH:", response.status_code)

            if not response.ok:

                log("❌ HTTP ERROR:", response.status_code)

                return {
                    "error": "HTTP error",
                    "status_code": response.status_code,
                    "text": response.text[:500]
                }

            data = self._safe_parse_json(response)            

            if isinstance(data, list):
                log("RESULT SIZE:", len(data))

            return sanitize_api_result(operation_id, data)

        except Exception as e:

            log("💥 API EXCEPTION:", str(e))

            return {"error": str(e)}


    # ============================================================
    # SAFE JSON PARSER
    # ============================================================

    def _safe_parse_json(self, response):

        try:
            return response.json()

        except Exception:

            text = response.text.strip()

            log("⚠️ NON JSON RESPONSE")

            try:

                if text.startswith("{") or text.startswith("["):
                    return json.loads(text)

            except Exception:
                pass

            return {
                "error": "Non-JSON response",
                "status_code": response.status_code,
                "text": text[:500]
            }

    # ============================================================
    # RAW HTTP REQUEST
    # ============================================================

    def _do_request(self, url: str, method: str, payload: Dict[str, Any]):

        log("PAYLOAD:", payload)

        if method == "POST":

            return requests.post(
                url,
                params=payload,
                timeout=120
            )

        return requests.get(
            url,
            params=payload,
            timeout=120
        )


    # ============================================================
    # RETRY LOGIC
    # ============================================================

    def _execute_with_retry(
        self,
        url: str,
        method: str,
        args: Dict[str, Any]
    ):

        log("➡️ REQUEST START")

        r = self._do_request(url, method, args)

        if r.status_code >= 500:
            log("🔁 RETRY REQUEST")
            r = self._do_request(url, method, args)

        return r

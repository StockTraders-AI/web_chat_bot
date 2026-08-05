import requests
import json
import sys
import re
import unicodedata
from datetime import date as date_cls, datetime, timedelta
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

    def _normalize_text(self, value: str | None) -> str:
        text = unicodedata.normalize("NFD", value or "")
        text = "".join(char for char in text if unicodedata.category(char) != "Mn")
        text = text.replace("\u0111", "d").replace("\u0110", "D")
        return re.sub(r"\s+", " ", text.lower()).strip()

    def _has_explicit_calendar_date(self, user_text: str | None) -> bool:
        normalized = self._normalize_text(user_text)
        if not normalized:
            return False
        if re.search(r"\b20\d{2}[-/]\d{1,2}([-/]\d{1,2})?\b", normalized):
            return True
        if re.search(r"\b\d{1,2}[/-]\d{1,2}([/-]\d{2,4})?\b", normalized):
            return True
        if re.search(r"\bngay\s+\d{1,2}\b", normalized):
            return True
        if re.search(r"\bthang\s+\d{1,2}\b", normalized):
            return True
        if re.search(r"\bnam\s+20\d{2}\b", normalized):
            return True
        if re.search(r"\b20\d{2}\b", normalized):
            return True
        if "hom qua" in normalized or "ngay hom qua" in normalized:
            return True
        if "dau nam" in normalized or "cuoi nam" in normalized:
            return True
        return False

    def _coerce_implicit_current_date(self, operation_id: str, args: Dict[str, Any], user_text: str | None) -> Dict[str, Any]:
        if user_text is None:
            return args
        date_value = str(args.get("date") or "").strip()
        if not date_value:
            return args
        if not re.match(r"^20\d{2}(-\d{2}){0,2}$", date_value):
            return args
        if self._has_explicit_calendar_date(user_text):
            return args
        today = date_cls.today().isoformat()
        if date_value == today:
            return args
        coerced = dict(args)
        coerced["date"] = today
        log("IMPLICIT CURRENT QUERY -> COERCE DATE:", date_value, "->", today)
        return coerced

    def _is_no_data_payload(self, value: Any) -> bool:
        if not isinstance(value, dict):
            return False
        text = " ".join(
            str(value.get(key) or "")
            for key in ("detail", "message", "text", "error")
        ).lower()
        return bool(text) and any(
            marker in text
            for marker in (
                "no data",
                "no matching",
                "khong co du lieu",
                "kh\u00f4ng c\u00f3 d\u1eef li\u1ec7u",
                "chua co du lieu",
                "ch\u01b0a c\u00f3 d\u1eef li\u1ec7u",
            )
        )

    def _is_effectively_empty(self, value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, list):
            return len(value) == 0
        if isinstance(value, dict):
            if value.get("unsupported_ticker"):
                return False
            if self._is_no_data_payload(value):
                return True
            if value.get("error"):
                return False
            domain_keys = (
                "data", "items", "records", "results", "result", "smdts", "cashFlows",
                "cashFlowTickers", "totalTradeDatas", "tradeDatas", "stockWaveDatas", "waveDatas",
                "ket_qua", "lich_su",
            )
            present = [value[key] for key in domain_keys if key in value]
            if present:
                return all(self._is_effectively_empty(item) for item in present)
            if any(key in value for key in ("date", "smdt", "close", "price", "content", "ticker")):
                return False
            return all(self._is_effectively_empty(item) for item in value.values()) if value else True
        return False

    def _should_retry_previous_dates(self, operation_id: str, args: Dict[str, Any], data: Any, user_text: str | None) -> bool:
        date_value = str(args.get("date") or "").strip()
        if not re.match(r"^20\d{2}-\d{2}-\d{2}$", date_value):
            return False
        if not self._is_effectively_empty(data):
            return False
        # Only auto-roll current-day style queries. Historical exact-date questions must stay exact.
        if date_value != date_cls.today().isoformat():
            return False
        if self._has_explicit_calendar_date(user_text):
            return False
        return True

    def _should_retry_cashflow_without_date(self, operation_id: str, args: Dict[str, Any], data: Any, user_text: str | None) -> bool:
        if operation_id not in {"getCashFlowTicker", "getCashFlowBranch"}:
            return False
        date_value = str(args.get("date") or "").strip()
        if date_value != date_cls.today().isoformat():
            return False
        if not self._is_effectively_empty(data):
            return False
        if self._has_explicit_calendar_date(user_text):
            return False
        return True

    def _execute_cashflow_without_date_fallback(self, url: str, method: str, args: Dict[str, Any], original_data: Any) -> tuple[Any, Any]:
        retry_args = dict(args)
        requested_date = str(retry_args.pop("date", "") or "")
        log("CASHFLOW TODAY EMPTY -> RETRY WITHOUT DATE")
        response = self._execute_with_retry(url, method, retry_args)
        data = self._safe_parse_json(response)
        if response.ok and not self._is_effectively_empty(data):
            if isinstance(data, dict):
                data.setdefault("_requested_date", requested_date)
                data.setdefault("_resolved_date", "latest")
            return response, data
        return None, original_data

    def _execute_previous_date_fallback(self, url: str, method: str, args: Dict[str, Any], original_data: Any) -> tuple[Any, Any]:
        original_date = str(args.get("date"))[:10]
        try:
            current = datetime.strptime(original_date, "%Y-%m-%d").date()
        except ValueError:
            return None, original_data

        # Calendar-day bound prevents accidental long loops against the source API.
        for offset in range(1, 15):
            fallback_date = (current - timedelta(days=offset)).isoformat()
            retry_args = dict(args)
            retry_args["date"] = fallback_date
            log("DATE EMPTY -> RETRY PREVIOUS DATE:", fallback_date)
            response = self._execute_with_retry(url, method, retry_args)
            data = self._safe_parse_json(response)
            if response.ok and not self._is_effectively_empty(data):
                if isinstance(data, dict):
                    data.setdefault("_requested_date", original_date)
                    data.setdefault("_resolved_date", fallback_date)
                return response, data
        return None, original_data

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

    def call(self, operation_id: str, args: Dict[str, Any], doc_name: str = None, user_text: str | None = None) -> Any:

        log("\n================ API CALL ================")
        log("OPERATION:", operation_id)
        log("ARGS FROM GPT:", args)
        args = self._normalize_args(operation_id, args)
        args = self._coerce_implicit_current_date(operation_id, args, user_text)

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
        if operation_id != "getAnalyzeWave" and doc_name in month_only_docs and isinstance(date, str):
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
                if self._should_retry_previous_dates(operation_id, args, data, user_text):
                    fallback_response, fallback_data = self._execute_previous_date_fallback(url, method, args, data)
                    if fallback_response is not None:
                        response = fallback_response
                        data = fallback_data

                if not response.ok:
                    log("HTTP ERROR:", response.status_code)

                    return {
                        "error": "HTTP error",
                        "status_code": response.status_code,
                        "text": response.text[:500]
                    }

            data = self._safe_parse_json(response) if not isinstance(data, (dict, list)) else data

            if self._should_retry_cashflow_without_date(operation_id, args, data, user_text):
                fallback_response, fallback_data = self._execute_cashflow_without_date_fallback(url, method, args, data)
                if fallback_response is not None:
                    response = fallback_response
                    data = fallback_data
            elif self._should_retry_previous_dates(operation_id, args, data, user_text):
                fallback_response, fallback_data = self._execute_previous_date_fallback(url, method, args, data)
                if fallback_response is not None:
                    response = fallback_response
                    data = fallback_data

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

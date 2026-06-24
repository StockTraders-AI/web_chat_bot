import requests
import unicodedata
import json
from typing import Any, Dict
from core.tool_engine import ToolRegistry
from services.branch_map import extract_branch_path
from services.branch_tickers import BRANCH_DATA
from services.chan_song_client import get_chan_song

DEBUG_API = True

def log(*args):
    if DEBUG_API:
        print(*args)


# ============================================================
# NORMALIZE TEXT
# ============================================================

def normalize_text(text: str):

    if not text:
        return ""

    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")

    return text.lower().strip()

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
    # ============================================================
    # MAIN TOOL CALL
    # ============================================================

    def call(self, operation_id: str, args: Dict[str, Any], doc_name: str = None) -> Any:

        log("\n================ API CALL ================")
        log("OPERATION:", operation_id)
        log("ARGS FROM GPT:", args)
        args = dict(args or {})

        if operation_id == "getChanSong":
            try:
                return get_chan_song()
            except Exception as e:
                log("CHAN SONG API EXCEPTION:", str(e))
                return {"error": str(e)}

        MONTH_ONLY_DOCS = {
            "Câu hỏi về [tháng, năm] là sóng lớn hay sóng hồi.txt"   # tên file guide chân sóng của bạn
        }

        date = args.get("date")

        if doc_name in MONTH_ONLY_DOCS and isinstance(date, str):

            # nếu GPT gửi yyyy-mm-dd → convert yyyy-mm
            if len(date) == 10 and date.count("-") == 2:
                log("⚙️ DOC RULE NORMALIZE DATE:", date, "->", date[:7])
                args["date"] = date[:7]

        SPECIAL_BRANCH_MAP = {
            "BDS": "Bất động sản dân cư",
            "BĐS": "Bất động sản dân cư",
        }

        ticker = args.get("ticker")

        if ticker:
            t = ticker.upper().strip()

            if t in SPECIAL_BRANCH_MAP:
                log("🧠 DETECTED BRANCH KEYWORD:", t)

                args.pop("ticker", None)
                args["keyName"] = SPECIAL_BRANCH_MAP[t]

        ticker = args.get("ticker")
        if ticker and "branch_path" not in args:
            branch_path = get_branch_path_by_ticker(ticker)
            if branch_path:
                log("🧠 BACKEND FOUND BRANCH PATH:", branch_path)
                args["branch_path"] = branch_path

        branch = args.get("branch")
        if branch and "branch_path" not in args:
            branch_path = extract_branch_path(str(branch))
            if branch_path:
                log("🧠 BACKEND RESOLVED branch -> branch_path:", branch_path)
                args["branch_path"] = branch_path
                args.pop("branch", None)
                
        if operation_id == "getSMDTBranch":
            branch_value = args.get("branch") or args.get("keyName") or args.get("name")
            branch_path = args.get("path") or args.get("branch_path")
            if not branch_path and branch_value:
                branch_path = extract_branch_path(str(branch_value))
            if branch_path:
                log("🧠 NORMALIZED getSMDTBranch TO PATH:", branch_path)
                args["path"] = branch_path
                args.pop("branch_path", None)
                args.pop("branch", None)
                args.pop("keyName", None)
                args.pop("name", None)

        op = self.registry.operations.get(operation_id)

        if not op:
            log("❌ UNKNOWN OPERATION:", operation_id)
            return {"error": f"Unknown operationId: {operation_id}"}

        url = self.registry.server_url + op["path"]
        method = op["method"]

        log("URL:", url)
        log("METHOD:", method)

        args.pop("branch_path", None)

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

            return data

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

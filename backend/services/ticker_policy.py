"""Project-wide stock ticker allowlist and sanitizers."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, Optional


ALLOWED_TICKERS = frozenset(
    """
FIT TLH PVS PGB PVT IDJ SHS IDI TTF VCB IDC SZC VTP VCG VCI L14 VCK HT1 TCH LPB
SHB PNJ AAA BSR TCM APS HHS TCB HHV TLG SAB C4G JVC MWG SIP POW SAM QNS FRT BSI
DTD GEG GVR NVL TV2 BCC HAG HSG HAH BCM GEX VJC QTP VEA BVH VIX HUT ASM BVS VDS
ACB VRE CMG BMI PPC BVB BMP SSI FTS EVF KLB TCX CMX GMD YEG BFC FMC SSB NAB HTN
LAS LHG VCS ABB CNG SBT CEO TDH PHR KDH VSC TDC CTR CTS KBC VGI NTC NKG VPB ORS
LSS MBS VGC TPB VPI QCG MSH VPL OCB NT2 FOX DXG NBC HDC SCR HDB ITC MBB DXS HDG
MSN HPG MST VPX MSR CSV DGC GAS GIL PTB DPG SMC PC1 MSB STB HVN CTG KSB LCG DDV
DGW CTD DHC CTI VIP NVB BID TNG NDN VND DCM PET LDG VIC FCN MIG VNM IJC DPR VIB
APG AGR D2D EIB DPM OIL AGG REE DRC ANV PLC NLG DBC VHM HCM DIG PDR PVC VHC PVD
MHC CII KHG MPC FPT PLX VGS VOS SGB NTL HQC
""".split()
)

NON_TICKER_TERMS = frozenset(
    {
        "AI", "API", "HTTP", "HTTPS", "JSON", "GET", "POST", "GPT",
        "SMDT", "RSI", "MACD", "NAV", "ETF", "IPO", "ROA", "ROE",
        "EPS", "PBR", "PER", "PE", "PB", "EBITDA", "USD", "CAGR",
        "YOY", "MOM", "TTM", "ALL", "NULL", "TRUE", "FALSE",
    }
)

TICKER_TOKEN_RE = re.compile(r"\b[A-Z]{2,5}\d?\b")
TICKER_FIELDS = frozenset(
    {"ticker", "symbol", "stockcode", "stock_code", "stockticker", "stock_ticker"}
)
TICKER_KEYVALUE_OPERATIONS = frozenset(
    {
        "getSMDTTicker", "getSMDTTickerCross", "getCashFlowTicker",
        "getSMDTTickerDrop", "getStockSignal",
    }
)
_DROP = object()


def is_allowed_ticker(value: Any) -> bool:
    return isinstance(value, str) and value.strip().upper() in ALLOWED_TICKERS


def normalize_ticker(value: Any) -> str:
    return str(value or "").strip().upper()


def allowed_tickers_text() -> str:
    return ", ".join(sorted(ALLOWED_TICKERS))


def find_disallowed_tickers(text: str) -> list[str]:
    found = []
    for match in TICKER_TOKEN_RE.finditer(text or ""):
        token = match.group(0)
        if token in ALLOWED_TICKERS or token in NON_TICKER_TERMS:
            continue
        if token not in found:
            found.append(token)
    return found


def invalid_api_ticker(operation_id: str, args: Dict[str, Any]) -> Optional[str]:
    """Return an invalid ticker argument without exposing it in error messages."""
    for key in TICKER_FIELDS:
        if key in args and args[key] not in (None, ""):
            value = normalize_ticker(args[key])
            if value not in ALLOWED_TICKERS:
                return value

    if operation_id in TICKER_KEYVALUE_OPERATIONS:
        value = args.get("keyValue")
        if value not in (None, "") and normalize_ticker(value) not in ALLOWED_TICKERS:
            return normalize_ticker(value)

    tickers = args.get("tickers")
    if isinstance(tickers, str):
        values: Iterable[Any] = re.split(r"[\s,;]+", tickers)
    elif isinstance(tickers, (list, tuple, set)):
        values = tickers
    else:
        values = ()
    for value in values:
        if value and normalize_ticker(value) not in ALLOWED_TICKERS:
            return normalize_ticker(value)
    return None


def _record_ticker(data: Dict[str, Any], operation_id: str) -> Optional[str]:
    lowered = {str(key).lower(): value for key, value in data.items()}
    for key in TICKER_FIELDS:
        value = lowered.get(key)
        if isinstance(value, str) and TICKER_TOKEN_RE.fullmatch(value.strip().upper()):
            return normalize_ticker(value)

    if operation_id in TICKER_KEYVALUE_OPERATIONS:
        value = data.get("keyValue")
        if isinstance(value, str) and TICKER_TOKEN_RE.fullmatch(value.strip().upper()):
            return normalize_ticker(value)
    return None


def _sanitize_api_value(operation_id: str, value: Any, key: str = "") -> Any:
    if isinstance(value, list):
        if key.lower() == "tickers" and all(isinstance(item, str) for item in value):
            return [normalize_ticker(item) for item in value if is_allowed_ticker(item)]
        cleaned = []
        for item in value:
            sanitized = _sanitize_api_value(operation_id, item, key)
            if sanitized is not _DROP:
                cleaned.append(sanitized)
        return cleaned

    if isinstance(value, dict):
        ticker = _record_ticker(value, operation_id)
        if ticker and ticker not in ALLOWED_TICKERS:
            return _DROP
        cleaned = {}
        for child_key, child_value in value.items():
            sanitized = _sanitize_api_value(operation_id, child_value, str(child_key))
            if sanitized is not _DROP:
                cleaned[child_key] = sanitized
        return cleaned

    if key.lower() == "tickers" and isinstance(value, str):
        allowed = [
            normalize_ticker(item)
            for item in re.split(r"[\s,;]+", value)
            if is_allowed_ticker(item)
        ]
        return ",".join(allowed)
    return value


def sanitize_api_result(operation_id: str, data: Any) -> Any:
    sanitized = _sanitize_api_value(operation_id, data)
    if sanitized is _DROP:
        return []
    return sanitized


def sanitize_response_text(text: str) -> str:
    """Remove unsupported uppercase ticker-like tokens from the final answer."""
    def replace(match: re.Match) -> str:
        token = match.group(0)
        if token in ALLOWED_TICKERS or token in NON_TICKER_TERMS:
            return token
        return ""

    cleaned = TICKER_TOKEN_RE.sub(replace, text or "")
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
    cleaned = re.sub(r"([,;:])(?:\s*[,;:])+", r"\1", cleaned)
    return cleaned.strip(" ,;:-")
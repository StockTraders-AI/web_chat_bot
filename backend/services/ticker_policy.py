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

MARKET_INDEX_TICKERS = frozenset({"VNINDEX"})
INDEX_TICKER_OPERATIONS = frozenset({"getTotalTrade", "getTotalTradeReal"})

NON_TICKER_TERMS = frozenset(
    {
        "AI", "API", "HTTP", "HTTPS", "JSON", "GET", "POST", "GPT",
        "SMDT", "RSI", "MACD", "NAV", "ETF", "IPO", "ROA", "ROE",
        "EPS", "PBR", "PER", "PE", "PB", "EBITDA", "USD", "CAGR",
        "YOY", "MOM", "TTM", "ALL", "NULL", "TRUE", "FALSE",
        "MUA", "BAN", "CAN", "NHAC", "THEO", "DOI", "TRANH", "VNINDEX",
    }
)

TICKER_TOKEN_RE = re.compile(r"\b[A-Z][A-Z0-9]{1,4}\b")
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


def _is_supported_ticker(operation_id: str, value: Any) -> bool:
    ticker = normalize_ticker(value)
    if ticker in ALLOWED_TICKERS:
        return True
    return operation_id in INDEX_TICKER_OPERATIONS and ticker in MARKET_INDEX_TICKERS


def invalid_api_ticker(operation_id: str, args: Dict[str, Any]) -> Optional[str]:
    """Return an invalid ticker argument without exposing it in error messages."""
    for key in TICKER_FIELDS:
        if key in args and args[key] not in (None, ""):
            value = normalize_ticker(args[key])
            if not _is_supported_ticker(operation_id, value):
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
        if value and not _is_supported_ticker(operation_id, value):
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
        if ticker and not _is_supported_ticker(operation_id, ticker):
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



FOUR_KEY_TEXT_REPLACEMENTS = (
    (re.compile("\\bD[u\\u00f9\\u00fa]ng\\s+s[o\\u00f3]ng\\s*-\\s*D[u\\u00f9\\u00fa]ng\\s+ng[a\\u00e0\\u00e1]nh\\b", re.IGNORECASE), "\u0110\u00fang s\u00f3ng - \u0110\u00fang ng\u00e0nh"),
    (re.compile("\\bDung\\s+song\\s*-\\s*Dung\\s+nganh\\b", re.IGNORECASE), "\u0110\u00fang s\u00f3ng - \u0110\u00fang ng\u00e0nh"),
    (re.compile("\\bD[u\\u00f9\\u00fa]ng\\s+s[o\\u00f3]ng\\s*-\\s*Sai\\s+ng[a\\u00e0\\u00e1]nh\\b", re.IGNORECASE), "\u0110\u00fang s\u00f3ng - Sai ng\u00e0nh"),
    (re.compile("\\bDung\\s+song\\s*-\\s*Sai\\s+nganh\\b", re.IGNORECASE), "\u0110\u00fang s\u00f3ng - Sai ng\u00e0nh"),
    (re.compile("\\bSai\\s+s[o\\u00f3]ng\\s*-\\s*D[u\\u00f9\\u00fa]ng\\s+ng[a\\u00e0\\u00e1]nh\\b", re.IGNORECASE), "\u0110\u00fang ng\u00e0nh - Sai s\u00f3ng"),
    (re.compile("\\bSai\\s+song\\s*-\\s*Dung\\s+nganh\\b", re.IGNORECASE), "\u0110\u00fang ng\u00e0nh - Sai s\u00f3ng"),
    (re.compile("\\bD[u\\u00f9\\u00fa]ng\\s+ng[a\\u00e0\\u00e1]nh\\s*-\\s*Sai\\s+s[o\\u00f3]ng\\b", re.IGNORECASE), "\u0110\u00fang ng\u00e0nh - Sai s\u00f3ng"),
    (re.compile("\\bDung\\s+nganh\\s*-\\s*Sai\\s+song\\b", re.IGNORECASE), "\u0110\u00fang ng\u00e0nh - Sai s\u00f3ng"),
    (re.compile("\\bSai\\s+s[o\\u00f3]ng\\s*-\\s*Sai\\s+ng[a\\u00e0\\u00e1]nh\\b", re.IGNORECASE), "Sai s\u00f3ng - Sai ng\u00e0nh"),
    (re.compile("\\bSai\\s+song\\s*-\\s*Sai\\s+nganh\\b", re.IGNORECASE), "Sai s\u00f3ng - Sai ng\u00e0nh"),
    (re.compile("\\bMUA\\s*-\\s*tin\\s+hieu\\s+thuan\\s+ca\\s+ma\\s+va\\s+nganh\\b", re.IGNORECASE), "MUA - t\u00edn hi\u1ec7u thu\u1eadn c\u1ea3 2 chi\u1ec1u"),
    (re.compile("\\bMUA\\s*-\\s*tin\\s+hieu\\s+thuan\\s+ca\\s+2\\s+chieu\\b", re.IGNORECASE), "MUA - t\u00edn hi\u1ec7u thu\u1eadn c\u1ea3 2 chi\u1ec1u"),
    (re.compile("\\bCAN\\s+NHAC\\s*-\\s*ma\\s+manh\\s+rieng(?:\\s+le)?,?\\s+nguoc\\s+dong\\s+nganh\\b", re.IGNORECASE), "C\u00c2N NH\u1eaeC - m\u00e3 m\u1ea1nh ri\u00eang l\u1ebb, ng\u01b0\u1ee3c d\u00f2ng ng\u00e0nh"),
    (re.compile("\\bTHEO\\s+DOI\\s*-\\s*nganh\\s+thuan\\s+nhung\\s+ma\\s+chua\\s+xac\\s+nhan\\b", re.IGNORECASE), "THEO D\u00d5I - ng\u00e0nh thu\u1eadn nh\u01b0ng m\u00e3 ch\u01b0a x\u00e1c nh\u1eadn"),
    (re.compile("\\bTRANH\\s*-\\s*ca\\s+ma\\s+va\\s+nganh\\s+deu\\s+bat\\s+loi\\b", re.IGNORECASE), "TR\u00c1NH - c\u1ea3 2 chi\u1ec1u b\u1ea5t l\u1ee3i"),
    (re.compile("\\bTRANH\\s*-\\s*ca\\s+2\\s+chieu\\s+bat\\s+loi\\b", re.IGNORECASE), "TR\u00c1NH - c\u1ea3 2 chi\u1ec1u b\u1ea5t l\u1ee3i"),
)

NOTE_TEXT_REPLACEMENTS = (
    (re.compile("Thieu du lieu dong tien(?: cho ngay nay)?(?: ->)? tinh nhu trung lap \\(50 diem\\)", re.IGNORECASE), "Thi\u1ebfu d\u1eef li\u1ec7u d\u00f2ng ti\u1ec1n cho ng\u00e0y n\u00e0y -> t\u00ednh nh\u01b0 trung l\u1eadp (50 \u0111i\u1ec3m)"),
    (re.compile("Thieu du lieu dong tien, tinh trung lap 50 diem", re.IGNORECASE), "Thi\u1ebfu d\u1eef li\u1ec7u d\u00f2ng ti\u1ec1n cho ng\u00e0y n\u00e0y -> t\u00ednh nh\u01b0 trung l\u1eadp (50 \u0111i\u1ec3m)"),
    (re.compile("Khong co PriceDataSource -> bo factor gia, don trong so sang cac factor con lai", re.IGNORECASE), "Kh\u00f4ng c\u00f3 PriceDataSource -> b\u1ecf factor gi\u00e1, d\u1ed3n tr\u1ecdng s\u1ed1 sang c\u00e1c factor c\u00f2n l\u1ea1i"),
    (re.compile("Co PriceDataSource nhung thieu du lieu gia \\(([^)]*)\\) -> bo factor gia", re.IGNORECASE), "C\u00f3 PriceDataSource nh\u01b0ng thi\u1ebfu d\u1eef li\u1ec7u gi\u00e1 (\\1) -> b\u1ecf factor gi\u00e1"),
    (re.compile("Chua co du lieu peer de tinh xep hang nganh -> bo factor nay", re.IGNORECASE), "Ch\u01b0a c\u00f3 d\u1eef li\u1ec7u peer \u0111\u1ec3 t\u00ednh x\u1ebfp h\u1ea1ng ng\u00e0nh -> b\u1ecf factor n\u00e0y"),
    (re.compile("PHAT HIEN PHAN KY: SMDT \\+([0-9.,-]+) nhung gia ([+-]?[0-9.,]+%) trong ([0-9]+) phien qua -> cong bonus \\+([0-9.,]+) diem", re.IGNORECASE), "PH\u00c1T HI\u1ec6N PH\u00c2N K\u1ef2: SMDT +\\1 nhưng gi\u00e1 \\2 trong \\3 phi\u00ean qua -> c\u1ed9ng bonus +\\4 \u0111i\u1ec3m"),
    (re.compile("Phat hien phan ky: SMDT tang ([0-9.,]+)%? nhung gia ([0-9]+) phien la ([+-]?[0-9.,]+)%?\\.?", re.IGNORECASE), "Ph\u00e1t hi\u1ec7n ph\u00e2n k\u1ef3: SMDT t\u0103ng \\1% nh\u01b0ng gi\u00e1 \\2 phi\u00ean l\u00e0 \\3%."),
    (re.compile("Tin hieu dong tien '([^']+)' chua co trong bang diem -> tinh nhu trung lap \\(50 diem\\)", re.IGNORECASE), "T\u00edn hi\u1ec7u d\u00f2ng ti\u1ec1n '\\1' ch\u01b0a c\u00f3 trong b\u1ea3ng \u0111i\u1ec3m -> t\u00ednh nh\u01b0 trung l\u1eadp (50 \u0111i\u1ec3m)"),
    (re.compile("Tin hieu dong tien '([^']+)' chua co trong bang diem, tinh trung lap 50 diem", re.IGNORECASE), "T\u00edn hi\u1ec7u d\u00f2ng ti\u1ec1n '\\1' ch\u01b0a c\u00f3 trong b\u1ea3ng \u0111i\u1ec3m, t\u00ednh trung l\u1eadp 50 \u0111i\u1ec3m"),
)
def normalize_four_key_text(text: str) -> str:
    fixed = text or ""
    fixed = re.sub(r"\b4-key\b", "4 Key", fixed, flags=re.IGNORECASE)
    for pattern, replacement in FOUR_KEY_TEXT_REPLACEMENTS:
        fixed = pattern.sub(replacement, fixed)
    for pattern, replacement in NOTE_TEXT_REPLACEMENTS:
        fixed = pattern.sub(replacement, fixed)
    return fixed
def sanitize_response_text(text: str) -> str:
    """Remove unsupported ticker mentions and renumber ordered ticker lists."""
    cleaned_lines = []
    ordered_item = re.compile(r"^(\s*)\d+(?:\.0%)?\.\s*(.+)$")

    for line in (text or "").splitlines():
        line = normalize_four_key_text(line)
        disallowed = find_disallowed_tickers(line)
        if disallowed and ordered_item.match(line):
            continue

        def replace(match: re.Match) -> str:
            token = match.group(0)
            if token in ALLOWED_TICKERS or token in NON_TICKER_TERMS:
                return token
            return ""

        cleaned_lines.append(TICKER_TOKEN_RE.sub(replace, line))

    number = 0
    renumbered = []
    for line in cleaned_lines:
        match = ordered_item.match(line)
        if match:
            number += 1
            line = f"{match.group(1)}{number}. {match.group(2)}"
        renumbered.append(line)

    cleaned = "\n".join(renumbered)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
    cleaned = re.sub(r"([,;:])(?:\s*[,;:])+", r"\1", cleaned)
    cleaned = normalize_four_key_text(cleaned)
    return cleaned.strip(" ,;:-")
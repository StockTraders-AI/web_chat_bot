import asyncio
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from settings import CLASSIFIER_MODEL
from services.ticker_policy import ALLOWED_TICKERS


@dataclass
class GuideResult:
    action: str
    message: str = ""
    canonical_question: str = ""


@dataclass(frozen=True)
class RuleCase:
    question: str
    groups: frozenset[str]
    document: str
    date_optional: bool = False


RULE_GROUPS: Dict[str, Set[str]] = {
    "Câu hỏi về giá của mã.txt": {"stock"},
    "Câu hỏi về lịch sử mua bán của một mã.txt": {"stock"},
    "Câu hỏi về mã, cổ phiếu, đạt chuẩn mã mạnh.txt": {"stock", "smdt"},
    "Câu hỏi về ngành, dẫn sóng, đạt chuẩn ngành mạnh.txt": {"branch", "smdt"},
    "Câu hỏi về số lượng mua bán, chờ mua, chờ bán, độ tin cậy.txt": {"market", "wait_signal"},
    "Câu hỏi về sức mạnh dòng tiền, smdt ngành, mã.txt": {"stock", "branch", "smdt"},
    "Câu hỏi về tín hiệu dòng tiền mã , dòng tiền mã.txt": {"stock", "branch", "cashflow"},
    "Câu hỏi về tín hiệu giao dịch (mua,bán), giá vốn trung bình, tỷ trọng nắm giữ, tỷ trọng giao dịch của mã.txt": {"stock"},
    "Câu hỏi về xác nhận chân sóng, [tháng, năm] là sóng lớn hay sóng hồi.txt": {"wave"},
    "Hiệu suất cổ phiếu khi dẫn sóng.txt": {"stock", "branch"},
}

STOCK_WORDS = {
    "anh", "ban", "co", "duoc", "em", "gio", "hoi", "khong", "ko",
    "la", "ma", "mua", "nen", "phieu", "toi", "ve", "vao", "chua",
    "nay", "the", "nao", "phan", "tich", "giup", "minh", "nganh",
    "dong", "ngan", "hang", "chung", "khoan", "thep", "bat", "san",
    "on", "muc", "gom", "xuc", "hom", "hien", "gia", "tin", "hieu",
    "ngay", "thang", "nam", "bao", "nhieu", "manh", "dat", "chuan",
}
NON_TICKERS = {"SMDT", "RSI", "MACD", "NAV", "API", "GPT", "AI", "VNINDEX"}
GENERIC_GUIDE_PREFIXES = (
    "hướng dẫn", "huong dan", "khi người dùng", "khi nguoi dung",
    "đối với", "doi voi", "mỗi lần", "moi lan", "để tránh", "de tranh",
    "điều kiện", "dieu kien",
)
DIRECT_RULE_STOPWORDS = {
    "anh", "chi", "cho", "toi", "minh", "vui", "long", "hay", "dang",
    "lap", "bang", "thong", "ke", "danh", "sach", "cac", "co",
    "ve", "cua", "vao", "trong", "hien", "nay", "hom", "ngay",
}
STOCK_PLACEHOLDERS = ("[ma]", "[ma co phieu]", "[ticker]", "[x]")
BRANCH_PLACEHOLDERS = ("[nganh]",)
DATE_PLACEHOLDERS = ("[date]", "[ngay]", "[month]", "mm-yyyy", "yyyy")


def _safe_console(value: Any) -> str:
    return str(value).encode("ascii", errors="backslashreplace").decode("ascii")


def debug_print(*args):
    print(*(_safe_console(arg) for arg in args))


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text or "")
    normalized = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
    normalized = normalized.replace("đ", "d").replace("Đ", "D")
    normalized = normalized.lower()
    normalized = re.sub(r"[^a-z0-9%/\-\s\[\]]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def extract_ticker(text: str) -> Optional[str]:
    raw = text or ""
    for item in re.findall(r"\b[A-Z][A-Z0-9]{1,4}\b", raw):
        if item not in NON_TICKERS and item in ALLOWED_TICKERS:
            return item

    normalized = normalize_text(raw)
    action_match = re.search(
        r"\b(?:mua|ban|muc|gom|xuc|ma|co phieu|phan tich|smdt|gia)\s+([a-z]{2,5}\d?)\b",
        normalized,
    )
    if action_match and action_match.group(1) not in STOCK_WORDS:
        ticker = action_match.group(1).upper()
        if ticker in ALLOWED_TICKERS:
            return ticker
    return None


def extract_branch(text: str) -> Optional[str]:
    raw = text or ""
    match = re.search(r"\b(?:ngành|dòng)\s+([\wÀ-ỹ\s]+)", raw, flags=re.IGNORECASE)
    if not match:
        match = re.search(r"\b(?:nganh|dong)\s+([a-z\s]+)", raw, flags=re.IGNORECASE)
    if not match:
        return None
    value = re.split(
        r"\b(?:ngày|ngay|hôm nay|hom nay|hiện nay|hien nay|thế nào|the nao|có nên|co nen|không|ko|bao nhiêu|bao nhieu|từ khi nào|tu khi nao)\b",
        match.group(1),
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    value = re.sub(r"\s+", " ", value).strip(" ?.!,")
    if normalize_text(value) in {"nao", "gi", "chu luc"}:
        return None
    return value or None


def extract_month(text: str) -> Optional[int]:
    normalized = normalize_text(text)
    match = re.search(r"\bthang\s*(1[0-2]|0?[1-9])\b", normalized)
    if match:
        return int(match.group(1))
    match = re.search(r"\b(1[0-2]|0?[1-9])[/-](20\d{2})\b", normalized)
    return int(match.group(1)) if match else None


def extract_day(text: str) -> Optional[int]:
    normalized = normalize_text(text)
    match = re.search(r"\bngay\s*(3[01]|[12]\d|0?[1-9])\b", normalized)
    if match:
        return int(match.group(1))
    match = re.search(
        r"\b(3[01]|[12]\d|0?[1-9])[/-](1[0-2]|0?[1-9])(?:[/-](20\d{2}))?\b",
        normalized,
    )
    return int(match.group(1)) if match else None


def extract_year(text: str) -> int:
    match = re.search(r"\b(20\d{2})\b", text or "")
    return int(match.group(1)) if match else datetime.now().year


def extract_date_value(text: str) -> Optional[str]:
    normalized = normalize_text(text)
    iso = re.search(r"\b(20\d{2})-(1[0-2]|0[1-9])-(3[01]|[12]\d|0[1-9])\b", normalized)
    if iso:
        return iso.group(0)
    full = re.search(r"\b(3[01]|[12]\d|0?[1-9])[/-](1[0-2]|0?[1-9])(?:[/-](20\d{2}))?\b", normalized)
    if full:
        day, month = int(full.group(1)), int(full.group(2))
        year = int(full.group(3) or datetime.now().year)
        return f"{day:02d}/{month:02d}/{year}"
    month = extract_month(text)
    if month:
        return f"tháng {month}/{extract_year(text)}"
    year_match = re.search(r"\b(20\d{2})\b", normalized)
    if year_match:
        return year_match.group(1)
    if any(value in normalized for value in ("hom nay", "hien tai", "bay gio", "gan nhat")):
        return "hôm nay"
    return None


def is_affirmative(text: str) -> bool:
    normalized = normalize_text(text)
    return normalized in {"dung", "ok", "co", "uh", "u", "yes", "chinh xac"} or normalized.startswith("dung ")


def option_number(text: str) -> Optional[int]:
    normalized = normalize_text(text)
    match = re.fullmatch(r"(?:chon|cau|so)?\s*([1-9])", normalized)
    return int(match.group(1)) if match else None


def classify_groups(text: str) -> Set[str]:
    normalized = normalize_text(text)
    groups: Set[str] = set()
    if extract_ticker(text) or "co phieu" in normalized or re.search(r"\bma\b", normalized):
        groups.add("stock")
    if "nganh" in normalized or re.search(r"\bdong\s+(?:chung khoan|ngan hang|thep|bat dong san)", normalized):
        groups.add("branch")
    if any(k in normalized for k in ("chan song", "song lon", "song hoi", "xac nhan tao day", "chuan bi tao day")):
        groups.add("wave")
    if any(k in normalized for k in ("cho mua", "cho ban", "do tin cay", "waitbuy", "waitsell")):
        groups.update(("market", "wait_signal"))
    if "smdt" in normalized or "suc manh dong tien" in normalized:
        groups.add("smdt")
    if "dong tien" in normalized and "suc manh dong tien" not in normalized and "smdt" not in normalized:
        groups.add("cashflow")
    return groups


def _clean_question_candidate(value: str) -> str:
    value = re.sub(r"\s+", " ", value or "").strip(" \t\r\n\"'“”")
    return value.rstrip(".。")


def _candidate_is_question(value: str) -> bool:
    normalized = normalize_text(value)
    if len(normalized) < 8 or len(normalized) > 180:
        return False
    if normalized.startswith(GENERIC_GUIDE_PREFIXES):
        return False
    return any(
        marker in normalized
        for marker in (
            "[ma]", "[ma co phieu]", "[ticker]", "[x]", "[nganh]", "[date]",
            "[ngay]", "[month]", "bao nhieu", "the nao", "khi nao", "ma nao",
            "nganh nao", "gan nhat", "lap bang", "lap danh sach", "hieu suat",
            "tin hieu", "smdt", "dong tien", "gia co phieu", "gia ", "chan song",
        )
    )


class RuleCaseCatalog:
    def __init__(self, rag: Any):
        self.rag = rag

    def cases(self, groups: Optional[Set[str]] = None) -> List[RuleCase]:
        found: List[RuleCase] = []
        seen: Set[str] = set()
        for document, metadata in (getattr(self.rag, "rule_docs", {}) or {}).items():
            doc_groups = RULE_GROUPS.get(document, set())
            if groups and not (doc_groups & groups):
                continue
            for chunk in metadata.get("chunks", []) or []:
                for question in self._extract_questions(chunk):
                    key = normalize_text(question)
                    if key in seen:
                        continue
                    seen.add(key)
                    found.append(RuleCase(
                        question,
                        frozenset(doc_groups),
                        document,
                        self._date_is_optional(chunk),
                    ))
        return found

    def direct_match(self, query: str) -> Optional[RuleCase]:
        """Return a rule only when the user's wording is already specific enough."""
        normalized_query = normalize_text(query)
        if not normalized_query:
            return None

        ticker = extract_ticker(query)
        branch = extract_branch(query)
        query_tokens = {
            token
            for token in normalized_query.split()
            if len(token) > 1 and token not in DIRECT_RULE_STOPWORDS
        }
        best_case: Optional[RuleCase] = None
        best_score = 0.0
        second_best_score = 0.0
        best_signature: Optional[frozenset[str]] = None

        for case in self.cases():
            normalized_case = normalize_text(case.question)
            if any(value in normalized_case for value in STOCK_PLACEHOLDERS) and not ticker:
                continue
            if any(value in normalized_case for value in BRANCH_PLACEHOLDERS) and not branch:
                continue
            if (
                any(value in normalized_case for value in DATE_PLACEHOLDERS)
                and not case.date_optional
                and not extract_date_value(query)
            ):
                continue

            if normalized_query == normalized_case or self._template_matches(
                normalized_query, normalized_case
            ):
                return case

            # Do not infer intent from short/generic phrases. Fuzzy matching is
            # reserved for queries carrying at least three meaningful terms.
            if len(query_tokens) < 3:
                continue
            case_tokens = {
                token
                for token in normalized_case.split()
                if len(token) > 1 and token not in DIRECT_RULE_STOPWORDS
            }
            overlap = query_tokens & case_tokens
            coverage = len(overlap) / len(query_tokens)
            if coverage < 0.8 or len(overlap) < 3:
                continue

            semantic_case_tokens = {
                token
                for token in case_tokens
                if token not in {
                    "date", "[date]", "ngay", "[ngay]", "month", "[month]",
                    "yyyy", "mm-yyyy",
                }
            }
            semantic_overlap = query_tokens & semantic_case_tokens
            precision = len(semantic_overlap) / max(len(semantic_case_tokens), 1)
            containment_bonus = 0.25 if (
                normalized_query in normalized_case or normalized_case in normalized_query
            ) else 0.0
            score = coverage + (precision * 0.5) + containment_bonus + min(len(overlap), 8) / 100
            signature = frozenset(semantic_case_tokens)
            if score > best_score:
                if best_case and signature != best_signature:
                    second_best_score = max(second_best_score, best_score)
                best_case = case
                best_score = score
                best_signature = signature
            elif signature != best_signature and score > second_best_score:
                second_best_score = score

        if best_case and best_score - second_best_score >= 0.08:
            return best_case
        return None

    @staticmethod
    def _template_matches(query: str, template: str) -> bool:
        pattern = re.escape(template)
        replacements = {
            "[ma co phieu]": r"[a-z]{2,5}\d?",
            "[ticker]": r"[a-z]{2,5}\d?",
            "[ma]": r"[a-z]{2,5}\d?",
            "[x]": r"[a-z]{2,5}\d?",
            "[nganh]": r".+?",
            "[date]": r"(?:20\d{2}(?:-\d{2}(?:-\d{2})?)?|\d{1,2}/\d{1,2}(?:/20\d{2})?|hom nay|hien tai)",
            "[ngay]": r"(?:20\d{2}-\d{2}-\d{2}|\d{1,2}/\d{1,2}(?:/20\d{2})?|hom nay)",
            "[month]": r"(?:20\d{2}-\d{2}|\d{1,2}-20\d{2}|thang \d{1,2}(?:/20\d{2})?)",
            "mm-yyyy": r"\d{1,2}-20\d{2}",
            "yyyy": r"20\d{2}",
        }
        for placeholder, placeholder_pattern in replacements.items():
            pattern = pattern.replace(re.escape(placeholder), placeholder_pattern)
        return re.fullmatch(pattern, query) is not None

    @staticmethod
    def _date_is_optional(chunk: str) -> bool:
        normalized = normalize_text(chunk)
        return any(
            marker in normalized
            for marker in (
                "khong neu ro date",
                "khong neu date",
                "khong co date",
                "khong truyen date",
                "date la tuy chon",
            )
        )

    def _extract_questions(self, chunk: str) -> Iterable[str]:
        text = chunk or ""
        candidates = re.findall(r'["“]([^"”\n]{8,180})["”]', text)
        first_line = text.splitlines()[0] if text.splitlines() else ""
        heading = re.sub(r"^\s*Guide\s*", "", first_line, flags=re.IGNORECASE).strip()
        if heading:
            candidates.append(heading)
        for candidate in candidates:
            cleaned = _clean_question_candidate(candidate)
            if _candidate_is_question(cleaned):
                yield cleaned


class QuestionGuide:
    def __init__(
        self,
        rag: Any,
        memory: Any = None,
        openai_client: Any = None,
        model: str = CLASSIFIER_MODEL,
    ):
        self.catalog = RuleCaseCatalog(rag)
        self.memory = memory
        self.openai = openai_client
        self.model = model
        self._fallback_states: Dict[str, Dict[str, object]] = {}

    async def _load_state(self, user_id: str) -> Optional[Dict[str, object]]:
        if self.memory and hasattr(self.memory, "get_semantic_guide_state"):
            return await self.memory.get_semantic_guide_state(user_id)
        return self._fallback_states.get(user_id)

    async def _save_state(self, user_id: str, state: Dict[str, object]):
        if self.memory and hasattr(self.memory, "set_semantic_guide_state"):
            await self.memory.set_semantic_guide_state(user_id, state)
        else:
            self._fallback_states[user_id] = state

    async def _clear_state(self, user_id: str):
        if self.memory and hasattr(self.memory, "clear_semantic_guide_state"):
            await self.memory.clear_semantic_guide_state(user_id)
        else:
            self._fallback_states.pop(user_id, None)

    async def handle(self, user_id: str, user_text: str) -> GuideResult:
        direct_case = self.catalog.direct_match(user_text)
        if direct_case:
            await self._clear_state(user_id)
            debug_print(
                "QUESTION GUIDE DIRECT RULE MATCH:",
                direct_case.document,
                "|",
                direct_case.question,
            )
            return GuideResult("run", canonical_question=user_text)

        pending = await self._load_state(user_id)
        if pending:
            resolved = await self._resolve_pending(user_id, user_text, pending)
            if resolved.action != "pass":
                return resolved
            return resolved
        return await self._route_new_question(user_id, user_text)

    async def _resolve_pending(self, user_id: str, user_text: str, pending: Dict[str, object]) -> GuideResult:
        kind = str(pending.get("kind") or "")
        normalized = normalize_text(user_text)
        number = option_number(user_text)

        if kind == "suggest_cases":
            suggestions = [str(item) for item in pending.get("suggestions") or []]
            if number and 1 <= number <= len(suggestions):
                await self._clear_state(user_id)
                return GuideResult("run", canonical_question=suggestions[number - 1])
            best = self._match_suggestion(normalized, suggestions)
            if best:
                await self._clear_state(user_id)
                return GuideResult("run", canonical_question=best)
            if is_affirmative(user_text) and suggestions:
                await self._clear_state(user_id)
                return GuideResult("run", canonical_question=suggestions[0])
            await self._clear_state(user_id)
            return GuideResult("pass")

        if kind == "missing_subject":
            intent = str(pending.get("intent") or "analysis")
            original = str(pending.get("original") or user_text)
            branch = extract_branch(user_text)
            ticker = extract_ticker(user_text)
            if branch:
                await self._clear_state(user_id)
                return await self._after_branch_collected(user_id, intent, branch, original)
            if ticker:
                await self._clear_state(user_id)
                return await self._after_ticker_collected(user_id, intent, ticker, original)
            return GuideResult("ask", message=await self._naturalize_question(
                user_text, "Anh/chị đang muốn kiểm tra một mã cổ phiếu hay một ngành cụ thể?"
            ))
        if kind == "missing_ticker":
            ticker = extract_ticker(user_text)
            if not ticker:
                return GuideResult("ask", message=await self._naturalize_question(
                    user_text, "Anh/chị muốn kiểm tra mã cổ phiếu nào?"
                ))
            await self._clear_state(user_id)
            intent = str(pending.get("intent") or "analysis")
            return await self._after_ticker_collected(
                user_id,
                intent,
                ticker,
                str(pending.get("original") or user_text),
            )

        if kind == "missing_branch":
            branch = extract_branch(user_text) or self._plain_branch_answer(user_text)
            if not branch:
                return GuideResult("ask", message=await self._naturalize_question(
                    user_text, "Anh/chị muốn kiểm tra ngành hoặc dòng nào?"
                ))
            await self._clear_state(user_id)
            intent = str(pending.get("intent") or "analysis")
            return await self._after_branch_collected(
                user_id,
                intent,
                branch,
                str(pending.get("original") or user_text),
            )

        if kind == "missing_time":
            value = extract_date_value(user_text)
            if not value:
                return GuideResult("ask", message=await self._naturalize_question(
                    user_text, "Anh/chị muốn xem hôm nay, một ngày cụ thể, hay theo tháng/năm nào?"
                ))
            await self._clear_state(user_id)
            template = str(pending.get("template") or "{time}")
            return GuideResult("run", canonical_question=template.format(time=value))

        if kind == "waitbuy_month":
            month = int(pending.get("month") or datetime.now().month)
            year = int(pending.get("year") or datetime.now().year)
            day = extract_day(user_text)
            if day:
                await self._clear_state(user_id)
                return GuideResult("run", canonical_question=f"Chờ mua ngày {day:02d}/{month:02d}/{year} là bao nhiêu?")
            if number == 1:
                return GuideResult("ask", message=f"Anh/chị muốn xem chờ mua ngày nào trong tháng {month}/{year}?")
            if number == 2 or any(k in normalized for k in ("thang", "ca thang", "tong hop", "dot bien", "tang manh")):
                await self._clear_state(user_id)
                return GuideResult("run", canonical_question=f"Trong tháng {month}/{year}, những ngày nào chờ mua tăng đột biến?")
            return GuideResult("ask", message=await self._naturalize_question(
                user_text,
                f"Anh/chị muốn xem một ngày cụ thể trong tháng {month}/{year}, hay tổng hợp các ngày chờ mua tăng đột biến?",
            ))

        if kind == "wave_nearest":
            year = extract_year(user_text)
            month = extract_month(user_text)
            day = extract_day(user_text)
            if day and month:
                await self._clear_state(user_id)
                return GuideResult("run", canonical_question=f"Ngày {day:02d}/{month:02d}/{year} có xác nhận chân sóng không?")
            if month:
                await self._clear_state(user_id)
                return GuideResult("run", canonical_question=f"Trong tháng {month}/{year}, ngày nào xác nhận chân sóng?")
            if number == 1 or "gan nhat" in normalized:
                await self._clear_state(user_id)
                return GuideResult("run", canonical_question="Chân sóng gần nhất là ngày nào?")
            if number == 2:
                return GuideResult("ask", message="Anh/chị muốn kiểm tra chân sóng trong tháng nào?")
            return GuideResult("ask", message=await self._naturalize_question(
                user_text, "Anh/chị muốn tìm chân sóng gần nhất, hay kiểm tra theo một tháng/ngày cụ thể?"
            ))

        await self._clear_state(user_id)
        return GuideResult("pass")

    async def _route_new_question(self, user_id: str, user_text: str) -> GuideResult:
        normalized = normalize_text(user_text)
        ticker = extract_ticker(user_text)
        groups = classify_groups(user_text)
        branch = extract_branch(user_text)

        stock_intent = self._stock_intent(normalized)
        branch_intent = self._branch_intent(normalized)
        subject_kind = (
            "both" if ticker and branch
            else "stock" if ticker
            else "branch" if branch
            else "missing"
        )

        if subject_kind == "both":
            return GuideResult("pass")

        if subject_kind == "missing" and (
            (stock_intent or branch_intent)
            and not any(k in normalized for k in ("co phieu", " ma ", "nganh", "dong"))
        ):
            intent = stock_intent or branch_intent or "analysis"
            await self._save_state(user_id, {"kind": "missing_subject", "intent": intent, "original": user_text})
            return GuideResult("ask", message=await self._naturalize_question(
                user_text, "Anh/chị đang muốn kiểm tra một mã cổ phiếu hay một ngành cụ thể?"
            ))

        if subject_kind == "missing" and stock_intent:
            await self._save_state(user_id, {"kind": "missing_ticker", "intent": stock_intent, "original": user_text})
            return GuideResult("ask", message=await self._naturalize_question(
                user_text, "Anh/chị muốn kiểm tra mã cổ phiếu nào?"
            ))

        if subject_kind == "missing" and branch_intent:
            await self._save_state(user_id, {"kind": "missing_branch", "intent": branch_intent, "original": user_text})
            return GuideResult("ask", message=await self._naturalize_question(
                user_text, "Anh/chị muốn kiểm tra ngành hoặc dòng nào?"
            ))

        if subject_kind == "stock" and stock_intent == "analysis":
            return await self._offer_stock_cases(user_id, ticker, user_text)

        if subject_kind == "stock" and stock_intent:
            canonical_question = (
                user_text
                if stock_intent == "strong" or extract_date_value(user_text)
                else self._canonical_stock_question(stock_intent, ticker)
            )
            return GuideResult("run", canonical_question=canonical_question)

        if subject_kind == "branch" and "branch" in groups and branch_intent == "analysis":
            return await self._offer_branch_cases(user_id, branch, user_text)

        if subject_kind == "branch" and branch_intent:
            canonical_question = (
                user_text
                if extract_date_value(user_text)
                else self._canonical_branch_question(branch_intent, branch)
            )
            return GuideResult("run", canonical_question=canonical_question)

        if "cho mua" in normalized:
            month = extract_month(user_text)
            day = extract_day(user_text)
            if month and not day:
                year = extract_year(user_text)
                await self._save_state(user_id, {"kind": "waitbuy_month", "month": month, "year": year})
                return GuideResult("ask", message=await self._naturalize_question(
                    user_text,
                    f"Anh/chị muốn xem chờ mua ngày cụ thể trong tháng {month}/{year}, hay tổng hợp các ngày chờ mua tăng đột biến trong tháng đó?",
                ))
            if not extract_date_value(user_text) and any(k in normalized for k in ("bao nhieu", "thong ke", "xem")):
                await self._save_state(user_id, {
                    "kind": "missing_time",
                    "template": "Chờ mua {time} là bao nhiêu?",
                    "original": user_text,
                })
                return GuideResult("ask", message=await self._naturalize_question(
                    user_text, "Anh/chị muốn xem chờ mua hôm nay, một ngày cụ thể, hay theo tháng/năm nào?"
                ))

        if "chan song" in normalized and "gan nhat" in normalized:
            await self._save_state(user_id, {"kind": "wave_nearest"})
            return GuideResult("ask", message=await self._naturalize_question(
                user_text, "Anh/chị muốn tìm chân sóng gần nhất, hay kiểm tra theo một tháng/ngày cụ thể?"
            ))

        if self._time_is_explicitly_missing(normalized):
            template = self._time_template(user_text, ticker, branch)
            if template:
                await self._save_state(user_id, {"kind": "missing_time", "template": template, "original": user_text})
                return GuideResult("ask", message=await self._naturalize_question(
                    user_text, "Anh/chị muốn xem hôm nay, một ngày cụ thể, hay theo tháng/năm nào?"
                ))

        return GuideResult("pass")

    async def _after_ticker_collected(
        self,
        user_id: str,
        intent: str,
        ticker: str,
        original: str,
    ) -> GuideResult:
        if intent == "analysis":
            return await self._offer_stock_cases(user_id, ticker, original)
        if self._time_is_explicitly_missing(normalize_text(original)):
            template = self._time_template(original, ticker, None)
            if template:
                await self._save_state(user_id, {"kind": "missing_time", "template": template, "original": original})
                return GuideResult("ask", message=await self._naturalize_question(
                    original, "Anh/chị muốn xem hôm nay, một ngày cụ thể, hay theo tháng/năm nào?"
                ))
        return GuideResult("run", canonical_question=self._canonical_stock_question(intent, ticker))

    async def _after_branch_collected(
        self,
        user_id: str,
        intent: str,
        branch: str,
        original: str,
    ) -> GuideResult:
        if intent == "analysis":
            return await self._offer_branch_cases(user_id, branch, original)
        if self._time_is_explicitly_missing(normalize_text(original)):
            template = self._time_template(original, None, branch)
            if template:
                await self._save_state(user_id, {"kind": "missing_time", "template": template, "original": original})
                return GuideResult("ask", message=await self._naturalize_question(
                    original, "Anh/chị muốn xem hôm nay, một ngày cụ thể, hay theo tháng/năm nào?"
                ))
        return GuideResult("run", canonical_question=self._canonical_branch_question(intent, branch))
    async def _offer_stock_cases(self, user_id: str, ticker: str, user_text: str) -> GuideResult:
        suggestions = self._stock_suggestions(ticker)
        await self._save_state(user_id, {"kind": "suggest_cases", "suggestions": suggestions})
        return GuideResult("ask", message=await self._format_suggestions(user_text, ticker, suggestions))

    async def _offer_branch_cases(self, user_id: str, branch: str, user_text: str) -> GuideResult:
        suggestions = self._branch_suggestions(branch)
        await self._save_state(user_id, {"kind": "suggest_cases", "suggestions": suggestions})
        return GuideResult("ask", message=await self._format_topic_suggestions(user_text, f"ngành {branch}", suggestions))

    def _stock_intent(self, normalized: str) -> Optional[str]:
        if any(p in normalized for p in ("co nen mua", "nen mua", "mua duoc khong", "co nen ban", "nen ban", "vao duoc", "muc", "gom", "xuc", "on khong", "phan tich co phieu", "phan tich ma")):
            return "analysis"
        if "phan tich" in normalized and "nganh" not in normalized:
            return "analysis"
        if "smdt" in normalized or "suc manh dong tien" in normalized:
            return "smdt"
        if "dong tien" in normalized:
            return "cashflow"
        price_text = re.sub(r"\b(?:tham|danh|chuyen)\s+gia\b", "", normalized)
        if re.search(r"\bgia\b", price_text):
            return "price"
        if "ma manh" in normalized or "dat chuan" in normalized:
            return "strong"
        if "tin hieu mua" in normalized or "tin hieu ban" in normalized or "mua ban" in normalized:
            return "trade"
        return None

    def _branch_intent(self, normalized: str) -> Optional[str]:
        if "phan tich nganh" in normalized or "phan tich dong" in normalized:
            return "analysis"
        if any(
            phrase in normalized
            for phrase in ("smdt nganh", "smdt dong", "suc manh dong tien nganh", "suc manh dong tien dong")
        ):
            return "smdt"
        if "dong tien nganh" in normalized or "dong tien dong" in normalized:
            return "cashflow"
        if "nganh" in normalized and any(k in normalized for k in ("dan song", "bat dau manh", "dat chuan")):
            return "strong"
        return None

    def _canonical_stock_question(self, intent: str, ticker: str) -> str:
        return {
            "smdt": f"SMDT {ticker} hiện nay là bao nhiêu?",
            "cashflow": f"Dòng tiền {ticker} hiện nay thế nào?",
            "price": f"Giá {ticker} hiện nay là bao nhiêu?",
            "strong": f"{ticker} có đạt chuẩn mã mạnh không?",
            "trade": f"Tín hiệu mua bán gần nhất của {ticker} là gì?",
        }.get(intent, f"Phân tích {ticker}")

    def _canonical_branch_question(self, intent: str, branch: str) -> str:
        return {
            "smdt": f"SMDT ngành {branch} hiện nay là bao nhiêu?",
            "cashflow": f"Dòng tiền ngành {branch} hiện nay thế nào?",
            "strong": f"Ngành {branch} bắt đầu mạnh hoặc dẫn sóng từ khi nào?",
        }.get(intent, f"Phân tích ngành {branch}")

    def _plain_branch_answer(self, text: str) -> Optional[str]:
        value = re.sub(r"\s+", " ", text or "").strip(" ?.!,")
        normalized = normalize_text(value)
        if not value or len(normalized.split()) > 6 or normalized in {"nganh", "dong", "khong biet"}:
            return None
        return value

    def _time_is_explicitly_missing(self, normalized: str) -> bool:
        return bool(
            re.search(r"\b(?:ngay|thang|nam)\s*(?:nao|bao nhieu)?\s*$", normalized)
            or any(p in normalized for p in ("vao ngay nao", "tu thang nao", "trong thang nao"))
        )

    def _time_template(self, user_text: str, ticker: Optional[str], branch: Optional[str]) -> Optional[str]:
        normalized = normalize_text(user_text)
        if ticker and "smdt" in normalized:
            return f"SMDT {ticker} {{time}} là bao nhiêu?"
        if ticker and "dong tien" in normalized:
            return f"Dòng tiền {ticker} {{time}} thế nào?"
        if branch and "smdt" in normalized:
            return f"SMDT ngành {branch} {{time}} là bao nhiêu?"
        if branch and "dong tien" in normalized:
            return f"Dòng tiền ngành {branch} {{time}} thế nào?"
        return None

    def _stock_suggestions(self, ticker: str) -> List[str]:
        cases = self.catalog.cases({"stock", "smdt", "cashflow"})
        intents: Sequence[tuple[Sequence[str], Sequence[str], str]] = (
            (("smdt [ma]", "smdt [ticker]", "smdt [x]"), ("Câu hỏi về sức mạnh dòng tiền, smdt ngành, mã.txt",), f"SMDT {ticker} hôm nay là bao nhiêu?"),
            (("dong tien [ma] hien nay", "dong tien [ticker] hien nay"), ("Câu hỏi về tín hiệu dòng tiền mã , dòng tiền mã.txt",), f"Dòng tiền {ticker} hiện nay thế nào?"),
            (("gia co phieu", "gia [ma]", "gia [ticker]"), ("Câu hỏi về giá của mã.txt",), f"Giá {ticker} hiện nay là bao nhiêu?"),
            (("dat chuan ma manh", "ma [x] bat dau manh"), ("Câu hỏi về mã, cổ phiếu, đạt chuẩn mã mạnh.txt",), f"{ticker} có đạt chuẩn mã mạnh không?"),
            (("tin hieu mua ban", "mua ban gan nhat"), ("Câu hỏi về tín hiệu giao dịch (mua,bán), giá vốn trung bình, tỷ trọng nắm giữ, tỷ trọng giao dịch của mã.txt",), f"Tín hiệu mua bán gần nhất của {ticker} là gì?"),
        )
        return self._render_intents(cases, intents, lambda question: self._render_case(question, ticker))

    def _branch_suggestions(self, branch: str) -> List[str]:
        cases = self.catalog.cases({"branch", "smdt", "cashflow"})
        intents: Sequence[tuple[Sequence[str], Sequence[str], str]] = (
            (("smdt [nganh] la bao nhieu", "smdt nganh"), ("Câu hỏi về sức mạnh dòng tiền, smdt ngành, mã.txt",), f"SMDT ngành {branch} hiện nay là bao nhiêu?"),
            (("dong tien [nganh] hien nay", "dong tien [nganh]"), ("Câu hỏi về tín hiệu dòng tiền mã , dòng tiền mã.txt",), f"Dòng tiền ngành {branch} hiện nay thế nào?"),
            (("nganh [x] bat dau manh", "nganh [x] bat dau dan song"), ("Câu hỏi về ngành, dẫn sóng, đạt chuẩn ngành mạnh.txt",), f"Ngành {branch} bắt đầu mạnh hoặc dẫn sóng từ khi nào?"),
            (("co phieu nao manh nhat dong [nganh x]",), ("Câu hỏi về mã, cổ phiếu, đạt chuẩn mã mạnh.txt",), f"Cổ phiếu nào mạnh nhất ngành {branch} hiện nay?"),
        )
        return self._render_intents(cases, intents, lambda question: self._render_branch_case(question, branch))

    def _render_intents(self, cases, intents, renderer) -> List[str]:
        suggestions: List[str] = []
        for keywords, documents, fallback in intents:
            selected = self._best_case(cases, keywords, documents)
            rendered = renderer(selected.question) if selected else fallback
            if normalize_text(rendered) not in {normalize_text(item) for item in suggestions}:
                suggestions.append(rendered)
        return suggestions

    def _best_case(self, cases, keywords, documents) -> Optional[RuleCase]:
        best = None
        best_score = 0
        allowed_documents = set(documents)
        for case in cases:
            if allowed_documents and case.document not in allowed_documents:
                continue
            normalized = normalize_text(case.question)
            score = sum(20 + len(normalize_text(k).split()) for k in keywords if normalize_text(k) in normalized)
            if "tu hom nay den nay" in normalized:
                score -= 25
            if score > best_score:
                best, best_score = case, score
        return best

    def _render_case(self, template: str, ticker: str) -> str:
        rendered = re.sub(r"\[(?:mã cổ phiếu|mã|ticker|x)\]", ticker, template, flags=re.IGNORECASE)
        rendered = re.sub(r"\[(?:ngày|date)\]", "hôm nay", rendered, flags=re.IGNORECASE)
        rendered = re.sub(r"\[(?:month|tháng)\]", f"{datetime.now().month}/{datetime.now().year}", rendered, flags=re.IGNORECASE)
        return self._question_punctuation(rendered)

    def _render_branch_case(self, template: str, branch: str) -> str:
        rendered = re.sub(r"\[ngành(?: x)?\]", branch, template, flags=re.IGNORECASE)
        rendered = re.sub(r"\[x\]", branch, rendered, flags=re.IGNORECASE)
        rendered = re.sub(r"\[(?:ngày|date)\]", "hôm nay", rendered, flags=re.IGNORECASE)
        return self._question_punctuation(rendered)

    def _question_punctuation(self, value: str) -> str:
        value = value.replace("?", "").strip()
        return value[:1].upper() + value[1:] + "?"

    def _match_suggestion(self, normalized: str, suggestions: Sequence[str]) -> Optional[str]:
        aliases = (
            ("smdt", "suc manh dong tien"),
            ("dong tien", "cashflow"),
            ("gia", "gia co phieu"),
            ("ma manh", "manh", "dat chuan"),
            ("mua ban", "tin hieu", "tin hieu mua ban", "mua", "ban"),
        )

        def contains_term(text: str, term: str) -> bool:
            return bool(re.search(rf"(?:^|\s){re.escape(term)}(?:$|\s)", text))

        for suggestion in suggestions:
            candidate = normalize_text(suggestion)
            for terms in aliases:
                if normalized in terms and any(contains_term(candidate, term) for term in terms):
                    return suggestion
        return None

    async def _format_suggestions(self, user_text: str, ticker: str, suggestions: Sequence[str]) -> str:
        fallback = f"Câu hỏi này còn khá rộng. Với {ticker}, anh/chị muốn kiểm tra theo hướng nào?"
        intro = await self._naturalize_intro(user_text, fallback, suggestions)
        return "\n".join([intro] + [f"{i}. {item}" for i, item in enumerate(suggestions, 1)])

    async def _format_topic_suggestions(self, user_text: str, topic: str, suggestions: Sequence[str]) -> str:
        fallback = f"Câu hỏi này còn khá rộng. Với {topic}, anh/chị muốn kiểm tra theo hướng nào?"
        intro = await self._naturalize_intro(user_text, fallback, suggestions)
        return "\n".join([intro] + [f"{i}. {item}" for i, item in enumerate(suggestions, 1)])

    async def _naturalize_intro(self, user_text: str, fallback: str, suggestions: Sequence[str]) -> str:
        if not self.openai:
            return fallback
        prompt = f"""
User vừa hỏi: {user_text}
Backend đã lọc đúng các case sau:
{chr(10).join(f'- {item}' for item in suggestions)}

Viết đúng 1 câu dẫn nhập tiếng Việt tự nhiên để mời user chọn một hướng.
Không liệt kê lại case, không thêm case mới, không kết luận mua/bán, không markdown.
""".strip()
        return await asyncio.to_thread(self._call_naturalizer, prompt, fallback)

    async def _naturalize_question(self, user_text: str, fixed_question: str) -> str:
        if not self.openai:
            return fixed_question
        prompt = f"""
Câu user vừa nhập: {user_text}
Nội dung bắt buộc phải hỏi lại: {fixed_question}

Viết lại thành đúng 1 câu tiếng Việt tự nhiên, ngắn gọn.
Không thay đổi dữ kiện cần hỏi, không thêm lựa chọn hoặc case mới, không markdown.
""".strip()
        return await asyncio.to_thread(self._call_naturalizer, prompt, fixed_question)

    def _call_naturalizer(self, prompt: str, fallback: str) -> str:
        try:
            response = self.openai.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Chỉ viết một câu tiếng Việt ngắn, tự nhiên, không markdown."},
                    {"role": "user", "content": prompt},
                ],
                tools=None,
            )
            text = (response.choices[0].message.content or "").strip()
            text = text.replace("**", "").replace("__", "")
            first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
            first_line = re.sub(r"^\s*(?:[-•]|\d+[.)])\s*", "", first_line)
            return first_line[:240] or fallback
        except Exception as exc:
            debug_print("QUESTION_GUIDE_NATURALIZER_ERROR:", exc)
            return fallback
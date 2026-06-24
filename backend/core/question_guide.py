import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set


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
    "on", "muc", "gom", "xuc", "vao", "chua",
}

NON_TICKERS = {"SMDT", "RSI", "MACD", "NAV", "API", "GPT", "AI", "VNINDEX"}
GENERIC_GUIDE_PREFIXES = (
    "hướng dẫn", "huong dan", "khi người dùng", "khi nguoi dung",
    "đối với", "doi voi", "mỗi lần", "moi lan", "để tránh", "de tranh",
    "điều kiện", "dieu kien",
)


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text or "")
    normalized = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
    normalized = normalized.lower()
    normalized = re.sub(r"[^a-z0-9%/\-\s\[\]]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def extract_ticker(text: str) -> Optional[str]:
    raw = text or ""
    for item in re.findall(r"\b[A-Z]{2,5}\b", raw):
        if item not in NON_TICKERS:
            return item

    normalized = normalize_text(raw)
    action_match = re.search(
        r"\b(?:mua|ban|muc|gom|xuc|ma|co phieu|phan tich)\s+([a-z]{2,5})\b",
        normalized,
    )
    if action_match and action_match.group(1) not in STOCK_WORDS:
        return action_match.group(1).upper()

    candidates = re.findall(r"\b[a-z]{2,5}\b", normalized)
    for item in reversed(candidates):
        if item not in STOCK_WORDS:
            return item.upper()
    return None


def extract_branch(text: str) -> Optional[str]:
    raw = text or ""
    match = re.search(r"\b(?:ngành|dòng)\s+([\wÀ-ỹ\s]+)", raw, flags=re.IGNORECASE)
    if not match:
        match = re.search(r"\b(?:nganh|dong)\s+([a-z\s]+)", raw, flags=re.IGNORECASE)
    if not match:
        return None
    value = re.split(
        r"\b(?:hôm nay|hom nay|hiện nay|hien nay|thế nào|the nao|có nên|co nen|không|ko)\b",
        match.group(1),
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    value = re.sub(r"\s+", " ", value).strip(" ?.!,")
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


def is_affirmative(text: str) -> bool:
    normalized = normalize_text(text)
    return normalized in {"dung", "ok", "co", "uh", "u", "yes", "chinh xac"} or normalized.startswith("dung ")


def option_number(text: str) -> Optional[int]:
    normalized = normalize_text(text)
    match = re.search(r"\b(?:chon|cau|so)?\s*([1-9])\b", normalized)
    return int(match.group(1)) if match else None


def classify_groups(text: str) -> Set[str]:
    normalized = normalize_text(text)
    groups: Set[str] = set()
    if extract_ticker(text) or any(k in normalized for k in ("co phieu", " ma ", "ticker")):
        groups.add("stock")
    if any(k in normalized for k in ("nganh", "dong chung khoan", "dong ngan hang", "dong thep")):
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
                    found.append(RuleCase(question, frozenset(doc_groups), document))
        return found

    def _extract_questions(self, chunk: str) -> Iterable[str]:
        text = chunk or ""
        candidates: List[str] = []
        candidates.extend(re.findall(r'["“]([^"”\n]{8,180})["”]', text))

        first_line = text.splitlines()[0] if text.splitlines() else ""
        heading = re.sub(r"^\s*Guide\s*", "", first_line, flags=re.IGNORECASE).strip()
        if heading:
            candidates.append(heading)

        for candidate in candidates:
            cleaned = _clean_question_candidate(candidate)
            if _candidate_is_question(cleaned):
                yield cleaned


class QuestionGuide:
    def __init__(self, rag: Any):
        self.pending: Dict[str, Dict[str, object]] = {}
        self.catalog = RuleCaseCatalog(rag)

    def handle(self, user_id: str, user_text: str) -> GuideResult:
        pending = self.pending.get(user_id)
        if pending:
            resolved = self._resolve_pending(user_id, user_text, pending)
            if resolved.action != "pass":
                return resolved
        return self._route_new_question(user_id, user_text)

    def _resolve_pending(self, user_id: str, user_text: str, pending: Dict[str, object]) -> GuideResult:
        kind = str(pending.get("kind") or "")
        normalized = normalize_text(user_text)
        number = option_number(user_text)

        if kind == "suggest_cases":
            suggestions = [str(item) for item in pending.get("suggestions") or []]
            if number and 1 <= number <= len(suggestions):
                self.pending.pop(user_id, None)
                return GuideResult("run", canonical_question=suggestions[number - 1])

            best = self._match_suggestion(normalized, suggestions)
            if best:
                self.pending.pop(user_id, None)
                return GuideResult("run", canonical_question=best)
            if is_affirmative(user_text) and suggestions:
                self.pending.pop(user_id, None)
                return GuideResult("run", canonical_question=suggestions[0])
            return GuideResult(
                "ask",
                message="Anh/chị chọn một hướng ở trên bằng số, hoặc nói ngắn như SMDT, dòng tiền, giá, mã mạnh hay tín hiệu mua bán.",
            )

        if kind == "waitbuy_month":
            month = int(pending.get("month") or datetime.now().month)
            year = int(pending.get("year") or datetime.now().year)
            day = extract_day(user_text)
            if day:
                self.pending.pop(user_id, None)
                return GuideResult("run", canonical_question=f"Chờ mua ngày {day:02d}/{month:02d}/{year} là bao nhiêu?")
            if number == 1:
                return GuideResult("ask", message=f"Anh/chị muốn xem chờ mua ngày nào trong tháng {month}/{year}?")
            if number == 2 or any(k in normalized for k in ("thang", "ca thang", "tong hop", "dot bien", "tang manh")):
                self.pending.pop(user_id, None)
                return GuideResult("run", canonical_question=f"Trong tháng {month}/{year}, những ngày nào chờ mua tăng đột biến?")
            return GuideResult("ask", message=f"Anh/chị muốn xem một ngày cụ thể trong tháng {month}/{year}, hay tổng hợp các ngày chờ mua tăng đột biến?")

        if kind == "wave_nearest":
            year = extract_year(user_text)
            month = extract_month(user_text)
            day = extract_day(user_text)
            if day and month:
                self.pending.pop(user_id, None)
                return GuideResult("run", canonical_question=f"Ngày {day:02d}/{month:02d}/{year} có xác nhận chân sóng không?")
            if month:
                self.pending.pop(user_id, None)
                return GuideResult("run", canonical_question=f"Trong tháng {month}/{year}, ngày nào xác nhận chân sóng?")
            if number == 1 or "gan nhat" in normalized:
                self.pending.pop(user_id, None)
                return GuideResult("run", canonical_question="Chân sóng gần nhất là ngày nào?")
            if number == 2:
                return GuideResult("ask", message="Anh/chị muốn kiểm tra chân sóng trong tháng nào?")
            return GuideResult("ask", message="Anh/chị muốn tìm chân sóng gần nhất, hay kiểm tra theo một tháng/ngày cụ thể?")

        self.pending.pop(user_id, None)
        return GuideResult("pass")

    def _route_new_question(self, user_id: str, user_text: str) -> GuideResult:
        normalized = normalize_text(user_text)
        ticker = extract_ticker(user_text)

        groups = classify_groups(user_text)
        branch = extract_branch(user_text)

        if ticker and self._is_broad_stock_question(normalized):
            suggestions = self._stock_suggestions(ticker)
            if suggestions:
                self.pending[user_id] = {"kind": "suggest_cases", "suggestions": suggestions}
                return GuideResult("ask", message=self._format_suggestions(ticker, suggestions))

        if "branch" in groups and branch and self._is_broad_analysis(normalized):
            suggestions = self._branch_suggestions(branch)
            if suggestions:
                self.pending[user_id] = {"kind": "suggest_cases", "suggestions": suggestions}
                return GuideResult("ask", message=self._format_topic_suggestions(f"ngành {branch}", suggestions))

        if "cho mua" in normalized:
            month = extract_month(user_text)
            day = extract_day(user_text)
            if month and not day:
                year = extract_year(user_text)
                self.pending[user_id] = {"kind": "waitbuy_month", "month": month, "year": year}
                return GuideResult(
                    "ask",
                    message=(
                        f"Anh/chị muốn xem chờ mua ngày cụ thể trong tháng {month}/{year}, "
                        "hay tổng hợp các ngày chờ mua tăng đột biến trong tháng đó?"
                    ),
                )

        if "chan song" in normalized and "gan nhat" in normalized:
            self.pending[user_id] = {"kind": "wave_nearest"}
            return GuideResult("ask", message="Anh/chị muốn tìm chân sóng gần nhất, hay kiểm tra theo một tháng/ngày cụ thể?")

        return GuideResult("pass")

    def _is_broad_stock_question(self, normalized: str) -> bool:
        advice = any(
            phrase in normalized
            for phrase in (
                "co nen mua", "nen mua", "mua duoc khong", "co nen ban", "nen ban",
                "ban duoc khong", "vao duoc khong", "vao duoc chua", "mua luc nay",
                "ban luc nay", "muc", "gom", "xuc", "on khong", "duoc chua",
            )
        )
        broad_analysis = "phan tich" in normalized and not any(
            detail in normalized for detail in ("smdt", "dong tien", "gia", "tin hieu", "ma manh", "hieu suat")
        )
        return advice or broad_analysis

    def _is_broad_analysis(self, normalized: str) -> bool:
        return "phan tich" in normalized and not any(
            detail in normalized
            for detail in ("smdt", "dong tien", "gia", "tin hieu", "dan song", "ma manh", "hieu suat")
        )
    def _stock_suggestions(self, ticker: str) -> List[str]:
        cases = self.catalog.cases({"stock", "smdt", "cashflow"})
        intents: Sequence[tuple[Sequence[str], Sequence[str], str]] = (
            (
                ("smdt [ma]", "smdt [ticker]", "smdt [x]", "smdt co phieu"),
                ("Câu hỏi về sức mạnh dòng tiền, smdt ngành, mã.txt",),
                f"SMDT {ticker} hôm nay là bao nhiêu?",
            ),
            (
                ("dong tien [ma] hien nay", "dong tien [ticker] hien nay", "tin hieu dong tien [ticker]"),
                ("Câu hỏi về tín hiệu dòng tiền mã , dòng tiền mã.txt",),
                f"Tín hiệu dòng tiền {ticker} hiện nay thế nào?",
            ),
            (
                ("gia co phieu", "gia [ma]", "gia [ticker]", "gia [x]"),
                ("Câu hỏi về giá của mã.txt",),
                f"Giá {ticker} hiện nay là bao nhiêu?",
            ),
            (
                ("dat chuan ma manh", "ma [x] bat dau manh", "ma manh"),
                ("Câu hỏi về mã, cổ phiếu, đạt chuẩn mã mạnh.txt",),
                f"{ticker} có đạt chuẩn mã mạnh không?",
            ),
            (
                ("tin hieu mua ban", "tin hieu mua", "mua ban gan nhat"),
                ("Câu hỏi về tín hiệu giao dịch (mua,bán), giá vốn trung bình, tỷ trọng nắm giữ, tỷ trọng giao dịch của mã.txt",),
                f"Tín hiệu mua bán gần nhất của {ticker} là gì?",
            ),
        )
        suggestions: List[str] = []
        for keywords, documents, fallback in intents:
            selected = self._best_case(cases, keywords, documents)
            rendered = self._render_case(selected.question, ticker) if selected else fallback
            if normalize_text(rendered) not in {normalize_text(item) for item in suggestions}:
                suggestions.append(rendered)
        return suggestions

    def _branch_suggestions(self, branch: str) -> List[str]:
        cases = self.catalog.cases({"branch", "smdt", "cashflow"})
        intents: Sequence[tuple[Sequence[str], Sequence[str], str]] = (
            (
                ("smdt [nganh] la bao nhieu", "smdt nganh", "suc manh dong tien"),
                ("Câu hỏi về sức mạnh dòng tiền, smdt ngành, mã.txt",),
                f"SMDT ngành {branch} hiện nay là bao nhiêu?",
            ),
            (
                ("dong tien [nganh] hien nay", "dong tien [nganh]"),
                ("Câu hỏi về tín hiệu dòng tiền mã , dòng tiền mã.txt",),
                f"Dòng tiền ngành {branch} hiện nay thế nào?",
            ),
            (
                ("nganh [x] bat dau manh", "nganh [x] bat dau dan song"),
                ("Câu hỏi về ngành, dẫn sóng, đạt chuẩn ngành mạnh.txt",),
                f"Ngành {branch} bắt đầu mạnh hoặc dẫn sóng từ khi nào?",
            ),
            (
                ("co phieu nao manh nhat dong [nganh x]", "ma co phieu dong [nganh]"),
                ("Câu hỏi về mã, cổ phiếu, đạt chuẩn mã mạnh.txt", "Câu hỏi về ngành, dẫn sóng, đạt chuẩn ngành mạnh.txt"),
                f"Cổ phiếu nào mạnh nhất ngành {branch} hiện nay?",
            ),
        )
        suggestions: List[str] = []
        for keywords, documents, fallback in intents:
            selected = self._best_case(cases, keywords, documents)
            rendered = self._render_branch_case(selected.question, branch) if selected else fallback
            if normalize_text(rendered) not in {normalize_text(item) for item in suggestions}:
                suggestions.append(rendered)
        return suggestions
    def _best_case(
        self,
        cases: Sequence[RuleCase],
        keywords: Sequence[str],
        documents: Sequence[str],
    ) -> Optional[RuleCase]:
        best: Optional[RuleCase] = None
        best_score = 0
        allowed_documents = set(documents)
        for case in cases:
            if allowed_documents and case.document not in allowed_documents:
                continue
            normalized = normalize_text(case.question)
            padded = f" {normalized} "
            score = 0
            for keyword in keywords:
                normalized_keyword = normalize_text(keyword)
                if f" {normalized_keyword} " in padded or normalized_keyword in normalized:
                    score += 20 + len(normalized_keyword.split())
            if "tu hom nay den nay" in normalized:
                score -= 25
            if score > best_score:
                best = case
                best_score = score
        return best
    def _render_case(self, template: str, ticker: str) -> str:
        rendered = template
        rendered = re.sub(r"\[(?:mã cổ phiếu|mã|ticker|x)\]", ticker, rendered, flags=re.IGNORECASE)
        rendered = re.sub(r"\[(?:ngày|date)\]", "hôm nay", rendered, flags=re.IGNORECASE)
        rendered = re.sub(r"\[(?:month|tháng)\]", f"{datetime.now().month}/{datetime.now().year}", rendered, flags=re.IGNORECASE)
        rendered = rendered.replace("?", "").strip()
        return rendered[:1].upper() + rendered[1:] + "?"

    def _render_branch_case(self, template: str, branch: str) -> str:
        rendered = template
        rendered = re.sub(r"\[ngành(?: x)?\]", branch, rendered, flags=re.IGNORECASE)
        rendered = re.sub(r"\[x\]", branch, rendered, flags=re.IGNORECASE)
        rendered = re.sub(r"\[(?:ngày|date)\]", "hôm nay", rendered, flags=re.IGNORECASE)
        rendered = rendered.replace("?", "").strip()
        return rendered[:1].upper() + rendered[1:] + "?"
    def _match_suggestion(self, normalized: str, suggestions: Sequence[str]) -> Optional[str]:
        aliases = {
            "smdt": ("smdt", "suc manh dong tien"),
            "cashflow": ("dong tien", "cashflow"),
            "price": ("gia",),
            "strong": ("manh", "dat chuan"),
            "trade": ("mua ban", "tin hieu", "mua", "ban"),
        }
        for suggestion in suggestions:
            candidate = normalize_text(suggestion)
            for terms in aliases.values():
                if any(term in normalized for term in terms) and any(term in candidate for term in terms):
                    return suggestion
        return None

    def _format_topic_suggestions(self, topic: str, suggestions: Sequence[str]) -> str:
        lines = [f"Câu hỏi này còn khá rộng. Với {topic}, anh/chị muốn kiểm tra theo hướng nào?"]
        lines.extend(f"{index}. {suggestion}" for index, suggestion in enumerate(suggestions, start=1))
        return "\n".join(lines)
    def _format_suggestions(self, ticker: str, suggestions: Sequence[str]) -> str:
        lines = [f"Câu hỏi này còn khá rộng. Với {ticker}, anh/chị muốn kiểm tra theo hướng nào?"]
        lines.extend(f"{index}. {suggestion}" for index, suggestion in enumerate(suggestions, start=1))
        return "\n".join(lines)
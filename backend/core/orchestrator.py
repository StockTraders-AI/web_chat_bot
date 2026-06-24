import asyncio
import json
import re
import unicodedata
from typing import Any, Dict, List, Tuple, Optional
from datetime import datetime

from core.prompt import SYSTEM_PROMPT
from core.model_router import pick_model
from core.memory import MemoryStore
from core.rag import RAGStore
from core.tool_engine import ToolRegistry
from core.condition_engine import extract_rows, scan_vnindex_waitbuy_reversal
from core.question_guide import QuestionGuide

from services.api_executor import APIExecutor
from services.openai_client import OpenAIClient
from settings import MAX_TOOL_LOOPS, CLASSIFIER_MODEL
from core.constants import MAIN_BRANCHES, MAIN_BRANCH_ALIASES

STREAM_CHUNK_CHARS = 60

# =====================================================
# DEBUG
# =====================================================

DEBUG = True

def log(*args):
    if DEBUG:
        print(*args)

# =====================================================
# STOCK ROUTER
# =====================================================

STOCK_KEYWORDS = [
    "giá","cổ phiếu","smdt","ngành","mã","tín hiệu", "suy yếu", "lộ trình", "thống kê",
    "chứng khoán","dòng tiền","sentiment","chân sóng","sóng", "chờ mua", "chờ bán", "mua", "bán", "độ tin cậy"
]

MAIN_BRANCH_KEYWORDS = [ "chủ lực", "chu luc", "ngành mạnh", "nganh manh", "dẫn sóng", "dan song"]

def need_main_branches(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in MAIN_BRANCH_KEYWORDS)

def enforce_main_branch_terms(text: str) -> str:
    fixed = text or ""
    fixed_l = fixed.lower()

    mentions_main_branch = any(branch.lower() in fixed_l for branch in MAIN_BRANCHES)
    mentions_alias = any(alias.lower() in fixed_l for alias in MAIN_BRANCH_ALIASES)

    if mentions_main_branch or mentions_alias:
        fixed = fixed.replace("ngành phụ", "ngành chủ lực")
        fixed = fixed.replace("Ngành phụ", "Ngành chủ lực")

    return fixed

TICKER_RE = re.compile(r"\b[A-Z]{2,5}\b")
NON_TICKER_SYMBOLS = frozenset({"RSI", "NAV", "SMDT", "GPT", "AI", "API", "MACD"})
NORMALIZED_STOCK_KEYWORDS = (
    "gia", "co phieu", "smdt", "nganh", "ma", "tin hieu", "suy yeu",
    "lo trinh", "thong ke", "chung khoan", "dong tien", "sentiment",
    "chan song", "song", "cho mua", "cho ban", "mua", "ban", "do tin cay",
)
FORCE_RULES_PHRASES = (
    "phan tich nganh", "phan tich co phieu", "phan tich ma", "smdt co phieu",
    "smdt nganh", "dong tien", "cho mua", "cho ban", "tin hieu",
    "nganh nao", "ma nao", "gia co phieu", "gia hom nay", "vuot", "cross",
    "dat chuan ma manh", "ma manh", "bat dau manh", "dan song", "chan song",
)
SMDT_DATA_INTENT_WORDS = (
    "hom nay", "ngay", "co phieu", "ma", "nganh", "bao nhieu", "tang",
    "giam", "vuot", "cross", "phien",
)
DEFINITION_INTENT_PHRASES = (
    "la gi", "nghia la gi", "khai niem", "dinh nghia", "hieu the nao",
    "nen hieu the nao",
)
DATA_INTENT_PHRASES = (
    "hom nay", "ngay", "thang", "nam", "bao nhieu", "thong ke",
    "phan tich", "tang", "giam", "vuot", "cross", "phien",
)


def normalize_search_text(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text or "")
    normalized = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
    normalized = normalized.replace("đ", "d").replace("Đ", "D")
    normalized = normalized.lower()
    return re.sub(r"\s+", " ", normalized).strip()


def ensure_smdt_percent(text: str) -> str:
    if "smdt" not in normalize_search_text(text):
        return text or ""

    text = re.sub(r"(\d+)%([.,])(\d+)%", r"\1\2\3%", text or "")

    def should_skip(match: re.Match) -> bool:
        raw = match.group(0)
        start, end = match.span()
        after = (text[end:end + 16] or "").lower()
        before = (text[max(0, start - 16):start] or "").lower()

        if after.lstrip().startswith("%"):
            return True
        if re.match(r"\s*(phien|phiên|ngay|ngày|thang|tháng|nam|năm|ma|mã|co phieu|cổ phiếu)", after):
            return True
        if re.search(r"(ngay|ngày|thang|tháng|nam|năm)\s*$", before):
            return True

        try:
            value = float(raw.replace(",", "."))
        except ValueError:
            return True

        if raw.isdigit() and 1900 <= value <= 2100:
            return True
        if raw.isdigit() and value < 10:
            return True
        return False

    fixed = re.sub(
        r"(?<![\w])(?:\d+[.,]\d+|\d+)(?![\w%])",
        lambda match: match.group(0) if should_skip(match) else f"{match.group(0)}%",
        text or "",
    )
    return re.sub(r"(\d+)%([.,])(\d+)%", r"\1\2\3%", fixed)


def clean_chat_output(text: str) -> str:
    fixed = text or ""
    fixed = fixed.replace("**", "")
    fixed = fixed.replace("__", "")
    fixed = re.sub(r"(?m)^\s*#{1,6}\s*", "", fixed)
    fixed = re.sub(
        r"(?<![\w])(\d+[.,]\d+|\d+)%",
        lambda match: f"{float(match.group(1).replace(',', '.')):.1f}%",
        fixed,
    )
    return fixed.strip()


def has_real_ticker(text: str) -> bool:
    return any(match.group(0) not in NON_TICKER_SYMBOLS for match in TICKER_RE.finditer(text or ""))


def is_definition_query(text: str) -> bool:
    normalized = normalize_search_text(text)
    if not normalized:
        return False
    if not any(phrase in normalized for phrase in DEFINITION_INTENT_PHRASES):
        return False
    if has_real_ticker(text):
        return False
    return not any(phrase in normalized for phrase in DATA_INTENT_PHRASES)


def is_stock_related(text: str) -> bool:
    t = (text or "").lower()
    normalized = normalize_search_text(text)
    if any(k in t for k in STOCK_KEYWORDS):
        return True
    if any(k in normalized for k in NORMALIZED_STOCK_KEYWORDS):
        return True
    return bool(TICKER_RE.search(text or ""))


def should_force_rules(user_text: str) -> bool:
    normalized = normalize_search_text(user_text)
    if not normalized or is_definition_query(user_text):
        return False
    if any(phrase in normalized for phrase in FORCE_RULES_PHRASES):
        return True
    if "phan tich" in normalized and any(k in normalized for k in ("nganh", "co phieu", "ma", "dong", "thi truong")):
        return True
    if "smdt" in normalized and any(k in normalized for k in SMDT_DATA_INTENT_WORDS):
        return True
    if has_real_ticker(user_text) and any(k in normalized for k in (
        "phan tich", "smdt", "gia", "tin hieu", "dong tien", "mua", "ban",
        "dat chuan", "ma manh", "bat dau manh", "hieu suat",
    )):
        return True
    return False


def extract_api_from_context(text: str):
    if not text:
        return []
    return list(set(re.findall(r"get[A-Za-z0-9_]+", text)))


def normalize_label(text: str) -> str:
    return (text or "").strip().upper()


def is_waitbuy_explain_query(text: str) -> bool:
    normalized = normalize_search_text(text)
    if is_definition_query(text):
        return False
    if any(k in normalized for k in ("thuyet minh cho mua", "giai thich cho mua", "waitbuy")):
        return True
    if "cho mua" in normalized:
        return any(k in normalized for k in ("hom nay", "ngay", "thang", "nam", "tang", "giam", "cao", "vuot", "phien", "vi du"))
    return False


def extract_requested_signal_period(text: str) -> Dict[str, Any]:
    date_match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", text or "")
    if date_match:
        return {"date": date_match.group(1)}
    year_match = re.search(r"\b(20\d{2})\b", text or "")
    if year_match:
        return {"year": int(year_match.group(1))}
    return {"year": datetime.now().year}


def format_vn_date(value: Any) -> str:
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return str(value or "")

# ORCHESTRATOR
class Orchestrator:

    def __init__(self, memory: MemoryStore, rag: RAGStore, registry: ToolRegistry):

        self.memory = memory
        self.rag = rag
        self.registry = registry

        self.executor = APIExecutor(registry)
        self.oa = OpenAIClient()
        self.question_guide = QuestionGuide(
            self.rag,
            memory=self.memory,
            openai_client=self.oa,
        )
        self._user_chat_locks: Dict[str, asyncio.Lock] = {}

    # =====================================================
    # BUILD BASE MESSAGES
    # =====================================================

    def classify_query_source(self, user_text: str) -> str:
        if should_force_rules(user_text):
            return "RULES"

        prompt = f"""
    Bạn là bộ phân loại rất ngắn cho chatbot chứng khoán.

    Nhiệm vụ:
    - Trả về đúng 1 nhãn duy nhất: RULES hoặc BOOKS

    RULES:
    - Lộ trình, thống kê
    - câu hỏi dữ liệu
    - câu hỏi cần API
    - hỏi giá, SMDT, tín hiệu, chờ mua, chờ bán, mã nào, ngành nào, ngày nào, thống kê
    - hỏi “dòng/ngành nào dẫn sóng từ khi nào”, “bắt đầu dẫn sóng khi nào”, “dẫn sóng từ ngày/tháng nào”, "thời điểm đạt chuẩn ngành mạnh của một ngành/dòng/mã"


    BOOKS:
    - câu hỏi kiến thức
    - câu hỏi giải thích, khái niệm, vì sao, bản chất, học thuyết, tiêu chí, nên hiểu thế nào

    Câu hỏi:
    {user_text}

    Chỉ trả về RULES hoặc BOOKS.
    """.strip()

        resp = self.oa.chat(
            model=CLASSIFIER_MODEL,
            messages=[
                {"role": "system", "content": "Chỉ trả về đúng 1 từ: RULES hoặc BOOKS."},
                {"role": "user", "content": prompt},
            ]
        )

        raw = normalize_label(resp.choices[0].message.content or "")

        if raw not in {"RULES", "BOOKS"}:
            return "RULES"

        return raw

    async def build_base_messages(
        self,
        user_id: str,
        user_text: str,
        language: str
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], bool, List[str], Optional[str]]:

        raw_user_text = user_text.strip()
        query_source = self.classify_query_source(raw_user_text)
        allowed_apis: List[str] = []
        current_doc: Optional[str] = None

        print("QUERY SOURCE:", query_source)
        history_all = await self.memory.recent_messages(user_id)

        def is_semantically_related(current: str, previous: str) -> bool:
            if not previous:
                return False

            cur_words = set(current.lower().split())
            prev_words = set(previous.lower().split())

            stop = {"là","bao","nhiêu","có","không","k","gì","sao","thì","vậy"}
            cur_words -= stop
            prev_words -= stop

            overlap = cur_words.intersection(prev_words)

            return len(overlap) >= 2


        history = []

        if history_all:
            recent_candidates = history_all[-3:]

            for h in reversed(recent_candidates):
                if is_semantically_related(raw_user_text, h["content"]):
                    history = history_all[-3:] 
                    break

        # ======================================
        # STOCK RELATED DETECTION
        # ======================================

        stock_related = is_stock_related(raw_user_text)

        if not stock_related:
            for h in reversed(history):
                if is_stock_related(h["content"]):
                    stock_related = True
                    break

        today_str = datetime.now().strftime("%Y-%m-%d")

        # ======================================
        # BUILD SYSTEM MESSAGE (ONLY 1)
        # ======================================

        system_parts = [
            SYSTEM_PROMPT,
            "Output format rule: trả lời dạng text thường, không dùng markdown, không dùng dấu ** hoặc __ để in đậm.",
            "SMDT formatting rule: SMDT is a percentage metric. Whenever you mention a numeric SMDT value, always append the % symbol, for example 15.57% or 70%.",
        ]

        if stock_related:
            branches_text = "\n".join([f"- {b}" for b in MAIN_BRANCHES])
            aliases_text = "\n".join([f"- {alias} = {canonical}" for alias, canonical in MAIN_BRANCH_ALIASES.items()])
            system_parts.append(
                "DANH SÁCH 6 NGÀNH CHỦ LỰC CỦA STOCKTRADERS AI - PHẢI GHI NHỚ TUYỆT ĐỐI:\n"
                + branches_text
                + "\n\n"
                + "QUY TẮC BẮT BUỘC VỀ NGÀNH CHỦ LỰC:\n"
                + "- 6 ngành trên luôn là ngành chủ lực trong hệ thống StockTraders AI.\n"
                + "- Tuyệt đối không gọi bất kỳ ngành nào trong danh sách này là ngành phụ.\n"
                + "- Nếu tài liệu hoặc ngữ cảnh có chữ 'ngành phụ' mâu thuẫn với danh sách này, phải ưu tiên danh sách 6 ngành chủ lực.\n"
                + "- Bất động sản dân cư là ngành chủ lực, không phải ngành phụ.\n"
                + "- BĐS dân cư/BDS dân cư là cách gọi tắt của Bất động sản dân cư.\n"
                + "\n"
                + "ALIAS NGÀNH CHỦ LỰC:\n"
                + aliases_text
                + "\n\nQUY TAC SACH VE NGANH CHU LUC:\n6 nganh chu luc cua StockTraders AI la:\n"
                + branches_text
                + "\n- Neu user hoi tong quat ve 'nganh chu luc', 'suc manh dong tien nganh chu luc', "
                + "hoac SMDT cua cac nganh chu luc, phai kiem tra/de cap du 6 nganh tren.\n"
                + "- Khong duoc tu bo sot Chung khoan. Neu khong co du lieu cho mot nganh, noi ro nganh do chua co du lieu.\n"
                + "- Neu user hoi rieng 'Chung khoan' hoac 'nganh chung khoan', can dung nganh Chung khoan/Moi gioi chung khoan."
            )

        if language == "en":
            system_parts.append(f"Today is {today_str}")
        else:
            system_parts.append(f"Ngày hiện tại là {today_str}")

        sources = []

        # ======================================
        # RAG CONTEXT
        # ======================================

        if query_source == "BOOKS":
            book_result = self.rag.retrieve_best_book(raw_user_text, top_k=3)
            doc = book_result.get("doc_name")
            score = book_result.get("score")
            chunks = book_result.get("chunks") or []

            print(f"\nBOOK DOC: {doc} | SCORE: {score}")

            for i, ch in enumerate(chunks, 1):
                preview = ch.replace("\n", " ")[:120]
                print(f"CHUNK {i}: {preview}...")

            current_doc = book_result.get("doc_name")
            book_chunks = book_result.get("chunks") or []

            if book_chunks:
                refs = []
                for i, ch in enumerate(book_chunks, start=1):
                    refs.append(f"[{i}] {ch}")

                system_parts.append("""BOOK KNOWLEDGE CONTEXT - STOCKTRADERS AI.
                    RULES:
                    - Chỉ trả lời dựa trên nội dung trong tài liệu bên dưới.
                    - Nếu user hỏi dạng "là gì", "khái niệm", "nghĩa là gì", "hiểu thế nào", hãy diễn giải thành 3-5 câu ngắn, rõ ý.
                    - Được tóm tắt và viết lại cho dễ hiểu, không bắt buộc giữ nguyên câu chữ trong tài liệu.
                    - Giải thích theo kiểu người mới cũng hiểu: nó là gì, dấu hiệu nào cần chú ý, và nên hiểu đúng ra sao.
                    - Không copy nguyên một đoạn dài, không bịa thêm ngoài tài liệu, không nhắc tài liệu nội bộ.
                    KNOWLEDGE:
                    """ + "\n\n".join(refs)
                    )

        elif stock_related:
            doc = await self.rag.pick_doc(raw_user_text)
            current_doc = doc

            chunks = self.rag.load_chunks(doc)
            ctx = self.rag.build_context(doc, chunks, raw_user_text)

            rules = (ctx.get("rules") or "").strip()
            refs = (ctx.get("refs") or "").strip()
            allowed_apis = extract_api_from_context(refs)

            if rules:
                system_parts.append(
                    "QUY TRÌNH XỬ LÝ BẮT BUỘC:\n" + rules
                )

            if refs:
                system_parts.append(
                    "KHUNG PHÂN TÍCH NỘI BỘ STOCKTRADERS AI:\n" + refs
                )

        system_text = "\n\n".join(system_parts)

        messages: List[Dict[str, Any]] = [
            {
                "role": "system",
                "content": system_text
            }
        ]

        # ======================================
        # HISTORY (SMART INJECTION)
        # ======================================

        for h in history:
            if h["role"] in ("user", "assistant"):
                messages.append({
                    "role": h["role"],
                    "content": h["content"]
                })

        # Current user message
        messages.append({
            "role": "user",
            "content": raw_user_text
        })

        enable_tools = (query_source == "RULES" and stock_related)
        return messages, sources, enable_tools, allowed_apis, current_doc

    # =====================================================
    # TOOL LOOP
    # =====================================================

    def _run_tool_loop(
            self,
            model: str,
            messages: List[Dict[str, Any]],
            enable_tools: bool,
            allowed_apis: Optional[List[str]] = None,
            current_doc: Optional[str] = None,
        ) -> Tuple[List[Dict[str, Any]], str]:

        if not enable_tools:

            resp = self.oa.chat(
                model=model,
                messages=messages
            )

            final_text = resp.choices[0].message.content or ""

            messages.append({
                "role": "assistant",
                "content": final_text
            })

            return messages, final_text

        tools = self.registry.tools

        if allowed_apis:

            tools = [
                t for t in tools
                if t["function"]["name"] in allowed_apis
            ]
        loops = 0

        while loops < MAX_TOOL_LOOPS:

            loops += 1

            log("\n================ TOOL LOOP =================")
            log("LOOP:", loops)

            resp = self.oa.chat(
                model=model,
                messages=messages,
                tools=tools,
                tool_choice="auto"
            )

            msg = resp.choices[0].message

            assistant_msg = {
                "role": "assistant",
                "content": msg.content or ""
            }

            # Nếu GPT gọi tool
            if getattr(msg, "tool_calls", None):

                assistant_msg["tool_calls"] = []

                for tc in msg.tool_calls:

                    assistant_msg["tool_calls"].append({
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    })

            messages.append(assistant_msg)

            # Nếu không có tool call → kết thúc
            if not getattr(msg, "tool_calls", None):

                final_text = msg.content or ""
                return messages, final_text

            # Chạy tool
            for tc in msg.tool_calls:

                op_name = tc.function.name

                log("🔧 TOOL CALL:", op_name)
                log("ARGS:", tc.function.arguments)

                try:
                    args = json.loads(tc.function.arguments or "{}")
                except Exception:
                    args = {}

                result = self.executor.call(op_name, args, doc_name=current_doc)

                log("API RESULT TYPE:", type(result))

                if isinstance(result, list):
                    log("API RESULT SIZE:", len(result))

                if op_name == "getAnalyzeWave":
                    if isinstance(result, dict) and "message" in result:
                        return messages, result["message"]
    
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, ensure_ascii=False)
                })

        final_text = "Tool loop vượt quá giới hạn."

        return messages, final_text

    # =====================================================
    # STREAM
    # =====================================================

    async def _find_waitbuy_target(self):
        targets = await self.memory.list_sales_discovery_targets(
            active_only=True,
            confirmed_only=True,
        )
        for target in targets:
            haystack = " ".join([
                str(target.get("target_key") or ""),
                str(target.get("name") or ""),
                str(target.get("description") or ""),
                str(target.get("suggested_question") or ""),
            ])
            normalized = normalize_search_text(haystack)
            if "cho mua" in normalized and any(
                keyword in normalized
                for keyword in ("thuyet minh", "giai thich", "waitbuy")
            ):
                return target
        return None

    async def _answer_waitbuy_explanation(self, user_text: str, model: str) -> str:
        target = await self._find_waitbuy_target()
        period = extract_requested_signal_period(user_text)
        year = str(period.get("date") or period.get("year") or datetime.now().year)[:4]

        raw_total_trade = self.executor.call(
            "getTotalTrade",
            {"ticker": "VNINDEX", "date": year},
        )
        raw_wave = self.executor.call("getStockWave", {"date": year})
        scan = scan_vnindex_waitbuy_reversal(
            extract_rows(raw_total_trade, ("totalTradeDatas", "tradeDatas", "records", "items")),
            extract_rows(raw_wave, ("waveDatas", "stockWaveDatas", "items")),
        )
        latest = scan.get("latest")

        if not latest:
            return f"Năm {year} chưa có phiên nào thỏa điều kiện chờ mua tăng mạnh sau phiên VNINDEX giảm."

        fallback = (
            f"Phiên {format_vn_date(latest['date'])} đáng chú ý: VNINDEX giảm "
            f"{abs(latest['close_change']):g} điểm so với phiên trước, trong khi chờ mua tăng từ "
            f"{latest['prev_waitbuy']:g} lên {latest['waitbuy']:g} mã "
            f"(+{latest['waitbuy_change']:g})."
        )
        target_prompt = (
            (target or {}).get("suggested_question")
            or (target or {}).get("description")
            or "Sau các phiên giảm mạnh thì chờ mua dễ tăng cao, như các phiên lấy ví dụ ra"
        )
        required_data = {
            "date": format_vn_date(latest.get("date")),
            "prev_date": format_vn_date(latest.get("prev_date")),
            "vnindex_down_points": abs(latest.get("close_change") or 0),
            "prev_waitbuy": latest.get("prev_waitbuy"),
            "waitbuy": latest.get("waitbuy"),
            "waitbuy_change": latest.get("waitbuy_change"),
        }
        prompt = f"""
Bạn là chatbot StockTraders AI đang nói chuyện với khách.

Prompt gợi ý của admin:
{target_prompt}

Số liệu bắt buộc dùng:
{json.dumps(required_data, ensure_ascii=False, indent=2)}

Yêu cầu:
- Viết 1 câu tự nhiên, ngắn gọn cho khách.
- Phải bám theo prompt gợi ý của admin để diễn giải ý nghĩa.
- Chỉ dùng số liệu bắt buộc ở trên, không bịa thêm.
- Không nhắc API, không nói "dữ liệu lấy từ", không giải thích định nghĩa nguyên lý.
- Không khuyến nghị mua/bán, không khẳng định thị trường chắc chắn tăng.
- Nếu cần diễn giải, chỉ nói nhẹ kiểu lực quan tâm/chờ mua quay lại sau phiên giảm.
""".strip()

        try:
            resp = self.oa.chat(
                model=model,
                messages=[
                    {"role": "system", "content": "Chỉ trả lời tiếng Việt, 1 câu ngắn, tự nhiên, không markdown."},
                    {"role": "user", "content": prompt},
                ],
                tools=None,
                tool_choice="auto",
            )
            text = (resp.choices[0].message.content or "").strip()
            return text or fallback
        except Exception as exc:
            print("WAITBUY_EXPLANATION_ERROR:", exc)
            return fallback
    async def chat_stream(
        self,
        user_id: str,
        user_text: str,
        language: str,
        selected_model: Optional[str]
    ):
        lock = self._user_chat_locks.setdefault(user_id, asyncio.Lock())
        async with lock:
            async for event, data in self._chat_stream_unlocked(
                user_id=user_id,
                user_text=user_text,
                language=language,
                selected_model=selected_model,
            ):
                yield event, data

    async def _chat_stream_unlocked(
        self,
        user_id: str,
        user_text: str,
        language: str,
        selected_model: Optional[str]
    ):
        model = pick_model(selected_model)
        await self.memory.add(user_id, "user", user_text)

        guide_result = await self.question_guide.handle(user_id, user_text)
        if guide_result.action == "ask":
            final_text = clean_chat_output(guide_result.message)
            full = ""
            for i in range(0, len(final_text), STREAM_CHUNK_CHARS):
                chunk = final_text[i:i + STREAM_CHUNK_CHARS]
                if chunk:
                    full += chunk
                    yield ("delta", {"text": chunk})
            await self.memory.add(user_id, "assistant", full)
            yield ("done", {"sources": []})
            return

        guided_question = False
        if guide_result.action == "run" and guide_result.canonical_question:
            user_text = guide_result.canonical_question
            guided_question = True

        if not guided_question and is_waitbuy_explain_query(user_text):
            final_text = await self._answer_waitbuy_explanation(user_text=user_text, model=model)
            final_text = clean_chat_output(final_text)
            full = ""
            for i in range(0, len(final_text), STREAM_CHUNK_CHARS):
                chunk = final_text[i:i + STREAM_CHUNK_CHARS]
                if chunk:
                    full += chunk
                    yield ("delta", {"text": chunk})
            await self.memory.add(user_id, "assistant", full)
            yield ("done", {"sources": []})
            return

        base_messages, sources, enable_tools, allowed_apis, current_doc = await self.build_base_messages(
            user_id,
            user_text,
            language,
        )
        _, final_text = self._run_tool_loop(
            model,
            base_messages,
            enable_tools=enable_tools,
            allowed_apis=allowed_apis,
            current_doc=current_doc,
        )
        final_text = enforce_main_branch_terms(final_text)
        final_text = ensure_smdt_percent(final_text)
        final_text = clean_chat_output(final_text)

        full = ""
        for i in range(0, len(final_text), STREAM_CHUNK_CHARS):
            chunk = final_text[i:i + STREAM_CHUNK_CHARS]
            if chunk:
                full += chunk
                yield ("delta", {"text": chunk})

        await self.memory.add(user_id, "assistant", full)
        yield ("done", {"sources": sources})
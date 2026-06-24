import os
import re
from pathlib import Path
from typing import List, Dict, Any

from settings import RULES_DIR, BOOKS_DIR
from services.openai_client import OpenAIClient
import unicodedata
# =============================
# DEBUG SWITCH
# =============================

DEBUG_RAG = True


def debug(*args):
    if DEBUG_RAG:
        print(*args)


SEARCH_STOPWORDS = {
    "a",
    "anh",
    "bao",
    "cac",
    "cai",
    "cho",
    "cua",
    "co",
    "duoc",
    "em",
    "hoi",
    "la",
    "luc",
    "mot",
    "nao",
    "nay",
    "nhung",
    "toi",
    "trong",
    "vao",
    "ve",
}


def search_tokens(text: str) -> List[str]:
    normalized = unicodedata.normalize("NFD", text or "")
    normalized = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
    normalized = re.sub(r"\s+", " ", normalized.lower()).strip()
    tokens = re.findall(r"[a-z0-9]+", normalized)
    return [token for token in tokens if token not in SEARCH_STOPWORDS and len(token) > 1]


def longest_common_token_run(left: List[str], right: List[str]) -> int:
    if not left or not right:
        return 0

    best = 0
    prev = [0] * (len(right) + 1)

    for left_token in left:
        curr = [0] * (len(right) + 1)
        for idx, right_token in enumerate(right, start=1):
            if left_token == right_token:
                curr[idx] = prev[idx - 1] + 1
                best = max(best, curr[idx])
        prev = curr

    return best


def chunk_heading(chunk: str) -> str:
    lines = [line.strip() for line in (chunk or "").splitlines() if line.strip()]
    if not lines:
        return ""

    first = lines[0]
    if first.lower().startswith("guide") and len(lines) > 1:
        return f"{first} {lines[1]}"

    return first

# =============================
# RAG STORE
# =============================

class RAGStore:

    def __init__(self):
        self.openai = OpenAIClient()
        self.rule_docs: Dict[str, Dict[str, Any]] = {}
        self.book_docs: Dict[str, Dict[str, Any]] = {}
    
    def _normalize_text(self, text: str) -> str:
        if not text:
            return ""

        text = text.lower().strip()
        text = unicodedata.normalize("NFD", text)
        text = "".join(c for c in text if unicodedata.category(c) != "Mn")
        text = re.sub(r"\s+", " ", text)
        return text
    # =============================
    # LOAD DOCS
    # =============================

    def load(self):

        debug("\n=========== RAG LOAD START ===========")

        # reset stores
        self.rule_docs = {}
        self.book_docs = {}

        # =============================
        # LOAD RULES
        # =============================

        debug("\n=========== LOAD RULES ===========")
        debug("RULES_DIR PATH:", RULES_DIR)

        rule_files = []

        if RULES_DIR.exists():

            for fn in os.listdir(RULES_DIR):
                p = Path(RULES_DIR) / fn

                if p.is_file() and p.suffix.lower() in [".pdf", ".docx", ".txt"]:
                    rule_files.append(p)

        debug("📚 RULE FILES FOUND:", [f.name for f in rule_files])

        for p in rule_files:

            debug("\n--- LOADING RULE DOC:", p.name)

            text = self._read_doc(p)

            chunks = self._extract_rule_chunks(text)

            debug("RULE CHUNKS:", len(chunks))

            self.rule_docs[p.name] = {
                "title": p.name,
                "type": "rule",
                "text": text,
                "chunks": chunks,
                "title_norm": self._normalize_text(p.stem),
            }

        # =============================
        # LOAD BOOKS
        # =============================

        debug("\n=========== LOAD BOOKS ===========")
        debug("BOOKS_DIR PATH:", BOOKS_DIR)

        book_files = []

        if BOOKS_DIR.exists():

            for fn in os.listdir(BOOKS_DIR):
                p = Path(BOOKS_DIR) / fn

                if p.is_file() and p.suffix.lower() in [".pdf", ".docx", ".txt"]:
                    book_files.append(p)

        debug("📚 BOOK FILES FOUND:", [f.name for f in book_files])

        for p in book_files:

            debug("\n--- LOADING BOOK DOC:", p.name)

            text = self._read_doc(p)

            chunks = self._extract_book_chunks(text)

            debug("BOOK CHUNKS:", len(chunks))

            self.book_docs[p.name] = {
                "title": p.name,
                "type": "book",
                "text": text,
                "chunks": chunks,
                "title_norm": self._normalize_text(p.stem),
            }

        debug("\n=========== RAG LOAD COMPLETE ===========")
        debug("TOTAL RULE DOCS:", len(self.rule_docs))
        debug("TOTAL BOOK DOCS:", len(self.book_docs))

    # =============================
    # READ FILE
    # =============================

    def _read_doc(self, path: Path) -> str:

        ext = path.suffix.lower()

        if ext == ".pdf":
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            pages = []

            for page in reader.pages:
                pages.append(page.extract_text() or "")

            text = "\n".join(pages)

        elif ext == ".docx":
            import docx

            d = docx.Document(str(path))

            paragraphs = []
            for p in d.paragraphs:
                if p.text:
                    paragraphs.append(p.text)

            text = "\n".join(paragraphs)

        elif ext == ".txt":
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()

        else:
            raise ValueError(f"Unsupported file type: {path}")

        debug("DOC LENGTH:", len(text))

        return text

    # =============================
    # SPLIT GUIDE CHUNKS
    # =============================

    def _extract_rule_chunks(self, text: str) -> List[str]:

        debug("SPLITTING GUIDE CHUNKS")

        parts = re.split(r"\bGuide\b", text, flags=re.IGNORECASE)

        chunks = []

        for p in parts:

            p = p.strip()

            if len(p) < 40:
                continue

            chunk = "Guide " + p

            chunks.append(chunk)

        debug("CHUNKS CREATED:", len(chunks))

        return chunks
    
    def _extract_book_chunks(self, text: str) -> List[str]:
        text = text.replace("\r", "\n")

        lines = [ln.strip() for ln in text.split("\n")]
        lines = [ln for ln in lines if ln]

        chunks: List[str] = []
        buffer: List[str] = []

        def flush():
            nonlocal buffer
            if buffer:
                chunk = " ".join(buffer).strip()
                if len(chunk) >= 60:
                    chunks.append(chunk)
                buffer = []

        for ln in lines:
            is_heading = (
                len(ln) <= 80
                and (
                    ln.isupper()
                    or re.match(r"^\d+[\.\)]", ln)
                    or ln.startswith("•")
                    or ln.startswith("-")
                )
            )

            if is_heading and buffer:
                flush()

            buffer.append(ln)

            joined = " ".join(buffer)
            if len(joined) >= 500:
                flush()

        flush()

        if not chunks and text.strip():
            chunks = [text.strip()]

        return chunks

    def _score_book_chunk(self, query: str, doc_title: str, chunk: str) -> int:
        q = self._normalize_text(query)
        t = self._normalize_text(chunk)
        title = self._normalize_text(doc_title)

        q_tokens = set(re.findall(r"[a-zA-Z0-9]+", q))
        t_tokens = set(re.findall(r"[a-zA-Z0-9]+", t))
        title_tokens = set(re.findall(r"[a-zA-Z0-9]+", title))

        overlap = q_tokens & t_tokens
        title_overlap = q_tokens & title_tokens

        score = 0
        score += len(overlap) * 2
        score += len(title_overlap) * 5

        # bonus exact phrase ngắn
        for n in [5, 4, 3, 2]:
            words = q.split()
            if len(words) >= n:
                for i in range(len(words) - n + 1):
                    phrase = " ".join(words[i:i+n])
                    if phrase in t:
                        score += n * 4
                    if phrase in title:
                        score += n * 6

        # bonus theo chủ đề đặc trưng
        special_phrases = [
            "chan song",
            "song cuoi thang",
            "ma manh",
            "smdt",
            "day",
            "downtrend",
            "gia von",
            "cho ban",
            "lap dinh",
        ]
        for sp in special_phrases:
            if sp in q and sp in t:
                score += 8

        return score
    
    def retrieve_best_book(self, query: str, top_k: int = 3):
        if not self.book_docs:
            return {
                "doc_name": None,
                "chunks": [],
                "score": 0
            }

        scored = []

        for doc_name, meta in self.book_docs.items():
            for ch in meta["chunks"]:
                score = self._score_book_chunk(query, doc_name, ch)
                scored.append((score, doc_name, ch))

        scored.sort(key=lambda x: x[0], reverse=True)

        best = scored[:top_k]

        if not best:
            return {
                "doc_name": None,
                "chunks": [],
                "score": 0
            }

        best_doc = best[0][1]
        best_chunks = [x[2] for x in best]
        best_score = best[0][0]

        return {
            "doc_name": best_doc,
            "chunks": best_chunks,
            "score": best_score
        }
    # =============================
    # GET TITLES
    # =============================

    def get_titles(self) -> List[str]:

        titles = list(self.rule_docs.keys())

        debug("RULE DOC TITLES:", titles)

        return titles

    # =============================
    # AI PICK DOC
    # =============================

    async def pick_doc(self, query: str):

        debug("USER QUERY:", query)

        titles = self.get_titles()
        debug("AVAILABLE DOCS:", titles)

        titles_text = "\n".join(titles)

        prompt = f"""
    Bạn là hệ thống chọn tài liệu cho chatbot chứng khoán.

    Câu hỏi:
    {query}

    Danh sách tài liệu:
    {titles_text}

    QUY TẮC:
    - Chỉ chọn đúng 1 tài liệu phù hợp nhất.
    - Trả về đúng tên file trong danh sách.
    - Không giải thích.
    """

        resp = self.openai.chat(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "Chỉ trả về đúng tên file trong danh sách."
                },
                {"role": "user", "content": prompt}
            ]
        )

        raw = (resp.choices[0].message.content or "").strip()

        debug("AI RAW:", raw)

        # match doc
        for title in titles:
            if title.lower() in raw.lower():
                debug("DOC SELECTED:", title)
                return title

        debug("⚠️ AI PICKED INVALID DOC:", raw)

        # fallback: chọn doc đầu tiên
        return titles[0] if titles else None

    # =============================
    # LOAD CHUNKS
    # =============================

    def load_chunks(self, doc_name: str) -> List[str]:

        doc = self.rule_docs.get(doc_name)

        if not doc:

            debug("❌ DOC NOT FOUND")

            return []

        chunks = doc["chunks"]

        return chunks

    # =============================
    # BUILD CONTEXT
    # =============================

    def build_context(self, doc_name: str, chunks: List[str], query: str, max_chunks: int = 3):

        if not chunks:

            debug("⚠️ NO CHUNKS")

            return {
                "rules": "",
                "refs": ""
            }

        query_l = self._normalize_text(query)
        q_tokens = set(search_tokens(query))
        q_token_list = search_tokens(query)
        asks_single_day = (
            "hom nay" in query_l
            or "ngay" in query_l
            or bool(re.search(r"\b20\d{2}-\d{2}-\d{2}\b", query_l))
        )
        asks_month_range = (
            "tu thang" in query_l
            or "den nay" in query_l
            or bool(re.search(r"\b20\d{2}-\d{2}\b", query_l))
        )
        asks_core_branches = (
            "nganh chu luc" in query_l
            or "cac nganh chu luc" in query_l
            or "dong chu luc" in query_l
        )
        asks_branch_tickers = any(
            phrase in query_l
            for phrase in (
                "cac ma dong",
                "cac ma nganh",
                "ma dong",
                "ma nganh",
                "cac ma trong dong",
                "cac ma trong nganh",
            )
        )

        scored = []

        for ch in chunks:

            text = self._normalize_text(ch)
            heading = chunk_heading(ch)
            heading_tokens = set(search_tokens(heading))
            heading_token_list = search_tokens(heading)
            body_tokens = set(search_tokens(ch))
            score = 0
            heading_score = 0

            # =============================
            # TOKEN OVERLAP (core similarity)
            # =============================

            heading_overlap = q_tokens & heading_tokens
            body_overlap = q_tokens & body_tokens
            heading_run = longest_common_token_run(q_token_list, heading_token_list)

            heading_score += len(heading_overlap) * 8
            heading_score += heading_run * heading_run * 3
            score += heading_score
            score += len(body_overlap) * 2

            # =============================
            # SEMANTIC BOOST
            # =============================

            if "sức mạnh dòng tiền" in query_l and "sức mạnh dòng tiền" in text:
                score += 12

            if "dòng tiền" in query_l and "dòng tiền" in text:
                score += 6

            if "ngành" in query_l and "ngành" in text:
                score += 4

            if "sóng" in query_l and "sóng" in text:
                score += 4

            if asks_core_branches:
                if "nganh chu luc" in text or "cac nganh chu luc" in text:
                    score += 200
                    heading_score += 50
                if (
                    "cac ma dong" in text
                    or "cac ma nganh" in text
                    or "ma dong" in text
                    or "ma nganh" in text
                    or "getbranchpath" in text
                    or "getsmdtticker" in text
                ):
                    score -= 160

            if asks_branch_tickers:
                if (
                    "cac ma dong" in text
                    or "cac ma nganh" in text
                    or "ma dong" in text
                    or "ma nganh" in text
                ):
                    score += 160
                    heading_score += 40
                if "nganh chu luc" in text or "cac nganh chu luc" in text:
                    score -= 160

            # =============================
            # DATE / MONTH / YEAR MATCH
            # =============================

            if re.search(r"\d{4}", query_l) and re.search(r"\d{4}", text):
                score += 3

            if "-" in query_l and "mm/yyyy" in text:
                score += 6

            if "-" in query_l and "yyyy-mm" in text:
                score += 6

            # =============================
            # API INSTRUCTION BOOST
            # =============================

            if "gọi api" in text or "api" in text:
                score += 2

            if asks_single_day and not asks_month_range:
                if "tu thang" in text or "den nay" in text or "from_date" in text:
                    score -= 80
                if "cua ngay" in text or "[ngay]" in text:
                    score += 40

            scored.append((score, heading_score, ch))

        # =============================
        # SORT BY SCORE
        # =============================

        scored.sort(reverse=True, key=lambda x: x[0])

        selected_scored = scored[:max_chunks]

        if scored:
            top_score, top_heading_score, _ = scored[0]
            second_score = scored[1][0] if len(scored) > 1 else 0

            if top_heading_score >= 18 and top_score >= second_score * 1.25:
                selected_scored = [scored[0]]

        selected = [c for _, _, c in selected_scored]

        debug("SELECTED CHUNKS:", len(selected))

        for i, ch in enumerate(selected):

            debug(f"\n--- CHUNK {i+1} ---")
            debug(ch[:500])

        # =============================
        # BUILD CONTEXT
        # =============================

        refs = []

        for i, ch in enumerate(selected):

            block = f"[{i+1}] {ch}"

            refs.append(block)

        debug("CONTEXT BUILT")

        return {
            "doc_name": doc_name,
            "rules": "",
            "refs": "\n\n".join(refs)
        }


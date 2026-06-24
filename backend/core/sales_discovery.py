import json
import re
import unicodedata
from datetime import datetime
from typing import Any, Dict, List

from services.openai_client import OpenAIClient
from settings import CLASSIFIER_MODEL


TARGET_DEFINITIONS = {
    "investment_experience": {
        "label": "Thâm niên đầu tư",
        "complete_when": "Biết khách mới tham gia, đầu tư được bao lâu, hoặc đã trải qua vài nhịp thị trường chưa.",
    },
    "nav": {
        "label": "NAV / quy mô vốn",
        "complete_when": "Biết khoảng vốn khách thường dùng cho chứng khoán, có thể là con số cụ thể hoặc khoảng tương đối.",
    },
    "portfolio_cost": {
        "label": "Danh mục hiện tại và giá vốn",
        "complete_when": "Biết các mã chính khách đang nắm và giá vốn nếu khách cung cấp được.",
    },
    "decision_basis": {
        "label": "Cơ sở ra quyết định đầu tư",
        "complete_when": "Biết khách thường mua bán dựa vào broker, tin tức, tự phân tích, bảng giá, dòng tiền, app, hay cảm tính.",
    },
}

TARGET_ORDER = [
    "investment_experience",
    "nav",
    "portfolio_cost",
    "decision_basis",
]

OPENING_MESSAGE = (
    "Em chào anh/chị. Giai đoạn này nhiều nhà đầu tư đang khó ở chỗ thị trường rung lắc "
    "nhưng dòng tiền lại luân chuyển rất nhanh giữa các ngành. Để em tư vấn đúng hơn, "
    "anh/chị tham gia thị trường chứng khoán được bao lâu rồi ạ?"
)


def default_targets() -> Dict[str, Dict[str, Any]]:
    return {
        key: {
            "label": TARGET_DEFINITIONS[key]["label"],
            "status": "missing",
            "value": None,
        }
        for key in TARGET_ORDER
    }


def fallback_target_configs() -> List[Dict[str, Any]]:
    return [
        {
            "target_key": key,
            "name": TARGET_DEFINITIONS[key]["label"],
            "description": TARGET_DEFINITIONS[key]["complete_when"],
            "suggested_question": "",
            "recognizer_key": key,
            "status": "confirmed",
            "active": 1,
            "sort_order": index * 10,
        }
        for index, key in enumerate(TARGET_ORDER, start=1)
    ]


def target_definitions_from_configs(configs: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {
        config["target_key"]: {
            "label": config.get("name") or config["target_key"],
            "complete_when": config.get("description") or "",
            "suggested_question": config.get("suggested_question") or "",
            "recognizer_key": config.get("recognizer_key") or "",
        }
        for config in configs
    }


def target_order_from_configs(configs: List[Dict[str, Any]]) -> List[str]:
    return [config["target_key"] for config in configs]


def is_explainer_target(config: Dict[str, Any]) -> bool:
    haystack = " ".join([
        str(config.get("target_key") or ""),
        str(config.get("name") or ""),
        str(config.get("description") or ""),
        str(config.get("suggested_question") or ""),
        str(config.get("recognizer_key") or ""),
    ])
    text = normalize_search_text(haystack)

    return any(
        keyword in text
        for keyword in [
            "thuyet minh",
            "giai thich",
            "nguyen ly",
            "so lieu",
            "vi du",
        ]
    )


def default_targets_from_configs(configs: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {
        config["target_key"]: {
            "label": config.get("name") or config["target_key"],
            "status": "missing",
            "value": None,
        }
        for config in configs
    }


def normalize_targets_for_configs(
    targets: Dict[str, Dict[str, Any]],
    configs: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    normalized = {}

    for config in configs:
        key = config["target_key"]
        current = targets.get(key) or {}
        normalized[key] = {
            "label": config.get("name") or current.get("label") or key,
            "status": current.get("status") or "missing",
            "value": current.get("value"),
        }

    return normalized


def targets_equal(left: Dict[str, Dict[str, Any]], right: Dict[str, Dict[str, Any]]) -> bool:
    return json.dumps(left, ensure_ascii=False, sort_keys=True) == json.dumps(
        right,
        ensure_ascii=False,
        sort_keys=True,
    )


def safe_json_loads(text: str) -> Dict[str, Any]:
    raw = (text or "").strip()

    if raw.startswith("```"):
        raw = raw.strip("`").strip()
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()

    start = raw.find("{")
    end = raw.rfind("}")

    if start != -1 and end != -1 and end > start:
        raw = raw[start : end + 1]

    return json.loads(raw)


def all_targets_complete(targets: Dict[str, Dict[str, Any]], target_order: List[str] | None = None) -> bool:
    order = target_order or TARGET_ORDER
    return all(targets.get(key, {}).get("status") == "complete" for key in order)


def normalize_search_text(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text or "")
    normalized = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
    normalized = normalized.lower()
    return re.sub(r"\s+", " ", normalized).strip()


def remove_formulaic_opening(text: str) -> str:
    cleaned = (text or "").strip()
    lowered = normalize_search_text(cleaned)
    blocked = (
        "cam on",
        "em ghi nhan",
        "da ghi nhan",
        "vang em ghi nhan",
        "vang, em ghi nhan",
    )

    if not lowered.startswith(blocked):
        return cleaned

    for separator in [". ", "! ", "? ", "\n"]:
        if separator in cleaned:
            return cleaned.split(separator, 1)[1].strip()

    return cleaned


def is_short_number_answer(text: str) -> bool:
    return bool(re.fullmatch(r"\s*\d+(?:[,.]\d+)?\s*", text or ""))


IGNORED_TICKER_WORDS = {
    "anh",
    "chi",
    "toi",
    "minh",
    "dang",
    "giu",
    "cam",
    "nam",
    "gia",
    "von",
    "ma",
    "hien",
    "tai",
    "khoang",
    "trieu",
    "ty",
    "tri",
    "va",
    "voi",
    "co",
    "phieu",
}


def extract_user_tickers(text: str) -> List[str]:
    tickers = []
    for raw in re.findall(r"\b[A-Za-z]{2,5}\b", text or ""):
        normalized = normalize_search_text(raw)
        if normalized in IGNORED_TICKER_WORDS:
            continue
        ticker = raw.upper()
        if ticker not in tickers:
            tickers.append(ticker)

    return tickers


def is_collection_related(user_text: str, targets: Dict[str, Dict[str, Any]]) -> bool:
    text = (user_text or "").strip()
    text_l = normalize_search_text(text)

    if not text:
        return False

    portfolio = targets.get("portfolio_cost") or {}
    if portfolio.get("status") == "partial" and is_short_number_answer(text):
        return True

    collection_keywords = [
        "tôi đầu tư",
        "toi dau tu",
        "tham gia",
        "kinh nghiem",
        "nav",
        "von",
        "trieu",
        "ty",
        "dang cam",
        "dang giu",
        "giu",
        "nam",
        "gia von",
        "broker",
        "moi gioi",
        "tu phan tich",
        "phan tich ky thuat",
        "ky thuat",
        "phan tich co ban",
        "co ban",
        "bang gia",
        "tin tuc",
        "cam tinh",
    ]
    normal_question_keywords = [
        "cho tôi",
        "cho toi",
        "phan tich",
        "gia ",
        "smdt",
        "tin hieu",
        "dong tien",
        "nganh",
        "ma nao",
        "co nen",
        "mua",
        "ban",
        "ssi",
        "vnindex",
    ]

    has_collection_signal = any(k in text_l for k in collection_keywords)
    has_decision_basis_answer = any(
        k in text_l for k in ["phan tich", "ky thuat", "co ban", "chart", "tin tuc", "broker", "cam tinh"]
    )
    has_normal_question_signal = any(k in text_l for k in normal_question_keywords)
    has_question_mark = "?" in text or text_l.startswith(("sao", "vi sao", "lam sao"))
    has_duration_answer = bool(re.search(r"\b(\d+(?:[,.]\d+)?)\s*(nam|thang)\b", text_l))
    has_vague_experience_answer = any(k in text_l for k in ["mot thoi gian", "cung lau"])
    has_inline_ticker_cost = bool(
        re.search(r"\b[a-z]{2,5}\s*(?:\(|gia|gia von)?\s*\d+(?:[,.]\d+)?\b", text_l)
    )

    # Ticker-only questions like "cho tôi giá SSI" should go to the normal StockTraders flow.
    if has_normal_question_signal and not has_collection_signal:
        return False

    # If the current target is portfolio, ticker lists can be collection answers.
    tickers = extract_user_tickers(text)
    if (tickers or has_inline_ticker_cost) and not has_normal_question_signal:
        return True

    if has_duration_answer or has_vague_experience_answer:
        return True

    if has_collection_signal or has_decision_basis_answer:
        return True

    # Very short acknowledgements are not useful for discovery; let normal chat handle them.
    if len(text_l.split()) <= 3 and not has_question_mark:
        return False

    return False


def merge_obvious_user_facts(
    targets: Dict[str, Dict[str, Any]],
    user_text: str,
) -> Dict[str, Dict[str, Any]]:
    updated = json.loads(json.dumps(targets, ensure_ascii=False))
    text = (user_text or "").strip()
    text_l = normalize_search_text(text)

    if "investment_experience" in updated and updated["investment_experience"]["status"] != "complete":
        exp_match = re.search(r"\b(\d+(?:[,.]\d+)?)\s*(nam|thang)\b", text_l)
        if exp_match or any(k in text_l for k in ["moi tham gia", "lau nam", "mot thoi gian"]):
            updated["investment_experience"]["status"] = "complete"
            updated["investment_experience"]["value"] = text

    if "nav" in updated and updated["nav"]["status"] != "complete":
        nav_match = re.search(
            r"\b(\d+(?:[,.]\d+)?)\s*(trieu|tr|ty|ti)\b",
            text_l,
        )
        if nav_match or "nav" in text_l:
            updated["nav"]["status"] = "complete"
            updated["nav"]["value"] = text

    if "portfolio_cost" in updated and updated["portfolio_cost"]["status"] != "complete":
        current_portfolio = updated["portfolio_cost"]
        if current_portfolio.get("status") == "partial" and is_short_number_answer(text):
            current_value = (current_portfolio.get("value") or "").strip()
            updated["portfolio_cost"]["status"] = "complete"
            updated["portfolio_cost"]["value"] = (
                f"{current_value} giá vốn {text}"
                if current_value
                else f"Giá vốn {text}"
            )
            return updated

        tickers = extract_user_tickers(text)
        ticker_cost_pairs = re.findall(
            r"\b([a-z]{2,5})\s*(?:\(|gia|gia von)?\s*(\d+(?:[,.]\d+)?)\b",
            text_l,
        )
        has_inline_ticker_cost = any(
            ticker not in IGNORED_TICKER_WORDS
            for ticker, _ in ticker_cost_pairs
        )
        mentions_holding = any(
            k in text_l
            for k in [
                "đang cầm",
                "dang cam",
                "dang giu",
                "giu",
                "nam",
                "cam",
            ]
        )
        mentions_cost = any(k in text_l for k in ["gia", "gia von"])
        has_parenthesized_cost = bool(re.search(r"\b[A-Za-z]{2,5}\s*\(\s*\d+(?:[,.]\d+)?\s*\)", text))
        if tickers or has_inline_ticker_cost:
            updated["portfolio_cost"]["status"] = "complete" if (mentions_cost or has_parenthesized_cost or mentions_holding or has_inline_ticker_cost) else "partial"
            updated["portfolio_cost"]["value"] = ", ".join(tickers) if tickers and text_l in [ticker.lower() for ticker in tickers] else text

    if "decision_basis" in updated and updated["decision_basis"]["status"] != "complete":
        basis_keywords = [
            "broker",
            "moi gioi",
            "tin tuc",
            "tu phan tich",
            "phan tich",
            "bang gia",
            "dong tien",
            "phan tich ky thuat",
            "ky thuat",
            "phan tich co ban",
            "co ban",
            "chart",
            "bieu do",
            "nen tang doanh nghiep",
            "bao cao tai chinh",
            "tin hieu",
            "khuyen nghi",
            "room",
            "tu van",
            "tu quyet",
            "kinh nghiem",
            "app",
            "cam tinh",
        ]
        if any(k in text_l for k in basis_keywords):
            updated["decision_basis"]["status"] = "complete"
            updated["decision_basis"]["value"] = text

    return updated


class SalesDiscovery:
    def __init__(self, memory, model: str | None = None):
        self.memory = memory
        self.oa = OpenAIClient()
        self.model = model or CLASSIFIER_MODEL

    async def active_target_configs(self) -> List[Dict[str, Any]]:
        configs = await self.memory.list_sales_discovery_targets(
            active_only=True,
            confirmed_only=True,
        )

        return configs or fallback_target_configs()

    def customer_pronoun(self, targets: Dict[str, Dict[str, Any]]) -> str:
        profile_text = targets.get("investment_experience", {}).get("value") or ""
        profile_text_l = normalize_search_text(profile_text)

        if (
            "nu" in profile_text_l
            or "nữ" in profile_text_l
            or "gender=nu" in profile_text_l
            or "gender=nữ" in profile_text_l
        ):
            return "chị"

        if "nam" in profile_text_l or "gender=nam" in profile_text_l:
            return "anh"

        return "anh/chị"

    def apply_customer_pronoun(self, text: str, targets: Dict[str, Dict[str, Any]]) -> str:
        customer = self.customer_pronoun(targets)
        if customer == "anh/chị":
            return text

        return (
            text.replace("anh/chị", customer)
            .replace("Anh/chị", customer.capitalize())
            .replace("anh / chị", customer)
            .replace("Anh / chị", customer.capitalize())
        )

    def investment_experience_level(self, targets: Dict[str, Dict[str, Any]]) -> str:
        profile_text = targets.get("investment_experience", {}).get("value") or ""
        profile_text_l = normalize_search_text(profile_text)

        if "moi tham gia" in profile_text_l:
            return "new"
        if "1-3" in profile_text_l or "1 den 3" in profile_text_l:
            return "mid"
        if "tren 3" in profile_text_l or "hon 3" in profile_text_l:
            return "experienced"

        return "unknown"

    def experience_tone_instruction(self, targets: Dict[str, Dict[str, Any]]) -> str:
        level = self.investment_experience_level(targets)

        if level == "new":
            return "Khách mới tham gia: nói chậm, dễ hiểu, tránh thuật ngữ nặng, ưu tiên hỏi để kiểm soát rủi ro."
        if level == "mid":
            return "Khách có 1-3 năm kinh nghiệm: công nhận đã có trải nghiệm, hỏi sâu hơn về thói quen, kỷ luật và cách phân bổ vốn."
        if level == "experienced":
            return "Khách trên 3 năm kinh nghiệm: nói chuyên nghiệp hơn, đi thẳng vào cấu trúc danh mục, chiến lược và hệ tiêu chí ra quyết định."

        return "Chưa rõ thâm niên: giữ giọng trung tính, lịch sự, khai thác từng ý một."

    async def classify_turn_route(self, user_text: str, targets: Dict[str, Dict[str, Any]]) -> str:
        portfolio = targets.get("portfolio_cost") or {}
        if portfolio.get("status") == "partial" and is_short_number_answer(user_text):
            return "collect"
        if portfolio.get("status") != "complete" and extract_user_tickers(user_text):
            text_l = normalize_search_text(user_text)
            if len(text_l.split()) <= 4:
                return "collect"

        configs = await self.active_target_configs()
        target_definitions = target_definitions_from_configs(configs)
        prompt = f"""
Bạn là bộ phân loại routing cho chatbot tư vấn đầu tư.

Nhiệm vụ:
Chọn đúng 1 route:
- collect: nếu câu user đang cung cấp, xác nhận, làm rõ thông tin thuộc các mục cần khai thác.
- normal: nếu câu user là câu hỏi nghiệp vụ/chứng khoán/app cần chatbot StockTraders AI trả lời.

Các mục cần khai thác:
{json.dumps(target_definitions, ensure_ascii=False, indent=2)}

Trạng thái hiện tại:
{json.dumps(targets, ensure_ascii=False, indent=2)}

Quy tắc:
- Nếu user nói "theo phân tích kỹ thuật", "phân tích cơ bản", "xem chart", "nghe broker", "đọc tin tức", "theo dòng tiền", "cảm tính" thì route là collect vì đó là cơ sở ra quyết định đầu tư.
- Nếu user nói "300 triệu", "1 tỷ", "100-150 triệu" thì route là collect vì đó là NAV.
- Nếu user nói "3 năm", "6 tháng", "mới tham gia", "đầu tư lâu rồi" thì route là collect vì đó là thâm niên đầu tư.
- Nếu user nói "đang giữ FPT 92", "cầm CTG giá 40", "VND (21)" thì route là collect vì đó là danh mục/giá vốn.
- Nếu user hỏi "cho tôi giá SSI", "phân tích VND", "SMDT ngành chứng khoán", "có nên mua HPG không" thì route là normal.
- Nếu câu vừa có thông tin cá nhân cần khai thác vừa có câu hỏi, ưu tiên collect.

Câu user:
{user_text}

Chỉ trả JSON hợp lệ:
{{"route":"collect hoặc normal","reason":"ngắn gọn"}}
""".strip()

        try:
            resp = self.oa.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Chỉ trả JSON hợp lệ, không markdown."},
                    {"role": "user", "content": prompt},
                ],
            )
            parsed = safe_json_loads(resp.choices[0].message.content or "")
            route = (parsed.get("route") or "").strip().lower()
            if route in {"collect", "normal"}:
                return route
        except Exception as exc:
            print("SALES_DISCOVERY_ROUTE_ERROR:", exc)

        return "collect" if is_collection_related(user_text, targets) else "normal"

    async def get_or_create_state(self, user_id: str) -> Dict[str, Any]:
        configs = await self.active_target_configs()
        row = await self.memory.get_sales_discovery(user_id)

        if row:
            original_targets = json.loads(row["targets_json"])
            targets = normalize_targets_for_configs(
                original_targets,
                configs,
            )
            if not targets_equal(original_targets, targets):
                await self.memory.upsert_sales_discovery(
                    user_id=user_id,
                    stage=row["stage"],
                    targets_json=json.dumps(targets, ensure_ascii=False),
                    summary_json=row["summary_json"],
                    completed_at=row["completed_at"],
                )
            return {
                "stage": row["stage"],
                "targets": targets,
                "summary": json.loads(row["summary_json"]) if row["summary_json"] else None,
                "target_configs": configs,
            }

        targets = default_targets_from_configs(configs)
        await self.memory.upsert_sales_discovery(
            user_id=user_id,
            stage="collecting",
            targets_json=json.dumps(targets, ensure_ascii=False),
        )

        return {
            "stage": "collecting",
            "targets": targets,
            "summary": None,
            "target_configs": configs,
        }

    def build_messages(
        self,
        user_text: str,
        targets: Dict[str, Dict[str, Any]],
        history: List[Dict[str, str]],
        configs: List[Dict[str, Any]] | None = None,
    ) -> List[Dict[str, str]]:
        configs = configs or fallback_target_configs()
        target_definitions = target_definitions_from_configs(configs)
        target_keys = target_order_from_configs(configs)
        customer = self.customer_pronoun(targets)
        tone_instruction = self.experience_tone_instruction(targets)
        system = f"""
Bạn là nhân viên sales/tư vấn của StockTraders AI.

Nhiệm vụ demo:
- Khai thác đủ {len(target_keys)} nhóm thông tin khách hàng.
- Nói chuyện tự nhiên, không hỏi như biểu mẫu.
- Mỗi lượt chỉ hỏi 1 ý chính.
- Nếu khách trả lời thiếu, hỏi bồi phần thiếu.
- Nếu khách lạc đề, phản hồi rất ngắn rồi kéo về mục tiêu còn thiếu.
- Khi khách vừa cung cấp thông tin hợp lệ, hãy ghi nhận tự nhiên ý đó trước rồi mới hỏi tiếp.
- Không nhảy thẳng sang câu hỏi kế tiếp như form khảo sát.
- Tránh lặp mở đầu công thức như "Cảm ơn", "Em ghi nhận", "Đã ghi nhận" trong assistant_message.
- Khi đủ các nhóm thông tin, dừng hỏi, tóm tắt hồ sơ khách để lưu DB.

Các nhóm thông tin:
{json.dumps(target_definitions, ensure_ascii=False, indent=2)}

Trạng thái hiện tại:
{json.dumps(targets, ensure_ascii=False, indent=2)}

Quy tắc đánh giá:
- status chỉ được là missing, partial, complete.
- Chỉ complete khi thông tin đủ dùng cho nhân viên sales hiểu khách.
- Nếu khách nói nhiều thông tin trong một câu, hãy cập nhật nhiều target cùng lúc.
- summary_for_db chỉ có khi stage là completed.
- Vẫn nói tiếng Việt có dấu với khách trong assistant_message.
- Những key JSON phải giữ nguyên bằng tiếng Anh.
- Xưng hô với khách là "{customer}". Nếu đã có giới tính/năm sinh từ bảng khai báo, không dùng "anh/chị" nữa.
- Điều chỉnh giọng theo thâm niên: {tone_instruction}
- Trường suggested_question trong target là prompt nội bộ để định hướng cách hỏi, không được bê nguyên văn ra assistant_message.
- Khi hỏi target tiếp theo, hãy tự viết câu hỏi phù hợp với ngữ cảnh, giọng điệu và thông tin đã có.

Bạn phải trả về JSON hợp lệ, không markdown, không giải thích ngoài JSON.
Schema:
{{
  "assistant_message": "câu trả lời tự nhiên gửi cho khách",
  "stage": "collecting hoặc completed",
  "current_target": "một key trong danh sách target hoặc null",
  "targets": {{
    "target_key": {{"status": "missing|partial|complete", "value": null hoặc string}}
  }},
  "summary_for_db": null hoặc {{
    "target_key": "string",
    "pain_points": "string hoặc rỗng"
  }}
}}
""".strip()

        messages = [{"role": "system", "content": system}]

        for h in history[-8:]:
            if h["role"] in ("user", "assistant"):
                messages.append({"role": h["role"], "content": h["content"]})

        messages.append({"role": "user", "content": user_text})
        return messages

    def fallback_response(
        self,
        targets: Dict[str, Dict[str, Any]],
        configs: List[Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        configs = configs or fallback_target_configs()
        for key in target_order_from_configs(configs):
            if targets.get(key, {}).get("status") != "complete":
                return {
                    "assistant_message": self.next_collection_question(targets, configs),
                    "stage": "collecting",
                    "current_target": key,
                    "targets": targets,
                    "summary_for_db": None,
                }

        return {
            "assistant_message": f"Em đã nắm được các thông tin chính của {self.customer_pronoun(targets)} rồi.",
            "stage": "completed",
            "current_target": None,
            "targets": targets,
            "summary_for_db": {},
        }

    def next_collection_question(
        self,
        targets: Dict[str, Dict[str, Any]],
        configs: List[Dict[str, Any]] | None = None,
    ) -> str:
        configs = configs or fallback_target_configs()
        customer = self.customer_pronoun(targets)
        level = self.investment_experience_level(targets)
        for config in configs:
            key = config["target_key"]
            if targets.get(key, {}).get("status") != "complete":
                if is_explainer_target(config):
                    return f"{customer.capitalize()} có muốn em thuyết minh thêm phần này không?"

                suggested_question = (config.get("suggested_question") or "").strip()
                if suggested_question:
                    label = config.get("name") or key
                    return f"Em cần nắm thêm thông tin về {label.lower()}, {customer} chia sẻ giúp em được không ạ?"

                if key == "investment_experience":
                    return f"Để em tư vấn đúng hơn, {customer} tham gia thị trường chứng khoán được bao lâu rồi ạ?"
                if key == "nav":
                    if level == "new":
                        return f"Vì {customer} mới tham gia, em muốn nắm quy mô vốn trước để tránh tư vấn quá rủi ro. Hiện {customer} dự định phân bổ khoảng bao nhiêu vốn cho chứng khoán ạ?"
                    if level == "mid":
                        return f"{customer.capitalize()} đã có một thời gian trải nghiệm thị trường rồi, nên em muốn hiểu cách mình đang phân bổ vốn. Hiện {customer} thường dùng khoảng bao nhiêu vốn cho chứng khoán ạ?"
                    if level == "experienced":
                        return f"{customer.capitalize()} đã có kinh nghiệm thị trường rồi, em xin đi thẳng vào quy mô vốn để tư vấn sát hơn. Hiện {customer} đang phân bổ khoảng bao nhiêu vốn cho chứng khoán ạ?"
                    return f"Hiện {customer} thường phân bổ khoảng bao nhiêu vốn cho chứng khoán ạ?"
                if key == "portfolio_cost":
                    if level == "new":
                        return f"Để em hiểu mức độ rủi ro hiện tại, {customer} đang nắm mã nào chưa và giá vốn khoảng bao nhiêu ạ?"
                    if level == "mid":
                        return f"Với danh mục hiện tại, {customer} đang nắm những mã nào và giá vốn khoảng bao nhiêu ạ?"
                    if level == "experienced":
                        return f"Em xin nắm nhanh cấu trúc danh mục hiện tại: {customer} đang giữ những mã chính nào và giá vốn khoảng bao nhiêu ạ?"
                    return f"{customer.capitalize()} đang nắm những mã nào và giá vốn khoảng bao nhiêu ạ?"
                if level == "new":
                    return f"Khi mới tham gia thị trường, nhiều người dễ mua theo cảm xúc. Thường {customer} quyết định mua bán dựa vào đâu là chính ạ?"
                if level == "mid":
                    return f"Với kinh nghiệm hiện tại, thường {customer} quyết định mua bán dựa vào chart, tin tức, broker hay tiêu chí riêng nào là chính ạ?"
                if level == "experienced":
                    return f"Em muốn hiểu hệ tiêu chí của {customer} rõ hơn: thường {customer} ra quyết định mua bán dựa vào phân tích kỹ thuật, cơ bản, dòng tiền hay phương pháp nào là chính ạ?"
                if key == "decision_basis":
                    return f"Thường {customer} quyết định mua bán dựa vào đâu là chính ạ?"

                label = config.get("name") or key
                return f"Em cần nắm thêm thông tin về {label.lower()}, {customer} chia sẻ giúp em được không ạ?"

        return ""

    async def next_collection_question_ai(
        self,
        targets: Dict[str, Dict[str, Any]],
        configs: List[Dict[str, Any]] | None = None,
        user_text: str | None = None,
        history: List[Dict[str, str]] | None = None,
    ) -> str:
        configs = configs or fallback_target_configs()
        customer = self.customer_pronoun(targets)
        level = self.investment_experience_level(targets)

        next_config = None
        for config in configs:
            key = config["target_key"]
            if targets.get(key, {}).get("status") != "complete":
                next_config = config
                break

        if not next_config:
            return ""

        fallback = self.next_collection_question(targets, configs)
        target_mode = "explainer" if is_explainer_target(next_config) else "collection"
        recent_context = []
        for item in (history or [])[-4:]:
            if item.get("role") in {"user", "assistant"}:
                recent_context.append({
                    "role": item.get("role"),
                    "content": item.get("content") or "",
                })
        prompt = f"""
Bạn là nhân viên tư vấn của StockTraders AI.

Nhiệm vụ:
- Viết 1 phản hồi ngắn, có câu nối theo nội dung khách vừa trả lời, rồi hỏi target tiếp theo.
- Không bê nguyên văn suggested_question; hãy xem nó là prompt nội bộ.
- Không hỏi như biểu mẫu.
- Không giải thích, không markdown.
- Giọng tự nhiên, lịch sự, đúng xưng hô với khách là "{customer}".
- Mỗi lượt chỉ hỏi 1 ý chính.
- Nếu có câu trả lời vừa rồi, hãy phản ứng theo ý nghĩa của câu đó, không chỉ nhắc lại.
- Tránh các mở đầu công thức: "Cảm ơn", "Em ghi nhận", "Đã ghi nhận", "Vâng, em ghi nhận".
- Không lặp lại cùng một cấu trúc ở nhiều lượt liên tiếp.
- Hãy nói giống người tư vấn đang trò chuyện: có thể dùng "Với mức...", "Như vậy...", "CTG quanh 40 thì...", "Ra quyết định theo cảm tính thì..." nếu phù hợp.
- Tổng độ dài tối đa 2 câu ngắn.

Target cần hỏi:
Nếu target_mode là "explainer":
- Không hỏi khách cung cấp thêm dữ liệu.
- Chỉ hỏi khách có muốn nghe phần thuyết minh đó không.
- Câu hỏi phải ngắn, dạng xin phép, ví dụ: "Anh/chị có muốn em thuyết minh thêm phần này không?"

target_mode: {target_mode}

{json.dumps(next_config, ensure_ascii=False, indent=2)}

Trạng thái thông tin hiện tại:
{json.dumps(targets, ensure_ascii=False, indent=2)}

Câu khách vừa trả lời:
{user_text or ""}

Lịch sử gần nhất:
{json.dumps(recent_context, ensure_ascii=False, indent=2)}

Mức kinh nghiệm khách:
{level}

Chỉ trả về nội dung gửi cho khách.
""".strip()

        try:
            resp = self.oa.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Chỉ viết phản hồi tiếng Việt tự nhiên để gửi cho khách, tối đa 2 câu ngắn."},
                    {"role": "user", "content": prompt},
                ],
            )
            question = (resp.choices[0].message.content or "").strip()
            question = remove_formulaic_opening(question)
            return self.apply_customer_pronoun(question or fallback, targets)
        except Exception as exc:
            print("SALES_DISCOVERY_NEXT_QUESTION_ERROR:", exc)
            return fallback

    async def handle_turn(self, user_id: str, user_text: str) -> Dict[str, Any]:
        state = await self.get_or_create_state(user_id)
        configs = state.get("target_configs") or await self.active_target_configs()
        target_order = target_order_from_configs(configs)

        if state["stage"] == "completed":
            return {
                "assistant_message": (
                    f"Em đã lưu lại thông tin tư vấn ban đầu của {self.customer_pronoun(state['targets'])} rồi. "
                    "Mình có thể chuyển sang phần phân tích danh mục hoặc cách dùng app."
                ),
                "stage": "completed",
                "current_target": None,
                "targets": state["targets"],
                "summary_for_db": state["summary"],
                "target_configs": configs,
            }

        targets_for_prompt = merge_obvious_user_facts(state["targets"], user_text)
        targets_for_prompt = normalize_targets_for_configs(targets_for_prompt, configs)
        history = await self.memory.recent_messages(user_id, turns=6)
        messages = self.build_messages(
            user_text=user_text,
            targets=targets_for_prompt,
            history=history,
            configs=configs,
        )

        parsed_from_fallback = False

        try:
            resp = self.oa.chat(model=self.model, messages=messages)
            content = resp.choices[0].message.content or ""
            parsed = safe_json_loads(content)
        except Exception as exc:
            print("SALES_DISCOVERY_PARSE_ERROR:", exc)
            parsed = self.fallback_response(targets_for_prompt, configs)
            parsed_from_fallback = True

        targets = parsed.get("targets") or targets_for_prompt
        targets = merge_obvious_user_facts(targets, user_text)
        targets = normalize_targets_for_configs(targets, configs)
        stage = parsed.get("stage") or "collecting"

        if all_targets_complete(targets, target_order):
            stage = "completed"

        summary = parsed.get("summary_for_db")
        completed_at = None

        if stage == "completed":
            completed_at = datetime.now().isoformat(timespec="seconds")
            if not summary:
                summary = {
                    key: targets.get(key, {}).get("value") or ""
                    for key in target_order
                }

        await self.memory.upsert_sales_discovery(
            user_id=user_id,
            stage=stage,
            targets_json=json.dumps(targets, ensure_ascii=False),
            summary_json=json.dumps(summary, ensure_ascii=False) if summary else None,
            completed_at=completed_at,
        )

        fallback = self.fallback_response(targets, configs)
        if stage != "completed":
            fallback["assistant_message"] = await self.next_collection_question_ai(
                targets,
                configs,
                user_text=user_text,
                history=history,
            )
        assistant_message = (
            ""
            if parsed_from_fallback
            else parsed.get("assistant_message")
        ) or fallback["assistant_message"]

        current_target = parsed.get("current_target")
        if (
            stage != "completed"
            and current_target
            and targets.get(current_target, {}).get("status") == "complete"
        ):
            assistant_message = fallback["assistant_message"]

        assistant_message = self.apply_customer_pronoun(assistant_message, targets)

        return {
            "assistant_message": assistant_message,
            "stage": stage,
            "current_target": current_target,
            "targets": targets,
            "summary_for_db": summary,
            "target_configs": configs,
        }

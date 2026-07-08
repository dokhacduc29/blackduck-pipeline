"""
=====================================================================
CLEANER AGENT — Làm sạch & phân loại tin (HYBRID: Regex + AI — PHASE B)
=====================================================================
KIẾN TRÚC 2 TẦNG:
    Tầng 1 (Regex — miễn phí, nhanh):
        - Lọc rác hiển nhiên (title rỗng), khử trùng lặp.
        - Gán tag thực thể rõ ràng (#OpenAI, #Google...).
    Tầng 2 (AI — chỉ chạy khi có GEMINI_API_KEY):
        - Chấm điểm liên quan 0-10 → loại bài lạc đề.
        - Gán tag cho bài mà regex KHÔNG nhận ra (thực thể mới).
        - Hết quota/lỗi → fallback về kết quả Tầng 1 (không vỡ pipeline).

Iron Laws: L02 logging, L03 async, L07 fault tolerance, L08 type hints,
L09 no magic numbers (→ config.py).
=====================================================================
"""
import re
import json
from google import genai
from base_agent import BaseAgent, AgentFactory
from models import Article, PipelineContext
from gemini_client import generate_with_retry
import config


@AgentFactory.register("cleaner")
class CleanerAgent(BaseAgent):
    """Lính dọn dẹp — Lọc rác, gán tag (regex + AI), chấm điểm liên quan."""

    def __init__(self, **kwargs):
        super().__init__("CleanerAgent")
        self._cleaned_count: int = 0
        self._client: genai.Client | None = None

    @property
    def total_cleaned(self) -> int:
        return self._cleaned_count

    # =================================================================
    # TẦNG 1 — REGEX (giữ nguyên hành vi cũ)
    # =================================================================
    @staticmethod
    def extract_entities(text: str) -> list[str]:
        """[DAY 18 Regex] Quét tiêu đề để gán nhãn thực thể."""
        tags = []
        entity_patterns = [
            (r'\b(openai|chatgpt|gpt[-]?4[o]?)\b', "#OpenAI"),
            (r'\b(google|gemini|deepmind|alphabet)\b', "#Google"),
            (r'\b(microsoft|copilot|azure)\b', "#Microsoft"),
            (r'\b(meta|llama|zuckerberg)\b', "#Meta"),
            (r'\b(anthropic|claude)\b', "#Anthropic"),
            (r'\bapple\b', "#Apple"),
            (r'\b(tesla|elon.?musk|cybertruck|autopilot)\b', "#Tesla"),
            (r'\b(nvidia|amd|intel|chip|gpu|semiconductor)\b', "#Hardware"),
            (r'\b(robot|robotics|humanoid|boston.?dynamics)\b', "#Robotics"),
            (r'\b(startup|funding|invest|raised|valuation|ipo)\b', "#Startup"),
            (r'\$[\d]+[MB]?', "#Funding_Money"),
        ]
        for pattern, tag in entity_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                tags.append(tag)
        return tags

    def _regex_clean(self, articles: list[Article]) -> list[Article]:
        """Lọc rác + khử trùng lặp + gán tag regex. Trả về danh sách bài sạch."""
        seen: set[str] = set()
        cleaned: list[Article] = []
        for article in articles:
            if not article.title:
                continue
            article.tags = self.extract_entities(article.title)
            clean_title = re.sub(r'[^\w\s+\-&#.]', '', article.title).lower().strip()
            if clean_title and clean_title not in seen:
                article.title = clean_title
                cleaned.append(article)
                seen.add(clean_title)
        cleaned.sort(key=lambda a: a.date, reverse=True)
        return cleaned

    # =================================================================
    # TẦNG 2 — AI (mới, tùy chọn)
    # =================================================================
    def _setup_gemini(self, api_key: str):
        self._client = genai.Client(api_key=api_key)

    def _build_score_prompt(self, articles: list[Article], topic: str) -> str:
        """Tạo prompt yêu cầu AI chấm điểm liên quan + gán tag cho từng bài."""
        listing = "\n".join(f"[{i}] {art.title}" for i, art in enumerate(articles))
        return (
            f"Bạn là bộ lọc tin tức về chủ đề '{topic}'. "
            f"Với MỖI tiêu đề dưới đây, hãy đánh giá:\n"
            f"- relevance: độ liên quan tới '{topic}' và lĩnh vực AI/công nghệ, thang 0-10 "
            f"(0 = hoàn toàn lạc đề, 10 = cực kỳ liên quan).\n"
            f"- tags: 1-3 nhãn chủ đề dạng '#TenChuDe' (vd #OpenAI, #Regulation, #Funding).\n\n"
            f"Trả về DUY NHẤT một JSON array (không markdown, không text thừa):\n"
            '[{"index": <số>, "relevance": <0-10>, "tags": ["#..."]}]\n\n'
            f"DANH SÁCH:\n{listing}"
        )

    async def _call_gemini(self, prompt: str) -> str:
        """Gọi Gemini qua helper chung (retry backoff). Lỗi → '[]'."""
        assert self._client is not None, "_setup_gemini() phải được gọi trước"
        return await generate_with_retry(
            self._client,
            config.CLEANER_AI_MODEL,
            prompt,
            log_error=self.log_error,
            fallback="[]",
        )

    @staticmethod
    def _normalize_tag(tag: str) -> str:
        """Đảm bảo tag bắt đầu bằng '#' và không có khoảng trắng."""
        t = str(tag).strip().replace(" ", "_")
        return t if t.startswith("#") else f"#{t}"

    def _apply_ai_results(self, raw: str, articles: list[Article]) -> None:
        """Đọc JSON từ AI → gán relevance_score + bổ sung tag cho bài thiếu."""
        try:
            text = raw.strip()
            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            results = json.loads(text.strip())
            for item in results:
                idx = item.get("index")
                if idx is None or not (0 <= idx < len(articles)):
                    continue
                art = articles[idx]
                rel = item.get("relevance")
                if isinstance(rel, (int, float)):
                    art.relevance_score = int(rel)
                # Chỉ dùng tag của AI khi regex KHÔNG gán được gì (Hybrid)
                if not art.tags:
                    ai_tags = [self._normalize_tag(t) for t in item.get("tags", []) if t]
                    art.tags = ai_tags[:3]
        except json.JSONDecodeError as e:
            self.log_error(f"Lỗi parse JSON cleaner: {e}\nRaw: {raw[:120]}...")
        except Exception as e:
            self.log_error(f"Lỗi xử lý response cleaner: {e}")

    async def _ai_enrich_and_filter(self, articles: list[Article], topic: str) -> list[Article]:
        """Chấm điểm + gán tag bằng AI, rồi loại bài dưới ngưỡng liên quan."""
        sample = articles[: config.CLEANER_AI_BATCH_SIZE]
        self.log_info(f"Tầng AI: chấm điểm liên quan cho {len(sample)} bài bằng {config.CLEANER_AI_MODEL}...")

        prompt = self._build_score_prompt(sample, topic)
        raw = await self._call_gemini(prompt)
        self._apply_ai_results(raw, sample)

        # Giữ bài chưa chấm (-1, benefit of the doubt) HOẶC đạt ngưỡng
        kept = [a for a in articles if a.relevance_score < 0 or a.relevance_score >= config.CLEANER_RELEVANCE_THRESHOLD]
        removed = len(articles) - len(kept)
        if removed > 0:
            self.log_info(f"Tầng AI: loại {removed} bài lạc đề (điểm < {config.CLEANER_RELEVANCE_THRESHOLD}).")
        return kept

    # =================================================================
    # ĐIỀU PHỐI
    # =================================================================
    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        """Tầng 1 (regex) luôn chạy → Tầng 2 (AI) chạy nếu có GEMINI_API_KEY."""
        self.log_info(f"Nhận {len(ctx.articles)} bài thô. Bắt đầu lọc...")
        cleaned = self._regex_clean(ctx.articles)
        self.log_info(f"Tầng regex: {len(cleaned)} bài sạch, độc nhất.")

        if ctx.gemini_api_key and cleaned:
            self._setup_gemini(ctx.gemini_api_key)
            cleaned = await self._ai_enrich_and_filter(cleaned, ctx.topic)
        else:
            self.log_info("Bỏ qua tầng AI (thiếu GEMINI_API_KEY) — dùng kết quả regex.")

        self._cleaned_count = len(cleaned)
        ctx.articles = cleaned
        self.log_info(f"Lọc xong: {self._cleaned_count} bài cuối cùng.")
        return ctx

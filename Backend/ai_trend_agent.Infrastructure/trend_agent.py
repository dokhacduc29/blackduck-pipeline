"""
=====================================================================
TREND SYNTHESIS AGENT — "Nhà phân tích chiến lược" (PHASE A)
=====================================================================
Khác biệt cốt lõi với SummarizationAgent:
    - SummarizationAgent: tóm tắt TỪNG bài (micro view).
    - TrendSynthesisAgent: đọc TOÀN BỘ bài để rút ra BỨC TRANH LỚN —
      các xu hướng đang nổi, tâm lý chung của thị trường (macro view).

Đây là phần "Trend" mà tên project hứa hẹn.

Áp dụng Iron Laws:
    - L03 Async-first: dùng client.aio của google-genai.
    - L07 Fault tolerance: retry exponential backoff cho lỗi 503/429.
    - L08 Type hints + docstring.
    - L09 No magic numbers: hằng số → config.py.
=====================================================================
"""
import json
from google import genai
from base_agent import BaseAgent, AgentFactory
from models import PipelineContext, TrendReport, Sentiment, Article
from gemini_client import generate_with_retry
import config
from decorators import ai_timer, ai_logger


@AgentFactory.register("trend")
class TrendSynthesisAgent(BaseAgent):
    """Nhà phân tích chiến lược — Rút ra xu hướng xuyên suốt các bài báo."""

    def __init__(self, **kwargs):
        super().__init__("TrendSynthesisAgent")
        self._client: genai.Client | None = None

    def _setup_gemini(self, api_key: str):
        """Khởi tạo Gemini client (lazy)."""
        self._client = genai.Client(api_key=api_key)

    def _build_prompt(self, articles: list[Article], topic: str) -> str:
        """Gộp tiêu đề + tóm tắt của tất cả bài thành một prompt phân tích vĩ mô."""
        corpus = "\n".join(
            f"- [{art.sentiment.value}] {art.title}"
            + (f" — {art.summary}" if art.summary else "")
            for art in articles
        )
        return (
            f"Bạn là chuyên gia phân tích xu hướng công nghệ AI. "
            f"Dưới đây là {len(articles)} tin tức về chủ đề '{topic}'.\n"
            f"Hãy đọc TOÀN BỘ và rút ra bức tranh tổng quan.\n\n"
            f"Trả về DUY NHẤT một JSON object (không markdown, không text thừa) dạng:\n"
            '{\n'
            f'  "trends": ["<tối đa {config.TREND_COUNT} xu hướng nổi bật, mỗi xu hướng 1 câu ngắn, '
            'kèm số bài liên quan trong ngoặc>"],\n'
            '  "overall_sentiment": "<bullish|bearish|neutral>",\n'
            '  "insight": "<nhận định tổng quan 1-2 câu về thị trường>"\n'
            '}\n\n'
            f"DỮ LIỆU:\n{corpus}"
        )

    @ai_logger
    @ai_timer
    async def _call_gemini(self, prompt: str) -> str:
        """Gọi Gemini qua helper chung (retry backoff). Lỗi → '{}'."""
        assert self._client is not None, "_setup_gemini() phải được gọi trước _call_gemini()"
        return await generate_with_retry(
            self._client,
            config.TREND_MODEL_NAME,
            prompt,
            log_error=self.log_error,
            fallback="{}",
        )

    def _parse_response(self, raw: str) -> TrendReport:
        """Chuyển JSON từ AI thành TrendReport. Lỗi → report rỗng (generated=False)."""
        report = TrendReport()
        try:
            text = raw.strip()
            # Bóc markdown code block nếu AI lỡ trả về
            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

            data = json.loads(text)
            report.trends = [str(t) for t in data.get("trends", [])][: config.TREND_COUNT]

            sent = str(data.get("overall_sentiment", "neutral")).lower()
            if "bull" in sent or "tích" in sent:
                report.overall_sentiment = Sentiment.BULLISH
            elif "bear" in sent or "tiêu" in sent:
                report.overall_sentiment = Sentiment.BEARISH
            else:
                report.overall_sentiment = Sentiment.NEUTRAL

            report.insight = str(data.get("insight", "")).strip()
            report.generated = bool(report.trends)
        except json.JSONDecodeError as e:
            self.log_error(f"Lỗi parse JSON xu hướng: {e}\nRaw: {raw[:120]}...")
        except Exception as e:
            self.log_error(f"Lỗi xử lý response xu hướng: {e}")
        return report

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        """Đọc ctx.articles → sinh ctx.trend_report."""
        if not ctx.gemini_api_key:
            self.log_warning("Thiếu GEMINI_API_KEY. Bỏ qua phân tích xu hướng.")
            return ctx

        if len(ctx.articles) < config.TREND_MIN_ARTICLES:
            self.log_info(
                f"Chỉ có {len(ctx.articles)} bài (< {config.TREND_MIN_ARTICLES}). "
                "Không đủ để rút xu hướng."
            )
            return ctx

        self._setup_gemini(ctx.gemini_api_key)
        sample = ctx.articles[: config.TREND_MAX_ARTICLES]
        self.log_info(f"Phân tích xu hướng từ {len(sample)} bài bằng {config.TREND_MODEL_NAME}...")

        prompt = self._build_prompt(sample, ctx.topic)
        raw = await self._call_gemini(prompt)
        ctx.trend_report = self._parse_response(raw)

        if ctx.trend_report.generated:
            self.log_info(f"Đã rút ra {len(ctx.trend_report.trends)} xu hướng nổi bật.")
        else:
            self.log_warning("Không rút được xu hướng nào từ AI.")
        return ctx

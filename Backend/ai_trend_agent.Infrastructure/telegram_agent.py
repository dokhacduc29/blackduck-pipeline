"""
=====================================================================
TELEGRAM AGENT — Gửi thông báo đến người dùng (PHASE 6)
=====================================================================
Bắn tin tức đã phân tích về điện thoại qua Telegram Bot API.
Áp dụng Iron Laws:
    - L03 Async-first: httpx.AsyncClient cho mọi API call.
    - L07 Fault tolerance: timeout + try/except trên từng request.
    - L09 No magic numbers: hằng số → config.py.
    - L02 Logging only: không print.

Định dạng: DIGEST gộp — gộp tất cả bài vào một (hoặc vài) tin nhắn,
tự chia chunk khi vượt giới hạn 4096 ký tự của Telegram.
=====================================================================
"""
import os
import html
import asyncio
import httpx
from base_agent import BaseAgent, AgentFactory
from models import Article, PipelineContext, Sentiment, TrendReport
import config


# Biểu tượng cảm xúc theo sentiment để nhìn nhanh xu hướng
_SENTIMENT_EMOJI = {
    Sentiment.BULLISH: "📈",
    Sentiment.BEARISH: "📉",
    Sentiment.NEUTRAL: "➖",
}


@AgentFactory.register("telegram")
class TelegramAgent(BaseAgent):
    """Lính liên lạc — Gửi tin tức đã phân tích qua Telegram Bot."""

    def __init__(self, **kwargs):
        super().__init__("TelegramAgent")

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        """
        Gửi các bài báo đã được tóm tắt qua Telegram dưới dạng digest gộp.
        Tự đọc TELEGRAM_BOT_TOKEN và TELEGRAM_CHAT_ID từ .env.
        """
        telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")

        if not telegram_token or not chat_id:
            self.log_info("Thiếu TELEGRAM_BOT_TOKEN hoặc TELEGRAM_CHAT_ID. Bỏ qua bước gửi Telegram.")
            return ctx

        if not ctx.articles:
            self.log_info("Không có bài báo nào để gửi.")
            return ctx

        chunks = self._build_digest_chunks(ctx.articles, ctx.topic, ctx.trend_report)
        self.log_info(f"Chuẩn bị gửi {len(ctx.articles)} bài (chia thành {len(chunks)} tin nhắn) qua Telegram...")

        url = f"{config.TELEGRAM_API_BASE}/bot{telegram_token}/sendMessage"
        sent = 0
        async with httpx.AsyncClient() as client:
            for idx, chunk in enumerate(chunks, start=1):
                if await self._send_message(client, url, chat_id, chunk):
                    sent += 1
                # Nghỉ giữa các chunk để tránh rate limit 429 (trừ chunk cuối)
                if idx < len(chunks):
                    await asyncio.sleep(config.TELEGRAM_SEND_DELAY)

        self.log_info(f"Đã gửi thành công {sent}/{len(chunks)} tin nhắn qua Telegram.")
        return ctx

    async def _send_message(
        self, client: httpx.AsyncClient, url: str, chat_id: str, text: str
    ) -> bool:
        """Gửi một tin nhắn. Trả True nếu thành công, False nếu lỗi."""
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": config.TELEGRAM_PARSE_MODE,
            "disable_web_page_preview": True,
        }
        try:
            res = await client.post(url, json=payload, timeout=config.REQUEST_TIMEOUT)
            res.raise_for_status()
            return True
        except Exception as e:
            self.log_error(f"Lỗi gửi Telegram: {e}")
            return False

    def _build_digest_chunks(
        self, articles: list[Article], topic: str, trend: TrendReport | None = None
    ) -> list[str]:
        """
        Gộp các bài thành digest HTML, tự chia thành nhiều chunk khi vượt
        TELEGRAM_MAX_MESSAGE_LENGTH. Không bao giờ cắt giữa một bài báo.
        Nếu có TrendReport → đặt phần xu hướng lên ĐẦU chunk đầu tiên.
        """
        header = f"📰 <b>AI TREND DIGEST — {html.escape(topic.upper())}</b>\n\n"
        blocks = [self._format_article(i, art) for i, art in enumerate(articles, start=1)]

        chunks: list[str] = []
        # Chunk đầu tiên mở đầu bằng phần xu hướng (nếu có) + header danh sách
        first_prefix = self._format_trend(trend) + header if trend and trend.generated else header
        current = first_prefix
        for block in blocks:
            # Nếu thêm block làm vượt giới hạn → chốt chunk hiện tại, mở chunk mới (chỉ header)
            if len(current) + len(block) > config.TELEGRAM_MAX_MESSAGE_LENGTH and current not in (first_prefix, header):
                chunks.append(current.rstrip())
                current = header
            current += block

        if current.strip() and current not in (first_prefix, header):
            chunks.append(current.rstrip())
        elif not chunks and current.strip():
            # Trường hợp chỉ có phần trend mà không có bài nào lọt block
            chunks.append(current.rstrip())
        return chunks

    def _format_trend(self, trend: TrendReport) -> str:
        """Định dạng phần phân tích xu hướng (đặt đầu digest)."""
        emoji = _SENTIMENT_EMOJI.get(trend.overall_sentiment, "➖")
        lines = [f"🔮 <b>XU HƯỚNG AI — {emoji} {html.escape(trend.overall_sentiment.value)}</b>"]
        for t in trend.trends:
            lines.append(f"• {html.escape(t)}")
        if trend.insight:
            lines.append(f"\n💬 <i>{html.escape(trend.insight)}</i>")
        return "\n".join(lines) + "\n\n" + "─" * 15 + "\n\n"

    def _format_article(self, index: int, art: Article) -> str:
        """Định dạng MỘT bài báo thành block HTML cho Telegram."""
        emoji = _SENTIMENT_EMOJI.get(art.sentiment, "➖")
        title = html.escape(art.title or "Không có tiêu đề")
        source = html.escape(art.source or "Unknown")
        summary = html.escape(art.summary) if art.summary else ""
        link = html.escape(art.url, quote=True) if art.url else ""

        title_line = f'{index}. {emoji} <b><a href="{link}">{title}</a></b>' if link else f"{index}. {emoji} <b>{title}</b>"
        lines = [title_line]
        if summary:
            lines.append(f"   📝 {summary}")
        lines.append(f"   📰 {source} | 📅 {html.escape(art.date)}")
        return "\n".join(lines) + "\n\n"

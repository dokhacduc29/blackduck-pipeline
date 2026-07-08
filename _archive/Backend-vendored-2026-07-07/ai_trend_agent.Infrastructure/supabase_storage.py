"""
=====================================================================
SUPABASE STORAGE AGENT — Lưu trữ lên PostgreSQL cloud (Phase 5)
=====================================================================
Thay thế StorageAgent (CSV) bằng Supabase PostgreSQL.
- Dedupe tự động qua constraint url UNIQUE trên DB
- Dùng asyncio.to_thread để không block Event Loop
- Upsert thay insert để bỏ qua trùng lặp không lỗi
=====================================================================
"""
import os
import asyncio
from supabase import create_client, Client
from base_agent import BaseAgent, AgentFactory
from models import Article, PipelineContext


@AgentFactory.register("storage")
class SupabaseStorageAgent(BaseAgent):
    """Lính hậu cần — Lưu trữ dữ liệu lên Supabase PostgreSQL."""

    def __init__(self, **kwargs):
        super().__init__("SupabaseStorageAgent")
        self._client: Client | None = None

    def _get_client(self) -> Client:
        if self._client is None:
            url = os.getenv("SUPABASE_URL")
            key = os.getenv("SUPABASE_KEY")
            if not url or not key:
                raise ValueError("Thiếu SUPABASE_URL hoặc SUPABASE_KEY trong .env")
            self._client = create_client(url, key)
        return self._client

    def _article_to_row(self, art: Article, topic: str = "") -> dict:
        return {
            "title": art.title,
            "source": art.source,
            "date": art.date,
            "tags": ", ".join(art.tags),
            "summary": art.summary,
            "sentiment": art.sentiment.value if hasattr(art.sentiment, "value") else str(art.sentiment),
            "url": art.url,
            "topic": topic,
        }

    def _insert_sync(self, rows: list[dict]) -> int:
        """Upsert vào Supabase — bỏ qua nếu url đã tồn tại."""
        client = self._get_client()
        result = (
            client.table("articles")
            .upsert(rows, on_conflict="url", ignore_duplicates=True)
            .execute()
        )
        return len(result.data) if result.data else 0

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        if not ctx.articles:
            self.log_info("Không có bài báo nào để lưu.")
            return ctx

        rows = [self._article_to_row(art, ctx.topic) for art in ctx.articles]
        self.log_info(f"Đang lưu {len(rows)} bài lên Supabase...")

        try:
            inserted = await asyncio.to_thread(self._insert_sync, rows)
            self.log_info(f"Đã lưu thành công {inserted} bài mới vào Supabase.")
        except Exception as e:
            self.log_error(f"Lỗi khi lưu Supabase: {e}")

        return ctx

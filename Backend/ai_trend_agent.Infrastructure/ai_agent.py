"""
=====================================================================
[DAY 31-40] SUMMARIZATION AGENT — "Bộ não" của hệ thống
=====================================================================
Áp dụng:
- Context Managers (Day 35): Quản lý phiên kết nối API an toàn.
- Generators (Day 32): Xử lý luồng dữ liệu (nếu cần stream).
- Decorators (Day 33-34): Theo dõi tốc độ và ghi log.
- FinOps (Token Optimization): Batching, Pre-filtering, Caching.
=====================================================================
"""
import os
import json
import asyncio
import hashlib
from google import genai

from base_agent import BaseAgent, AgentFactory
from models import PipelineContext, Sentiment, Article
from gemini_client import generate_with_retry
import config
from decorators import ai_timer, ai_logger


@AgentFactory.register("analyzer")
class SummarizationAgent(BaseAgent):
    """Chuyên viên phân tích — Nhận bài báo, đẩy cho Gemini tóm tắt."""

    def __init__(self, **kwargs):
        super().__init__("SummarizationAgent")
        self._client: genai.Client | None = None
        self._cache_file = os.path.join(config.OUTPUT_DIR, ".ai_cache.json")
        self._cache = self._load_cache()

    def _setup_gemini(self, api_key: str):
        """Cấu hình Gemini API."""
        self._client = genai.Client(api_key=api_key)

    def _get_cache_key(self, title: str) -> str:
        """Chiến lược 3: Hàm băm (Hash) để tạo khóa cho Cache."""
        return hashlib.md5(title.encode('utf-8')).hexdigest()[:12]

    def _load_cache(self) -> dict:
        """Đọc lịch sử Cache để tránh lãng phí AI Token vào các bài cũ."""
        if os.path.exists(self._cache_file):
            try:
                with open(self._cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                self.log_error(f"Lỗi đọc cache: {e}")
        return {}

    def _save_cache(self):
        """Lưu lại Cache sau khi phân tích xong."""
        os.makedirs(os.path.dirname(self._cache_file), exist_ok=True)
        try:
            with open(self._cache_file, 'w', encoding='utf-8') as f:
                json.dump(self._cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.log_error(f"Lỗi ghi cache: {e}")

    @ai_logger
    @ai_timer
    async def _analyze_batch(self, articles_batch: list[Article]) -> str:
        """
        Chiến lược 1: Gộp nhiều bài vào một prompt duy nhất để tiết kiệm 70% token.
        Yêu cầu AI trả về dưới định dạng JSON Array.
        """
        articles_text = "\n---\n".join([
            f"[{i}] Title: {art.title}\nSource: {art.source}"
            for i, art in enumerate(articles_batch)
        ])
        
        prompt = (
            "Phân tích các bài báo AI dưới đây. "
            "Trả về JSON array, mỗi phần tử gồm:\n"
            '{"index": <số thứ tự trong prompt>, "summary": "<tóm tắt tối đa 15 từ>", "sentiment": "<bullish/bearish/neutral>"}\n'
            "Chỉ trả đúng JSON array, tuyệt đối không thêm markdown code blocks (như ```json) hay bất kỳ văn bản nào khác.\n\n"
            f"{articles_text}"
        )
        
        assert self._client is not None, "_setup_gemini() phải được gọi trước _analyze_batch()"
        return await generate_with_retry(
            self._client,
            config.GEMINI_MODEL_NAME,
            prompt,
            log_error=self.log_error,
            fallback="[]",
        )

    def _parse_batch_response(self, response_text: str, articles_batch: list[Article]):
        """Phân tích kết quả JSON trả về từ AI thành dữ liệu Article."""
        try:
            # Loại bỏ các tag markdown nếu AI lỡ trả về
            text = response_text.strip()
            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

            results = json.loads(text)
            for item in results:
                idx = item.get("index")
                summary = item.get("summary", "Không có tóm tắt.")
                sentiment_str = item.get("sentiment", "neutral").lower()

                if idx is not None and 0 <= idx < len(articles_batch):
                    article = articles_batch[idx]
                    article.summary = summary
                    
                    if "bullish" in sentiment_str or "tích" in sentiment_str:
                        article.sentiment = Sentiment.BULLISH
                    elif "bearish" in sentiment_str or "tiêu" in sentiment_str:
                        article.sentiment = Sentiment.BEARISH
                    else:
                        article.sentiment = Sentiment.NEUTRAL

                    # Lưu vào cache ngay lập tức
                    cache_key = self._get_cache_key(article.title)
                    self._cache[cache_key] = {
                        "summary": article.summary,
                        "sentiment": article.sentiment.value
                    }

        except json.JSONDecodeError as e:
            self.log_error(f"Lỗi phân tích JSON từ AI: {e}\nRaw Response: {response_text[:100]}...")
        except Exception as e:
            self.log_error(f"Lỗi xử lý response: {e}")

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        """
        [FIX LSP] Hàm xử lý chính kết hợp cả 3 chiến lược tối ưu FinOps.
        """
        if not ctx.gemini_api_key:
            self.log_error("Thiếu GEMINI_API_KEY. Bỏ qua phân tích AI.")
            return ctx

        if not ctx.articles:
            self.log_info("Không có bài báo nào để phân tích.")
            return ctx

        self._setup_gemini(ctx.gemini_api_key)
        self.log_info(f"Bắt đầu phân tích AI cho {len(ctx.articles)} bài báo bằng {config.GEMINI_MODEL_NAME}...")

        # -------------------------------------------------------------
        # CHIẾN LƯỢC 3: Caching (Dùng Hash để bỏ qua bài báo trùng lặp)
        # -------------------------------------------------------------
        articles_to_process = []
        for article in ctx.articles:
            cache_key = self._get_cache_key(article.title)
            if cache_key in self._cache:
                cached_data = self._cache[cache_key]
                article.summary = cached_data.get("summary", "")
                
                sent_val = cached_data.get("sentiment", "Trung lập")
                if sent_val == Sentiment.BULLISH.value:
                    article.sentiment = Sentiment.BULLISH
                elif sent_val == Sentiment.BEARISH.value:
                    article.sentiment = Sentiment.BEARISH
                else:
                    article.sentiment = Sentiment.NEUTRAL
            else:
                articles_to_process.append(article)

        self.log_info(f"Đã phục hồi {len(ctx.articles) - len(articles_to_process)} bài từ Cache.")

        if not articles_to_process:
            self.log_info("Tất cả bài báo đều đã có trong cache.")
            return ctx

        # -------------------------------------------------------------
        # CHIẾN LƯỢC 2: Giới hạn số bài gửi AI mỗi lần (tránh rate limit)
        # -------------------------------------------------------------
        articles_to_analyze = articles_to_process[:config.AI_MAX_ARTICLES_PER_BATCH]

        ignored_count = len(articles_to_process) - len(articles_to_analyze)
        if ignored_count > 0:
            self.log_info(f"Bỏ qua {ignored_count} bài (vượt limit {config.AI_MAX_ARTICLES_PER_BATCH}).")

        if not articles_to_analyze:
            self.log_info("Không còn bài báo quan trọng nào cần gửi cho AI.")
            return ctx

        # -------------------------------------------------------------
        # CHIẾN LƯỢC 1: Batch Prompting (Gộp 5 bài vào 1 request)
        # -------------------------------------------------------------
        BATCH_SIZE = 5
        batches = [articles_to_analyze[i:i + BATCH_SIZE] for i in range(0, len(articles_to_analyze), BATCH_SIZE)]
        
        sem = asyncio.Semaphore(1)  # Nối tiếp để không vượt 5 RPM free tier

        async def process_batch(batch):
            async with sem:
                response_text = await self._analyze_batch(batch)
                self._parse_batch_response(response_text, batch)

        self.log_info(f"Đang gửi {len(articles_to_analyze)} bài báo (chia thành {len(batches)} batches) cho Gemini...")
        
        tasks = [process_batch(batch) for batch in batches]
        await asyncio.gather(*tasks)

        # Lưu lại Cache xuống ổ đĩa
        self._save_cache()

        self.log_info("Hoàn thành phân tích AI và cập nhật Cache.")
        return ctx

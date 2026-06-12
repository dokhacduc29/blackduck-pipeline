"""
=====================================================================
SCRAPER AGENT — Cào tin đa nguồn (BẢN SỬA TOÀN BỘ BUGS & SMELLS)
=====================================================================
FIX LIST:
    - [SMELL] Magic numbers → Import từ config.py
    - [LSP] execute() signature thống nhất: nhận/trả PipelineContext
    - [OCP] Tự đăng ký vào Factory bằng decorator @AgentFactory.register
=====================================================================
"""
import os
import httpx
import asyncio
import xml.etree.ElementTree as ET
from base_agent import BaseAgent, AgentFactory
from models import Article, PipelineContext
import config


@AgentFactory.register("scraper")
class ScraperAgent(BaseAgent):
    """Lính trinh sát — Cào tin từ 3 nguồn."""

    def __init__(self, **kwargs):
        super().__init__("ScraperAgent")

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        """
        [FIX LSP] Chữ ký thống nhất: nhận PipelineContext, trả PipelineContext.
        Agent tự đọc api_key và topic từ context, không cần truyền riêng.
        """
        self.log_info(f"Bắt đầu cào tin về: '{ctx.topic}'")

        async with httpx.AsyncClient() as client:
            tasks = [
                self._fetch_newsapi(client, ctx.api_key, ctx.topic),
                self._fetch_reddit(client),
                self._fetch_google_rss(client, ctx.topic),
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for idx, result in enumerate(results):
                if isinstance(result, list):
                    ctx.articles.extend(result)
                elif isinstance(result, Exception):
                    self.log_error(f"Task {idx} thất bại: {result}")

        self.log_info(f"Thu thập xong: {len(ctx.articles)} bài thô")
        return ctx

    async def _fetch_newsapi(self, client: httpx.AsyncClient, api_key: str, topic: str) -> list[Article]:
        url = (
            f"https://newsapi.org/v2/everything"
            f"?q={topic}&language=en"
            f"&pageSize={config.NEWSAPI_PAGE_SIZE}"
            f"&apiKey={api_key}"
        )
        try:
            response = await client.get(url, timeout=config.REQUEST_TIMEOUT)
            response.raise_for_status()
            data = response.json()
            if data.get("status") == "ok":
                return [
                    Article(
                        title=post.get("title", ""),
                        source=post.get("source", {}).get("name", "Unknown"),
                        date=post.get("publishedAt", "1970-01-01")[:10],
                        url=post.get("url", ""),
                    )
                    for post in data.get("articles", [])
                    if post.get("title") and "[Removed]" not in post.get("title")
                ]
            self.log_error(f"NewsAPI trả về lỗi: {data.get('message')}")
            return []
        except Exception as e:
            self.log_error(f"Lỗi mạng NewsAPI: {e}")
            return []

    async def _fetch_reddit(self, client: httpx.AsyncClient) -> list[Article]:
        """
        Ưu tiên OAuth (ổn định, không bị 403) nếu có REDDIT_CLIENT_ID/SECRET.
        Không có credentials → fallback sang JSON công khai (có thể bị 403 → trả []).
        """
        client_id = os.getenv("REDDIT_CLIENT_ID")
        client_secret = os.getenv("REDDIT_CLIENT_SECRET")

        if client_id and client_secret:
            token = await self._get_reddit_token(client, client_id, client_secret)
            if token:
                return await self._fetch_reddit_oauth(client, token)
            self.log_warning("Lấy Reddit OAuth token thất bại → thử kênh công khai.")

        return await self._fetch_reddit_public(client)

    async def _get_reddit_token(self, client: httpx.AsyncClient, client_id: str, client_secret: str) -> str | None:
        """Lấy access token qua luồng application-only OAuth (client_credentials)."""
        try:
            res = await client.post(
                config.REDDIT_OAUTH_TOKEN_URL,
                data={"grant_type": "client_credentials"},
                auth=(client_id, client_secret),
                headers={"User-Agent": config.REDDIT_USER_AGENT},
                timeout=config.REQUEST_TIMEOUT,
            )
            res.raise_for_status()
            return res.json().get("access_token")
        except Exception as e:
            self.log_error(f"Lỗi lấy Reddit OAuth token: {e}")
            return None

    async def _fetch_reddit_oauth(self, client: httpx.AsyncClient, token: str) -> list[Article]:
        """Lấy bài qua endpoint oauth.reddit.com đã xác thực."""
        url = f"{config.REDDIT_OAUTH_API_BASE}/r/{config.REDDIT_SUBREDDIT}/new?limit={config.REDDIT_LIMIT}"
        headers = {
            "Authorization": f"bearer {token}",
            "User-Agent": config.REDDIT_USER_AGENT,
        }
        try:
            res = await client.get(url, headers=headers, timeout=config.REQUEST_TIMEOUT)
            res.raise_for_status()
            return self._parse_reddit_posts(res.json()["data"]["children"])
        except Exception as e:
            self.log_error(f"Lỗi Reddit OAuth: {e}")
            return []

    async def _fetch_reddit_public(self, client: httpx.AsyncClient) -> list[Article]:
        """Kênh công khai (không xác thực) — Reddit thường chặn 403, dùng làm fallback."""
        headers = {"User-Agent": config.REDDIT_USER_AGENT, "Accept": "application/json"}
        urls = [
            f"https://www.reddit.com/r/{config.REDDIT_SUBREDDIT}/new.json?limit={config.REDDIT_LIMIT}",
            f"https://old.reddit.com/r/{config.REDDIT_SUBREDDIT}/new.json?limit={config.REDDIT_LIMIT}",
        ]
        for url in urls:
            try:
                res = await client.get(url, headers=headers, timeout=config.REQUEST_TIMEOUT)
                if res.status_code == 403:
                    continue
                res.raise_for_status()
                return self._parse_reddit_posts(res.json()["data"]["children"])
            except Exception as e:
                self.log_error(f"Lỗi Reddit ({url}): {e}")
        self.log_warning("Reddit chặn kênh công khai (403). Thêm REDDIT_CLIENT_ID/SECRET để dùng OAuth.")
        return []

    @staticmethod
    def _parse_reddit_posts(posts: list) -> list[Article]:
        """Chuyển danh sách post JSON của Reddit thành Article."""
        return [
            Article(
                title=p["data"].get("title", ""),
                source="Reddit",
                date="N/A",
                url=f"https://www.reddit.com{p['data'].get('permalink', '')}",
            )
            for p in posts
        ]

    async def _fetch_google_rss(self, client: httpx.AsyncClient, topic: str) -> list[Article]:
        url = f"https://news.google.com/rss/search?q={topic}&hl=en-US&gl=US&ceid=US:en"
        try:
            res = await client.get(url, timeout=config.REQUEST_TIMEOUT)
            res.raise_for_status()
            root = ET.fromstring(res.text)
            articles = []
            for item in root.findall(".//item")[: config.GOOGLE_RSS_LIMIT]:
                title = (el.text or "") if (el := item.find("title")) is not None else ""
                link = (el.text or "") if (el := item.find("link")) is not None else ""
                pub_date = (el.text or "N/A") if (el := item.find("pubDate")) is not None else "N/A"
                source_el = item.find("source")
                source = (source_el.text or "Google News RSS") if source_el is not None else "Google News RSS"
                articles.append(Article(title=title, source=source, date=pub_date[:16], url=link))
            return articles
        except Exception as e:
            self.log_error(f"Lỗi Google RSS: {e}")
            return []

"""
=====================================================================
UNIT TESTING CHUYÊN NGHIỆP VỚI PYTEST (DAY 49)
=====================================================================
Mục tiêu:
    - Kiểm thử tự động các module lõi mà không phụ thuộc vào mạng.
    - Đảm bảo tính chính xác của thuật toán lọc trùng và gán nhãn Regex.
=====================================================================
"""
import pytest
import sys
import os

# Nạp động các thư mục Backend vào sys.path để pytest nhận diện các module phẳng
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)
for layer in ["ai_trend_agent.Domain", "ai_trend_agent.Application", "ai_trend_agent.Infrastructure"]:
    layer_dir = os.path.join(backend_dir, layer)
    if layer_dir not in sys.path:
        sys.path.insert(0, layer_dir)

from models import Article, PipelineContext, Sentiment
from base_agent import AgentFactory

# Import side-effect để đăng ký các agent vào AgentFactory
import cleaner


def test_article_model_basics():
    """Kiểm thử cấu trúc dữ liệu Article."""
    art1 = Article(title="OpenAI ra mắt GPT-5", source="NewsAPI", date="2026-05-14", url="http://example.com")
    art2 = Article(title="openai ra mắt gpt-5", source="Reddit", date="2026-05-14", url="http://reddit.com")
    
    # Test dunder methods __eq__ và __len__
    assert art1 == art2  # Cùng tiêu đề (không phân biệt hoa thường) được coi là bằng nhau
    assert len(art1) == len("OpenAI ra mắt GPT-5")
    assert art1.sentiment == Sentiment.NEUTRAL


def test_cleaner_extract_entities():
    """Kiểm thử bộ máy gán nhãn thực thể tự động bằng Regex (Day 18)."""
    cleaner_agent = AgentFactory.create("cleaner")
    
    tags_openai = cleaner_agent.extract_entities("Sức mạnh của ChatGPT và GPT-4o")
    assert "#OpenAI" in tags_openai
    
    tags_multi = cleaner_agent.extract_entities("Cuộc đua giữa Google Gemini và Microsoft Copilot")
    assert "#Google" in tags_multi
    assert "#Microsoft" in tags_multi


@pytest.mark.asyncio
async def test_cleaner_agent_execute():
    """Kiểm thử luồng thực thi làm sạch và lọc trùng dữ liệu (Async Unit Test)."""
    cleaner_agent = AgentFactory.create("cleaner")
    
    articles = [
        Article(title="Apple công bố chip mới", source="SourceA", date="2026-05-10", url=""),
        Article(title="   Apple công bố chip mới   ", source="SourceB", date="2026-05-11", url=""), # Trùng tiêu đề
        Article(title="", source="SourceC", date="2026-05-12", url=""), # Tiêu đề rỗng bị loại
    ]
    
    ctx = PipelineContext(topic="Technology", articles=articles)
    updated_ctx = await cleaner_agent.execute(ctx)
    
    # Đảm bảo bài báo rỗng và bài báo trùng lặp đã bị loại bỏ
    assert len(updated_ctx.articles) == 1
    assert updated_ctx.articles[0].title == "apple công bố chip mới"
    assert "#Apple" in updated_ctx.articles[0].tags
    assert cleaner_agent.total_cleaned == 1

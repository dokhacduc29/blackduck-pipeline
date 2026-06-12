"""
=====================================================================
AI TREND AGENT v3.1 — SOLID Edition
=====================================================================
FIX LIST:
    - [DIP] run_pipeline nhận BaseAgent thay vì concrete class
    - [ASYNC] Toàn bộ main() chạy trong asyncio.run() — loại bỏ schedule
    - [OCP] Factory không cần import class cụ thể — Agent tự đăng ký
    - [L09] Magic numbers → config.py
=====================================================================
"""
import os
import re
import asyncio
import logging
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

import sys
# Dynamically add Backend layers to sys.path so direct imports work seamlessly
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)
for layer in ["ai_trend_agent.Domain", "ai_trend_agent.Application", "ai_trend_agent.Infrastructure"]:
    layer_dir = os.path.join(backend_dir, layer)
    if layer_dir not in sys.path:
        sys.path.insert(0, layer_dir)

# Import base_agent TRƯỚC để Factory sẵn sàng
from base_agent import BaseAgent, AgentFactory
from models import PipelineContext
import config

# Import các module Agent — decorator @register sẽ TỰ ĐĂNG KÝ vào Factory
import scrapers   # noqa: F401 — side-effect import (đăng ký "scraper")
import cleaner    # noqa: F401 — side-effect import (đăng ký "cleaner")
import ai_agent   # noqa: F401 — side-effect import (đăng ký "analyzer")
import trend_agent # noqa: F401 — side-effect import (đăng ký "trend" → phân tích xu hướng)
import supabase_storage  # noqa: F401 — side-effect import (đăng ký "storage" → Supabase)
import telegram_agent # noqa: F401 — side-effect import (đăng ký "telegram")


def validate_topic(user_input: str) -> str | None:
    topic = user_input.strip()
    if not topic:
        return "Artificial Intelligence"
    essence = re.sub(r'[^a-zA-Z0-9\s]', '', topic).strip()
    if not essence:
        return None
    clean_topic = re.sub(r'[\\/*?:"<>|]', "", topic).strip()
    return clean_topic[:config.MAX_TOPIC_LENGTH]


async def run_pipeline(agents: list[BaseAgent], ctx: PipelineContext):
    """
    [FIX DIP] Nhận danh sách BaseAgent (abstraction), KHÔNG nhận concrete class.
    
    Nhờ đó, bạn có thể swap bất kỳ Agent nào mà KHÔNG sửa hàm này:
        - Thay StorageAgent bằng DatabaseStorageAgent? Được!
        - Thêm TelegramAgent vào cuối pipeline? Được!
    
    [FIX LSP] Vì execute() giờ có CÙNG chữ ký (ctx → ctx),
    ta có thể duyệt vòng lặp qua MỌI loại Agent một cách đồng nhất.
    """
    logging.info("=" * 60)
    logging.info(f"KHOI DONG CHU KY QUET: '{ctx.topic.upper()}'")
    logging.info("=" * 60)

    for agent in agents:
        try:
            ctx = await agent.execute(ctx)
            if not ctx.articles and isinstance(agent, BaseAgent):
                logging.warning(f"{agent.agent_name} tra ve 0 bai. Kiem tra nguon.")
        except Exception as e:
            logging.error(f"Loi tai {agent.agent_name}: {e}")
            return

    logging.info("=" * 60 + "\n")


async def main():
    """
    [FIX ASYNC] Toàn bộ main() giờ là async.
    Dùng asyncio.sleep() thay cho schedule + time.sleep().
    Loại bỏ dependency 'schedule', loại bỏ antipattern asyncio.run() trong sync wrapper.
    """
    env_path = os.path.join(backend_dir, ".env")
    load_dotenv(env_path)
    api_key = os.getenv("NEWS_API_KEY")
    gemini_api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        logging.error("Thieu NEWS_API_KEY trong file .env!")
        return
    if not gemini_api_key:
        logging.warning("Thieu GEMINI_API_KEY. Chuc nang AI se bi bo qua!")

    logging.info("AI TREND AGENT v3.1 (SOLID Edition)")

    # [CONTAINER] Đọc topic từ env var TOPIC (dùng trong Docker/K8s).
    # Nếu không có, fallback sang interactive stdin (dùng khi chạy local).
    env_topic = os.getenv("TOPIC", "").strip()
    if env_topic:
        target_topic = validate_topic(env_topic)
        if not target_topic:
            logging.error(f"TOPIC env var '{env_topic}' khong hop le! Su dung default.")
            target_topic = "Artificial Intelligence"
        logging.info(f"[CONTAINER MODE] Topic tu env: '{target_topic}'")
    else:
        target_topic = None
        while not target_topic:
            try:
                raw = input("\nMoi ban nhap tu khoa can tim: ")
            except (KeyboardInterrupt, EOFError):
                logging.info("Huy khoi dong. Tam biet!")
                return
            target_topic = validate_topic(raw)
            if not target_topic:
                logging.error("Tu khoa khong hop le. Vui long thu lai!")

    # Tạo pipeline context — chứa mọi thứ Agent cần
    ctx_template = PipelineContext(
        topic=target_topic, 
        api_key=api_key, 
        gemini_api_key=gemini_api_key or ""
    )

    # Tạo đội quân Agent qua Factory (Agent đã tự đăng ký nhờ decorator)
    agents: list[BaseAgent] = [
        AgentFactory.create("scraper"),
        AgentFactory.create("cleaner"),
        AgentFactory.create("analyzer"), # [Phase 4] Tích hợp bộ não AI
        AgentFactory.create("trend"),    # [Phase A] Phân tích xu hướng vĩ mô
        AgentFactory.create("storage"),  # Lưu vào Supabase cloud (supabase_storage)
        AgentFactory.create("telegram"), # [Phase 6] Gửi thông báo Telegram
    ]

    for agent in agents:
        logging.info(f"Da trien khai: {agent}")

    # Vòng lặp chính — FULL ASYNC, không cần thư viện schedule
    interval_seconds = config.SCHEDULE_INTERVAL_HOURS * 3600
    logging.info(f"AGENT TRUC CANH ({config.SCHEDULE_INTERVAL_HOURS} gio/lan)")
    logging.info("Nhan [Ctrl + C] de tat he thong.")

    # Chờ DNS/network sẵn sàng trong môi trường container (K8s pod start)
    startup_delay = int(os.getenv("STARTUP_DELAY_SECONDS", "0"))
    if startup_delay > 0:
        logging.info(f"Cho {startup_delay}s de DNS san sang...")
        await asyncio.sleep(startup_delay)

    try:
        while True:
            # Tạo context MỚI cho mỗi chu kỳ (tránh articles bị dồn từ chu kỳ trước)
            ctx = PipelineContext(
                topic=ctx_template.topic, 
                api_key=ctx_template.api_key,
                gemini_api_key=ctx_template.gemini_api_key
            )
            await run_pipeline(agents, ctx)
            logging.info(f"Ngu {config.SCHEDULE_INTERVAL_HOURS} gio roi quet tiep...")
            await asyncio.sleep(interval_seconds)
    except (KeyboardInterrupt, asyncio.CancelledError):
        logging.info("=" * 60)
        logging.info("DANG TAT HE THONG AN TOAN...")
        logging.info("=" * 60)


if __name__ == "__main__":
    if "--profile" in sys.argv:
        import cProfile
        import pstats
        import io
        logging.info("BAT DAU CHE DO PROFILING (Day 47)...")
        pr = cProfile.Profile()
        pr.enable()
        try:
            asyncio.run(main())
        except (KeyboardInterrupt, SystemExit):
            pass
        finally:
            pr.disable()
            s = io.StringIO()
            sortby = pstats.SortKey.CUMULATIVE
            ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
            ps.print_stats(30)
            logging.info("=" * 60)
            logging.info("KET QUA PROFILING (Top 30 ham tieu ton thoi gian nhat):")
            print(s.getvalue())
            logging.info("=" * 60)
    else:
        asyncio.run(main())
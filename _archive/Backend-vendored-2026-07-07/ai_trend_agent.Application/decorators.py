"""
=====================================================================
[DAY 33-34] DECORATORS — Gắn "Tracker" cho AI
=====================================================================
Mục đích:
- Đo lường thời gian (Timer) AI xử lý mà không cần sửa code gốc.
- Tự động ghi nhật ký (Logger) khi gọi API bên thứ 3.
=====================================================================
"""
import time
import logging
from functools import wraps

logger = logging.getLogger("AI_Tracker")

def ai_timer(func):
    """
    [Day 33] Decorator đo thời gian chạy của hàm bất đồng bộ.
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        result = await func(*args, **kwargs)
        end_time = time.perf_counter()
        duration = end_time - start_time
        logger.info(f"⏱️ [Timer] {func.__name__} hoan thanh trong {duration:.2f} giay.")
        return result
    return wrapper

def ai_logger(func):
    """
    [Day 34] Decorator tự động ghi log trước và sau khi gọi hàm.
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        logger.info(f"🤖 [AI-Start] Dang goi model AI thong qua '{func.__name__}'...")
        try:
            result = await func(*args, **kwargs)
            logger.info(f"✅ [AI-Success] Mo hinh AI da tra ve ket qua.")
            return result
        except Exception as e:
            logger.error(f"❌ [AI-Failed] Loi khi goi mo hinh: {e}")
            raise
    return wrapper

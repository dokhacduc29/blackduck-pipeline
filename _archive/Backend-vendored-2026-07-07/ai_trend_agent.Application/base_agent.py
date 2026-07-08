"""
=====================================================================
[DAY 27] BASE AGENT — Nền tảng trừu tượng + Factory tự đăng ký
=====================================================================
FIX OCP (Open/Closed Principle):
    Vấn đề cũ: AgentFactory._registry phải SỬA tay mỗi khi thêm Agent mới.
    Giải pháp: Dùng decorator @AgentFactory.register("tên") — Agent TỰ ĐĂNG KÝ.
    Factory không cần biết Agent nào tồn tại. Thêm Agent mới = 0 dòng sửa Factory.
=====================================================================
"""
from abc import ABC, abstractmethod
import logging
from models import PipelineContext


class AgentFactory:
    """
    [DAY 29 + FIX OCP] Nhà máy sản xuất Agent — Phiên bản tự đăng ký.
    
    CÁCH DÙNG (Decorator-based Registration):
        @AgentFactory.register("scraper")
        class ScraperAgent(BaseAgent):
            ...
        
        # Tạo agent:
        agent = AgentFactory.create("scraper", api_key="abc", topic="AI")
    
    TẠI SAO TỐT HƠN BẢN CŨ?
        Bản cũ: Thêm TelegramAgent → phải mở file main.py, sửa _registry → Vi phạm OCP.
        Bản mới: Thêm TelegramAgent → chỉ cần viết @AgentFactory.register("telegram")
                 ở đầu class mới. Factory TỰ ĐỘNG biết. main.py KHÔNG SỬA GÌ!
    """
    _registry: dict[str, type] = {}

    @classmethod
    def register(cls, name: str):
        """
        Decorator để Agent TỰ ĐĂNG KÝ vào nhà máy.
        
        Khi Python đọc dòng @AgentFactory.register("scraper") ở đầu class,
        nó tự động chạy hàm này và ghi tên "scraper" → ScraperAgent vào sổ đăng ký.
        """
        def decorator(agent_class):
            cls._registry[name] = agent_class
            return agent_class
        return decorator

    @classmethod
    def create(cls, agent_type: str, **kwargs):
        """Tạo Agent theo tên đã đăng ký."""
        agent_class = cls._registry.get(agent_type)
        if not agent_class:
            raise ValueError(
                f"Không tìm thấy Agent: '{agent_type}'. "
                f"Hợp lệ: {list(cls._registry.keys())}"
            )
        return agent_class(**kwargs)


class BaseAgent(ABC):
    """
    [DAY 21-27] Bản thiết kế trừu tượng — "Hiến pháp" của mọi Agent.
    """

    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self._logger = logging.getLogger(agent_name)

    @abstractmethod
    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        """
        [FIX LSP] Chữ ký THỐNG NHẤT: Mọi Agent đều nhận PipelineContext, trả PipelineContext.
        
        Giờ đây bạn CÓ THỂ viết code đa hình thật sự:
            agents = [scraper, cleaner, storage]
            for agent in agents:
                ctx = await agent.execute(ctx)  # Chạy được với MỌI loại Agent!
        """
        pass

    def log_info(self, message: str):
        self._logger.info(f"[{self.agent_name}] {message}")

    def log_warning(self, message: str):
        self._logger.warning(f"[{self.agent_name}] {message}")

    def log_error(self, message: str):
        self._logger.error(f"[{self.agent_name}] {message}")

    def __str__(self) -> str:
        return f"Agent: {self.agent_name} (Sẵn sàng)"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(agent_name='{self.agent_name}')"

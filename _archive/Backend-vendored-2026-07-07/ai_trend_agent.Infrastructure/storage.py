"""
=====================================================================
STORAGE AGENT — Lưu trữ dữ liệu (BẢN SỬA BUGS + LSP + OCP + THREADING)
=====================================================================
FIX LIST:
    - [BUG] STT counter: Dùng max(STT) từ file thay vì đếm title
    - [LSP] execute(ctx: PipelineContext) → PipelineContext
    - [OCP] @AgentFactory.register("storage")
    - [SMELL] Magic numbers → Import từ config.py
    - [DAY 42] Threading: Tách tác vụ đọc/ghi file CSV sang Thread riêng
               để không gây ách tắc (block) vòng lặp sự kiện asyncio.
=====================================================================
"""
import csv
import os
import asyncio
from collections import defaultdict
from base_agent import BaseAgent, AgentFactory
from models import Article, PipelineContext
import config


@AgentFactory.register("storage")
class StorageAgent(BaseAgent):
    """Lính hậu cần — Lưu trữ dữ liệu xuống CSV."""

    def __init__(self, **kwargs):
        super().__init__("StorageAgent")

    def _generate_safe_filename(self, topic: str) -> str:
        import re
        safe_name = re.sub(r'[\\/*?:"<>|]', "", topic)
        safe_name = safe_name.strip().replace(" ", "_").lower()
        if not safe_name:
            return "unknown_topic_news.csv"
        return f"{safe_name}_news.csv"

    def _load_existing_data(self, filepath: str) -> tuple[set[str], int]:
        """
        [FIX BUG STT] Đọc file cũ, trả về:
            - Set các title đã lưu (để lọc trùng)
            - Giá trị STT lớn nhất (để đánh số tiếp theo CHÍNH XÁC)
        """
        existing_titles: set[str] = set()
        max_stt: int = 0

        if os.path.isfile(filepath):
            try:
                with open(filepath, mode="r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        if "Tieu_De" in row:
                            existing_titles.add(row["Tieu_De"].strip())
                        if "STT" in row:
                            try:
                                stt = int(row["STT"])
                                max_stt = max(max_stt, stt)
                            except ValueError:
                                pass
            except Exception as e:
                self.log_error(f"Lỗi đọc file cũ: {e}")

        return existing_titles, max_stt

    def _print_analytics(self, new_data: list[Article]):
        source_stats: dict[str, int] = defaultdict(int)
        tag_stats: dict[str, int] = defaultdict(int)
        for art in new_data:
            source_stats[art.source] += 1
            for tag in art.tags:
                tag_stats[tag] += 1

        self.log_info("Thong ke nguon tin moi:")
        for source, count in source_stats.items():
            self.log_info(f"   [Nguon] {source}: {count} bai")
        if tag_stats:
            for tag, count in tag_stats.items():
                self.log_info(f"   [Tag] {tag}: xuat hien {count} lan")

    def _write_csv_sync(self, filepath: str, file_exists: bool, new_data: list[Article], max_stt: int):
        """Hàm thực thi ghi file CSV đồng bộ được gọi qua Threading."""
        try:
            with open(filepath, mode="a", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=config.CSV_FIELDNAMES)
                if not file_exists:
                    writer.writeheader()

                for i, art in enumerate(new_data, max_stt + 1):
                    writer.writerow({
                        "STT": i,
                        "Tieu_De": art.title,
                        "Nguon": art.source,
                        "Ngay": art.date,
                        "Tags": ", ".join(art.tags),
                        "Tom_Tat": art.summary,
                        "Tam_Ly": art.sentiment.value if hasattr(art.sentiment, "value") else str(art.sentiment),
                        "Link_Bai": art.url,
                    })
            self.log_info(f"Da noi them {len(new_data)} tin MOI vao: {filepath} (qua Threading)")
        except Exception as e:
            self.log_error(f"Loi ghi file CSV: {e}")

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        """
        [FIX LSP + DAY 42 THREADING] Chữ ký thống nhất.
        Offload các tác vụ I/O file nặng sang luồng riêng qua asyncio.to_thread.
        """
        os.makedirs(config.OUTPUT_DIR, exist_ok=True)
        filepath = os.path.join(config.OUTPUT_DIR, self._generate_safe_filename(ctx.topic))
        file_exists = os.path.isfile(filepath)

        # Đọc lịch sử + lấy STT max CHÍNH XÁC qua Threading (Day 42)
        existing_titles, max_stt = await asyncio.to_thread(self._load_existing_data, filepath)

        # Lọc tin mới
        new_data = [art for art in ctx.articles if art.title.strip() not in existing_titles]

        if not new_data:
            self.log_info("Khong co tin moi. Du lieu cu giu nguyen an toan.")
            return ctx

        self._print_analytics(new_data)

        # Ghi nối tiếp sang Thread riêng tránh block Event Loop (Day 42)
        await asyncio.to_thread(self._write_csv_sync, filepath, file_exists, new_data, max_stt)

        return ctx

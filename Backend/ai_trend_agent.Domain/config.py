"""
=====================================================================
[LUẬT THÉP L09] CONFIG — Tập trung MỌI hằng số / Magic Numbers
=====================================================================
TẠI SAO CẦN FILE NÀY?
    Trước đây: timeout=10.0, limit=5, pageSize=10 nằm rải rác khắp nơi.
    Nếu muốn đổi timeout thành 15s, bạn phải mò từng file → Dễ sót, dễ bug.
    
    Giờ: Tất cả nằm ở ĐÂY. Đổi 1 chỗ = áp dụng toàn hệ thống.
=====================================================================
"""

# --- SCRAPER CONFIG ---
REQUEST_TIMEOUT: float = 10.0       # Giây chờ tối đa cho mỗi API call
NEWSAPI_PAGE_SIZE: int = 10          # Số bài tối đa lấy từ NewsAPI mỗi lần
REDDIT_LIMIT: int = 5               # Số bài tối đa lấy từ Reddit
REDDIT_SUBREDDIT: str = "ArtificialIntelligence"  # Tên subreddit ĐÚNG CHÍNH TẢ
GOOGLE_RSS_LIMIT: int = 5           # Số bài tối đa lấy từ Google News RSS
REDDIT_USER_AGENT: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
REDDIT_OAUTH_TOKEN_URL: str = "https://www.reddit.com/api/v1/access_token"  # Endpoint lấy access token
REDDIT_OAUTH_API_BASE: str = "https://oauth.reddit.com"  # API base khi đã xác thực OAuth

# --- RETRY CONFIG ---
GEMINI_RETRY_MAX: int = 3            # Số lần thử lại tối đa khi Gemini 503
GEMINI_RETRY_BASE_DELAY: float = 2.0 # Delay ban đầu (giây), tăng gấp đôi mỗi lần

# --- PIPELINE CONFIG ---
SCHEDULE_INTERVAL_HOURS: int = 4    # Chu kỳ quét tự động (giờ)
MAX_TOPIC_LENGTH: int = 50          # Độ dài tối đa từ khóa tìm kiếm

# --- AI CONFIG (PHASE 4) ---
GEMINI_MODEL_NAME: str = "gemini-2.5-flash" # Mô hình tối ưu tốc độ/chi phí
AI_MAX_ARTICLES_PER_BATCH: int = 15         # Số bài tối đa gửi AI mỗi lần để tránh quá tải

# --- AI CLEANER CONFIG (PHASE B) ---
CLEANER_AI_MODEL: str = "gemini-2.5-flash"   # Model chấm điểm liên quan + gán tag
CLEANER_RELEVANCE_THRESHOLD: int = 4         # Bài < ngưỡng này bị loại (lạc đề)
CLEANER_AI_BATCH_SIZE: int = 30              # Số bài tối đa gửi AI mỗi chu kỳ

# --- TREND SYNTHESIS CONFIG (PHASE A) ---
TREND_MODEL_NAME: str = "gemini-2.5-flash"  # Mô hình dùng cho phân tích xu hướng
TREND_MAX_ARTICLES: int = 30                # Số bài tối đa đưa vào prompt phân tích xu hướng
TREND_MIN_ARTICLES: int = 3                 # Dưới ngưỡng này thì bỏ qua (không đủ để rút xu hướng)
TREND_COUNT: int = 5                        # Số xu hướng tối đa AI cần rút ra

# --- TELEGRAM CONFIG (PHASE 6) ---
TELEGRAM_API_BASE: str = "https://api.telegram.org"  # Endpoint gốc Bot API
TELEGRAM_MAX_MESSAGE_LENGTH: int = 4000  # Giới hạn an toàn (Telegram cap cứng 4096)
TELEGRAM_PARSE_MODE: str = "HTML"        # HTML dễ escape hơn Markdown
TELEGRAM_SEND_DELAY: float = 0.5         # Giây nghỉ giữa các chunk để tránh rate limit 429

# --- STORAGE CONFIG ---
OUTPUT_DIR: str = "data"             # Thư mục lưu file CSV
CSV_FIELDNAMES: list[str] = ["STT", "Tieu_De", "Nguon", "Ngay", "Tags", "Tom_Tat", "Tam_Ly", "Link_Bai"]

"""
Application Constants
"""

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
MAX_CONCURRENT_SEARCHES = 20
CHUNK_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB streaming chunks for Telegram
TELEGRAM_MAX_FILE_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB Telegram bot API limit

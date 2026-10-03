"""
Application Constants
"""

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
MAX_CONCURRENT_SEARCHES = 20
CHUNK_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB streaming chunks for Telegram
# Searched per drive: recordings (video/audio/transcript) + documents.
SEARCH_EXTENSIONS = [
    ".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv",
    ".m4a", ".mp3", ".wav", ".wma", ".vtt",
    ".pdf", ".pptx", ".ppt",
    ".docx", ".doc", ".xlsx", ".zip", ".rar",
]
VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv",
    ".m4a", ".mp3", ".wav", ".wma",
}

# Backward-compatible alias for helper.fast_transfer
from helper.fast_transfer import fast_download, get_media_session, CHUNK_SIZE, CONCURRENT_WORKERS, BUFFER_SIZE

__all__ = ["fast_download", "get_media_session", "CHUNK_SIZE", "CONCURRENT_WORKERS", "BUFFER_SIZE"]

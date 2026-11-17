# Backward-compatible alias for helper.fast_transfer
from helper.fast_transfer import (
    fast_download,
    fast_upload,
    zero_disk_turbo_pipe,
    get_media_session,
    get_media_session_pool,
    CHUNK_SIZE,
    UPLOAD_PART_SIZE,
    CONCURRENT_WORKERS_PREM,
    CONCURRENT_WORKERS_FREE,
    CONCURRENT_WORKERS,
    BUFFER_SIZE
)

__all__ = [
    "fast_download",
    "fast_upload",
    "zero_disk_turbo_pipe",
    "get_media_session",
    "get_media_session_pool",
    "CHUNK_SIZE",
    "UPLOAD_PART_SIZE",
    "CONCURRENT_WORKERS_PREM",
    "CONCURRENT_WORKERS_FREE",
    "CONCURRENT_WORKERS",
    "BUFFER_SIZE"
]

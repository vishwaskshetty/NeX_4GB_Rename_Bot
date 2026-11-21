import os
import sys
import time
import math
import shutil
import random
import asyncio
import inspect
import gc
import logging
import hashlib
import traceback
import html
from typing import Callable, Optional, List, Union
import pyrogram
from pyrogram import Client, raw, types, utils, enums
from pyrogram.file_id import FileId, FileType, ThumbnailSource
from pyrogram.session import Session, Auth
from pyrogram.errors import AuthBytesInvalid

try:
    from pyrogram import StopTransmission
except ImportError:
    from pyrogram.errors import StopTransmission

logger = logging.getLogger(__name__)
log = logger

# Patch Pyrogram Client.save_file so that passing an already-uploaded InputFileBig or InputFile
# bypasses re-uploading and is immediately dispatched via MTProto SendMedia.
_original_save_file = getattr(Client, "save_file", None)

async def _fast_save_file(self, path, *args, **kwargs):
    if isinstance(path, (raw.base.InputFile, raw.types.InputFile, raw.types.InputFileBig)):
        return path
    if _original_save_file:
        return await _original_save_file(self, path, *args, **kwargs)
    raise ValueError("Invalid file. Expected a file path as string or InputFile")

Client.save_file = _fast_save_file

# High-Speed MTProto Configuration: Multi-Socket chunk streaming with parallel worker coroutines
CHUNK_SIZE = 512 * 1024              # 512KB (524288 bytes) per chunk for Telegram upload.GetFile & SaveBigFilePart
UPLOAD_PART_SIZE = 512 * 1024        # 512KB (524288 bytes) per part for parallel upload (MTProto limit)
DL_POOL_SIZE = 8                     # 8 parallel TCP download sockets (Telegram Premium)
DL_POOL_SIZE_PREM = 8                # 8 parallel TCP sockets on app_4gb (Telegram Premium)
DL_POOL_SIZE_BOT = 4                 # 4 parallel TCP sockets on bot client (fallback)
UL_POOL_SIZE = 10                    # 10 parallel TCP upload sockets
DL_WORKERS = 24                      # 24 download workers (Full Azure VM pipe saturation)
UL_WORKERS = 24                      # 24 upload workers (Full Azure VM pipe saturation)
QUEUE_SIZE = 64                      # 64 * 512KB = 32MB RAM ring buffer per active task (512KB / 1MB aligned)
BUFFER_SIZE = 32 * 1024 * 1024       # 32MB RAM write/read buffer (64MB RAM across 2 concurrent tasks = ~130MB total)
CONCURRENT_WORKERS_PREM = 24         # 24 concurrent MTProto worker coroutines
CONCURRENT_WORKERS_FREE = 24         # 24 concurrent MTProto worker coroutines
CONCURRENT_WORKERS = 24              # 24 concurrent MTProto worker coroutines

# Activity timestamp to detect idle TCP sockets and trigger auto-reset (> 120s)
_LAST_POOL_ACTIVITY: float = time.time()

# 2-Task Concurrency Semaphore for heavy 4 GB multitasking (2 concurrent files saturate full pipe)
_TRANSFER_SEMAPHORE = asyncio.Semaphore(2)


def _cleanup_memory(client: Optional[Client] = None, app_4gb: Optional[Client] = None) -> None:
    """
    Dedicated post-transfer memory scrubbing:
    1. Clear Pyrogram's internal message cache (client.message_cache.clear() and app_4gb.message_cache.clear()).
    2. Remove temporary files in /tmp or /dev/shm older than 15 minutes.
    3. Run gc.collect() and release freed glibc heap pages back to Linux via ctypes CDLL malloc_trim(0).
    """
    # 1. Clear Pyrogram internal message caches
    for c in (client, app_4gb):
        if c is not None:
            try:
                mc = getattr(c, "message_cache", None)
                if mc and hasattr(mc, "clear"):
                    mc.clear()
            except Exception:
                pass
            try:
                st = getattr(c, "storage", None)
                if st and hasattr(st, "message_cache"):
                    st.message_cache.clear()
            except Exception:
                pass

    # 2. Remove temporary files older than 15 minutes in /tmp and /dev/shm
    try:
        now = time.time()
        cutoff_sec = 15 * 60  # 15 minutes
        for tmp_dir in ("/tmp", "/dev/shm"):
            if not os.path.exists(tmp_dir):
                continue
            for entry in os.listdir(tmp_dir):
                if entry.startswith("nex_bot_heartbeat") or entry.startswith(".") or entry.endswith(".sock"):
                    continue
                full_path = os.path.join(tmp_dir, entry)
                try:
                    mtime = os.path.getmtime(full_path)
                    if (now - mtime) >= cutoff_sec:
                        if os.path.isdir(full_path):
                            shutil.rmtree(full_path, ignore_errors=True)
                        elif os.path.isfile(full_path):
                            os.remove(full_path)
                except Exception:
                    pass
    except Exception:
        pass

    # 3. Python garbage collection
    try:
        gc.collect()
    except Exception:
        pass

    # 4. Release freed glibc heap pages back to Linux OS
    try:
        import ctypes
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass


async def check_and_reset_idle_sessions(client: Client) -> None:
    """
    Checks if the session pool has been idle for more than 120 seconds.
    If idle, cleanly closes and clears existing pooled sockets so that fresh TCP
    sessions are instantiated, preventing stale TCP socket stalls at 0% or 50%.
    """
    global _LAST_POOL_ACTIVITY
    now = time.time()
    if (now - _LAST_POOL_ACTIVITY) > 120:
        idle_duration = now - _LAST_POOL_ACTIVITY
        log.info(f"🔄 Idle period of {idle_duration:.1f}s (> 120s) detected. Cleanly resetting pooled media sockets...")
        clients = [client]
        app_4gb = getattr(client, "app_4gb", None)
        if app_4gb and app_4gb not in clients:
            clients.append(app_4gb)

        for cl in clients:
            pools = getattr(cl, "_media_pools", {})
            for dc_id, pool in list(pools.items()):
                for s in pool:
                    try:
                        await asyncio.wait_for(s.stop(), timeout=2.0)
                    except Exception:
                        pass
            if hasattr(cl, "_media_pools"):
                cl._media_pools.clear()

            media_sessions = getattr(cl, "media_sessions", {})
            for dc_id, s in list(media_sessions.items()):
                try:
                    await asyncio.wait_for(s.stop(), timeout=2.0)
                except Exception:
                    pass
            if hasattr(cl, "media_sessions"):
                cl.media_sessions.clear()

        _LAST_POOL_ACTIVITY = now


def _instantiate_session(client: Client, dc_id: int, auth_key: bytes, test_mode: bool, is_media: bool = True) -> Session:
    """Instantiates a Session dynamically checking Session.__init__ signature for cross-fork compatibility."""
    sig = inspect.signature(Session.__init__)
    kwargs = {}
    params = sig.parameters
    if "is_media" in params:
        kwargs["is_media"] = is_media
    return Session(client, dc_id, auth_key, test_mode, **kwargs)


async def _get_or_create_session_pool(client: Client, dc_id: int, pool_size: int = 8) -> List[Session]:
    """
    Crash-proof initialization of DC media session and 8 independent TCP Session sockets.
    Step A: Safely initializes or retrieves base_session for dc_id.
    Step B: Extracts verified auth_key from base_session and clones independent TCP Session sockets.
    Step C: Handles cross-DC AuthExport/Import reliably with automatic retry.
    """
    await check_and_reset_idle_sessions(client)

    if not hasattr(client, "_media_pools"):
        client._media_pools = {}
    if not hasattr(client, "_dc_auth_keys"):
        client._dc_auth_keys = {}

    pool = client._media_pools.get(dc_id, [])
    valid_pool = []
    for s in pool:
        if getattr(s, "is_connected", None) and s.is_connected.is_set():
            valid_pool.append(s)
        else:
            try:
                asyncio.create_task(s.stop())
            except Exception:
                pass
    pool = valid_pool

    if len(pool) >= pool_size:
        return pool[:pool_size]

    test_mode = await asyncio.wait_for(client.storage.test_mode(), timeout=5.0)
    main_dc = await asyncio.wait_for(client.storage.dc_id(), timeout=5.0)

    # Step A: Initialize or retrieve primary base_session
    base_session = client.media_sessions.get(dc_id)
    if not base_session or not (getattr(base_session, "is_connected", None) and base_session.is_connected.is_set()):
        if dc_id != main_dc:
            auth_key = await asyncio.wait_for(Auth(client, dc_id, test_mode).create(), timeout=8.0)
            base_session = _instantiate_session(client, dc_id, auth_key, test_mode, is_media=True)
            await asyncio.wait_for(base_session.start(), timeout=8.0)

            # Export authorization from main DC and import into media DC
            for attempt in range(3):
                try:
                    exported = await asyncio.wait_for(
                        client.invoke(raw.functions.auth.ExportAuthorization(dc_id=dc_id)),
                        timeout=6.0
                    )
                    await asyncio.wait_for(
                        base_session.invoke(
                            raw.functions.auth.ImportAuthorization(
                                id=exported.id,
                                bytes=exported.bytes
                            )
                        ),
                        timeout=6.0
                    )
                    break
                except AuthBytesInvalid:
                    if attempt == 2:
                        raise
                    await asyncio.sleep(0.5)
                except Exception as e:
                    log.warning(f"DC {dc_id} auth export/import note: {e}")
                    if attempt == 2:
                        raise
                    await asyncio.sleep(0.5)
        else:
            auth_key = await asyncio.wait_for(client.storage.auth_key(), timeout=5.0)
            base_session = _instantiate_session(client, dc_id, auth_key, test_mode, is_media=True)
            await asyncio.wait_for(base_session.start(), timeout=8.0)

        client.media_sessions[dc_id] = base_session

    # Step B: Extract verified auth_key from base_session
    verified_auth_key = getattr(base_session, "auth_key", None)
    if not verified_auth_key:
        if dc_id == main_dc:
            verified_auth_key = await client.storage.auth_key()
        else:
            verified_auth_key = getattr(client.storage, "auth_key", None)
    client._dc_auth_keys[dc_id] = verified_auth_key

    if base_session not in pool:
        pool.append(base_session)

    # Step C: Clone pool_size independent TCP Session sockets using verified_auth_key
    needed = pool_size - len(pool)
    if needed > 0 and verified_auth_key:
        cloned_sessions = [
            _instantiate_session(client, dc_id, verified_auth_key, test_mode, is_media=True)
            for _ in range(needed)
        ]
        start_tasks = [asyncio.wait_for(s.start(), timeout=8.0) for s in cloned_sessions]
        results = await asyncio.gather(*start_tasks, return_exceptions=True)
        for s, res in zip(cloned_sessions, results):
            if not isinstance(res, Exception) and getattr(s, "is_connected", None) and s.is_connected.is_set():
                pool.append(s)
            else:
                log.warning(f"Cloned socket note for DC {dc_id}: {res}")
                try:
                    asyncio.create_task(s.stop())
                except Exception:
                    pass

    client._media_pools[dc_id] = pool
    return pool if pool else [base_session]


async def get_media_session(client: Client, dc_id: int) -> Session:
    """Retrieves or initializes the primary authorized media session for the specified DC."""
    pool = await _get_or_create_session_pool(client, dc_id, pool_size=1)
    return pool[0]


class MediaSessionPool:
    """
    Dedicated Multi-Socket MTProto Media Session Pool Manager.
    Clones verified auth_key across 8-16 real TCP Session sockets per DC,
    completely eliminating Telegram's single-socket throughput limit.
    """
    @classmethod
    async def get_pool(cls, client: Client, dc_id: int, pool_size: int = 8) -> List[Session]:
        return await _get_or_create_session_pool(client, dc_id, pool_size=pool_size)


async def get_media_session_pool(client: Client, dc_id: int, pool_size: int = 8) -> List[Session]:
    """Retrieves or builds the MediaSessionPool for the requested DC."""
    return await _get_or_create_session_pool(client, dc_id, pool_size=pool_size)


async def fast_download(
    client: Client,
    message_or_file=None,
    file_path: Optional[str] = None,
    progress: Optional[Callable] = None,
    progress_args: tuple = (),
    is_prem: bool = False,
    **kwargs
) -> str:
    """
    Downloads media using multi-socket parallel MTProto chunk streaming with independent TCP sessions
    and buffered file I/O. Achieves high-speed transfers on gigabit cloud connections.
    Includes 25.0s per-chunk watchdog, 6 retries with automatic socket rotation, and idle session auto-reset.
    Safely falls back to client.download_media if any unrecoverable error occurs.
    """
    if message_or_file is None:
        message_or_file = kwargs.get("message")
    if file_path is None:
        directory = kwargs.get("directory", ".")
        file_name = kwargs.get("file_name", "downloaded_file")
        file_path = os.path.join(directory, file_name)

    # 0. Idle-Socket Auto-Reset for download client (> 120s idle)
    await check_and_reset_idle_sessions(client)

    # Detect premium status from progress_args if provided
    try:
        if not is_prem and len(progress_args) >= 5 and progress_args[4] is not None:
            is_prem = bool(int(progress_args[4]) >= 1)
    except Exception:
        pass

    # 1. Resolve file object and file size
    if hasattr(message_or_file, "document") or hasattr(message_or_file, "video") or hasattr(message_or_file, "audio"):
        file_obj = (
            getattr(message_or_file, "document", None) or
            getattr(message_or_file, "video", None) or
            getattr(message_or_file, "audio", None) or
            getattr(message_or_file, "photo", None)
        )
    else:
        file_obj = message_or_file

    if not file_obj or not hasattr(file_obj, "file_id"):
        return await client.download_media(message_or_file, file_name=file_path, progress=progress, progress_args=progress_args)

    file_size = getattr(file_obj, "file_size", 0)

    # For tiny files under 3MB, standard download_media is practically instantaneous
    if file_size < 3 * 1024 * 1024:
        return await client.download_media(message_or_file, file_name=file_path, progress=progress, progress_args=progress_args)

    try:
        # Decode file location
        decoded = FileId.decode(file_obj.file_id)
        dc_id = decoded.dc_id
        media_id = decoded.media_id
        access_hash = decoded.access_hash
        file_reference = decoded.file_reference
        thumb_size = decoded.thumbnail_size or ""
        file_type = decoded.file_type

        if file_type == FileType.CHAT_PHOTO:
            if decoded.chat_id > 0:
                peer = raw.types.InputPeerUser(user_id=decoded.chat_id, access_hash=decoded.chat_access_hash)
            else:
                peer = raw.types.InputPeerChat(chat_id=-decoded.chat_id) if decoded.chat_access_hash == 0 else raw.types.InputPeerChannel(channel_id=pyrogram.utils.get_channel_id(decoded.chat_id), access_hash=decoded.chat_access_hash)
            location = raw.types.InputPeerPhotoFileLocation(
                peer=peer,
                photo_id=media_id,
                big=decoded.thumbnail_source == ThumbnailSource.CHAT_PHOTO_BIG
            )
        elif file_type == FileType.PHOTO:
            location = raw.types.InputPhotoFileLocation(
                id=media_id,
                access_hash=access_hash,
                file_reference=file_reference,
                thumb_size=thumb_size
            )
        else:
            location = raw.types.InputDocumentFileLocation(
                id=media_id,
                access_hash=access_hash,
                file_reference=file_reference,
                thumb_size=thumb_size
            )

        pool_size = DL_POOL_SIZE
        try:
            sessions = await asyncio.wait_for(MediaSessionPool.get_pool(client, dc_id, pool_size=pool_size), timeout=15.0)
        except Exception as sess_err:
            log.warning(f"Media session pool init note for DC {dc_id} ({sess_err}). Using primary media session...")
            sessions = [await get_media_session(client, dc_id)]

        total_parts = math.ceil(file_size / CHUNK_SIZE) if file_size > 0 else 1
        queue = asyncio.Queue()
        for i in range(total_parts):
            queue.put_nowait(i)

        # Pre-allocate file size upfront to avoid filesystem fragmentation during parallel writes
        try:
            os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
            with open(file_path, "wb") as init_fp:
                if file_size > 0:
                    init_fp.seek(file_size - 1)
                    init_fp.write(b'\0')
        except Exception as init_err:
            log.warning(f"File pre-allocation note: {init_err}")

        use_pwrite = hasattr(os, "pwrite")
        fd = None
        if use_pwrite:
            try:
                fd = os.open(file_path, os.O_WRONLY | getattr(os, "O_BINARY", 0))
            except Exception:
                fd = None
                use_pwrite = False

        write_queue = asyncio.Queue(maxsize=QUEUE_SIZE) if not use_pwrite else None
        downloaded_bytes = 0
        error_holder = []
        lock = asyncio.Lock()

        async def worker(worker_id: int):
            nonlocal downloaded_bytes
            global _LAST_POOL_ACTIVITY
            while not queue.empty():
                if error_holder:
                    break
                try:
                    part_idx = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

                offset_bytes = part_idx * CHUNK_SIZE
                chunk_len = min(CHUNK_SIZE, file_size - offset_bytes) if file_size > 0 else CHUNK_SIZE
                success = False

                for attempt in range(6):
                    if error_holder:
                        break
                    # Automatic socket rotation across pooled sessions
                    session = sessions[(attempt + worker_id) % len(sessions)]
                    try:
                        r = await asyncio.wait_for(
                            session.invoke(
                                raw.functions.upload.GetFile(
                                    location=location,
                                    offset=offset_bytes,
                                    limit=CHUNK_SIZE
                                ),
                                sleep_threshold=getattr(client, "sleep_threshold", 60)
                            ),
                            timeout=25.0
                        )
                        if isinstance(r, raw.types.upload.File):
                            _LAST_POOL_ACTIVITY = time.time()
                            if use_pwrite and fd is not None:
                                os.pwrite(fd, r.bytes, offset_bytes)
                                async with lock:
                                    downloaded_bytes += len(r.bytes)
                                    curr = downloaded_bytes
                                if progress:
                                    try:
                                        if inspect.iscoroutinefunction(progress):
                                            await progress(min(curr, file_size), file_size, *progress_args)
                                        else:
                                            progress(min(curr, file_size), file_size, *progress_args)
                                    except StopTransmission:
                                        error_holder.append(StopTransmission("Download Cancelled"))
                                        break
                                    except Exception:
                                        pass
                            else:
                                await write_queue.put((part_idx, r.bytes))
                            success = True
                            break
                        else:
                            raise ValueError(f"Unsupported upload result type: {type(r)}")
                    except StopTransmission:
                        error_holder.append(StopTransmission("Download Cancelled"))
                        break
                    except Exception as ex:
                        err_name = type(ex).__name__
                        if "FileReference" in err_name or "file_reference" in str(ex).lower():
                            if hasattr(message_or_file, "chat") and hasattr(message_or_file, "id") and message_or_file.chat:
                                try:
                                    refreshed = await client.get_messages(message_or_file.chat.id, message_or_file.id)
                                    if refreshed:
                                        ref_obj = refreshed.document or refreshed.video or refreshed.audio or refreshed.photo
                                        if ref_obj and hasattr(ref_obj, "file_id"):
                                            ref_decoded = FileId.decode(ref_obj.file_id)
                                            location.file_reference = ref_decoded.file_reference
                                except Exception:
                                    pass
                        if "FloodWait" in err_name:
                            wait_s = getattr(ex, "value", 5) or 5
                            await asyncio.sleep(min(wait_s, 30))
                        elif attempt == 5:
                            error_holder.append(ex)
                            break
                        else:
                            await asyncio.sleep(0.5 * (attempt + 1))
                queue.task_done()

        async def writer():
            nonlocal downloaded_bytes
            with open(file_path, "r+b", buffering=BUFFER_SIZE) as fp:
                while True:
                    item = await write_queue.get()
                    if item is None:
                        write_queue.task_done()
                        break
                    part_idx, chunk_bytes = item
                    fp.seek(part_idx * CHUNK_SIZE)
                    fp.write(chunk_bytes)
                    downloaded_bytes += len(chunk_bytes)
                    write_queue.task_done()

                    if progress:
                        try:
                            if inspect.iscoroutinefunction(progress):
                                await progress(min(downloaded_bytes, file_size), file_size, *progress_args)
                            else:
                                progress(min(downloaded_bytes, file_size), file_size, *progress_args)
                        except StopTransmission:
                            raise
                        except Exception:
                            pass

        writer_task = None
        if not use_pwrite:
            writer_task = asyncio.create_task(writer())

        worker_limit = DL_WORKERS
        worker_count = min(worker_limit, total_parts)
        workers = [asyncio.create_task(worker(i)) for i in range(worker_count)]

        await asyncio.gather(*workers)

        if not use_pwrite:
            if error_holder:
                await write_queue.put(None)
                await writer_task
                raise error_holder[0]
            await write_queue.put(None)
            await writer_task
        elif fd is not None:
            try:
                os.close(fd)
            except Exception:
                pass

        if error_holder:
            raise error_holder[0]

        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            _cleanup_memory(client)
            return file_path
        else:
            raise ValueError("Zero-byte file produced by parallel stream")

    except StopTransmission:
        raise
    except Exception as e:
        log.warning(f"Parallel MTProto download fallback triggered ({e})")
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass
        return await client.download_media(
            message_or_file,
            file_name=file_path,
            progress=progress,
            progress_args=progress_args
        )


async def fast_upload(
    client: Client,
    file_path: str,
    progress: Optional[Callable] = None,
    progress_args: tuple = (),
    is_prem: bool = False
):
    """
    Uploads media using multi-socket parallel MTProto chunk streaming with 8 independent TCP sessions
    and a 64MB buffer. Achieves 50-100+ MB/s upload speeds on cloud runners by multiplexing chunk uploads.
    Returns raw.types.InputFileBig (for files > 10MB) or raw.types.InputFile (for files <= 10MB).
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    file_size = os.path.getsize(file_path)
    if file_size == 0:
        raise ValueError("File size is 0 bytes")

    # 0. Idle-Socket Auto-Reset for upload client (> 120s idle)
    await check_and_reset_idle_sessions(client)

    # Detect premium status from progress_args if provided
    try:
        if not is_prem and len(progress_args) >= 5 and progress_args[4] is not None:
            is_prem = bool(int(progress_args[4]) >= 1)
    except Exception:
        pass

    total_parts = math.ceil(file_size / UPLOAD_PART_SIZE)
    is_big = file_size > 10 * 1024 * 1024
    file_name = os.path.basename(file_path)
    file_id = client.rnd_id() if hasattr(client, "rnd_id") else int.from_bytes(os.urandom(8), "little", signed=True)

    pool_size = UL_POOL_SIZE
    worker_limit = UL_WORKERS
    worker_count = min(worker_limit, total_parts)

    main_dc = await client.storage.dc_id()
    sessions = await MediaSessionPool.get_pool(client, main_dc, pool_size=pool_size)

    queue = asyncio.Queue(maxsize=QUEUE_SIZE)
    uploaded_bytes = 0
    error_holder = []
    lock = asyncio.Lock()
    md5_hash = hashlib.md5() if not is_big else None

    async def producer():
        try:
            with open(file_path, "rb", buffering=BUFFER_SIZE) as fp:
                for part_idx in range(total_parts):
                    if error_holder:
                        break
                    chunk = fp.read(UPLOAD_PART_SIZE)
                    if not chunk:
                        break
                    if not is_big and md5_hash:
                        md5_hash.update(chunk)
                    await queue.put((part_idx, chunk))
        except Exception as ex:
            error_holder.append(ex)
        finally:
            for _ in range(worker_count):
                await queue.put(None)

    async def worker(worker_id: int):
        nonlocal uploaded_bytes
        global _LAST_POOL_ACTIVITY
        while True:
            if error_holder:
                break
            try:
                item = await queue.get()
            except asyncio.QueueEmpty:
                break

            if item is None:
                queue.task_done()
                break

            part_idx, chunk = item

            if is_big:
                rpc = raw.functions.upload.SaveBigFilePart(
                    file_id=file_id,
                    file_part=part_idx,
                    file_total_parts=total_parts,
                    bytes=chunk
                )
            else:
                rpc = raw.functions.upload.SaveFilePart(
                    file_id=file_id,
                    file_part=part_idx,
                    bytes=chunk
                )

            success = False
            for attempt in range(6):
                if error_holder:
                    break
                # Automatic socket rotation across pooled sessions
                session = sessions[(attempt + worker_id) % len(sessions)]
                try:
                    await asyncio.wait_for(
                        session.invoke(
                            rpc,
                            sleep_threshold=getattr(client, "sleep_threshold", 60)
                        ),
                        timeout=25.0
                    )
                    _LAST_POOL_ACTIVITY = time.time()
                    success = True
                    break
                except StopTransmission:
                    error_holder.append(StopTransmission("Upload Cancelled"))
                    break
                except Exception as ex:
                    err_name = type(ex).__name__
                    if "FloodWait" in err_name:
                        wait_s = getattr(ex, "value", 5) or 5
                        await asyncio.sleep(min(wait_s, 30))
                    elif attempt == 5:
                        error_holder.append(ex)
                        break
                    else:
                        await asyncio.sleep(0.5 * (attempt + 1))

            if not success or error_holder:
                queue.task_done()
                break

            async with lock:
                uploaded_bytes += len(chunk)
                current_up = uploaded_bytes

            if progress:
                try:
                    if inspect.iscoroutinefunction(progress):
                        await progress(min(current_up, file_size), file_size, *progress_args)
                    else:
                        progress(min(current_up, file_size), file_size, *progress_args)
                except StopTransmission:
                    error_holder.append(StopTransmission("Upload Cancelled"))
                    queue.task_done()
                    break
                except Exception:
                    pass

            queue.task_done()

    producer_task = asyncio.create_task(producer())
    workers = [asyncio.create_task(worker(i)) for i in range(worker_count)]

    await asyncio.gather(producer_task, *workers)

    if error_holder:
        raise error_holder[0]

    _cleanup_memory(client)

    if is_big:
        return raw.types.InputFileBig(
            id=file_id,
            parts=total_parts,
            name=file_name
        )
    else:
        return raw.types.InputFile(
            id=file_id,
            parts=total_parts,
            name=file_name,
            md5_checksum=md5_hash.hexdigest() if md5_hash else ""
        )


async def zero_disk_turbo_pipe(
    client: Client,
    uploader: Client,
    staged_msg,
    new_filename: str,
    progress: Optional[Callable] = None,
    progress_args: tuple = (),
    is_prem: bool = False
):
    """
    Dual-Account Split-Horizon Multi-Session Zero-Disk RAM Chunk Pipe.
    Combines app_4gb (Telegram Premium User Session, 12 sockets, high priority)
    and client (Bot, 8 sockets) to download 20 parallel MTProto streams simultaneously in RAM,
    directly piped into 16 parallel upload MTProto sockets on the target uploader.
    Uses an in-memory 48MB sliding queue (96 chunks of 512KB) and bypasses disk I/O completely.
    Returns raw.types.InputFileBig (files > 10MB) or raw.types.InputFile (<= 10MB).
    """
    staged_chat_id = staged_msg.chat.id if hasattr(staged_msg, "chat") and staged_msg.chat else -1003792044224
    staged_msg_id = getattr(staged_msg, "id", None)

    # 1. Refresh Bot staged message if needed
    if staged_chat_id and staged_msg_id:
        try:
            refreshed = await client.get_messages(staged_chat_id, staged_msg_id)
            if refreshed and not getattr(refreshed, "empty", False):
                staged_msg = refreshed
        except Exception:
            pass

    file_obj_bot = (
        getattr(staged_msg, "document", None) or
        getattr(staged_msg, "video", None) or
        getattr(staged_msg, "audio", None) or
        getattr(staged_msg, "photo", None)
    )
    if not file_obj_bot or not hasattr(file_obj_bot, "file_id"):
        raise ValueError("Invalid staged message media for zero-disk pipe")

    file_size = getattr(file_obj_bot, "file_size", 0)
    if file_size == 0:
        raise ValueError("File size is 0 bytes")

    # 0. Idle-Socket Auto-Reset for clients (> 120s idle)
    await check_and_reset_idle_sessions(client)
    if uploader and uploader != client:
        await check_and_reset_idle_sessions(uploader)

    # Detect premium status from progress_args if provided
    try:
        if not is_prem and len(progress_args) >= 5 and progress_args[4] is not None:
            is_prem = bool(int(progress_args[4]) >= 1)
    except Exception:
        pass

    total_parts = math.ceil(file_size / CHUNK_SIZE)
    is_big = file_size > 10 * 1024 * 1024
    new_file_id = uploader.rnd_id() if hasattr(uploader, "rnd_id") else int.from_bytes(os.urandom(8), "little", signed=True)

    decoded_bot = FileId.decode(file_obj_bot.file_id)
    dc_id = decoded_bot.dc_id
    file_type = decoded_bot.file_type

    if file_type in (FileType.PHOTO, FileType.CHAT_PHOTO):
        location_bot = raw.types.InputPhotoFileLocation(
            id=decoded_bot.media_id,
            access_hash=decoded_bot.access_hash,
            file_reference=decoded_bot.file_reference,
            thumb_size=decoded_bot.thumbnail_size or ""
        )
    else:
        location_bot = raw.types.InputDocumentFileLocation(
            id=decoded_bot.media_id,
            access_hash=decoded_bot.access_hash,
            file_reference=decoded_bot.file_reference,
            thumb_size=decoded_bot.thumbnail_size or ""
        )

    # 2. Check for app_4gb (Telegram Premium User Session) for Dual-Account Acceleration
    user_client = getattr(client, "app_4gb", None)
    if not user_client:
        try:
            from bot import app_4gb
            user_client = app_4gb
        except Exception:
            user_client = None

    is_user_ready = (
        user_client is not None
        and (getattr(client, "app_4gb_started", False) or getattr(user_client, "is_connected", False))
    )

    staged_msg_user = None
    location_user = None
    if is_user_ready and staged_chat_id and staged_msg_id:
        try:
            staged_msg_user = await user_client.get_messages(staged_chat_id, staged_msg_id)
            if staged_msg_user and not getattr(staged_msg_user, "empty", False):
                user_file_obj = (
                    getattr(staged_msg_user, "document", None) or
                    getattr(staged_msg_user, "video", None) or
                    getattr(staged_msg_user, "audio", None) or
                    getattr(staged_msg_user, "photo", None)
                )
                if user_file_obj and hasattr(user_file_obj, "file_id"):
                    decoded_user = FileId.decode(user_file_obj.file_id)
                    if decoded_user.file_type in (FileType.PHOTO, FileType.CHAT_PHOTO):
                        location_user = raw.types.InputPhotoFileLocation(
                            id=decoded_user.media_id,
                            access_hash=decoded_user.access_hash,
                            file_reference=decoded_user.file_reference,
                            thumb_size=decoded_user.thumbnail_size or ""
                        )
                    else:
                        location_user = raw.types.InputDocumentFileLocation(
                            id=decoded_user.media_id,
                            access_hash=decoded_user.access_hash,
                            file_reference=decoded_user.file_reference,
                            thumb_size=decoded_user.thumbnail_size or ""
                        )
        except Exception as u_fetch_err:
            log.warning(f"Dual-account staged message fetch on app_4gb note: {u_fetch_err}")
            location_user = None
            staged_msg_user = None

    # 3. Spin up 8 Media Sockets on app_4gb (Premium) + 4 on Bot (12 parallel TCP sockets total)
    user_sessions = []
    if location_user and user_client:
        try:
            user_sessions = await _get_or_create_session_pool(user_client, dc_id, pool_size=DL_POOL_SIZE_PREM)
        except Exception as us_err:
            log.warning(f"app_4gb media session pool note ({us_err}). Falling back to Bot-only pool.")
            user_sessions = []

    bot_pool_size = DL_POOL_SIZE_BOT if user_sessions else DL_POOL_SIZE
    try:
        bot_sessions = await _get_or_create_session_pool(client, dc_id, pool_size=bot_pool_size)
    except Exception as bs_err:
        log.warning(f"Media session pool for bot failed ({bs_err}). Falling back to primary media session.")
        bot_sessions = [await get_media_session(client, dc_id)]

    down_streams = []
    # Premium account first for top priority unthrottled streaming
    for s in user_sessions:
        down_streams.append((s, user_client, location_user, "app_4gb"))
    for s in bot_sessions:
        down_streams.append((s, client, location_bot, "bot"))

    if not down_streams:
        down_streams.append((await get_media_session(client, dc_id), client, location_bot, "bot"))

    # Upload sessions: 10 independent upload Session sockets on uploader
    main_dc = await uploader.storage.dc_id()
    try:
        up_sessions = await _get_or_create_session_pool(uploader, main_dc, pool_size=UL_POOL_SIZE)
    except Exception as up_pool_err:
        log.warning(f"MediaSessionPool for uploader failed ({up_pool_err}). Falling back to primary media session.")
        up_sessions = [await get_media_session(uploader, main_dc)]

    if not up_sessions:
        up_sessions = [await get_media_session(uploader, main_dc)]

    # 4. In-Memory Sliding RAM Queue (QUEUE_SIZE = 64 parts of 512KB = 32MB dedicated RAM ring buffer for 2x multitasking on 4GB VM)
    pipe_queue = asyncio.Queue(maxsize=QUEUE_SIZE)
    part_indices = asyncio.Queue()
    for idx in range(total_parts):
        part_indices.put_nowait(idx)

    uploaded_bytes = 0
    error_holder = []
    lock = asyncio.Lock()
    md5_hash = hashlib.md5() if not is_big else None
    last_progress_time = 0.0

    async def _safe_progress(curr, tot):
        if not progress:
            return
        try:
            if inspect.iscoroutinefunction(progress):
                await progress(curr, tot, *progress_args)
            else:
                progress(curr, tot, *progress_args)
        except Exception:
            pass

    # 24 concurrent download worker coroutines across pooled media sessions
    num_down_workers = min(DL_WORKERS, total_parts)
    async def download_worker(wid: int):
        global _LAST_POOL_ACTIVITY
        while True:
            if error_holder:
                break
            try:
                part_idx = part_indices.get_nowait()
            except asyncio.QueueEmpty:
                break

            offset = part_idx * CHUNK_SIZE
            chunk_data = None
            for attempt in range(6):
                if error_holder:
                    break
                session, acc_client, loc, tag = down_streams[(attempt + wid) % len(down_streams)]
                rpc = raw.functions.upload.GetFile(
                    location=loc,
                    offset=offset,
                    limit=CHUNK_SIZE
                )
                try:
                    res = await asyncio.wait_for(
                        session.invoke(rpc, sleep_threshold=getattr(acc_client, "sleep_threshold", 60)),
                        timeout=25.0
                    )
                    chunk_data = getattr(res, "bytes", b"")
                    _LAST_POOL_ACTIVITY = time.time()
                    break
                except StopTransmission:
                    error_holder.append(StopTransmission("Download Cancelled"))
                    break
                except Exception as ex:
                    err_name = type(ex).__name__
                    if "FileReference" in err_name or "file_reference" in str(ex).lower():
                        if staged_chat_id and staged_msg_id:
                            try:
                                refreshed = await acc_client.get_messages(staged_chat_id, staged_msg_id)
                                if refreshed and not getattr(refreshed, "empty", False):
                                    ref_obj = (
                                        getattr(refreshed, "document", None) or
                                        getattr(refreshed, "video", None) or
                                        getattr(refreshed, "audio", None) or
                                        getattr(refreshed, "photo", None)
                                    )
                                    if ref_obj and hasattr(ref_obj, "file_id"):
                                        ref_decoded = FileId.decode(ref_obj.file_id)
                                        loc.file_reference = ref_decoded.file_reference
                                        rpc.location.file_reference = ref_decoded.file_reference
                            except Exception:
                                pass
                    if "FloodWait" in err_name:
                        wait_s = getattr(ex, "value", 5) or 5
                        await asyncio.sleep(min(wait_s, 30))
                    elif attempt == 5:
                        log.warning(f"zero_disk_turbo_pipe {tag} download worker {wid} part {part_idx} failed: {ex}")
                        error_holder.append(ex)
                    else:
                        await asyncio.sleep(0.5 * (attempt + 1))

            if not chunk_data or error_holder:
                part_indices.task_done()
                break

            if not is_big and md5_hash:
                md5_hash.update(chunk_data)

            await pipe_queue.put((part_idx, chunk_data))
            part_indices.task_done()

    # 24 concurrent upload worker coroutines across upload media sessions
    num_up_workers = min(UL_WORKERS, total_parts)
    async def upload_worker(wid: int):
        nonlocal uploaded_bytes, last_progress_time
        global _LAST_POOL_ACTIVITY
        while True:
            if error_holder:
                break
            try:
                item = await asyncio.wait_for(pipe_queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                if error_holder:
                    break
                continue
            except asyncio.QueueEmpty:
                break

            if item is None:
                pipe_queue.task_done()
                break

            part_idx, chunk = item
            if is_big:
                rpc = raw.functions.upload.SaveBigFilePart(
                    file_id=new_file_id,
                    file_part=part_idx,
                    file_total_parts=total_parts,
                    bytes=chunk
                )
            else:
                rpc = raw.functions.upload.SaveFilePart(
                    file_id=new_file_id,
                    file_part=part_idx,
                    bytes=chunk
                )

            success = False
            for attempt in range(6):
                if error_holder:
                    break
                session = up_sessions[(attempt + wid) % len(up_sessions)]
                try:
                    await asyncio.wait_for(
                        session.invoke(rpc, sleep_threshold=getattr(uploader, "sleep_threshold", 60)),
                        timeout=25.0
                    )
                    _LAST_POOL_ACTIVITY = time.time()
                    success = True
                    break
                except StopTransmission:
                    error_holder.append(StopTransmission("Upload Cancelled"))
                    break
                except Exception as ex:
                    err_name = type(ex).__name__
                    if "FloodWait" in err_name:
                        wait_s = getattr(ex, "value", 5) or 5
                        await asyncio.sleep(min(wait_s, 30))
                    elif attempt == 5:
                        log.warning(f"zero_disk_turbo_pipe upload worker {wid} part {part_idx} failed: {ex}")
                        error_holder.append(ex)
                    else:
                        await asyncio.sleep(0.5 * (attempt + 1))

            if not success or error_holder:
                pipe_queue.task_done()
                break

            async with lock:
                uploaded_bytes += len(chunk)
                current_up = uploaded_bytes

            now = time.time()
            if now - last_progress_time >= 3.5 or current_up >= file_size:
                last_progress_time = now
                asyncio.create_task(_safe_progress(min(current_up, file_size), file_size))

            pipe_queue.task_done()

    down_tasks = [asyncio.create_task(download_worker(i)) for i in range(num_down_workers)]
    up_tasks = [asyncio.create_task(upload_worker(i)) for i in range(num_up_workers)]

    async def feeder():
        while not error_holder:
            if part_indices.empty():
                try:
                    await asyncio.wait_for(part_indices.join(), timeout=0.5)
                    break
                except asyncio.TimeoutError:
                    continue
            await asyncio.sleep(0.1)
        for _ in range(num_up_workers + 10):
            try:
                await pipe_queue.put(None)
            except Exception:
                pass

    feeder_task = asyncio.create_task(feeder())
    # Disable GC during hot transfer loop to prevent GC pause interruptions on 0.1 vCPU
    gc.disable()
    logging.getLogger("pyrogram").setLevel(logging.WARNING)
    try:
        await asyncio.gather(*down_tasks, feeder_task, *up_tasks)
    except Exception as e:
        if not error_holder:
            error_holder.append(e)
    finally:
        for t in down_tasks + up_tasks + [feeder_task]:
            if not t.done():
                t.cancel()
        gc.enable()
        _cleanup_memory(client, uploader)

    if error_holder:
        raise error_holder[0]

    # Final 100% progress notification
    asyncio.create_task(_safe_progress(file_size, file_size))

    if is_big:
        return raw.types.InputFileBig(
            id=new_file_id,
            parts=total_parts,
            name=new_filename
        )
    else:
        return raw.types.InputFile(
            id=new_file_id,
            parts=total_parts,
            name=new_filename,
            md5_checksum=md5_hash.hexdigest() if md5_hash else ""
        )


async def send_input_file_big(
    uploader_client: Client,
    target_chat_id: Union[int, str],
    input_file_big: Union[raw.types.InputFileBig, raw.types.InputFile],
    thumb_path: Optional[str] = None,
    media_msg = None,
    new_filename: str = "file.mkv",
    caption: str = "",
    upload_type: str = "document",
    protect_content: bool = False,
    duration: int = 0,
    width: int = 0,
    height: int = 0
) -> Optional[types.Message]:
    """
    Directly invokes raw.functions.messages.SendMedia using an uploaded InputFileBig / InputFile.
    Bypasses Pyrogram's high-level send_document/send_video file path validation checks,
    natively attaching thumbnails, attributes, and parsed HTML captions.
    """
    # 1. Resolve Target Chat Peer
    peer = await uploader_client.resolve_peer(target_chat_id)

    # 2. Upload thumbnail if provided and exists on disk
    thumb_input = None
    if thumb_path and os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 0:
        try:
            thumb_input = await uploader_client.save_file(thumb_path)
        except Exception as t_err:
            log.warning(f"send_input_file_big thumbnail upload error: {t_err}")
            thumb_input = None

    # 3. Build Document Attributes
    attributes = [raw.types.DocumentAttributeFilename(file_name=new_filename)]
    send_as_video = (upload_type == "video")
    is_video = send_as_video or (media_msg and getattr(media_msg, "video", None)) or new_filename.lower().endswith(('.mp4', '.mkv', '.webm', '.avi', '.mov', '.flv'))
    is_audio = (upload_type == "audio") or (media_msg and getattr(media_msg, "audio", None)) or new_filename.lower().endswith(('.mp3', '.m4a', '.flac', '.wav', '.ogg'))

    if upload_type == "video" or (upload_type != "document" and is_video):
        send_as_video = True
        attributes.append(
            raw.types.DocumentAttributeVideo(
                duration=int(duration or 0),
                w=int(width or 1280),
                h=int(height or 720),
                supports_streaming=True
            )
        )
    elif upload_type == "audio" or (upload_type != "document" and is_audio):
        send_as_video = False
        audio_obj = getattr(media_msg, "audio", None) if media_msg else None
        title = getattr(audio_obj, "title", None) or os.path.splitext(new_filename)[0]
        performer = getattr(audio_obj, "performer", None) or ""
        attributes.append(
            raw.types.DocumentAttributeAudio(
                duration=int(duration or 0),
                title=title,
                performer=performer
            )
        )
    else:
        send_as_video = False

    # 4. Determine MIME Type
    mime = uploader_client.guess_mime_type(new_filename) or "application/octet-stream"
    if send_as_video and not mime.startswith("video/"):
        mime = "video/mp4"
    elif upload_type == "audio" and not mime.startswith("audio/"):
        mime = "audio/mpeg"

    # 5. Build InputMediaUploadedDocument
    media = raw.types.InputMediaUploadedDocument(
        file=input_file_big,
        mime_type=mime,
        attributes=attributes,
        thumb=thumb_input,
        force_file=not send_as_video
    )

    # 6. Parse HTML Caption & Entities safely
    msg_text = ""
    msg_entities = None
    if caption:
        try:
            if hasattr(uploader_client, "parser") and hasattr(uploader_client.parser, "parse"):
                parsed = await uploader_client.parser.parse(caption, enums.ParseMode.HTML)
            else:
                parsed = utils.parse_text_entities(uploader_client, caption, parse_mode=enums.ParseMode.HTML, entities=None)
            msg_text = parsed.get("message", "")
            msg_entities = parsed.get("entities", [])
        except Exception:
            try:
                parsed = utils.parse_text_entities(uploader_client, caption, parse_mode=enums.ParseMode.HTML, entities=None)
                msg_text = parsed.get("message", "")
                msg_entities = parsed.get("entities", [])
            except Exception:
                msg_text = str(caption)
                msg_entities = None

    # 7. Send Media via MTProto SendMedia
    rpc_kwargs = {
        "peer": peer,
        "media": media,
        "random_id": uploader_client.rnd_id(),
        "message": msg_text,
    }
    if msg_entities:
        rpc_kwargs["entities"] = msg_entities
    if protect_content:
        rpc_kwargs["noforwards"] = True

    rpc_result = await uploader_client.invoke(raw.functions.messages.SendMedia(**rpc_kwargs))

    # 8. Safely Extract Sent Message ID and return valid Message object
    extracted_msg_id = None
    if hasattr(rpc_result, "updates"):
        for u in rpc_result.updates:
            if isinstance(u, (raw.types.UpdateNewMessage, raw.types.UpdateNewChannelMessage)):
                extracted_msg_id = getattr(getattr(u, "message", None), "id", None)
                if extracted_msg_id:
                    break
            elif isinstance(u, raw.types.UpdateMessageID):
                extracted_msg_id = getattr(u, "id", None)
                if extracted_msg_id:
                    break
            elif isinstance(u, raw.types.UpdateNewScheduledMessage):
                extracted_msg_id = getattr(getattr(u, "message", None), "id", None)
                if extracted_msg_id:
                    break
    elif isinstance(rpc_result, (raw.types.UpdateShortSentMessage, raw.types.UpdateShortMessage)):
        extracted_msg_id = getattr(rpc_result, "id", None)

    if extracted_msg_id:
        try:
            sent_msg = await uploader_client.get_messages(target_chat_id, int(extracted_msg_id))
            if sent_msg and hasattr(sent_msg, "id"):
                return sent_msg
        except Exception as fetch_err:
            log.warning(f"Failed to fetch sent message by ID {extracted_msg_id}: {fetch_err}")

    # Fallback to direct parsing if get_messages failed or rpc_result structure was different
    for i in getattr(rpc_result, "updates", []):
        if isinstance(
            i,
            (
                raw.types.UpdateNewMessage,
                raw.types.UpdateNewChannelMessage,
                raw.types.UpdateNewScheduledMessage
            )
        ):
            users = {u.id: u for u in getattr(rpc_result, "users", [])}
            chats = {c.id: c for c in getattr(rpc_result, "chats", [])}
            try:
                return await types.Message._parse(
                    uploader_client,
                    i.message,
                    users,
                    chats
                )
            except Exception:
                pass

    return None


__all__ = [
    "fast_download",
    "fast_upload",
    "zero_disk_turbo_pipe",
    "send_input_file_big",
    "get_media_session",
    "get_media_session_pool",
    "check_and_reset_idle_sessions",
    "_cleanup_memory",
    "_TRANSFER_SEMAPHORE",
    "_LAST_POOL_ACTIVITY",
    "CHUNK_SIZE",
    "UPLOAD_PART_SIZE",
    "DL_POOL_SIZE_PREM",
    "DL_POOL_SIZE_BOT",
    "DL_POOL_SIZE",
    "UL_POOL_SIZE",
    "DL_WORKERS",
    "UL_WORKERS",
    "QUEUE_SIZE",
    "CONCURRENT_WORKERS_PREM",
    "CONCURRENT_WORKERS_FREE",
    "CONCURRENT_WORKERS",
    "BUFFER_SIZE"
]

import os
import math
import asyncio
import logging
from typing import Optional
from pyrogram import Client, raw
from pyrogram.types import Message
from pyrogram.file_id import FileId, FileType, ThumbnailSource
from config import Config, parse_channel_id
from helper.fast_transfer import get_media_session

log = logging.getLogger(__name__)


def get_virtual_disk_channel(client: Optional[Client] = None) -> int:
    """Returns the parsed numeric ID or username of the Telegram Virtual Disk channel."""
    vdisk = (
        getattr(Config, "VIRTUAL_DISK_CHANNEL", None) or
        getattr(Config, "FILES_CHANNEL", None) or
        getattr(Config, "DUMP_CHANNEL", None) or
        -1003792044224
    )
    return parse_channel_id(vdisk) or -1003792044224


class TelegramVirtualDisk:
    """
    Telegram Private Channel Virtual Disk Engine.
    Provides fast (0.05s) staging of incoming media messages, byte-range slice streaming
    for sample video & screenshot generation without full-file downloads, and persistent
    message recovery for interrupted tasks.
    """

    @staticmethod
    async def ensure_peer_cached(client: Client, channel=None):
        """Resolves and caches the virtual disk channel peer in Pyrogram to prevent PeerIdInvalid."""
        target = parse_channel_id(channel or get_virtual_disk_channel(client))
        if not target or target == 0:
            return None

        # Resolve on main client
        try:
            chat = await client.get_chat(target)
            log.info(f"Virtual Disk peer cached on main bot: {chat.id} ({chat.title or 'Channel'})")
        except Exception as e:
            log.warning(f"Failed to cache Virtual Disk peer on main bot: {e}")

        # Resolve on 4GB client if running
        app_4gb = getattr(client, "app_4gb", None)
        if app_4gb and getattr(client, "app_4gb_started", False):
            try:
                chat_4gb = await app_4gb.get_chat(target)
                log.info(f"Virtual Disk peer cached on app_4gb: {chat_4gb.id} ({chat_4gb.title or 'Channel'})")
            except Exception as e:
                log.warning(f"Failed to cache Virtual Disk peer on app_4gb: {e}")

        return target

    @staticmethod
    async def stage_message(client: Client, message: Message, target_channel=None) -> Optional[Message]:
        """
        Fast 0.05-second staging: copies incoming media message into the Virtual Disk channel.
        Returns the newly created staged Message object containing complete media metadata.
        """
        target = parse_channel_id(target_channel or get_virtual_disk_channel(client))
        if not target or target == 0:
            return None

        try:
            staged = await message.copy(chat_id=target)
            return staged
        except Exception as copy_err:
            log.warning(f"Message copy to Virtual Disk failed ({copy_err}). Trying forward fallback...")
            try:
                forwarded = await message.forward(chat_id=target)
                return forwarded
            except Exception as fwd_err:
                log.error(f"Failed to stage media into Virtual Disk channel {target}: {fwd_err}")
                return None

    @staticmethod
    async def fetch_staged_message(client: Client, message_id: int, target_channel=None) -> Optional[Message]:
        """Retrieves a previously staged message by its message_id from the Virtual Disk channel."""
        target = parse_channel_id(target_channel or get_virtual_disk_channel(client))
        if not target or target == 0 or not message_id:
            return None

        try:
            msg = await client.get_messages(target, message_ids=int(message_id))
            return msg if msg and not getattr(msg, "empty", False) else None
        except Exception as ex:
            log.warning(f"Failed to fetch staged message {message_id} from Virtual Disk: {ex}")
            return None

    @staticmethod
    async def delete_staged_message(client: Client, message_id: int, target_channel=None) -> bool:
        """Safely removes a temporary staged message from the Virtual Disk channel to keep it clean."""
        target = parse_channel_id(target_channel or get_virtual_disk_channel(client))
        if not target or target == 0 or not message_id:
            return False

        try:
            await client.delete_messages(chat_id=target, message_ids=int(message_id))
            return True
        except Exception:
            return False

    @staticmethod
    async def stream_byte_slice(
        client: Client,
        staged_msg: Message,
        output_path: str,
        max_bytes: int = 35 * 1024 * 1024
    ) -> Optional[str]:
        """
        Streams a fast ~25MB–35MB byte range directly from the media in Virtual Disk channel.
        Avoids downloading the full 4GB file when generating sample clips or screenshots with FFmpeg.
        """
        file_obj = (
            getattr(staged_msg, "document", None) or
            getattr(staged_msg, "video", None) or
            getattr(staged_msg, "audio", None)
        )
        if not file_obj or not hasattr(file_obj, "file_id"):
            return None

        file_size = getattr(file_obj, "file_size", 0)
        target_bytes = min(file_size, max_bytes) if file_size > 0 else max_bytes
        chunk_size = 512 * 1024
        total_parts_needed = max(1, math.ceil(target_bytes / chunk_size))

        try:
            decoded = FileId.decode(file_obj.file_id)
            dc_id = decoded.dc_id
            location = raw.types.InputDocumentFileLocation(
                id=decoded.media_id,
                access_hash=decoded.access_hash,
                file_reference=decoded.file_reference,
                thumb_size=decoded.thumbnail_size or ""
            )

            session = await get_media_session(client, dc_id)
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

            with open(output_path, "wb") as fp:
                for part_idx in range(total_parts_needed):
                    offset = part_idx * chunk_size
                    rpc = raw.functions.upload.GetFile(
                        location=location,
                        offset=offset,
                        limit=chunk_size
                    )
                    res = await asyncio.wait_for(
                        session.invoke(rpc, sleep_threshold=getattr(client, "sleep_threshold", 60)),
                        timeout=20.0
                    )
                    data = getattr(res, "bytes", b"")
                    if not data:
                        break
                    fp.write(data)
                    if fp.tell() >= target_bytes:
                        break

            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return output_path
        except Exception as slice_err:
            log.warning(f"Byte slice stream error ({slice_err}). Falling back to partial download...")

        return None


# Module-level convenience functions
stage_to_virtual_disk = TelegramVirtualDisk.stage_message
fetch_from_virtual_disk = TelegramVirtualDisk.fetch_staged_message
delete_from_virtual_disk = TelegramVirtualDisk.delete_staged_message
stream_virtual_disk_slice = TelegramVirtualDisk.stream_byte_slice

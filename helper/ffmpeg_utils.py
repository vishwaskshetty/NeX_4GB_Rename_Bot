import os
import sys
import time
import math
import html
import shutil
import asyncio
import traceback
import inspect
import gc
import random
import logging
import json
from typing import Tuple, List, Dict

logger = logging.getLogger(__name__)
log = logger

try:
    from hachoir.metadata import extractMetadata
    from hachoir.parser import createParser
except ImportError:
    extractMetadata = None
    createParser = None

# NeX 4GB Rename Bot - FFmpeg Engine
# Developed by @Nex_bots

# Instant startup: only load static_ffmpeg if system ffmpeg/ffprobe binaries are not found
if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
    try:
        import static_ffmpeg
        static_ffmpeg.add_paths()
    except Exception as e:
        print(f"static_ffmpeg auto-init info: {e}")


def _wrap_nice(cmd: List[str]) -> List[str]:
    """
    Wraps command with 'nice -n 10' on Linux/Unix systems so heavy FFmpeg tasks
    never starve the event loop or freeze concurrent file downloads/uploads.
    """
    if sys.platform != "win32" and shutil.which("nice"):
        return ["nice", "-n", "10"] + cmd
    return cmd


async def inject_metadata(input_path: str, output_path: str, meta_text: str) -> bool:
    """
    Losslessly injects custom metadata tags into container and audio/video/subtitle streams.
    """
    cmd = [
        "ffmpeg", "-y",
        "-threads", "2",
        "-i", input_path,
        "-map", "0",
        "-c", "copy",
        "-metadata", f"title={meta_text}",
        "-metadata", f"author={meta_text}",
        "-metadata", f"artist={meta_text}",
        "-metadata", f"comment={meta_text}",
        "-metadata:s:v", f"title={meta_text}",
        "-metadata:s:a", f"title={meta_text}",
        "-metadata:s:s", f"title={meta_text}",
        output_path
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *_wrap_nice(cmd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
        return os.path.exists(output_path) and os.path.getsize(output_path) > 0
    except Exception as e:
        print(f"FFmpeg inject_metadata error: {e}")
        return False


async def generate_sample_video(input_path: str, output_path: str, total_duration: int, sample_sec: int, start_mode: str = "auto") -> bool:
    """
    Cuts a lossless sample video clip of sample_sec length based on timeline start mode:
    - 'auto': 15% into the video
    - 'start': 60s (00:01:00)
    - 'mid': 50% middle of video
    - 'ten' / '10:00': 600s
    - or custom MM:SS / numeric seconds
    """
    start_sec = 0
    try:
        mode_lower = str(start_mode).strip().lower()
        if mode_lower == "auto":
            start_sec = int(total_duration * 0.15) if total_duration > (sample_sec + 10) else 0
        elif mode_lower in ("start", "01:00"):
            start_sec = 60
        elif mode_lower in ("mid", "50%"):
            start_sec = int(total_duration * 0.50)
        elif mode_lower in ("ten", "10:00"):
            start_sec = 600
        elif ":" in mode_lower:
            parts = mode_lower.split(":")
            if len(parts) == 2:
                start_sec = int(parts[0]) * 60 + int(parts[1])
            elif len(parts) == 3:
                start_sec = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        else:
            start_sec = int(float(mode_lower))
    except Exception:
        start_sec = int(total_duration * 0.15) if total_duration > (sample_sec + 10) else 0

    if total_duration > sample_sec:
        start_sec = max(0, min(start_sec, total_duration - sample_sec))
    else:
        start_sec = 0

    cmd = [
        "ffmpeg", "-y",
        "-threads", "2",
        "-ss", str(start_sec),
        "-i", input_path,
        "-t", str(sample_sec),
        "-c", "copy",
        output_path
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *_wrap_nice(cmd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
        return os.path.exists(output_path) and os.path.getsize(output_path) > 0
    except Exception as e:
        print(f"FFmpeg generate_sample_video error: {e}")
        return False


async def apply_video_watermark(
    input_path: str,
    output_path: str,
    text: str = "",
    wm_type: str = "image",
    image_path: str = None,
    position: str = "top_left",
    size: int = 28,
    opacity: float = 0.78,
    color: str = "white",
    status_msg = None,
    client = None,
    total_duration: int = 0
) -> bool:
    """
    Applies clean OTT-style corner logo or text watermark over video using FFmpeg.
    - Uses scale2ref to auto-scale logo to 11% of video width with aspect ratio preservation.
    - Applies subtle OTT transparency (aa=0.78 by default).
    - Uses -c:v libx264 -preset ultrafast -crf 23 -c:a copy -c:s copy -threads 2 for fast, lossless audio/subtitle remuxing.
    - Shows live FFmpeg encoding progress (% + ETA + Speed) in Telegram status message.
    - Always deletes temporary or failed files in a finally: block.
    """
    from helper.utils import CANCEL_REQUESTS, edit_message_content
    from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    if total_duration <= 0:
        try:
            dur, _, _ = await get_video_duration_and_dims(input_path)
            total_duration = int(dur or 0)
        except Exception:
            total_duration = 0

    norm_pos = str(position).lower().strip() if position else "top_left"
    pos_coords_img = {
        "top_left": "overlay=W*0.03:H*0.04",
        "top_right": "overlay=W-w-W*0.03:H*0.04",
        "center": "overlay=(W-w)/2:(H-h)/2",
        "bottom_left": "overlay=W*0.03:H-h-H*0.04",
        "bottom_right": "overlay=W-w-W*0.03:H-h-H*0.04"
    }
    coords_img = pos_coords_img.get(norm_pos, "overlay=W*0.03:H*0.04")

    op = max(0.1, min(1.0, float(opacity if opacity is not None else 0.78)))
    is_img = bool(wm_type == "image" and image_path and os.path.exists(image_path) and os.path.getsize(image_path) > 0)

    if is_img:
        filter_complex = (
            f"[1:v]format=rgba,colorchannelmixer=aa={op:.2f}[wm];"
            f"[wm][0:v]scale2ref=w=trunc(main_w*0.11/2)*2:h=-2[wm_s][vid];"
            f"[vid][wm_s]{coords_img}[outv]"
        )
        cmd = [
            "ffmpeg", "-y",
            "-threads", "2",
            "-i", input_path,
            "-i", image_path,
            "-filter_complex", filter_complex,
            "-map", "[outv]",
            "-map", "0:a?",
            "-map", "0:s?",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "23",
            "-c:a", "copy",
            "-c:s", "copy",
            "-movflags", "+faststart",
            "-progress", "pipe:1",
            "-nostats",
            output_path
        ]
    else:
        pos_coords_text = {
            "top_left": "x=w*0.03:y=h*0.04",
            "top_right": "x=w-tw-w*0.03:y=h*0.04",
            "center": "x=(w-tw)/2:y=(h-th)/2",
            "bottom_left": "x=w*0.03:y=h-th-h*0.04",
            "bottom_right": "x=w-tw-w*0.03:y=h-th-h*0.04"
        }
        coords_txt = pos_coords_text.get(norm_pos, "x=w*0.03:y=h*0.04")
        safe_text = str(text or "").replace('\\', '\\\\').replace("'", "'\\\\''").replace(':', '\\:').replace('%', '\\%')
        font_color = str(color).lower() if str(color).lower() in ("white", "yellow", "cyan", "red", "green") else "white"
        font_size = int(size) if int(size) > 0 else 28

        vf_filter = (
            f"drawtext=text='{safe_text}':{coords_txt}:fontsize={font_size}:fontcolor={font_color}@{op:.2f}:"
            f"box=1:boxcolor=black@{op*0.55:.2f}:boxborderw=4"
        )
        cmd = [
            "ffmpeg", "-y",
            "-threads", "2",
            "-i", input_path,
            "-vf", vf_filter,
            "-map", "0:v:0",
            "-map", "0:a?",
            "-map", "0:s?",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "23",
            "-c:a", "copy",
            "-c:s", "copy",
            "-movflags", "+faststart",
            "-progress", "pipe:1",
            "-nostats",
            output_path
        ]

    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            *_wrap_nice(cmd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        start_time = time.time()
        last_edit_time = 0.0
        current_sec = 0.0
        speed_val = "1.0x"

        msg_id = getattr(status_msg, 'id', None)
        chat_id = getattr(status_msg.chat, 'id', None) if (status_msg and getattr(status_msg, 'chat', None)) else None

        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            line_str = line.decode('utf-8', errors='ignore').strip()

            if line_str.startswith("out_time_us="):
                try:
                    out_us = int(line_str.split("=")[1])
                    current_sec = out_us / 1_000_000.0
                except Exception:
                    pass
            elif line_str.startswith("speed="):
                speed_val = line_str.split("=")[1].strip()
            elif line_str.startswith("progress="):
                prog = line_str.split("=")[1].strip()
                now = time.time()

                if msg_id and (
                    msg_id in CANCEL_REQUESTS
                    or (chat_id and (f"{chat_id}_{msg_id}" in CANCEL_REQUESTS or chat_id in CANCEL_REQUESTS))
                ):
                    try:
                        proc.terminate()
                    except Exception:
                        pass
                    return False

                if status_msg and total_duration > 0 and (now - last_edit_time >= 3.5 or prog == "end"):
                    last_edit_time = now
                    pct = min(99.0, max(0.0, (current_sec / total_duration) * 100.0))
                    completed_blocks = min(20, max(0, math.floor(pct / 5.0)))
                    progress_bar = '▣' * completed_blocks + '▢' * (20 - completed_blocks)

                    elapsed = max(now - start_time, 0.001)
                    rem_sec = max(0.0, total_duration - current_sec)
                    try:
                        speed_mult = float(speed_val.replace('x', '').strip())
                    except Exception:
                        speed_mult = 1.0

                    if speed_mult > 0.1:
                        eta_sec = int(rem_sec / speed_mult)
                    elif current_sec > 0:
                        eta_sec = int((elapsed / current_sec) * rem_sec)
                    else:
                        eta_sec = 0

                    eta_str = f"{eta_sec // 60}m {eta_sec % 60}s" if eta_sec >= 60 else f"{eta_sec}s"
                    curr_fmt = f"{int(current_sec) // 60:02d}:{int(current_sec) % 60:02d}"
                    tot_fmt = f"{int(total_duration) // 60:02d}:{int(total_duration) % 60:02d}"

                    status_text = (
                        "<b>◈ ᴀᴘᴘʟʏɪɴɢ ᴠɪᴅᴇᴏ ᴡᴀᴛᴇʀᴍᴀʀᴋ... 💧</b>\n\n"
                        f"{progress_bar} <b>{pct:.1f}%</b>\n\n"
                        f"▸ <b>Sᴘᴇᴇᴅ :</b> <code>{speed_val}</code>\n"
                        f"▸ <b>Tɪᴍᴇ :</b> <code>{curr_fmt} / {tot_fmt}</code>\n"
                        f"▸ <b>ETA :</b> <code>{eta_str}</code>\n\n"
                        "⚡ <b>NᴇX 4GB Rᴇɴᴀᴍᴇ Bᴏᴛ</b> | @Nex_bots"
                    )
                    try:
                        cancel_markup = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{msg_id}")]])
                        await edit_message_content(status_msg, status_text, reply_markup=cancel_markup)
                    except Exception:
                        pass

        stderr_data = await proc.stderr.read()
        await proc.wait()
        if proc.returncode != 0:
            err_msg = stderr_data.decode('utf-8', errors='ignore') if stderr_data else ""
            print(f"FFmpeg apply_video_watermark non-zero exit ({proc.returncode}): {err_msg[-1000:]}", flush=True)
            if status_msg:
                try:
                    await edit_message_content(
                        status_msg,
                        f"❌ <b>Watermark Encoding Failed!</b>\n\n<code>{html.escape(err_msg[-200:].strip())}</code>\n\n⚡ @Nex_bots"
                    )
                except Exception:
                    pass
            return False
        return os.path.exists(output_path) and os.path.getsize(output_path) > 0
    except Exception as e:
        print(f"FFmpeg apply_video_watermark error: {e}")
        return False
    finally:
        if proc and proc.returncode is None:
            try:
                proc.terminate()
                await asyncio.sleep(0.2)
                if proc.returncode is None:
                    proc.kill()
            except Exception:
                pass
        if not (os.path.exists(output_path) and os.path.getsize(output_path) > 0):
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except Exception:
                    pass


async def generate_screenshots(input_path: str, output_folder: str, total_duration: int, count: int) -> List[str]:
    """
    Extracts count high-quality evenly spaced JPEG screenshots from video.
    """
    os.makedirs(output_folder, exist_ok=True)
    screenshots = []
    if count <= 0:
        return screenshots

    if total_duration <= 0:
        total_duration = 60

    step = max(1, total_duration // (count + 1))
    for i in range(1, count + 1):
        target_time = step * i
        img_out = os.path.join(output_folder, f"screenshot_{i}.jpg")
        cmd = [
            "ffmpeg", "-y",
            "-threads", "2",
            "-ss", str(target_time),
            "-i", input_path,
            "-frames:v", "1",
            "-q:v", "2",
            img_out
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *_wrap_nice(cmd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            if os.path.exists(img_out) and os.path.getsize(img_out) > 0:
                screenshots.append(img_out)
        except Exception as e:
            print(f"FFmpeg screenshot generation error at {target_time}s: {e}")

    return screenshots


async def get_video_duration_and_dims(file_path: str) -> Tuple[int, int, int]:
    """
    Reliably extracts duration (seconds), width, and height using ffprobe with hachoir fallback.
    """
    duration = 0
    width = 0
    height = 0

    # 1. Try ffprobe (fast & accurate)
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "stream=width,height,duration:format=duration",
            "-of", "json",
            file_path
        ]
        proc = await asyncio.create_subprocess_exec(
            *_wrap_nice(cmd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        if stdout:
            data = json.loads(stdout.decode())
            if "format" in data and "duration" in data["format"]:
                try:
                    duration = int(float(data["format"]["duration"]))
                except (ValueError, TypeError):
                    pass
            for stream in data.get("streams", []):
                if stream.get("width") and not width:
                    width = int(stream["width"])
                if stream.get("height") and not height:
                    height = int(stream["height"])
                if stream.get("duration") and not duration:
                    try:
                        duration = int(float(stream["duration"]))
                    except (ValueError, TypeError):
                        pass
    except Exception:
        pass

    # 2. Fallback to hachoir if ffprobe was missing or incomplete
    if not (duration and width and height) and createParser and extractMetadata:
        try:
            parser = createParser(file_path)
            if parser:
                with parser:
                    metadata = extractMetadata(parser)
                    if metadata:
                        if not duration and metadata.has("duration"):
                            duration = metadata.get("duration").seconds
                        if not width and metadata.has("width"):
                            width = metadata.get("width")
                        if not height and metadata.has("height"):
                            height = metadata.get("height")
        except Exception:
            pass

    return int(duration), int(width), int(height)


async def get_media_streams(file_path: str) -> Dict[str, list]:
    """
    Inspects all video, audio, and subtitle streams in a media file using ffprobe.
    """
    res = {"video": [], "audio": [], "subtitle": []}
    try:
        cmd = [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_streams",
            file_path
        ]
        proc = await asyncio.create_subprocess_exec(
            *_wrap_nice(cmd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        if stdout:
            data = json.loads(stdout.decode())
            for stream in data.get("streams", []):
                stype = stream.get("codec_type")
                tags = stream.get("tags", {})
                info = {
                    "index": int(stream.get("index", 0)),
                    "codec": stream.get("codec_name", "unknown"),
                    "lang": tags.get("language", "und"),
                    "title": tags.get("title", tags.get("handler_name", ""))
                }
                if stype == "video":
                    info["width"] = stream.get("width")
                    info["height"] = stream.get("height")
                    res["video"].append(info)
                elif stype == "audio":
                    info["channels"] = stream.get("channels", 2)
                    res["audio"].append(info)
                elif stype == "subtitle":
                    res["subtitle"].append(info)
    except Exception as e:
        print(f"ffprobe get_media_streams error: {e}")
    return res


async def remux_select_streams(
    input_path: str,
    output_path: str,
    a_indices: List[int] = None,
    s_indices: List[int] = None
) -> bool:
    """
    Losslessly strips unwanted tracks or selects specific audio/subtitle streams in under 5 seconds.
    """
    cmd = ["ffmpeg", "-y", "-threads", "2", "-i", input_path, "-map", "0:v"]

    if a_indices:
        for idx in a_indices:
            cmd.extend(["-map", f"0:{idx}"])
    else:
        cmd.extend(["-map", "0:a?"])

    if s_indices:
        for idx in s_indices:
            cmd.extend(["-map", f"0:{idx}"])
    elif s_indices is not None and len(s_indices) == 0:
        # Strip all subtitles if empty list provided
        pass
    else:
        cmd.extend(["-map", "0:s?"])

    cmd.extend(["-c", "copy", output_path])

    try:
        proc = await asyncio.create_subprocess_exec(
            *_wrap_nice(cmd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
        return os.path.exists(output_path) and os.path.getsize(output_path) > 0
    except Exception as e:
        print(f"FFmpeg remux_select_streams error: {e}")
        return False


async def remux_container(input_path: str, output_path: str) -> bool:
    """
    Fast lossless container remuxing between MKV and MP4 in 4-8 seconds without CPU re-encoding.
    """
    cmd = ["ffmpeg", "-y", "-threads", "2", "-i", input_path, "-c", "copy"]
    if output_path.lower().endswith(".mp4"):
        cmd.extend(["-movflags", "+faststart"])
    cmd.append(output_path)

    try:
        proc = await asyncio.create_subprocess_exec(
            *_wrap_nice(cmd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
        return os.path.exists(output_path) and os.path.getsize(output_path) > 0
    except Exception as e:
        print(f"FFmpeg remux_container error: {e}")
        return False


async def generate_screenshot_grid(input_path: str, output_path: str, total_duration: int) -> bool:
    """
    Generates a high-resolution 3x3 contact sheet (9 evenly spaced frames) in a single image.
    """
    if total_duration <= 0:
        total_duration = 120

    # Extract 9 frames evenly distributed and tile them 3x3
    interval = max(5, total_duration // 10)
    # Fast select filter to pick 9 frames
    vf = f"select='not(mod(n\\,{interval}))',scale=480:-1,tile=3x3"
    cmd = [
        "ffmpeg", "-y",
        "-threads", "2",
        "-i", input_path,
        "-vf", vf,
        "-frames:v", "1",
        "-q:v", "2",
        output_path
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *_wrap_nice(cmd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
        return os.path.exists(output_path) and os.path.getsize(output_path) > 0
    except Exception as e:
        print(f"FFmpeg generate_screenshot_grid error: {e}")
        return False



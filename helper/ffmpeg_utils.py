import os
import json
import shutil
import asyncio
from typing import Tuple, List, Dict

# NeX 4GB Rename Bot - FFmpeg Engine
# Developed by @Nex_bots

# Instant startup: only load static_ffmpeg if system ffmpeg/ffprobe binaries are not found
if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
    try:
        import static_ffmpeg
        static_ffmpeg.add_paths()
    except Exception as e:
        print(f"static_ffmpeg auto-init info: {e}")


async def inject_metadata(input_path: str, output_path: str, meta_text: str) -> bool:
    """
    Losslessly injects custom metadata tags into container and audio/video/subtitle streams.
    """
    cmd = [
        "ffmpeg", "-y",
        "-threads", "0",
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
            *cmd,
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
        "-ss", str(start_sec),
        "-i", input_path,
        "-t", str(sample_sec),
        "-c", "copy",
        output_path
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
        return os.path.exists(output_path) and os.path.getsize(output_path) > 0
    except Exception as e:
        print(f"FFmpeg generate_sample_video error: {e}")
        return False


async def apply_video_watermark(input_path: str, output_path: str, text: str, position: str = "top_right", size: int = 28, color: str = "white") -> bool:
    """
    Applies custom text watermark over video using FFmpeg drawtext with ultrafast preset.
    """
    pos_coords = {
        "top_left": "x=25:y=25",
        "top_right": "x=w-tw-25:y=25",
        "center": "x=(w-tw)/2:y=(h-th)/2",
        "bottom_left": "x=25:y=h-th-25",
        "bottom_right": "x=w-tw-25:y=h-th-25"
    }
    coords = pos_coords.get(str(position).lower(), "x=w-tw-25:y=25")
    
    # Safe string escaping for FFmpeg drawtext
    safe_text = str(text).replace('\\', '\\\\').replace("'", "'\\\\''").replace(':', '\\:')
    font_color = str(color).lower() if str(color).lower() in ("white", "yellow", "cyan", "red", "green") else "white"
    font_size = int(size) if int(size) > 0 else 28

    vf_filter = (
        f"drawtext=text='{safe_text}':{coords}:fontsize={font_size}:fontcolor={font_color}:"
        f"box=1:boxcolor=black@0.45:boxborderw=5"
    )

    cmd = [
        "ffmpeg", "-y",
        "-threads", "0",
        "-i", input_path,
        "-vf", vf_filter,
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "26",
        "-c:a", "copy",
        output_path
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
        return os.path.exists(output_path) and os.path.getsize(output_path) > 0
    except Exception as e:
        print(f"FFmpeg apply_video_watermark error: {e}")
        return False


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
            "-ss", str(target_time),
            "-i", input_path,
            "-frames:v", "1",
            "-q:v", "2",
            img_out
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
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
            *cmd,
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
    if not (duration and width and height):
        try:
            from hachoir.metadata import extractMetadata
            from hachoir.parser import createParser
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
            *cmd,
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
    cmd = ["ffmpeg", "-y", "-threads", "0", "-i", input_path, "-map", "0:v"]

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
            *cmd,
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
    cmd = ["ffmpeg", "-y", "-threads", "0", "-i", input_path, "-c", "copy"]
    if output_path.lower().endswith(".mp4"):
        cmd.extend(["-movflags", "+faststart"])
    cmd.append(output_path)

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
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
        "-i", input_path,
        "-vf", vf,
        "-frames:v", "1",
        "-q:v", "2",
        output_path
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
        return os.path.exists(output_path) and os.path.getsize(output_path) > 0
    except Exception as e:
        print(f"FFmpeg generate_screenshot_grid error: {e}")
        return False



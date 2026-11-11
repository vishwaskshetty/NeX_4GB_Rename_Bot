import os
import json
import asyncio
from typing import Tuple, List

# NeX 4GB Rename Bot - FFmpeg Engine
# Developed by @Nex_bots


async def inject_metadata(input_path: str, output_path: str, meta_text: str) -> bool:
    """
    Losslessly injects custom metadata tags into container and audio/video/subtitle streams.
    """
    cmd = [
        "ffmpeg", "-y",
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


async def generate_sample_video(input_path: str, output_path: str, total_duration: int, sample_sec: int) -> bool:
    """
    Cuts a lossless sample video clip of sample_sec length starting 20% into the video.
    """
    if total_duration > (sample_sec + 10):
        start_sec = int(total_duration * 0.20)
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


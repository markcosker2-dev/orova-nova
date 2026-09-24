#!/usr/bin/env python
"""Fail closed on basic Instagram Reel media and OROVA caption defects.

This checks a local deliverable before it enters Make. A pass does *not* prove
that Make retained the caption or that Instagram accepted the media; both still
need to be verified in their respective live systems.

Usage:
    python scripts/ig_reel_preflight.py VIDEO CAPTION [--url PUBLIC_VIDEO_URL]
"""

from __future__ import annotations

import argparse
from fractions import Fraction
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlparse
from urllib.request import Request, urlopen


HASHTAG_BLOCK = re.compile(r"#[\w]+(?:[ \t]+#[\w]+){2,4}", re.UNICODE)
MAX_VIDEO_BYTES = 1_000_000_000


def validate_caption(caption: str) -> list[str]:
    """Return only deterministic formatting errors, never claim judgments."""
    errors: list[str] = []
    normalized = caption.replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(normalized) > 2200:
        errors.append("caption exceeds Instagram's 2,200-character limit")
    blocks = [block.strip() for block in re.split(r"\n[ \t]*\n", normalized) if block.strip()]
    if len(blocks) < 3:
        errors.append("caption needs short paragraphs and a separate hashtag block with real blank lines")
    if not blocks or not HASHTAG_BLOCK.fullmatch(blocks[-1]):
        errors.append("final block must contain 3-5 space-separated hashtags only")
    if any("#" in block for block in blocks[:-1]):
        errors.append("keep hashtags in the final block, after the CTA")
    return errors


def probe_video(path: Path) -> dict:
    command = [
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration,size:stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate,bit_rate",
        "-of", "json", str(path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=20, check=True)
    return json.loads(result.stdout)


def validate_video(probe: dict, file_size: int) -> list[str]:
    errors: list[str] = []
    if file_size <= 0 or file_size > MAX_VIDEO_BYTES:
        errors.append("video size must be greater than zero and at most 1 GB")
    streams = probe.get("streams") or []
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
    try:
        duration = float((probe.get("format") or {}).get("duration", 0))
    except (TypeError, ValueError):
        duration = 0
    if not 3 <= duration <= 900:
        errors.append("Reel duration must be between 3 seconds and 15 minutes")
    if not video:
        errors.append("video stream is missing")
    else:
        if video.get("codec_name") not in {"h264", "hevc"}:
            errors.append("video codec must be H.264 or HEVC")
        width, height = video.get("width") or 0, video.get("height") or 0
        if not width or not height or width > 1920 or abs(width / height - 9 / 16) > 0.03:
            errors.append("video must be vertical 9:16 with width at most 1920 pixels")
        try:
            fps = float(Fraction(video.get("r_frame_rate") or "0"))
        except (TypeError, ValueError, ZeroDivisionError):
            fps = 0
        if not 23 <= fps <= 60:
            errors.append("video frame rate must be between 23 and 60 fps")
    if not audio:
        errors.append("informational OROVA Reels require an audio stream")
    else:
        if audio.get("codec_name") != "aac":
            errors.append("audio codec must be AAC")
        if str(audio.get("sample_rate")) != "48000":
            errors.append("audio sample rate must be 48 kHz")
    return errors


def check_public_url(url: str, local_size: int) -> tuple[list[str], list[str]]:
    """Check public fetchability; MIME alone is a warning, not a proof of failure."""
    errors: list[str] = []
    warnings: list[str] = []
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        return ["video URL must be public HTTPS without embedded credentials"], warnings
    try:
        request = Request(url, method="HEAD", headers={"User-Agent": "OROVA-Reel-Preflight/1.0"})
        with urlopen(request, timeout=15) as response:
            if response.status != 200:
                errors.append(f"video URL returned HTTP {response.status}, not 200")
            length = response.headers.get("Content-Length")
            if length and int(length) != local_size:
                errors.append("hosted video byte count differs from local file")
            media_type = response.headers.get_content_type()
            if media_type not in {"video/mp4", "video/quicktime"}:
                warnings.append(f"host serves {media_type}; Instagram ingestion still needs live verification")
    except Exception as exc:  # Network/provider errors should fail visibly.
        errors.append(f"public video URL could not be checked: {type(exc).__name__}")
    return errors, warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path, help="local MP4 file")
    parser.add_argument("caption", type=Path, help="UTF-8 CAPTION.txt file")
    parser.add_argument("--url", help="public URL that Make will fetch")
    args = parser.parse_args(argv)
    errors: list[str] = []
    warnings: list[str] = []
    if not args.video.is_file() or args.video.suffix.lower() != ".mp4":
        errors.append("video must be an existing MP4 file")
    if not args.caption.is_file():
        errors.append("caption file does not exist")
    if not errors:
        try:
            errors.extend(validate_caption(args.caption.read_text(encoding="utf-8")))
        except (OSError, UnicodeError) as exc:
            errors.append(f"caption could not be read as UTF-8: {type(exc).__name__}")
        try:
            errors.extend(validate_video(probe_video(args.video), args.video.stat().st_size))
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
            errors.append(f"ffprobe could not inspect video: {type(exc).__name__}")
        if args.url:
            url_errors, url_warnings = check_public_url(args.url, args.video.stat().st_size)
            errors.extend(url_errors)
            warnings.extend(url_warnings)
    print(json.dumps({"ok": not errors, "errors": errors, "warnings": warnings}, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

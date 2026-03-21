"""
Export transcripts to TXT and SRT formats.
"""
from typing import Optional


def _format_srt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def export_transcript(
    text: str,
    segments: list,
    filepath: str,
    fmt: str = "txt",
) -> None:
    if fmt == "srt":
        _export_srt(segments, text, filepath)
    else:
        _export_txt(text, filepath)


def _export_txt(text: str, filepath: str) -> None:
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(text)


def _export_srt(segments: list, fallback_text: str, filepath: str) -> None:
    with open(filepath, "w", encoding="utf-8") as f:
        if not segments:
            f.write(f"1\n00:00:00,000 --> 00:00:30,000\n{fallback_text}\n")
            return

        for i, seg in enumerate(segments, 1):
            start = _format_srt_time(seg.start)
            end = _format_srt_time(seg.end)
            speaker = f"[{seg.speaker}] " if getattr(seg, "speaker", None) else ""
            f.write(f"{i}\n{start} --> {end}\n{speaker}{seg.text}\n\n")

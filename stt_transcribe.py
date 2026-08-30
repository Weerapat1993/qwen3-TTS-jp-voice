#!/usr/bin/env python3
"""Whisper STT wrapper สำหรับ /transcribe (TTS-1005) — local, no cloud

ใช้ mlx-whisper บน Apple Silicon; ไม่ import discord
โมเดล default = mlx-community/whisper-large-v3-turbo (~1.6 GB, โหลดครั้งแรก
ลง Hugging Face cache) override ด้วย env var TRANSCRIBE_WHISPER_MODEL
ต้องมี ffmpeg/ffprobe ใน PATH (โปรเจกต์นี้ require อยู่แล้ว)
"""
import os
import subprocess

WHISPER_MODEL = os.environ.get(
    "TRANSCRIBE_WHISPER_MODEL", "mlx-community/whisper-large-v3-turbo")


def probe_duration(audio_path: str) -> float:
    """คืนความยาวเสียง (วินาที) ผ่าน ffprobe

    raise RuntimeError ถ้า ffprobe ล้มเหลวหรือ parse ค่าไม่ได้
    (caller แปลงเป็น ephemeral error)
    """
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", audio_path],
            capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as e:
        raise RuntimeError(f"ffprobe failed: {e}") from e
    if out.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {out.stderr.strip()}")
    try:
        return float(out.stdout.strip())
    except ValueError as e:
        raise RuntimeError(f"ffprobe returned no duration: {out.stdout!r}") from e


def transcribe(audio_path: str) -> list[str]:
    """ถอดเสียงไฟล์เป็น list ของข้อความต่อ segment (ตัด segment ว่างทิ้ง คงลำดับ)

    import mlx_whisper ในฟังก์ชัน เพื่อไม่ให้การ import โมดูลนี้ (เช่นตอน test
    probe_duration) ลาก mlx เข้ามาโหลดช้า
    mlx_whisper แคชน้ำหนักโมเดลเองใน HF cache — call แรกของโมเดลใหม่ = ดาวน์โหลด
    """
    import mlx_whisper

    result = mlx_whisper.transcribe(
        audio_path, path_or_hf_repo=WHISPER_MODEL, language="th")
    lines: list[str] = []
    for seg in result.get("segments", []):
        text = (seg.get("text") or "").strip()
        if text:
            lines.append(text)
    return lines

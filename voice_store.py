#!/usr/bin/env python3
"""Voice-clone file store สำหรับ /voice-clone (TTS-1009) — pure, ไม่ import discord

จัดการไฟล์ใน voices/<name>.{wav,txt,instruct.txt}:
  <name>.wav           เสียงอ้างอิงสำหรับโคลน (mono 24kHz)
  <name>.txt           transcript ของเสียงอ้างอิง (จาก Whisper) — ช่วย cloning
  <name>.instruct.txt  default voice instruction (optional)

ชื่อเสียงถูกจำกัดที่ [a-z0-9_]{1,32} เพื่อกัน path traversal / อักขระแปลก
"liino" เป็น reserved: ห้ามลบ/rename และ create ทับต้องใส่ overwrite=True

โมดูลนี้ import VOICES_DIR จาก qwen_clone_tts (single source of truth ของ
constants ตาม CLAUDE.md) และ probe_duration จาก stt_transcribe — ไม่ duplicate
"""
import os
import re
import subprocess

from qwen_clone_tts import VOICES_DIR
from stt_transcribe import probe_duration as probe_duration_seconds

VOICE_NAME_RE = re.compile(r"^[a-z0-9_]{1,32}$")
RESERVED = frozenset({"liino"})

MIN_REF_SECONDS = 3.0
REF_TRIM_SECONDS = 12


class VoiceStoreError(Exception):
    """error ที่ปลอดภัยจะแสดงให้ผู้ใช้ Discord เห็น (ข้อความเป็น English)"""


def sanitize_name(raw: str) -> str:
    """normalize + validate ชื่อเสียง — lowercase + strip

    raise VoiceStoreError ถ้าไม่ตรง [a-z0-9_]{1,32} (กัน path traversal, space,
    emoji, ชื่อว่าง, ยาวเกิน)
    """
    name = (raw or "").strip().lower()
    if not VOICE_NAME_RE.match(name):
        raise VoiceStoreError(
            "voice name must be 1-32 chars of a-z, 0-9, underscore only")
    return name


def is_reserved(name: str) -> bool:
    return name.lower() in RESERVED


def voice_paths(name: str) -> tuple[str, str, str]:
    """คืน absolute (wav, txt, instruct_txt) — ไม่เช็คว่าไฟล์มีอยู่จริง"""
    base = os.path.join(VOICES_DIR, name)
    return (os.path.abspath(base + ".wav"),
            os.path.abspath(base + ".txt"),
            os.path.abspath(base + ".instruct.txt"))


def voice_exists(name: str) -> bool:
    return os.path.exists(voice_paths(name)[0])


def read_instruction(name: str) -> str | None:
    """คืนเนื้อหา <name>.instruct.txt (strip) หรือ None ถ้าไม่มี/ว่าง"""
    _, _, ins = voice_paths(name)
    if not os.path.exists(ins):
        return None
    with open(ins, "r", encoding="utf-8") as f:
        text = f.read().strip()
    return text or None


def write_instruction(name: str, text: str) -> None:
    """เขียน <name>.instruct.txt — text ว่าง/ช่องว่างล้วน = ลบไฟล์ถ้ามี"""
    _, _, ins = voice_paths(name)
    text = (text or "").strip()
    if not text:
        if os.path.exists(ins):
            os.remove(ins)
        return
    with open(ins, "w", encoding="utf-8") as f:
        f.write(text + "\n")


def list_voices() -> list[dict]:
    """หนึ่ง dict ต่อ voices/*.wav (เรียงตามชื่อ):
    {"name": str, "has_transcript": bool, "instruction": str | None}
    """
    if not os.path.isdir(VOICES_DIR):
        return []
    names = sorted(
        f[:-4] for f in os.listdir(VOICES_DIR) if f.endswith(".wav"))
    out: list[dict] = []
    for name in names:
        _, txt, _ = voice_paths(name)
        out.append({
            "name": name,
            "has_transcript": os.path.exists(txt),
            "instruction": read_instruction(name),
        })
    return out


def rename_voice(old: str, new: str) -> None:
    """ย้าย .wav/.txt/.instruct.txt ที่มีอยู่จาก old -> new

    old/new ต้อง sanitize มาแล้ว raise VoiceStoreError ถ้า old ไม่มีอยู่,
    old หรือ new เป็น reserved, หรือ new มีอยู่แล้ว
    """
    if is_reserved(old) or is_reserved(new):
        raise VoiceStoreError("cannot rename to or from a reserved voice name")
    if not voice_exists(old):
        raise VoiceStoreError(f"voice '{old}' not found")
    if voice_exists(new):
        raise VoiceStoreError(f"voice '{new}' already exists")
    for src, dst in zip(voice_paths(old), voice_paths(new)):
        if os.path.exists(src):
            os.rename(src, dst)


def delete_voice(name: str) -> list[str]:
    """ลบ .wav/.txt/.instruct.txt ที่มีอยู่ — คืน basename ที่ลบ

    name ต้อง sanitize มาแล้ว raise VoiceStoreError ถ้า reserved หรือไม่มีอยู่
    """
    if is_reserved(name):
        raise VoiceStoreError("cannot delete a reserved voice name")
    if not voice_exists(name):
        raise VoiceStoreError(f"voice '{name}' not found")
    removed: list[str] = []
    for p in voice_paths(name):
        if os.path.exists(p):
            os.remove(p)
            removed.append(os.path.basename(p))
    return removed


def prepare_ref_audio(src_path: str, dst_wav: str) -> float:
    """แปลงไฟล์เสียงอ้างอิงเป็น mono 24kHz wav ตัดต้นคลิป REF_TRIM_SECONDS วิ

    raise VoiceStoreError ถ้าไฟล์สั้นกว่า MIN_REF_SECONDS, probe ไม่ได้,
    หรือ ffmpeg ล้มเหลว คืนความยาว (วินาที) ของไฟล์ต้นทาง

    argv ส่งเป็น list เสมอ ไม่มี shell=True; dst_wav ต้องมาจาก sanitize_name
    ของ caller เท่านั้น
    """
    try:
        duration = probe_duration_seconds(src_path)
    except RuntimeError as e:
        raise VoiceStoreError(f"cannot read audio file: {e}") from e
    if duration < MIN_REF_SECONDS:
        raise VoiceStoreError(
            f"reference clip too short ({duration:.1f}s) — "
            f"need at least {MIN_REF_SECONDS:.0f}s")
    r = subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-i", src_path, "-t", str(REF_TRIM_SECONDS),
         "-ac", "1", "-ar", "24000", "-c:a", "pcm_s16le", dst_wav],
        capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(dst_wav):
        # ffmpeg อาจทิ้ง output ที่เขียนไม่จบไว้ — ลบทิ้งไม่ให้กลายเป็น voice เสีย
        if os.path.exists(dst_wav):
            os.remove(dst_wav)
        raise VoiceStoreError(f"ffmpeg convert failed: {r.stderr.strip()}")
    return duration

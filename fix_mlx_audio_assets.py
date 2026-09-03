#!/usr/bin/env python3
"""One-time post-install fixup: copy missing Whisper tokenizer assets into mlx-audio.

ปัญหา: `mlx-audio` (pinned เป็น git dependency ใน requirements.txt) ขาดไฟล์
`mlx_audio/stt/models/whisper/assets/{gpt2,multilingual}.tiktoken` จริง ๆ —
หายไปตั้งแต่ upstream source repo เอง ไม่ใช่แค่ install พังฝั่งเรา (เช็คแล้วจาก
git commit ที่ pin ไว้). ไฟล์พวกนี้จำเป็นสำหรับ mlx_audio.tts.generate.generate_audio()
เวลาต้อง auto-transcribe ref_audio เอง (เมื่อไม่มี ref_text ส่งเข้าไป) — ถ้าขาด
จะ crash ด้วย FileNotFoundError: ...multilingual.tiktoken ทุกครั้งที่ voice-clone
ไม่มี transcript พร้อม (เช่น /voice-clone create ที่ STT ได้ transcript ว่างเปล่า)

แก้โดย copy ไฟล์เดียวกันเป๊ะจาก `mlx-whisper` (pinned อยู่แล้วใน requirements.txt,
เช็ค md5 ตรงกัน) ไปวางใน assets dir ของ mlx_audio ที่หายไป

รันครั้งเดียวหลัง `pip install -r requirements.txt` ทุกครั้ง (รวมถึงหลัง reinstall/
upgrade mlx-audio) — idempotent, รันซ้ำได้ปลอดภัย ไม่ error ถ้าไฟล์มีอยู่แล้ว
"""
import shutil
import sys
from pathlib import Path

ASSET_NAMES = ("gpt2.tiktoken", "multilingual.tiktoken")


def main() -> int:
    try:
        import mlx_audio
        import mlx_whisper
    except ImportError as e:
        print(f"ERROR: {e} — run `pip install -r requirements.txt` first",
              file=sys.stderr)
        return 1

    src_dir = Path(mlx_whisper.__file__).parent / "assets"
    dst_dir = (Path(mlx_audio.__file__).parent
               / "stt" / "models" / "whisper" / "assets")
    dst_dir.mkdir(parents=True, exist_ok=True)

    copied = []
    for name in ASSET_NAMES:
        src = src_dir / name
        dst = dst_dir / name
        if not src.exists():
            print(f"ERROR: source asset missing: {src} "
                  f"(mlx-whisper version changed? check requirements.txt)",
                  file=sys.stderr)
            return 1
        if dst.exists():
            continue
        shutil.copy2(src, dst)
        copied.append(name)

    if copied:
        print(f"OK copied {copied} -> {dst_dir}")
    else:
        print(f"OK already present in {dst_dir} (nothing to do)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

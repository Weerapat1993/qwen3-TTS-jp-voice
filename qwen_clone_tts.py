#!/usr/bin/env python3
"""Qwen3-TTS voice-clone CLI — ใช้เสียงโคลนจาก voices/ สร้างไฟล์เสียง

Usage:
    qwen_clone_tts.py --text "ข้อความ" [--voice Liino] [--out /path/out.wav]
                      [--instruct "คำบรรยายน้ำเสียง"] [--lang th|en|...]
"""
import argparse
import os
import sys
import tempfile
import time

PROJ = os.path.dirname(os.path.abspath(__file__))
VOICES_DIR = os.path.join(PROJ, "voices")
MODEL_PATH = os.path.join(PROJ, "models", "Qwen3-TTS-12Hz-1.7B-Base-8bit")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", required=True, help="ข้อความที่จะให้อ่าน")
    ap.add_argument("--voice", default="Liino", help="ชื่อเสียงโคลนใน voices/")
    ap.add_argument("--out", default=None, help="ไฟล์ .wav ปลายทาง")
    ap.add_argument("--instruct", default=None,
                    help="คำบรรยายน้ำเสียง เช่น 'cheerful idol voice'")
    args = ap.parse_args()

    ref_audio = os.path.join(VOICES_DIR, f"{args.voice}.wav")
    if not os.path.exists(ref_audio):
        print(f"ERROR: ref voice not found: {ref_audio}", file=sys.stderr)
        return 1
    ref_text = None
    txt_path = os.path.join(VOICES_DIR, f"{args.voice}.txt")
    if os.path.exists(txt_path):
        with open(txt_path, "r", encoding="utf-8") as f:
            ref_text = f.read().strip()

    out_path = args.out or os.path.join(
        tempfile.gettempdir(), "qwen_clone_out.wav")

    t0 = time.time()
    from mlx_audio.tts.utils import load_model
    from mlx_audio.tts.generate import generate_audio

    model = load_model(MODEL_PATH)
    load_s = time.time() - t0

    t1 = time.time()
    generate_audio(model=model, text=args.text, ref_audio=ref_audio,
                   ref_text=ref_text, instruct=args.instruct,
                   output_path=out_path)
    gen_s = time.time() - t1

    # หาไฟล์ที่ mlx_audio เขียนจริง (บางครั้งต่อท้ายเลขนับ)
    if os.path.isdir(out_path):
        cands = sorted(
            (os.path.join(out_path, f) for f in os.listdir(out_path)
             if f.endswith((".wav", ".mp3"))),
            key=os.path.getmtime)
        if not cands:
            print("ERROR: no audio produced", file=sys.stderr)
            return 1
        final = cands[-1]
    elif os.path.exists(out_path):
        final = out_path
    else:
        print("ERROR: output missing", file=sys.stderr)
        return 1

    print(f"OK {final}")
    print(f"TIMING load={load_s:.1f}s gen={gen_s:.1f}s", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

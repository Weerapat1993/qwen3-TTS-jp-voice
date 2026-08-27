#!/usr/bin/env python3
"""Qwen3-TTS voice-clone CLI — ใช้เสียงโคลนจาก voices/ สร้างไฟล์เสียง

Usage:
    qwen_clone_tts.py --text "ข้อความ" [--voice Liino] [--out /path/out.wav]
                      [--instruct "คำบรรยายน้ำเสียง"] [--lang th|en|...]

Hermes command-provider mode:
    qwen_clone_tts.py --stdin <input_path> <output_path>
    (อ่านข้อความจากไฟล์ UTF-8, ตัดความยาวเกิน 300 ตัวอักษร, ใช้เสียงโคลน Liino)
"""
import argparse
import os
import sys
import tempfile
import time

PROJ = os.path.dirname(os.path.abspath(__file__))
VOICES_DIR = os.path.join(PROJ, "voices")
MODEL_PATH = os.path.join(PROJ, "models", "Qwen3-TTS-12Hz-1.7B-Base-8bit")
MAX_CHARS = 300
DEFAULT_INSTRUCT = (
    "cheerful and cute voice, natural clear pronunciation")


def _run(voice: str, text: str, out_path: str, instruct: str | None) -> int:
    ref_audio = os.path.join(VOICES_DIR, f"{voice}.wav")
    if not os.path.exists(ref_audio):
        print(f"ERROR: ref voice not found: {ref_audio}", file=sys.stderr)
        return 1
    ref_text = None
    txt_path = os.path.join(VOICES_DIR, f"{voice}.txt")
    if os.path.exists(txt_path):
        with open(txt_path, "r", encoding="utf-8") as f:
            ref_text = f.read().strip()

    t0 = time.time()
    from mlx_audio.tts.utils import load_model
    from mlx_audio.tts.generate import generate_audio

    model = load_model(MODEL_PATH)
    load_s = time.time() - t0

    t1 = time.time()
    generate_audio(model=model, text=text, ref_audio=ref_audio,
                   ref_text=ref_text, instruct=instruct,
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


def main() -> int:
    # โหมด Hermes provider: --stdin <input_path> <output_path>
    if "--stdin" in sys.argv:
        rest = [a for a in sys.argv[1:] if a != "--stdin"]
        if len(rest) < 1:
            print("usage: --stdin <input_path> [output_path]",
                  file=sys.stderr)
            return 2
        input_path = rest[0]
        out_path = rest[1] if len(rest) > 1 else os.path.join(
            tempfile.gettempdir(), "qwen_clone_out.wav")
        with open(input_path, "r", encoding="utf-8") as f:
            text = f.read().strip()
        if not text:
            print("ERROR: empty input", file=sys.stderr)
            return 1
        if len(text) > MAX_CHARS:
            text = text[:MAX_CHARS]
            print(f"NOTE: text truncated to {MAX_CHARS} chars",
                  file=sys.stderr)
        return _run("Liino", text, out_path, DEFAULT_INSTRUCT)

    ap = argparse.ArgumentParser()
    ap.add_argument("--text", required=True, help="ข้อความที่จะให้อ่าน")
    ap.add_argument("--voice", default="Liino", help="ชื่อเสียงโคลนใน voices/")
    ap.add_argument("--out", default=None, help="ไฟล์ .wav ปลายทาง")
    ap.add_argument("--instruct", default=None,
                    help="คำบรรยายน้ำเสียง เช่น 'cheerful idol voice'")
    args = ap.parse_args()
    out_path = args.out or os.path.join(
        tempfile.gettempdir(), "qwen_clone_out.wav")
    return _run(args.voice, args.text, out_path, args.instruct)


if __name__ == "__main__":
    sys.exit(main())

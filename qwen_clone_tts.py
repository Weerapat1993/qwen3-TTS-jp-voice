#!/usr/bin/env python3
"""Qwen3-TTS voice-clone CLI — ใช้เสียงโคลนจาก voices/ สร้างไฟล์เสียง

Usage:
    qwen_clone_tts.py --text "ข้อความ" [--voice Liino] [--out /path/out.wav]
                      [--instruct "คำบรรยายน้ำเสียง"] [--lang th|en|...]

Hermes command-provider mode:
    qwen_clone_tts.py --stdin <input_path> <output_path>
    (อ่านข้อความจากไฟล์ UTF-8, ข้อความยาวเกิน 300 ตัวอักษรจะถูกแบ่งเป็น chunk
     แล้วต่อเสียงเป็นไฟล์เดียว, ใช้เสียงโคลน Liino)
"""
import argparse
import contextlib
import io
import os
import re
import sys
import tempfile
import time

PROJ = os.path.dirname(os.path.abspath(__file__))
VOICES_DIR = os.path.join(PROJ, "voices")
MODEL_PATH = os.path.join(PROJ, "models", "Qwen3-TTS-12Hz-1.7B-Base-8bit")
MAX_CHARS = 300
DEFAULT_INSTRUCT = "Cheerful, bright, playful young female voice. Clear and friendly, natural pace, not childish."
# Instruct เดิม (ยาว) — เสียงสไตล์เดิม ใช้ผ่าน --instruct-long หรือ --instruct แบบระบุเอง
DEFAULT_INSTRUCT_LONG = (
    "A youthful Japanese female anime game character voice. "
    "Clear, bright, soft, and feminine timbre with a slightly high pitch. "
    "She sounds cheerful, lively, curious, and friendly, with a subtle "
    "playful quality. Her voice is expressive and energetic but remains "
    "natural and conversational. Use clear Japanese pronunciation, natural "
    "Japanese intonation, and a moderate speaking pace. Add gentle "
    "emotional variation to make the character sound lively and "
    "spontaneous. The overall impression is a charming, energetic young "
    "female game character who is approachable and slightly mischievous. "
    "Do not make the voice overly childish, squeaky, breathy, or "
    "exaggerated.")


# ตัวอักษรที่จบประโยค/ช่องว่างธรรมชาติ (ไทย, อังกฤษ, เลข, วรรคตอน)
_SENT_END = "…!?.;:\n\r"
_SENT_END_RE = re.compile(rf"[{re.escape(_SENT_END)}](?=[\s\u0e01-\u0e4eA-Za-z0-9\"'“”‘’«»-]|$)")


def chunk_text(text: str, max_chars: int = MAX_CHARS) -> list[str]:
    """แบ่งข้อความยาวเป็น chunk ไม่เกิน max_chars โดยตัดที่ขอบเขตประโยค
    หรือช่องว่างเป็นอย่างมาก ไม่ตัดกลางคำ"""
    text = text.strip()
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    rest = text
    while len(rest) > max_chars:
        window = rest[:max_chars]
        # หาตำแหน่งจบประโยค (นับ index ใน window + 1 เพื่อรวมเครื่องหมาย)
        cut = 0
        for m in _SENT_END_RE.finditer(window):
            cut = m.end()
        if cut < 20:  # ไม่มีขอบประโยคที่เหมาะสม -> เลื่อนไปตัดที่ช่องว่าง
            sp = window.rfind(" ")
            if sp < 20:
                # ไทยไม่มีช่องว่างระหว่างคำ: พยายามหา space ทั้งข้อความถัดไป
                sp = rest.find(" ", max_chars)
                cut = sp + 1 if sp != -1 else max_chars
            else:
                cut = sp + 1
        chunk = rest[:cut].strip()
        if chunk:
            chunks.append(chunk)
        rest = rest[cut:].strip()
    if rest:
        chunks.append(rest)
    return chunks


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

    chunks = chunk_text(text)
    multi = len(chunks) > 1
    if multi:
        print(f"NOTE: {len(text)} chars -> {len(chunks)} chunks",
              file=sys.stderr)

    t0 = time.time()
    from mlx_audio.tts.utils import load_model
    from mlx_audio.tts.generate import generate_audio

    model = load_model(MODEL_PATH)
    load_s = time.time() - t0

    t1 = time.time()
    if multi:
        # สร้างเสียงทีละ chunk แล้ว concat ด้วย ffmpeg เป็นไฟล์เดียว
        import shutil
        import subprocess
        if shutil.which("ffmpeg") is None:
            print("ERROR: ffmpeg not found for concat", file=sys.stderr)
            return 1
        tmpdir = tempfile.mkdtemp(prefix="qwen_clone_chunks_")
        part_paths: list[str] = []
        try:
            for i, chunk in enumerate(chunks):
                part = os.path.join(tmpdir, f"part_{i:03d}.wav")
                # suppress tqdm progress bars จาก mlx_audio ในลูป
                with contextlib.redirect_stderr(io.StringIO()), \
                        contextlib.redirect_stdout(io.StringIO()):
                    generate_audio(model=model, text=chunk,
                                   ref_audio=ref_audio, ref_text=ref_text,
                                   instruct=instruct, output_path=part)
                if os.path.isdir(part):
                    cands = sorted(
                        (os.path.join(part, f) for f in os.listdir(part)
                         if f.endswith((".wav", ".mp3"))),
                        key=os.path.getmtime)
                    if not cands:
                        print(f"ERROR: no audio for chunk {i}",
                              file=sys.stderr)
                        return 1
                    part = cands[-1]
                elif not os.path.exists(part):
                    print(f"ERROR: chunk {i} output missing", file=sys.stderr)
                    return 1
                part_paths.append(part)
            list_file = os.path.join(tmpdir, "list.txt")
            with open(list_file, "w", encoding="utf-8") as f:
                for p in part_paths:
                    f.write(f"file '{p}'\n")
            final_out = out_path
            os.makedirs(os.path.dirname(final_out) or ".", exist_ok=True)
            r = subprocess.run(
                ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                 "-f", "concat", "-safe", "0", "-i", list_file,
                 "-ar", "24000", "-ac", "1", final_out],
                capture_output=True, text=True)
            if r.returncode != 0 or not os.path.exists(final_out):
                print(f"ERROR: ffmpeg concat failed: {r.stderr}",
                      file=sys.stderr)
                return 1
            final = final_out
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
    else:
        generate_audio(model=model, text=text, ref_audio=ref_audio,
                       ref_text=ref_text, instruct=instruct,
                       output_path=out_path)
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

    gen_s = time.time() - t1

    print(f"OK {final}")
    print(f"TIMING load={load_s:.1f}s gen={gen_s:.1f}s", file=sys.stderr)
    return 0


def main() -> int:
    # โหมด Hermes provider: --stdin <input_path> <output_path>
    if "--stdin" in sys.argv:
        rest = [a for a in sys.argv[1:] if a not in ("--stdin",)]
        instruct_long = "--instruct-long" in rest
        rest = [a for a in rest if a != "--instruct-long"]
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
        instruct = DEFAULT_INSTRUCT_LONG if instruct_long else DEFAULT_INSTRUCT
        return _run("Liino", text, out_path, instruct)

    ap = argparse.ArgumentParser()
    ap.add_argument("--text", required=True, help="ข้อความที่จะให้อ่าน")
    ap.add_argument("--voice", default="Liino", help="ชื่อเสียงโคลนใน voices/")
    ap.add_argument("--out", default=None, help="ไฟล์ .wav ปลายทาง")
    ap.add_argument("--instruct", default=None,
                    help="คำบรรยายน้ำเสียง เช่น 'cheerful idol voice'")
    ap.add_argument("--instruct-long", action="store_true",
                    help="ใช้ instruct ยาวสไตล์เดิม (full_default)")
    args = ap.parse_args()
    out_path = args.out or os.path.join(
        tempfile.gettempdir(), "qwen_clone_out.wav")
    if args.instruct_long:
        instruct = DEFAULT_INSTRUCT_LONG
    else:
        instruct = args.instruct
    return _run(args.voice, args.text, out_path, instruct)


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Qwen3-TTS voice-clone CLI — ใช้เสียงโคลนจาก voices/ สร้างไฟล์เสียง

Usage:
    qwen_clone_tts.py --text "ข้อความ" [--voice Liino] [--out /path/out.wav]
                      [--instruct "คำบรรยายน้ำเสียง"]
                      [--lang auto|japanese|english|chinese|...]

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


MOOD_PRESETS: dict[str, str] = {
    # ชื่อ mood -> instruct ที่ส่งให้โมเดล (ภาษาอังกฤษเพื่อความแม่นของโมเดล)
    "default":   DEFAULT_INSTRUCT,
    "long":      DEFAULT_INSTRUCT_LONG,
    "excited":   "Very excited and enthusiastic young female voice, "
                 "fast-paced and energetic, sparkling with joy.",
    "sleepy":    "Soft, drowsy, relaxed young female voice. Slow pace, "
                 "gentle and low energy, like talking just before falling asleep.",
    "surprised": "Surprised young female voice with a gasp of amazement, "
                 "wide-eyed and astonished, briefly raised pitch.",
    "sad":       "Sad, melancholic young female voice. Slow, quiet and "
                 "emotional, with a hint of sniffle, not overly dramatic.",
    "angry":     "Angry, pouty young female voice. Sharp and huffy like "
                 "playful irritation, not genuinely hostile.",
    "whisper":   "Soft whispering young female voice. Very quiet, intimate "
                 "and close to the microphone, sharing a secret.",
    "gentle":    "Warm, gentle, soothing young female voice. Kind and calm, "
                 "comforting, moderate slow pace.",
    "giggle":    "Playful young female voice mid-giggle, light and bouncy, "
                 "cheerful with a little laugh in the tone.",
    "bored":     "Bored, unenthusiastic young female voice. Flat and droning, "
                 "dragging slightly, with a sigh in the middle, low energy.",
    "storyteller": "Warm expressive storyteller voice, like narrating a "
                   "bedtime story. Rich intonation, gentle suspense, "
                   "slowing down at key moments, inviting the listener in.",
}


# ภาษาที่ Qwen3-TTS-12Hz รองรับ — ดึงจาก config.json ของโมเดล
# (talker_config.codec_language_id) + "auto" (ให้โมเดลเดาจากข้อความ)
# หมายเหตุ: โมเดลไม่รองรับภาษาไทย — ข้อความไทยใช้ "auto" เท่านั้น
LANG_CODES: tuple[str, ...] = (
    "auto", "chinese", "english", "french", "german", "italian",
    "japanese", "korean", "portuguese", "russian", "spanish",
)


def resolve_lang(lang: str | None) -> str:
    """normalize + validate language code — คืน "auto" ถ้าไม่ระบุ

    lowercase + strip; ไม่อยู่ใน LANG_CODES -> ValueError (caller แปลงเป็น
    ERROR: / ephemeral). ปล่อยผ่านเงียบ ๆ ไม่ได้ เพราะ lang ผิดจะออกเสียงเพี้ยน
    """
    if not lang:
        return "auto"
    code = lang.strip().lower()
    if code not in LANG_CODES:
        raise ValueError(
            f"unknown lang '{code}' — choices: {', '.join(LANG_CODES)}")
    return code


def resolve_instruct(mood: str | None, instruct: str | None,
                     instruct_long: bool) -> str | None:
    """เลือก instruct: --mood มีลำดับความสำคัญก่อน --instruct / --instruct-long"""
    if instruct_long:
        return DEFAULT_INSTRUCT_LONG
    if mood:
        m = mood.strip().lower()
        if m not in MOOD_PRESETS:
            raise ValueError(
                f"unknown mood '{m}' — choices: {', '.join(sorted(MOOD_PRESETS))}")
        return MOOD_PRESETS[m]
    if instruct:
        return instruct
    return MOOD_PRESETS["default"]


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


SOCK_PATH = "/tmp/qwen_tts_daemon.sock"
DAEMON_TIMEOUT_S = 600.0        # รอผล generation นานสุด 10 นาที
DAEMON_CONNECT_TIMEOUT_S = 5.0  # connect socket ต้องเร็ว


def _try_daemon(text: str, out_path: str, instruct: str | None,
                voice: str = "Liino", fmt: str = "wav",
                lang: str = "auto") -> bool:
    """ส่งงานผ่าน tts_daemon ถ้ารันอยู่ — คืน False ถ้า daemon ไม่พร้อม"""
    import json as _json
    import socket as _socket
    if not os.path.exists(SOCK_PATH):
        return False
    try:
        sock = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
        # connect เร็ว (daemon ควรตอบทันทีว่าพร้อมหรือไม่) แต่รอผล gen ได้นาน
        sock.settimeout(DAEMON_CONNECT_TIMEOUT_S)
        sock.connect(SOCK_PATH)
        sock.sendall((_json.dumps(
            {"text": text, "instruct": instruct, "out_path": out_path,
             "voice": voice, "format": fmt, "lang": lang}) + "\n").encode("utf-8"))
        sock.settimeout(DAEMON_TIMEOUT_S)
        buf = b""
        while not buf.endswith(b"\n"):
            data = sock.recv(65536)
            if not data:
                break
            buf += data
        sock.close()
        resp = _json.loads(buf.decode("utf-8"))
    except (OSError, ValueError):
        return False
    if not resp.get("ok"):
        print(f"ERROR: daemon failed: {resp.get('error')}", file=sys.stderr)
        return False
    tag = " (cached)" if resp.get("cached") else ""
    print(f"OK {resp['out_path']}")
    qw = resp.get("queue_wait_s")
    qw_s = f" queue_wait={qw:.2f}s" if isinstance(qw, (int, float)) else ""
    print(f"TIMING via daemon gen={resp.get('gen_s', 0):.2f}s{qw_s}{tag}",
          file=sys.stderr)
    return True


def _convert_to_mp3(path: str) -> str:
    """แปลงไฟล์เสียงเป็น .mp3 ด้วย ffmpeg — คืน path ของ mp3"""
    import shutil as _shutil
    import subprocess as _sub
    if _shutil.which("ffmpeg") is None:
        print("ERROR: ffmpeg not found for mp3 convert", file=sys.stderr)
        return path
    base, _ = os.path.splitext(path)
    mp3_path = base + ".mp3"
    r = _sub.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-i", path, "-codec:a", "libmp3lame", "-qscale:a", "4", mp3_path],
        capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(mp3_path):
        print(f"ERROR: ffmpeg mp3 convert failed: {r.stderr}", file=sys.stderr)
        return path
    return mp3_path


def _run(voice: str, text: str, out_path: str, instruct: str | None,
         mp3: bool = False, lang: str = "auto") -> int:
    ref_audio = os.path.join(VOICES_DIR, f"{voice}.wav")
    if not os.path.exists(ref_audio):
        print(f"ERROR: ref voice not found: {ref_audio}", file=sys.stderr)
        return 1

    # ลอง daemon ก่อน (ไม่ต้องโหลดโมเดล) — ถ้าไม่รัน fallback โหลดเอง
    if _try_daemon(text, out_path, instruct, voice,
                   fmt="mp3" if mp3 else "wav", lang=lang):
        return 0

    ref_text = None
    txt_path = os.path.join(VOICES_DIR, f"{voice}.txt")
    if os.path.exists(txt_path):
        with open(txt_path, "r", encoding="utf-8") as f:
            ref_text = f.read().strip()

    chunks = chunk_text(text)
    if len(text) > MAX_CHARS:
        print(f"ERROR: text is {len(text)} chars — max is {MAX_CHARS} "
              f"(long-text chunking is disabled)", file=sys.stderr)
        return 1
    multi = False

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
                                   instruct=instruct, lang_code=lang,
                                   output_path=part)
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
                       ref_text=ref_text, instruct=instruct, lang_code=lang,
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

    final_out = final
    if mp3:
        final_out = _convert_to_mp3(final)

    print(f"OK {final_out}")
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
        mood = None
        if "--mood" in rest:
            i = rest.index("--mood")
            mood = rest[i + 1] if i + 1 < len(rest) else None
            rest = rest[:i] + rest[i + 2:]
        lang = "auto"
        if "--lang" in rest:
            i = rest.index("--lang")
            lang = rest[i + 1] if i + 1 < len(rest) else "auto"
            rest = rest[:i] + rest[i + 2:]
        try:
            lang = resolve_lang(lang)
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 2
        try:
            instruct = resolve_instruct(mood, None,
                                        "--instruct-long" in rest)
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 2
        return _run("Liino", text, out_path, instruct,
                    mp3="--mp3" in rest, lang=lang)

    ap = argparse.ArgumentParser()
    ap.add_argument("--text", required=True, help="ข้อความที่จะให้อ่าน")
    ap.add_argument("--voice", default="Liino", help="ชื่อเสียงโคลนใน voices/")
    ap.add_argument("--out", default=None, help="ไฟล์ .wav ปลายทาง")
    ap.add_argument("--mp3", action="store_true",
                    help="แปลงผลลัพธ์เป็น .mp3 (ffmpeg libmp3lame)")
    ap.add_argument("--instruct", default=None,
                    help="คำบรรยายน้ำเสียง เช่น 'cheerful idol voice'")
    ap.add_argument("--instruct-long", action="store_true",
                    help="ใช้ instruct ยาวสไตล์เดิม (full_default)")
    ap.add_argument("--mood", default=None,
                    choices=sorted(MOOD_PRESETS),
                    help="น้ำเสียงสำเร็จรูป เช่น excited, sleepy, whisper")
    ap.add_argument("--lang", default="auto", choices=LANG_CODES,
                    help="ภาษาที่โมเดลออกเสียง (default auto = เดาจากข้อความ; "
                         "ภาษาไทยใช้ auto)")
    args = ap.parse_args()
    out_path = args.out or os.path.join(
        tempfile.gettempdir(), "qwen_clone_out.wav")
    try:
        instruct = resolve_instruct(args.mood, args.instruct,
                                    args.instruct_long)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    return _run(args.voice, args.text, out_path, instruct, mp3=args.mp3,
                lang=args.lang)


if __name__ == "__main__":
    sys.exit(main())

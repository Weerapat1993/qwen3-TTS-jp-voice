#!/usr/bin/env python3
"""Qwen3-TTS daemon — โหลดโมเดลครั้งเดียว รับ request ผ่าน Unix domain socket

Protocol (JSON บรรทัดเดียว จบด้วย newline):
    request : {"text": str, "instruct": str|null, "out_path": str, "voice": str?}
    response: {"ok": bool, "out_path": str, "gen_s": float,
               "error": str|null, "cached": bool}

รัน: .venv/bin/python tts_daemon.py
Socket: /tmp/qwen_tts_daemon.sock (Unix domain เท่านั้น — ไม่เปิด TCP)
Cache: ~/.cache/qwen_tts/ (key = sha256(text|instruct|voice))
"""
import hashlib
import json
import os
import shutil
import signal
import socket
import sys
import tempfile
import time

PROJ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJ)

from qwen_clone_tts import (  # noqa: E402
    DEFAULT_INSTRUCT, MAX_CHARS, MODEL_PATH, VOICES_DIR, chunk_text)

SOCK_PATH = "/tmp/qwen_tts_daemon.sock"
CACHE_DIR = os.path.expanduser("~/.cache/qwen_tts")
_running = True


def _on_signal(signum, frame):
    global _running
    _running = False


def _cache_key(text: str, instruct: str | None, voice: str) -> str:
    h = hashlib.sha256()
    h.update(f"{voice}\x00{text}\x00{instruct or ''}".encode("utf-8"))
    return h.hexdigest()


def _resolve_audio_path(path: str) -> str | None:
    """mlx_audio บางครั้งเขียนเป็น dir หรือต่อท้ายเลขนับ — หาไฟล์จริง"""
    if os.path.isdir(path):
        cands = sorted(
            (os.path.join(path, f) for f in os.listdir(path)
             if f.endswith((".wav", ".mp3"))),
            key=os.path.getmtime)
        return cands[-1] if cands else None
    return path if os.path.exists(path) else None


def _generate(model, ref_audio: str, ref_text: str | None, text: str,
              instruct: str | None, out_path: str) -> float:
    """generate เสียง 1 ชิ้น (chunk เองถ้ายาว) คืนเวลา gen เป็นวินาที"""
    import contextlib
    import io
    import subprocess

    from mlx_audio.tts.generate import generate_audio

    chunks = chunk_text(text, MAX_CHARS)
    multi = len(chunks) > 1
    t1 = time.time()
    if multi:
        tmpdir = tempfile.mkdtemp(prefix="qwen_daemon_chunks_")
        part_paths: list[str] = []
        try:
            for i, chunk in enumerate(chunks):
                part = os.path.join(tmpdir, f"part_{i:03d}.wav")
                with contextlib.redirect_stderr(io.StringIO()), \
                        contextlib.redirect_stdout(io.StringIO()):
                    generate_audio(model=model, text=chunk,
                                   ref_audio=ref_audio, ref_text=ref_text,
                                   instruct=instruct, output_path=part)
                final = _resolve_audio_path(part)
                if final is None:
                    raise RuntimeError(f"chunk {i} produced no audio")
                part_paths.append(final)
            list_file = os.path.join(tmpdir, "list.txt")
            with open(list_file, "w", encoding="utf-8") as f:
                for p in part_paths:
                    f.write(f"file '{p}'\n")
            os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
            r = subprocess.run(
                ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                 "-f", "concat", "-safe", "0", "-i", list_file,
                 "-ar", "24000", "-ac", "1", out_path],
                capture_output=True, text=True)
            if r.returncode != 0 or not os.path.exists(out_path):
                raise RuntimeError(f"ffmpeg concat failed: {r.stderr}")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
    else:
        with contextlib.redirect_stderr(io.StringIO()), \
                contextlib.redirect_stdout(io.StringIO()):
            generate_audio(model=model, text=text, ref_audio=ref_audio,
                           ref_text=ref_text, instruct=instruct,
                           output_path=out_path)
        final = _resolve_audio_path(out_path)
        if final is None:
            raise RuntimeError("no audio produced")
        if final != out_path:
            # mlx_audio ใช้ output_path เป็น directory เสมอ
            # (เขียน out_path/audio_000.wav) — copy ไฟล์จริงออกมาก่อน
            # แล้วค่อยแทนที่ out_path ให้เป็นไฟล์เดียวตามที่ client ขอ
            tmp = out_path + ".daemon_tmp"
            shutil.copy2(final, tmp)
            shutil.rmtree(out_path, ignore_errors=True)
            os.replace(tmp, out_path)
    return time.time() - t1


def handle_request(model, req: dict) -> dict:
    text = req.get("text", "")
    instruct = req.get("instruct")
    out_path = req.get("out_path")
    voice = req.get("voice", "Liino")
    if not text or not out_path:
        return {"ok": False, "out_path": out_path or "", "gen_s": 0.0,
                "error": "text and out_path are required", "cached": False}

    ref_audio = os.path.join(VOICES_DIR, f"{voice}.wav")
    if not os.path.exists(ref_audio):
        return {"ok": False, "out_path": out_path, "gen_s": 0.0,
                "error": f"ref voice not found: {ref_audio}",
                "cached": False}
    ref_text = None
    txt_path = os.path.join(VOICES_DIR, f"{voice}.txt")
    if os.path.exists(txt_path):
        with open(txt_path, "r", encoding="utf-8") as f:
            ref_text = f.read().strip()

    # cache hit -> copy ทันที
    os.makedirs(CACHE_DIR, exist_ok=True)
    cached_file = os.path.join(CACHE_DIR, _cache_key(text, instruct, voice)
                               + os.path.splitext(out_path)[1] or ".wav")
    if os.path.exists(cached_file):
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        shutil.copy2(cached_file, out_path)
        return {"ok": True, "out_path": out_path, "gen_s": 0.0,
                "error": None, "cached": True}

    try:
        gen_s = _generate(model, ref_audio, ref_text, text, instruct,
                          out_path)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "out_path": out_path, "gen_s": 0.0,
                "error": str(e), "cached": False}
    shutil.copy2(out_path, cached_file)
    return {"ok": True, "out_path": out_path, "gen_s": round(gen_s, 2),
            "error": None, "cached": False}


def main() -> int:
    global _running
    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    if os.path.exists(SOCK_PATH):
        os.unlink(SOCK_PATH)

    t0 = time.time()
    from mlx_audio.tts.utils import load_model
    model = load_model(MODEL_PATH)
    print(f"daemon: model loaded in {time.time() - t0:.1f}s",
          file=sys.stderr, flush=True)

    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(SOCK_PATH)
    srv.listen(8)
    print(f"daemon: listening on {SOCK_PATH}", file=sys.stderr, flush=True)

    try:
        srv.settimeout(0.5)
        while _running:
            try:
                conn, _ = srv.accept()
            except socket.timeout:
                continue
            with conn:
                buf = b""
                while not buf.endswith(b"\n"):
                    data = conn.recv(65536)
                    if not data:
                        break
                    buf += data
                if not buf.strip():
                    continue
                try:
                    req = json.loads(buf.decode("utf-8"))
                except json.JSONDecodeError as e:
                    resp = {"ok": False, "out_path": "", "gen_s": 0.0,
                            "error": f"bad json: {e}", "cached": False}
                else:
                    resp = handle_request(model, req)
                try:
                    conn.sendall(
                        (json.dumps(resp, ensure_ascii=False) + "\n")
                        .encode("utf-8"))
                except OSError:
                    # client หลุดกลางคัน — ไม่ให้ล้ม daemon
                    pass
    finally:
        srv.close()
        if os.path.exists(SOCK_PATH):
            os.unlink(SOCK_PATH)
        print("daemon: shutdown, socket removed", file=sys.stderr,
              flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Qwen3-TTS daemon — โหลดโมเดลครั้งเดียว รับ request ผ่าน Unix domain socket

Protocol (JSON บรรทัดเดียว จบด้วย newline):
    request : {"text": str, "instruct": str|null, "out_path": str, "voice": str?}
    response: {"ok": bool, "out_path": str, "gen_s": float,
               "error": str|null, "cached": bool, "queue_wait_s": float}

FIFO queue + timeout: งานจัดคิวแบบ FIFO ทีละงาน (serial, atomic — งานที่
generate อยู่จะไม่ถูกยกเลิกกลางทาง) ถ้างานถูกประเมินว่าต้องรอคิวเกิน
TTS_QUEUE_TIMEOUT วินาที (default 60) daemon จะตอบ error "queue timeout"
กลับทันทีโดยไม่เข้าคิว

Config ผ่าน environment variables:
    TTS_DAEMON_SOCK     socket path   (default /tmp/qwen_tts_daemon.sock)
    TTS_CACHE_DIR       cache dir     (default ~/.cache/qwen_tts)
    TTS_QUEUE_TIMEOUT   วินาที        (default 60)
    TTS_TELEMETRY_LOG   JSONL log     (default ~/Library/Logs/qwen_tts_daemon.log)

รัน: .venv/bin/python tts_daemon.py
"""
import hashlib
import json
import os
import queue
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time

PROJ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJ)

from qwen_clone_tts import (  # noqa: E402
    DEFAULT_INSTRUCT, MAX_CHARS, MODEL_PATH, VOICES_DIR, chunk_text)

SOCK_PATH = os.environ.get("TTS_DAEMON_SOCK", "/tmp/qwen_tts_daemon.sock")
CACHE_DIR = os.environ.get("TTS_CACHE_DIR", os.path.expanduser("~/.cache/qwen_tts"))
QUEUE_TIMEOUT = float(os.environ.get("TTS_QUEUE_TIMEOUT", "60"))
TELEMETRY_LOG = os.environ.get(
    "TTS_TELEMETRY_LOG",
    os.path.expanduser("~/Library/Logs/qwen_tts_daemon.log"))

_running = True
_log_lock = threading.Lock()


def _on_signal(signum, frame):
    global _running
    _running = False


def _cache_key(text: str, instruct: str | None, voice: str) -> str:
    h = hashlib.sha256()
    h.update(f"{voice}\x00{text}\x00{instruct or ''}".encode("utf-8"))
    return h.hexdigest()


def _load_snapshot() -> dict:
    """system load snapshot สำหรับ telemetry (เร็ว ๆ)"""
    snap: dict = {"loadavg": [round(x, 2) for x in os.getloadavg()]}
    try:
        out = subprocess.run(
            ["ps", "-axo", "pcpu,comm", "-r"],
            capture_output=True, text=True, timeout=2).stdout
        busy = []
        for line in out.splitlines()[1:]:
            parts = line.split(None, 1)
            if len(parts) == 2:
                try:
                    cpu = float(parts[0])
                except ValueError:
                    continue
                if cpu >= 20.0:
                    busy.append({"cpu": cpu,
                                 "cmd": os.path.basename(parts[1].strip())})
        snap["busy_processes"] = sorted(busy, key=lambda d: -d["cpu"])[:5]
    except Exception:  # noqa: BLE001
        pass
    return snap


def log_event(event: str, **fields) -> None:
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
           "event": event, "load": _load_snapshot()}
    rec.update(fields)
    try:
        os.makedirs(os.path.dirname(TELEMETRY_LOG) or ".", exist_ok=True)
        with _log_lock:
            with open(TELEMETRY_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass  # telemetry ต้องไม่ทำให้ daemon ล้ม


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


def handle_request(model, req: dict, queue_wait_s: float = 0.0) -> dict:
    """process งาน 1 ชิ้น (atomic — ไม่ยอมรับงานใหม่ระหว่างทำ)"""
    t_start = time.time()
    text = req.get("text", "")
    instruct = req.get("instruct")
    out_path = req.get("out_path")
    voice = req.get("voice", "Liino")
    log_event("request", text_len=len(text),
              queue_wait_s=round(queue_wait_s, 2))

    def resp(ok: bool, gen_s: float, error: str | None,
             cached: bool = False) -> dict:
        total = time.time() - t_start
        if ok:
            log_event("complete" if not cached else "cache_hit",
                      text_len=len(text), gen_s=round(gen_s, 2),
                      total_s=round(total, 2), queue_wait_s=round(queue_wait_s, 2),
                      cached=cached)
        else:
            log_event("error", text_len=len(text), gen_s=round(gen_s, 2),
                      total_s=round(total, 2), queue_wait_s=round(queue_wait_s, 2),
                      error=error)
        return {"ok": ok, "out_path": out_path or "",
                "gen_s": round(gen_s, 2), "error": error, "cached": cached,
                "queue_wait_s": round(queue_wait_s, 2)}

    if not text or not out_path:
        return resp(False, 0.0, "text and out_path are required")

    ref_audio = os.path.join(VOICES_DIR, f"{voice}.wav")
    if not os.path.exists(ref_audio):
        return resp(False, 0.0, f"ref voice not found: {ref_audio}")
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
        return resp(True, 0.0, None, cached=True)

    try:
        gen_s = _generate(model, ref_audio, ref_text, text, instruct,
                          out_path)
    except Exception as e:  # noqa: BLE001
        return resp(False, 0.0, str(e))
    shutil.copy2(out_path, cached_file)
    _update_est_job_s(gen_s)
    return resp(True, gen_s, None)


# ---- FIFO queue + queue-timeout -------------------------------------------
# ประเมินเวลางานเฉลี่ยล่าสุด (moving average จาก gen_s จริง) เพื่อตัดสินว่า
# งานใหม่จะรอคิวเกิน QUEUE_TIMEOUT หรือไม่ — default 10s ก่อนมีข้อมูลจริง
_est_job_s_val = 10.0
_est_lock = threading.Lock()


def _est_job_s() -> float:
    with _est_lock:
        return _est_job_s_val


def _update_est_job_s(gen_s: float) -> None:
    with _est_lock:
        global _est_job_s_val
        _est_job_s_val = max(1.0, 0.7 * _est_job_s_val + 0.3 * gen_s)


def _apply_process_qos() -> None:
    """ตั้ง Process QoS ของ daemon เป็น user-initiated (best-effort)

    nice ค่าลบ (-5) ต้อง root ซึ่ง launchd user agent ทำไม่ได้ — ใช้
    macOS Process QoS แทน: `taskpolicy -c utility` ได้ แต่เราต้องการ priority
    "สำคัญกว่า" ไม่ใช่ "ยอมแพ้" จึงเรียก `taskpolicy -s policy user-initiated`
    (self ตั้งได้เฉพาะ QoS ต่ำกว่าของเดิมไม่ได้สูงกว่าบนแต่ละ process —
    ถ้าเรียกไม่สำเร็จก็ปล่อยผ่าน เป็น best-effort)
    """
    try:
        subprocess.run(
            ["taskpolicy", "-s", "policy", "user-initiated"],
            check=True, timeout=5,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("daemon: Process QoS set to user-initiated",
              file=sys.stderr, flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"daemon: taskpolicy QoS unavailable ({e}) — running at default",
              file=sys.stderr, flush=True)


def main() -> int:
    global _running
    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)
    _apply_process_qos()

    if os.path.exists(SOCK_PATH):
        os.unlink(SOCK_PATH)

    t0 = time.time()
    from mlx_audio.tts.utils import load_model
    model = load_model(MODEL_PATH)
    print(f"daemon: model loaded in {time.time() - t0:.1f}s",
          file=sys.stderr, flush=True)
    log_event("startup", sock=SOCK_PATH, queue_timeout_s=QUEUE_TIMEOUT,
              telemetry_log=TELEMETRY_LOG)

    # ---- worker thread: ดึงงานจาก FIFO queue ทีละงาน (atomic) ----
    q: queue.Queue = queue.Queue()
    q_depth = 0
    q_lock = threading.Lock()

    def worker() -> None:
        nonlocal q_depth
        while _running or not q.empty():
            try:
                item = q.get(timeout=0.5)
            except queue.Empty:
                continue
            req, t_enq = item
            with q_lock:
                q_depth -= 1
            wait_s = time.time() - t_enq
            if wait_s > QUEUE_TIMEOUT:
                # รอคิวเกิน timeout — ตอบ error ทันที ไม่ generate (งานที่
                # generate อยู่แล้วไม่ถูกยกเลิก: เช็คก่อนเริ่มงานเท่านั้น)
                log_event("error", text_len=len(req.get("text", "")),
                          error="queue timeout", queue_wait_s=round(wait_s, 2))
                conn = req.pop("_conn", None)
                if conn is not None:
                    try:
                        conn.sendall((json.dumps(
                            {"ok": False, "out_path": req.get("out_path", ""),
                             "gen_s": 0.0, "error": "queue timeout",
                             "cached": False,
                             "queue_wait_s": round(wait_s, 2)},
                            ensure_ascii=False) + "\n").encode("utf-8"))
                    except OSError:
                        pass
                    finally:
                        try:
                            conn.close()
                        except OSError:
                            pass
                continue
            try:
                resp = handle_request(model, req, queue_wait_s=wait_s)
            except Exception as e:  # noqa: BLE001
                resp = {"ok": False, "out_path": req.get("out_path", ""),
                        "gen_s": 0.0, "error": str(e), "cached": False,
                        "queue_wait_s": round(wait_s, 2)}
                log_event("error", text_len=len(req.get("text", "")),
                          error=str(e))
            conn = req.pop("_conn", None)
            if conn is not None:
                try:
                    conn.sendall((json.dumps(resp, ensure_ascii=False) + "\n")
                                 .encode("utf-8"))
                except OSError:
                    pass  # client หลุดกลางคัน — ไม่ให้ล้ม daemon
                finally:
                    try:
                        conn.close()
                    except OSError:
                        pass

    threading.Thread(target=worker, daemon=True).start()

    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(SOCK_PATH)
    srv.listen(8)
    print(f"daemon: listening on {SOCK_PATH}", file=sys.stderr, flush=True)

    def send(conn, resp: dict) -> None:
        try:
            conn.sendall((json.dumps(resp, ensure_ascii=False) + "\n")
                         .encode("utf-8"))
        except OSError:
            pass

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
                    send(conn, {"ok": False, "out_path": "", "gen_s": 0.0,
                                "error": f"bad json: {e}", "cached": False,
                                "queue_wait_s": 0.0})
                    continue

                with q_lock:
                    depth = q_depth
                # timeout เชิงป้องกัน: ถ้างานหน้าคิวรวมกันน่าจะกินเวลา
                # เกิน QUEUE_TIMEOUT แล้ว งานใหม่นี้ตอบ timeout ทันที
                if depth > 0 and depth * _est_job_s() > QUEUE_TIMEOUT:
                    log_event("error", text_len=len(req.get("text", "")),
                              error="queue timeout", queue_depth=depth)
                    send(conn, {"ok": False,
                                "out_path": req.get("out_path", ""),
                                "gen_s": 0.0, "error": "queue timeout",
                                "cached": False, "queue_wait_s": 0.0})
                    continue

                # dup socket กัน (with conn จะปิดตอนออกจาก block) แล้ว
                # ยก conn ให้ worker ปิดเองหลังส่งผล
                req["_conn"] = conn.dup()
                with q_lock:
                    q_depth += 1
                q.put((req, time.time()))  # FIFO enqueue
    finally:
        srv.close()
        if os.path.exists(SOCK_PATH):
            os.unlink(SOCK_PATH)
        print("daemon: shutdown, socket removed", file=sys.stderr,
              flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Qwen3-TTS daemon — โหลดโมเดลครั้งเดียว รับ request ผ่าน Unix domain socket

Protocol (JSON บรรทัดเดียว จบด้วย newline):
    request : {"text": str, "instruct": str|null, "out_path": str, "voice": str?,
               "format": "wav"|"mp3"?}
    response: {"ok": bool, "out_path": str, "gen_s": float,
               "error": str|null, "cached": bool, "queue_wait_s": float,
               "format": "wav"|"mp3"}

FIFO queue + timeout: งานจัดคิวแบบ FIFO ทีละงาน (serial, atomic — งานที่
generate อยู่จะไม่ถูกยกเลิกกลางทาง) ถ้างานถูกประเมินว่าต้องรอคิวเกิน
TTS_QUEUE_TIMEOUT วินาที (default 60) daemon จะตอบ error "queue timeout"
กลับทันทีโดยไม่เข้าคิว

Config ผ่าน environment variables:
    TTS_DAEMON_SOCK     socket path   (default /tmp/qwen_tts_daemon.sock)
    TTS_CACHE_DIR       cache dir     (default ~/.cache/qwen_tts)
    TTS_QUEUE_TIMEOUT   วินาที        (default 60)
    TTS_TELEMETRY_LOG   JSONL log     (default ~/Library/Logs/qwen_tts_daemon.log)
    TTS_IDLE_UNLOAD     วินาที        (default 0 = ปิด) — ถ้าไม่มี request
                        นานเกินค่านี้ จะ unload โมเดลเพื่อคืน memory
                        (request ถัดไปโหลดใหม่อัตโนมัติ ~3s)

รัน: .venv/bin/python tts_daemon.py
"""
import hashlib
import gc
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
IDLE_UNLOAD = float(os.environ.get("TTS_IDLE_UNLOAD", "0"))

_running = True
_log_lock = threading.Lock()


def _on_signal(signum, frame):
    global _running
    _running = False


def _load_model() -> object:  # noqa: ANN202
    from mlx_audio.tts.utils import load_model
    return load_model(MODEL_PATH)  # type: ignore[arg-type]


def _ensure_model(holder: dict):
    """lazy reload — ถ้า model ถูก idle-unload ไปแล้วโหลดใหม่"""
    if holder.get("model") is None:
        t0 = time.time()
        holder["model"] = _load_model()
        log_event("model_reload", reload_s=round(time.time() - t0, 2))
        print(f"daemon: model reloaded in {time.time() - t0:.1f}s",
              file=sys.stderr, flush=True)
    return holder["model"]


def _unload_model(holder: dict) -> None:
    """คืน memory: ลบ reference + gc + mlx metal cache"""
    holder["model"] = None
    gc.collect()
    try:
        import mlx.core as mx
        mx.metal.clear_cache()
    except Exception:  # noqa: BLE001
        pass


def _cache_key(text: str, instruct: str | None, voice: str) -> str:
    h = hashlib.sha256()
    h.update(f"{voice}\x00{text}\x00{instruct or ''}".encode("utf-8"))
    return h.hexdigest()


def _convert_mp3(src_wav: str, dst_mp3: str) -> None:
    """แปลง wav -> mp3 ด้วย ffmpeg (libmp3lame -qscale:a 4)"""
    os.makedirs(os.path.dirname(dst_mp3) or ".", exist_ok=True)
    r = subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-i", src_wav, "-codec:a", "libmp3lame", "-qscale:a", "4",
         dst_mp3],
        capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(dst_mp3):
        raise RuntimeError(f"ffmpeg mp3 convert failed: {r.stderr}")


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


def _generate(model_holder, ref_audio: str, ref_text: str | None, text: str,
              instruct: str | None, out_path: str) -> float:
    """generate เสียง 1 ชิ้น (chunk เองถ้ายาว) คืนเวลา gen เป็นวินาที

    model_holder คือ dict {"model": ...} — ถ้า idle-unload ไปแล้วจะโหลดใหม่
    lazy ที่นี่ (cache hit ไม่ผ่านฟังก์ชันนี้ จึงไม่ต้องโหลด model)
    """
    import contextlib
    import io

    from mlx_audio.tts.generate import generate_audio

    model = _ensure_model(model_holder)
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


def handle_request(model_holder, req: dict, queue_wait_s: float = 0.0) -> dict:
    """process งาน 1 ชิ้น (atomic — ไม่ยอมรับงานใหม่ระหว่างทำ)

    model_holder: dict {"model": ...} — เพื่อให้ lazy reload ได้เมื่อ
    idle-unload ปล่อย model ไปแล้ว (ถือ dict ไม่ยึด reference โมเดลตรง ๆ)
    """
    t_start = time.time()
    text = req.get("text", "")
    instruct = req.get("instruct")
    out_path = req.get("out_path")
    voice = req.get("voice", "Liino")
    fmt = req.get("format", "wav")
    if fmt not in ("wav", "mp3"):
        fmt = "wav"
    if len(text) > MAX_CHARS:
        # ข้อความยาวปิด feature แล้ว — ปฏิเสธพร้อม error ชัดเจน
        return {"ok": False, "out_path": out_path or "",
                "gen_s": 0.0,
                "error": f"text is {len(text)} chars — max is {MAX_CHARS} "
                         f"(long-text chunking is disabled)",
                "cached": False, "queue_wait_s": round(queue_wait_s, 2),
                "format": fmt}
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
                "queue_wait_s": round(queue_wait_s, 2), "format": fmt}

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

    # cache hit -> ใช้ไฟล์ cache ทันที (key เป็น wav; mp3 แปลงจาก wav cache)
    os.makedirs(CACHE_DIR, exist_ok=True)
    key = _cache_key(text, instruct, voice)
    cached_wav = os.path.join(CACHE_DIR, key + ".wav")
    out_ext = os.path.splitext(out_path)[1].lower()
    # mp3 จะ generate เป็น wav ใน out_path ก่อน (ถ้าขอ .mp3) แล้วแปลงทีหลัง
    gen_path = out_path if fmt == "wav" else (
        out_path[:-len(out_ext)] + ".wav" if out_ext == ".mp3"
        else out_path + ".wav")

    if fmt == "mp3" and out_path.endswith(".mp3"):
        cached_mp3 = os.path.join(CACHE_DIR, key + ".mp3")
        if os.path.exists(cached_mp3):
            os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
            shutil.copy2(cached_mp3, out_path)
            return resp(True, 0.0, None, cached=True)
    if os.path.exists(cached_wav):
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        if fmt == "mp3" and out_path.endswith(".mp3"):
            _convert_mp3(cached_wav, out_path)
        else:
            shutil.copy2(cached_wav, out_path)
        return resp(True, 0.0, None, cached=True)

    try:
        gen_s = _generate(model_holder, ref_audio, ref_text, text, instruct,
                          gen_path)
    except Exception as e:  # noqa: BLE001
        return resp(False, 0.0, str(e))
    try:
        shutil.copy2(gen_path, cached_wav)
        if fmt == "mp3" and out_path.endswith(".mp3"):
            _convert_mp3(gen_path, out_path)
            cached_mp3 = os.path.join(CACHE_DIR, key + ".mp3")
            shutil.copy2(out_path, cached_mp3)
    except Exception as e:  # noqa: BLE001
        return resp(False, gen_s, str(e))
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
    model_holder: dict = {"model": _load_model()}
    print(f"daemon: model loaded in {time.time() - t0:.1f}s",
          file=sys.stderr, flush=True)
    log_event("startup", sock=SOCK_PATH, queue_timeout_s=QUEUE_TIMEOUT,
              telemetry_log=TELEMETRY_LOG, idle_unload_s=IDLE_UNLOAD)

    # ---- idle unload: ถ้าเปิด feature และไม่มี request นานเกินไป คืน memory
    # ห้าม unload ขณะ worker กำลัง generate หรือคิวมีงานค้าง — ไม่งั้นจะ
    # ยกเลิกงานกลางทาง / แย่ง memory กับงานที่กำลังรัน (บั๊กที่พบตอน test
    # ข้อความใหญ่: model_unload ยิงระหว่าง generate ทำให้ request ค้าง)
    _last_request_t = time.time()
    _worker_busy = {"flag": False}

    def idle_watch() -> None:
        nonlocal _last_request_t
        while _running:
            time.sleep(1.0)
            if IDLE_UNLOAD > 0 and model_holder.get("model") is not None \
                    and not _worker_busy["flag"] \
                    and time.time() - _last_request_t > IDLE_UNLOAD:
                rss_mb = 0.0
                try:
                    with open("/proc/self/statm") as f:
                        rss_mb = int(f.read().split()[1]) * 4096 / 1e6
                except Exception:  # noqa: BLE001, S110
                    pass
                _unload_model(model_holder)
                _last_request_t = time.time()
                log_event("model_unload", idle_s=IDLE_UNLOAD,
                          rss_before_mb=round(rss_mb, 1))
                print(f"daemon: model unloaded after {IDLE_UNLOAD:.0f}s idle",
                      file=sys.stderr, flush=True)

    if IDLE_UNLOAD > 0:
        threading.Thread(target=idle_watch, daemon=True).start()

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
            _worker_busy["flag"] = True
            _last_request_t = time.time()  # งานเริ่มรัน = ไม่ idle
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
                             "queue_wait_s": round(wait_s, 2),
                             "format": req.get("format", "wav")},
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
                resp = handle_request(model_holder, req, queue_wait_s=wait_s)
            except Exception as e:  # noqa: BLE001
                resp = {"ok": False, "out_path": req.get("out_path", ""),
                        "gen_s": 0.0, "error": str(e), "cached": False,
                        "queue_wait_s": round(wait_s, 2),
                        "format": req.get("format", "wav")}
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
            _worker_busy["flag"] = False
            _last_request_t = time.time()  # งานจบ — เริ่มนับ idle ใหม่

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

    def _err(resp_dict: dict) -> dict:
        resp_dict.setdefault("format", "wav")
        return resp_dict

    try:
        srv.settimeout(0.5)
        while _running:
            try:
                conn, _ = srv.accept()
            except socket.timeout:
                continue
            with conn:
                buf = b""
                # อ่านจนครบบรรทัด (รองรับ request JSON ใหญ่ ~50KB+)
                while not buf.endswith(b"\n"):
                    try:
                        data = conn.recv(65536)
                    except (socket.timeout, OSError):
                        break
                    if not data:
                        break
                    buf += data
                if not buf.strip():
                    # client หลุดก่อนส่งครบ — ไม่มีงานค้างในคิว
                    log_event("client_disconnect", stage="recv",
                              bytes_read=len(buf))
                    continue
                try:
                    req = json.loads(buf.decode("utf-8"))
                except json.JSONDecodeError as e:
                    send(conn, _err({"ok": False, "out_path": "",
                                     "gen_s": 0.0,
                                     "error": f"bad json: {e}",
                                     "cached": False,
                                     "queue_wait_s": 0.0}))
                    continue

                with q_lock:
                    depth = q_depth
                # timeout เชิงป้องกัน: ถ้างานหน้าคิวรวมกันน่าจะกินเวลา
                # เกิน QUEUE_TIMEOUT แล้ว งานใหม่นี้ตอบ timeout ทันที
                if depth > 0 and depth * _est_job_s() > QUEUE_TIMEOUT:
                    log_event("error", text_len=len(req.get("text", "")),
                              error="queue timeout", queue_depth=depth)
                    send(conn, _err({"ok": False,
                                     "out_path": req.get("out_path", ""),
                                     "gen_s": 0.0, "error": "queue timeout",
                                     "cached": False, "queue_wait_s": 0.0}))
                    continue

                # dup socket กัน (with conn จะปิดตอนออกจาก block) แล้ว
                # ยก conn ให้ worker ปิดเองหลังส่งผล
                req["_conn"] = conn.dup()
                with q_lock:
                    q_depth += 1
                q.put((req, time.time()))  # FIFO enqueue
                _last_request_t = time.time()
    finally:
        srv.close()
        if os.path.exists(SOCK_PATH):
            os.unlink(SOCK_PATH)
        print("daemon: shutdown, socket removed", file=sys.stderr,
              flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

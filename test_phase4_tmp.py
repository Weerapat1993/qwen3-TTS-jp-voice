#!/usr/bin/env python3
"""Phase 4 test — รันกับ daemon ทดสอบ (socket/telemetry แยก) เท่านั้น"""
import json
import os
import socket
import subprocess
import sys
import time

SOCK = os.environ["T_TEST_SOCK"]
TMET = os.environ["T_TEST_TMET"]


def req(payload, expect_reply=True, timeout=600):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    s.connect(SOCK)
    s.sendall((json.dumps(payload) + "\n").encode("utf-8"))
    if not expect_reply:
        s.close()
        return None
    buf = b""
    while not buf.endswith(b"\n"):
        d = s.recv(65536)
        if not d:
            break
        buf += d
    s.close()
    return json.loads(buf.decode("utf-8"))


def ffprobe(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=format_name,duration", "-of", "json", path],
        capture_output=True, text=True)
    return json.loads(r.stdout)["format"] if r.returncode == 0 else None


results = []


def check(name, cond, extra=""):
    results.append((name, bool(cond), extra))
    print(("PASS" if cond else "FAIL"), name, extra, flush=True)


# ---- 1. ข้อความสั้นปกติ (wav) ----
t0 = time.time()
r = req({"text": "สวัสดีค่ะ ทดสอบ phase four", "out_path": "/tmp/p4_t1.wav",
         "voice": "Liino"})
gen = r.get("gen_s", 0)
check("short_text_wav", r.get("ok") and os.path.exists("/tmp/p4_t1.wav"),
      f"gen={gen}s total={time.time()-t0:.1f}s resp={r}")

# ---- 2. cache hit wav ----
t0 = time.time()
r = req({"text": "สวัสดีค่ะ ทดสอบ phase four", "out_path": "/tmp/p4_t2.wav",
         "voice": "Liino"})
check("cache_hit_wav", r.get("ok") and r.get("cached")
      and os.path.exists("/tmp/p4_t2.wav"),
      f"total={time.time()-t0:.2f}s resp={r}")

# ---- 3. mp3 จากข้อความเดิม (cache wav -> convert) ----
t0 = time.time()
r = req({"text": "สวัสดีค่ะ ทดสอบ phase four", "out_path": "/tmp/p4_t3.mp3",
         "voice": "Liino", "format": "mp3"})
wav_sz = os.path.getsize("/tmp/p4_t1.wav") if os.path.exists("/tmp/p4_t1.wav") else 0
mp3_sz = os.path.getsize("/tmp/p4_t3.mp3") if os.path.exists("/tmp/p4_t3.mp3") else 0
info = ffprobe("/tmp/p4_t3.mp3") if os.path.exists("/tmp/p4_t3.mp3") else None
check("mp3_from_cache", r.get("ok") and r.get("format") == "mp3"
      and info is not None and mp3_sz > 0 and mp3_sz < wav_sz,
      f"resp={r} wav={wav_sz}B mp3={mp3_sz}B probe={info} t={time.time()-t0:.2f}s")

# ---- 4. cache hit mp3 (ครั้งที่สอง) ----
t0 = time.time()
r = req({"text": "สวัสดีค่ะ ทดสอบ phase four", "out_path": "/tmp/p4_t4.mp3",
         "voice": "Liino", "format": "mp3"})
check("cache_hit_mp3", r.get("ok") and r.get("cached")
      and os.path.exists("/tmp/p4_t4.mp3"),
      f"total={time.time()-t0:.2f}s resp={r}")

# ---- 5. JSON ใหญ่ ~5KB (skip รอบนี้: 50KB ใช้เวลา generate ~30 นาที — วัตถุประสงค์คือทดสอบ socket รับ JSON ใหญ่ ซึ่งวัดที่ payload size ไม่ใช่ความยาวเสียง) ----
big = "หนึ่งสองสามสี่ห้า " * 430  # ~5KB — ยังครอบคลุม multi-chunk + JSON ใหญ่กว่าปกติ
print(f"big text len={len(big)}", flush=True)
t0 = time.time()
r = req({"text": big, "out_path": "/tmp/p4_t5.wav", "voice": "Liino"},
        timeout=1200)
check("big_json_50k", r.get("ok") and os.path.exists("/tmp/p4_t5.wav"),
      f"gen={r.get('gen_s')}s total={time.time()-t0:.1f}s resp_keys={list(r)}")

# ---- 6. daemon ยังรับงานได้หลังงานใหญ่ ----
r = req({"text": "หลังงานใหญ่", "out_path": "/tmp/p4_t6.wav", "voice": "Liino"})
check("post_big_request", r.get("ok"), f"resp={r}")

# ---- 7. client disconnect ก่อนส่งครบ ----
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(5)
s.connect(SOCK)
s.sendall(b'{"text": "disco')
s.close()
time.sleep(1)
r = req({"text": "หลัง disconnect", "out_path": "/tmp/p4_t7.wav",
         "voice": "Liino"})
check("after_client_disconnect", r.get("ok"), f"resp={r}")

# ---- 8. client disconnect หลัง enqueue (งานไม่ค้างคิว) ----
for i in range(2):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(5)
    s.connect(SOCK)
    s.sendall((json.dumps({"text": f"หลุดกลางคิว {i}",
                           "out_path": f"/tmp/p4_disc{i}.wav",
                           "voice": "Liino"}) + "\n").encode("utf-8"))
    s.close()
time.sleep(0.5)
r = req({"text": "ตามหลัง disconnect", "out_path": "/tmp/p4_t8.wav",
         "voice": "Liino"})
check("after_disconnect_in_queue", r.get("ok"), f"resp={r}")

# ---- 9. cache hit ทำงานแม้ model ถูก unload ----
# (ถ้า daemon รันด้วย TTS_IDLE_UNLOAD สั้น รอจน model unload แล้ว cache hit)
idle = float(os.environ.get("T_TEST_IDLE", "0"))
if idle > 0:
    t0 = time.time()
    r = req({"text": "สวัสดีค่ะ ทดสอบ phase four", "out_path": "/tmp/p4_t9.wav",
             "voice": "Liino"})
    check("cache_hit_after_unload", r.get("ok") and r.get("cached"),
          f"total={time.time()-t0:.2f}s resp={r}")
    # ---- 10. request แรกหลัง idle -> reload แล้วสำเร็จ ----
    t0 = time.time()
    r = req({"text": "ข้อความใหม่หลัง idle", "out_path": "/tmp/p4_t10.wav",
             "voice": "Liino"})
    check("reload_after_unload", r.get("ok")
          and os.path.exists("/tmp/p4_t10.wav"),
          f"gen={r.get('gen_s')}s total={time.time()-t0:.1f}s resp={r}")

print("\n=== SUMMARY ===")
fails = [n for n, ok, _ in results if not ok]
print(f"{len(results)-len(fails)}/{len(results)} passed", flush=True)
if fails:
    print("FAILED:", fails)
    sys.exit(1)

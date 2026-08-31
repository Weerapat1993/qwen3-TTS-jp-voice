#!/usr/bin/env python3
"""รวมไฟล์ wav หลายชิ้น เว้นช่องเงียบ 1 วินาทีระหว่างประโยค (TTS gap merge)

ใช้ pydub-style concat ผ่าน ffmpeg แบบ per-file: แปลงแต่ละชิ้นเป็น PCM แล้ว
ต่อกันด้วยชิ้นเงียบ 1s (aevalsrc) ระหว่างชิ้น — ทำใน one-liner ที่เสถียรกว่า
filter_complex ยาว ๆ
"""
import subprocess
import sys
import glob
import os

GAP_S = 1.0
SR = 24000

parts = sorted(glob.glob(sys.argv[1] if len(sys.argv) > 1 else "outputs/jp_part*.wav"))
out = sys.argv[2] if len(sys.argv) > 2 else "outputs/jp_full_gap.wav"
assert len(parts) >= 2, f"need >=2 parts, got {len(parts)}"

# ใช้ concat demuxer ไม่ได้เพราะไฟล์ต่าง header ไม่ได้ — ใช้วิธี concat filter
# ทีละคู่: merge สะสม + เติม gap ด้วย adelay บนชิ้นถัดไปง่ายกว่า:
# วิธีที่เสถียร: aevalsrc gap เป็นไฟล์ wav แล้วใช้ concat filter โดยอ้างเป็น input
gap_wav = "/tmp/_gap1s.wav"
subprocess.run(["ffmpeg", "-y", "-f", "lavfi",
                "-i", f"anullsrc=r={SR}:cl=mono", "-t", str(GAP_S),
                "-c:a", "pcm_s16le", gap_wav], capture_output=True, check=True)

# สร้าง input list: part0 gap part1 gap part2 ... partN
inputs = []
for i, p in enumerate(parts):
    inputs.append(p)
    if i < len(parts) - 1:
        inputs.append(gap_wav)

cmd = ["ffmpeg", "-y"]
for f in inputs:
    cmd += ["-i", f]
seq = ""
for i in range(len(inputs)):
    seq += f"[{i}:a]"
cmd += ["-filter_complex", f"{seq}concat=n={len(inputs)}:v=0:a=1", out]
r = subprocess.run(cmd, capture_output=True, text=True)
if r.returncode != 0:
    print(r.stderr[-800:])
    sys.exit(1)
d = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                    "-of", "default=nw=1:nk=1", out], capture_output=True, text=True)
print(f"OK {out} parts={len(parts)} gaps={len(parts)-1} dur={d.stdout.strip()}s")

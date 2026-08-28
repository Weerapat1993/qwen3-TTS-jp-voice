#!/usr/bin/env python3
"""Phase 1: ปรับคุณภาพเสียงโคลน Liino — ชุดทดสอบ A/B

โหลดโมเดลครั้งเดียว แล้ว generate ข้อความทดสอบชุดเดียวกันหลาย config:
  - instruct แบบต่างๆ (default / สั้น / ไทยเน้นชัด)
  - ref audio เต็ม 50s vs ตัด 20s แรก

ผลลัพธ์อยู่ใน outputs/tuning/<run_id>/ พร้อม results.md สรุปค่าเวลา
"""
import os
import sys
import time

PROJ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJ)

from qwen_clone_tts import DEFAULT_INSTRUCT, MODEL_PATH, VOICES_DIR

INSTRUCTS = {
    "default": DEFAULT_INSTRUCT,
    "short": "Cheerful, bright, playful young female voice. Clear and friendly, natural pace, not childish.",
    "th_clear": ("A youthful female anime character voice. Clear, bright, soft, feminine timbre, "
                 "slightly high pitch. Speak each word crisply and clearly at a moderate pace, "
                 "natural lively intonation, friendly and energetic but not exaggerated."),
}


def cut_ref(src: str, dst: str, seconds: int) -> str:
    import subprocess
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-i", src, "-t", str(seconds),
        "-c", "copy", dst,
    ], check=True)
    return dst


def main() -> None:
    from mlx_audio.tts.utils import load_model
    from mlx_audio.tts.generate import generate_audio

    run_id = time.strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(PROJ, "outputs", "tuning", run_id)
    os.makedirs(out_dir, exist_ok=True)

    texts = {
        "th": "สวัสดีค่ะ หนู Liino เองค่ะ วันนี้มาช่วยหาเสียงที่เนียนที่สุดกันเถอะ!",
        "en": "Hi! I'm Liino. Let's find the clearest, most natural voice setting today!",
    }

    refs = {"full": os.path.join(VOICES_DIR, "Liino.wav")}
    cut20 = os.path.join(out_dir, "Liino_cut20.wav")
    cut_ref(refs["full"], cut20, 20)
    refs["cut20"] = cut20

    ref_text = open(os.path.join(VOICES_DIR, "Liino.txt"),
                    encoding="utf-8").read().strip()

    t0 = time.time()
    model = load_model(MODEL_PATH)
    print(f"model load: {time.time()-t0:.1f}s")

    # ชุดทดสอบ: (tag, ref_key, instruct_key)
    cases = [
        ("full_default", "full", "default"),
        ("full_short", "full", "short"),
        ("full_thclear", "full", "th_clear"),
        ("cut20_default", "cut20", "default"),
        ("cut20_short", "cut20", "short"),
    ]

    lines = [f"# Tuning run {run_id}\n",
             f"| case | lang | gen_s | file |", "|---|---|---|---|"]
    for tag, ref_key, ins_key in cases:
        for lang, text in texts.items():
            out = os.path.join(out_dir, f"{tag}_{lang}.wav")
            t1 = time.time()
            try:
                generate_audio(model=model, text=text,
                               ref_audio=refs[ref_key], ref_text=ref_text,
                               instruct=INSTRUCTS[ins_key], output_path=out)
                gen = time.time() - t1
                ok = os.path.exists(out)
                print(f"{tag}_{lang}: {'OK' if ok else 'MISS'} gen={gen:.1f}s")
                lines.append(f"| {tag} | {lang} | {gen:.1f} | {os.path.basename(out)} |")
            except Exception as e:
                print(f"{tag}_{lang}: FAIL {e}")
                lines.append(f"| {tag} | {lang} | FAIL | {type(e).__name__}: {e} |")

    with open(os.path.join(out_dir, "results.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"done -> {out_dir}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Local MT (machine translation) ผ่าน mlx-lm — สำหรับ /translate (TTS-1013)

โหลด mlx-community/Qwen2.5-7B-Instruct-4bit เป็น lazy singleton (module-level
cache, thread-safe) ตอนเรียก translate() ครั้งแรก — ไม่โหลดตอน import โมดูล
เพื่อไม่ให้ import เฉย ๆ (เช่นตอน test mock) ลาก mlx-lm เข้ามาโหลดโมเดล ~4.5GB
โดยไม่จำเป็น (แนวเดียวกับ stt_transcribe.py ที่ import mlx_whisper ใน function)

ADR-0001: โมเดลนี้อยู่ใน discord_say_bot.py process ไม่ใช่ tts_daemon.py — เป็น
one-shot MT step ก่อน TTS ต่อ request, ไม่ใช่งาน queue ต่อเนื่องแบบ TTS จึงไม่มี
idle-unload/lifecycle management (accepted RAM trade-off)

pure module — ไม่ import discord ตาม pattern ของ voice_store.py/say_moods.py/
transcribe_mood.py เพื่อ unit test ได้ isolated
"""
import threading

MT_MODEL = "mlx-community/Qwen2.5-7B-Instruct-4bit"

# target_lang code -> ชื่อภาษาที่ใส่ใน prompt (ให้โมเดลเข้าใจชัดกว่าส่ง code ดิบ)
TARGET_LANG_NAMES: dict[str, str] = {
    "en": "English",
    "th": "Thai",
}

# translate() รับทั้งเอกสารเป็นก้อนเดียว (ไม่ per-segment ตาม Decisions ของ
# TTS-1013) — เผื่อ token budget ให้กว้างกว่า MAX_TOKENS ปกติของ mlx_lm.generate
# (default 256) เพราะ transcript จากเสียงยาวสุด 10 นาทีอาจยาวหลายร้อยคำ
MIN_MAX_TOKENS = 512
MAX_MAX_TOKENS = 4096

_model = None
_tokenizer = None
_load_lock = threading.Lock()


def _load():
    """โหลด model+tokenizer ครั้งแรก (thread-safe ผ่าน double-checked lock),
    ครั้งต่อไปคืนตัวที่ cache ไว้แล้ว"""
    global _model, _tokenizer
    if _model is None:
        with _load_lock:
            if _model is None:
                from mlx_lm import load
                _model, _tokenizer = load(MT_MODEL)
    return _model, _tokenizer


def _estimate_max_tokens(text: str) -> int:
    """ประมาณ max_tokens จากความยาว text ต้นฉบับ — คำแปลความยาวใกล้เคียงต้นฉบับ
    เสมอ (คูณ 2 กันภาษาเป้าหมาย tokenize ถี่กว่า เช่นไทย) clamp ไว้ในช่วง
    [MIN_MAX_TOKENS, MAX_MAX_TOKENS] กัน generate ค้างนานเกินไปกับ transcript ยาว"""
    return max(MIN_MAX_TOKENS, min(MAX_MAX_TOKENS, len(text) * 2))


def build_prompt(text: str, target_lang: str) -> str:
    """สร้าง user-message content สำหรับแปล text ทั้งก้อนเป็น target_lang เดียว
    (whole-document call ไม่ใช่ per-segment ตาม Decisions ของ TTS-1013)

    raise ValueError ถ้า target_lang ไม่ใช่ key ใน TARGET_LANG_NAMES
    """
    if target_lang not in TARGET_LANG_NAMES:
        raise ValueError(
            f"unknown target_lang '{target_lang}' — choices: "
            f"{', '.join(sorted(TARGET_LANG_NAMES))}")
    lang_name = TARGET_LANG_NAMES[target_lang]
    return (
        f"Translate the following text into {lang_name}. "
        "Output ONLY the translation itself — no notes, no explanations, "
        "no quotes or labels around it.\n\n"
        f"{text}"
    )


def translate(text: str, target_lang: str) -> str:
    """แปล text (ทั้งก้อนเดียว) เป็น target_lang ("en"/"th") ผ่านโมเดล mlx-lm
    local ตัวเดียวกันทุก target_lang (เปลี่ยนแค่ prompt)

    raise ValueError ถ้า text ว่างหรือ target_lang ไม่รู้จัก (ก่อนโหลดโมเดล —
    fail-fast โดยไม่เสียเวลาโหลด 4.5GB ถ้า input ผิดอยู่แล้ว)
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("text is empty")
    prompt_content = build_prompt(text, target_lang)

    model, tokenizer = _load()
    from mlx_lm import generate

    messages = [{"role": "user", "content": prompt_content}]
    prompt = tokenizer.apply_chat_template(
        messages, add_generation_prompt=True)
    result = generate(
        model, tokenizer, prompt=prompt,
        max_tokens=_estimate_max_tokens(text), verbose=False)
    return result.strip()

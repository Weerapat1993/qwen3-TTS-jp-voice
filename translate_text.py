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
import re
import threading

MT_MODEL = "mlx-community/Qwen2.5-7B-Instruct-4bit"

# target_lang code -> ชื่อภาษาที่ใส่ใน prompt (ให้โมเดลเข้าใจชัดกว่าส่ง code ดิบ)
TARGET_LANG_NAMES: dict[str, str] = {
    "en": "English",
    "th": "Thai",
}

# ตัวอักษร Latin/CJK/Kana/Hangul ปนอยู่ในคำแปลไทย = โมเดล drift หลุดไปพูดภาษาอื่น
# กลางประโยค (พบได้กับสำนวน/คำเฉพาะที่โมเดลแปลไม่ออก) — ไม่นับตัวเลข/เว้นวรรค/
# เครื่องหมายวรรคตอนทั่วไปที่ปนในข้อความไทยได้ตามปกติ
_FOREIGN_SCRIPT_RE = re.compile(
    "[A-Za-z぀-ヿ一-鿿가-힣]")
# กลุ่มอักขระต่อเนื่องที่ไม่ใช่ไทย — ใช้แยกเป็น "คำ/สำนวน" ทีละก้อนตอนทับศัพท์
# รายคำ (safety net รอบสุดท้าย ดู _force_thai_script)
_FOREIGN_RUN_RE = re.compile(
    "[A-Za-z぀-ヿ一-鿿가-힣]+")

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


def _build_purify_prompt(text: str, target_lang: str) -> str:
    """prompt สำหรับ retry ครั้งเดียวเมื่อคำแปลรอบแรกยังมีอักขระภาษาอื่นปนอยู่
    (โมเดล drift กลางประโยค พบได้กับสำนวน/คำเฉพาะ) — บังคับทับศัพท์แทนปนภาษาเดิม
    """
    lang_name = TARGET_LANG_NAMES[target_lang]
    return (
        f"The following {lang_name} text still has some words left in "
        f"another language or script. Rewrite it ENTIRELY in {lang_name} "
        "script — for any word with no natural translation, spell it out "
        f"phonetically in {lang_name} instead of leaving it as-is. Keep the "
        "meaning and order of the rest exactly the same. Output ONLY the "
        "corrected text — no notes, no explanations.\n\n"
        f"{text}"
    )


def _force_thai_script(text: str, model, tokenizer) -> str:
    """safety net รอบสุดท้าย: ทับศัพท์ทุกคำ/สำนวนที่ไม่ใช่อักษรไทยที่เหลือหลัง
    retry (พบกับคำ/สำนวนที่โมเดลไม่รู้จักจริง ๆ เช่น 前者/后者) เรียกโมเดลทีละคำ
    (dedupe คำซ้ำ, เรียงยาว->สั้นกัน substring ทับกันตอนแทนที่)

    ไม่รับประกันคำอ่านถูกต้อง 100% (โมเดล 7B 4-bit บางครั้งหลุดแปะอักขระ Latin
    เดี่ยว ๆ ปนมาด้วย เช่น "แท้จริงly") แต่**รับประกันว่าผลลัพธ์สุดท้ายเป็นอักษรไทย
    ล้วน** ไม่มีอักขระภาษาอื่นหลุดไปถึง TTS เด็ดขาด — คำไหนทับศัพท์ไม่สำเร็จ
    (ยังมีอักขระภาษาอื่นปน) จะปล่อยคำเดิมไว้ก่อน แล้วตัดอักขระที่เหลือทิ้งท้ายสุด
    (เสี่ยงเสียความหมายบางคำ ยอมแลกกับไม่ให้ TTS หลุดไปพูดผิดภาษาทั้งประโยค)
    """
    from mlx_lm import generate

    words = sorted(set(_FOREIGN_RUN_RE.findall(text)), key=len, reverse=True)
    for word in words:
        # CJK/Kana ไม่มีช่องว่างคั่นคำ -> "run" หนึ่งก้อนอาจเป็นทั้งวลี/ประโยค
        # ไม่ใช่แค่คำเดียว จึงให้ทั้งแปลความหมายหรือทับศัพท์ก็ได้ (ไม่บังคับทับศัพท์
        # อย่างเดียวเหมือนเดิม) และคำนวณ max_tokens ตามความยาวจริงกันตัดคำขาด
        prompt_content = (
            "Translate the following into Thai. If part of it is a name or "
            "term with no direct translation, spell that part phonetically "
            "in Thai instead. Output ONLY the Thai result, nothing else.\n\n"
            f"{word}"
        )
        messages = [{"role": "user", "content": prompt_content}]
        prompt = tokenizer.apply_chat_template(
            messages, add_generation_prompt=True)
        spelled = generate(
            model, tokenizer, prompt=prompt,
            max_tokens=max(60, len(word) * 8), verbose=False).strip()
        if spelled and not _FOREIGN_SCRIPT_RE.search(spelled):
            text = text.replace(word, spelled)

    # ตัดทิ้งอักขระภาษาอื่นที่ยังเหลือ (ทับศัพท์ไม่สำเร็จ) — การันตีผลลัพธ์เป็น
    # อักษรไทยล้วน กัน TTS หลุดไปพูดผิดภาษาแน่นอน ยอมเสียความหมายบางคำ
    if _FOREIGN_SCRIPT_RE.search(text):
        text = _FOREIGN_RUN_RE.sub(" ", text)
        text = re.sub(r"\s{2,}", " ", text).strip()
    return text


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
        max_tokens=_estimate_max_tokens(text), verbose=False).strip()

    # target_lang="th": โมเดล MT บางครั้ง drift หลุดไปพูดภาษาอื่นกลางประโยค
    # (พบกับสำนวน/คำเปรียบเทียบที่โมเดลผูกกับภาษาอื่นแน่น เช่น "前者...而后者...")
    # ถ้าปนมา ลอง retry อีกครั้งเดียวด้วย prompt บังคับทับศัพท์ — สำคัญเพราะ
    # ข้อความที่ปนภาษาแบบนี้จะทำให้ TTS (lang_code=auto) หลุดไปพูดผิดภาษาด้วย
    if target_lang == "th" and _FOREIGN_SCRIPT_RE.search(result):
        purify_content = _build_purify_prompt(result, target_lang)
        purify_messages = [{"role": "user", "content": purify_content}]
        purify_prompt = tokenizer.apply_chat_template(
            purify_messages, add_generation_prompt=True)
        retried = generate(
            model, tokenizer, prompt=purify_prompt,
            max_tokens=_estimate_max_tokens(result), verbose=False).strip()
        if retried:
            result = retried

    if target_lang == "th" and _FOREIGN_SCRIPT_RE.search(result):
        # ยังมีคำหลุดเหลือหลัง retry — ทับศัพท์รายคำแทน ไม่ปล่อยอักขระภาษาอื่น
        # หลุดไปถึง TTS เด็ดขาด (ดู docstring ของ _force_thai_script)
        result = _force_thai_script(result, model, tokenizer)

    return result

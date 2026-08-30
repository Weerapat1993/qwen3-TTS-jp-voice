#!/usr/bin/env python3
"""Pure logic: เดา mood จากข้อความที่ถอดเสียงได้ (TTS-1005)

แยกจาก discord_say_bot.py / stt_transcribe.py เพื่อ unit test ได้ isolated —
ไม่ import discord, qwen_clone_tts หรือ mlx ใด ๆ (เหมือน say_moods.py)

detect_mood() คืนชื่อ mood ที่ say_moods.MOOD_EMOJI รู้จักเสมอ (หรือ None)
เพื่อให้เติม emoji canonical นำหน้าบรรทัดได้
"""

# ตารางเรียงตามลำดับความสำคัญ: entry แรกที่มี substring ใด ๆ อยู่ใน text ชนะ
# key = tuple ของ substring (ตัวพิมพ์เล็กแล้ว), value = ชื่อ mood ใน MOOD_EMOJI
MOOD_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("555", "ฮ่า", "ขำ", "ฮามาก", "lol", "haha", "lmao"), "giggle"),
    (("เศร้า", "เสียใจ", "ร้องไห้", "ผิดหวัง", "น้ำตา", "sad", "unhappy"), "sad"),
    (("โกรธ", "โมโห", "หงุดหงิด", "น่ารำคาญ", "angry", "furious"), "angry"),
    (("ตกใจ", "ว้าว", "ไม่น่าเชื่อ", "แปลกใจ", "wow", "omg", "whoa", "unbelievable"),
     "surprised"),
    (("ง่วง", "เหนื่อย", "อยากนอน", "เพลีย", "tired", "sleepy", "exhausted"),
     "sleepy"),
    (("กระซิบ", "เงียบ ๆ", "แอบบอก", "อย่าบอกใคร", "whisper", "secret"), "whisper"),
    (("ไม่เป็นไรนะ", "ใจเย็น ๆ", "กอดหน่อย", "เดี๋ยวก็ดีขึ้น", "there there",
      "it's okay"), "gentle"),
    (("เย้", "สุดยอด", "ตื่นเต้น", "ไปกันเลย", "เจ๋งมาก", "yay", "let's go",
      "awesome"), "excited"),
    (("เบื่อ", "น่าเบื่อ", "เฉย ๆ", "ไม่มีอะไรทำ", "bored", "boring", "meh"),
     "bored"),
    (("กาลครั้งหนึ่ง", "นานมาแล้ว", "ณ ดินแดน", "once upon a time", "long ago"),
     "storyteller"),
]


def detect_mood(text: str) -> str | None:
    """คืนชื่อ mood ของ entry แรกใน MOOD_KEYWORDS ที่มี substring ตรงกับ text

    เทียบแบบ case-insensitive (lower ทั้ง text; key ใน MOOD_KEYWORDS lower ไว้แล้ว)
    ไม่เจอเลย -> None
    """
    low = text.lower()
    for needles, mood in MOOD_KEYWORDS:
        if any(n in low for n in needles):
            return mood
    return None

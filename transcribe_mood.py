#!/usr/bin/env python3
"""Pure logic: เดา mood จากข้อความที่ถอดเสียงได้ (TTS-1005)

แยกจาก discord_say_bot.py / stt_transcribe.py เพื่อ unit test ได้ isolated —
ไม่ import discord, qwen_clone_tts หรือ mlx ใด ๆ (เหมือน say_moods.py)

detect_mood() คืนชื่อ mood ที่ say_moods.MOOD_EMOJI รู้จักเสมอ (หรือ None)
เพื่อให้เติม emoji canonical นำหน้าบรรทัดได้
"""

# ตารางเรียงตามลำดับความสำคัญ: entry แรกที่มี substring ใด ๆ อยู่ใน text ชนะ
# key = tuple ของ substring (ตัวพิมพ์เล็กแล้ว), value = ชื่อ mood ใน MOOD_EMOJI
# ครอบ 3 ภาษา: ไทย / อังกฤษ / ญี่ปุ่น (ญี่ปุ่นไม่มีช่องว่าง -> substring match ตรง ๆ)
MOOD_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("555", "ฮ่า", "ขำ", "ฮามาก", "lol", "haha", "lmao",
      "笑", "わら", "www", "あはは", "うける"), "giggle"),
    (("เศร้า", "เสียใจ", "ร้องไห้", "ผิดหวัง", "น้ำตา", "sad", "unhappy",
      "悲し", "泣", "寂し", "切な", "ごめん"), "sad"),
    (("โกรธ", "โมโห", "หงุดหงิด", "น่ารำคาญ", "angry", "furious",
      "怒", "むかつく", "ふざけるな", "イライラ"), "angry"),
    (("งอน", "บูด", "ไม่คุยด้วย", "เอาแต่ใจ", "pouty", "sulky", "sulking",
      "ふてくされ", "むくれ", "ぶすっ"), "pouty"),
    (("ตกใจ", "ว้าว", "ไม่น่าเชื่อ", "แปลกใจ", "wow", "omg", "whoa", "unbelievable",
      "びっくり", "まさか", "うそ", "へぇ", "えっ", "ええっ"), "surprised"),
    (("ง่วง", "เหนื่อย", "อยากนอน", "เพลีย", "tired", "sleepy", "exhausted",
      "眠", "疲れ", "ねむ", "だるい"), "sleepy"),
    (("กระซิบ", "เงียบ ๆ", "แอบบอก", "อย่าบอกใคร", "whisper", "secret",
      "ないしょ", "内緒", "こっそり", "静かに", "ひそひそ"), "whisper"),
    (("กังวล", "เป็นห่วง", "ไม่สบายใจ", "กลุ้ม", "worried", "anxious", "nervous",
      "心配", "不安", "気がかり"), "worried"),
    (("ไม่เป็นไรนะ", "ใจเย็น ๆ", "กอดหน่อย", "เดี๋ยวก็ดีขึ้น", "there there",
      "it's okay", "大丈夫だよ", "落ち着いて", "よしよし", "そばにいる"), "gentle"),
    (("เขิน", "เขินอาย", "อายจัง", "กระดากอาย", "shy", "bashful", "embarrassed",
      "照れ", "恥ずかし", "てれくさ"), "shy"),
    (("เย้", "สุดยอด", "ตื่นเต้น", "ไปกันเลย", "เจ๋งมาก", "yay", "let's go",
      "awesome", "やった", "すごい", "最高", "わくわく", "行こう", "始まり",
      "きらめき", "輝", "ビビッ"), "excited"),
    (("ภูมิใจ", "ปลื้มใจ", "ภาคภูมิ", "proud", "so proud",
      "誇らし", "自慢", "どや"), "proud"),
    (("เบื่อ", "น่าเบื่อ", "เฉย ๆ", "ไม่มีอะไรทำ", "bored", "boring", "meh",
      "つまらない", "退屈", "どうでもいい", "めんどくさい"), "bored"),
    (("กาลครั้งหนึ่ง", "นานมาแล้ว", "ณ ดินแดน", "once upon a time", "long ago",
      "むかしむかし", "昔々", "ある日"), "storyteller"),
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

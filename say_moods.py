#!/usr/bin/env python3
"""Pure logic สำหรับ ?say multi-line + emoji auto-mood (TTS-1002)

แยกจาก discord_say_bot.py เพื่อ unit test ได้ isolated — ไม่ import discord
หรือ qwen_clone_tts (ยกเว้น mood name ที่ตรวจใน test) เพื่อให้ test เร็วและ
ไม่มี side-effect
"""

# emoji ตัวเดียว -> ชื่อ mood preset ใน MOOD_PRESETS ของ qwen_clone_tts.py
# map เฉพาะ mood ที่มี emoji สื่อความหมายชัด — ไม่ map default/long
EMOJI_MOOD: dict[str, str] = {
    "😄": "excited", "😁": "excited", "😃": "excited", "🎉": "excited", "⚡": "excited",
    "😆": "giggle", "🤣": "giggle", "😂": "giggle", "😹": "giggle",
    "😮": "surprised", "😲": "surprised", "😯": "surprised", "😱": "surprised",
    "😢": "sad", "😭": "sad", "😔": "sad", "💔": "sad",
    "😠": "angry", "😡": "angry", "😤": "angry",
    "😴": "sleepy", "😪": "sleepy", "🥱": "sleepy",
    "🤫": "whisper", "🤐": "whisper",
    "🥺": "gentle", "🤗": "gentle", "💗": "gentle",
    "😑": "bored", "😐": "bored", "🙄": "bored",
    "📖": "storyteller", "📚": "storyteller", "🧚": "storyteller",
}


# mood name -> emoji ตัวแทนหนึ่งตัวที่ extract_mood() map กลับมาเป็น mood เดิม
# เลือก emoji ตัวแรกของแต่ละกลุ่มใน EMOJI_MOOD ด้านบน; mood ที่ไม่มี emoji สื่อ
# ความหมายชัด (default, long) ตั้งใจไม่ใส่ -> /transcribe จะไม่เติม prefix
MOOD_EMOJI: dict[str, str] = {
    "excited": "😄",
    "giggle": "😆",
    "surprised": "😮",
    "sad": "😢",
    "angry": "😠",
    "sleepy": "😴",
    "whisper": "🤫",
    "gentle": "🥺",
    "bored": "😑",
    "storyteller": "📖",
}


def parse_lines(raw: str) -> list[str]:
    """split ข้อความเป็นบรรทัด: 1 บรรทัด = 1 ประโยค

    strip แต่ละบรรทัด, ทิ้งบรรทัดที่ว่าง/whitespace-ล้วน, คงลำดับเดิม
    """
    out: list[str] = []
    for line in raw.split("\n"):
        s = line.strip()
        if s:
            out.append(s)
    return out


def first_line_over_limit(lines, max_chars: int) -> tuple[int, int] | None:
    """หาบรรทัดแรกที่ยาวเกิน max_chars (TTS-1003)

    รับ iterable ของข้อความที่พูดจริง (หลังตัด emoji/trim แล้ว) คืน
    (เลขบรรทัดฐาน 1, ความยาว) ของบรรทัดแรกที่เกิน; ถ้าทุกบรรทัดอยู่ในลิมิต -> None

    เช็ค per-line ไม่รวมความยาวทุกบรรทัด และไม่จำกัดจำนวนบรรทัด — daemon reject
    ที่ MAX_CHARS ต่อ request อยู่แล้ว ลิมิตต่อบรรทัดจึงสอดคล้องกันพอดี
    """
    for idx, line in enumerate(lines, start=1):
        n = len(line)
        if n > max_chars:
            return idx, n
    return None


def extract_mood(line: str) -> tuple[str, str | None]:
    """หา emoji ตัวแรกที่ map ได้ใน line -> คืน (ข้อความที่ตัด emoji นั้นออก, mood)

    - scan ทีละ character หา key แรกที่อยู่ใน EMOJI_MOOD (emoji ในตารางนี้เป็น
      codepoint เดี่ยวทั้งหมด ไม่มี ZWJ sequence จึง iterate ทีละ char พอ)
    - ตัด emoji ตัวนั้นออก 1 ครั้ง แล้ว strip ช่องว่างหัวท้าย
    - ไม่เจอ emoji ที่ map ได้ -> คืน (line.strip(), None); emoji อื่นไม่แตะ
    """
    for i, ch in enumerate(line):
        mood = EMOJI_MOOD.get(ch)
        if mood is not None:
            stripped = (line[:i] + line[i + 1:]).strip()
            return stripped, mood
    return line.strip(), None

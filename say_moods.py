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

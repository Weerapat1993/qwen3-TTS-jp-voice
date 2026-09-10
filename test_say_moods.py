"""Unit test สำหรับ say_moods pure logic (TTS-1002, TTS-1003)"""
from say_moods import (
    EMOJI_MOOD,
    MOOD_EMOJI,
    extract_mood,
    first_line_over_limit,
    parse_lines,
)
from qwen_clone_tts import MOOD_PRESETS


def test_emoji_mood_values_are_real_presets():
    for emoji, mood in EMOJI_MOOD.items():
        assert mood in MOOD_PRESETS, f"{emoji!r} -> unknown mood {mood!r}"


def test_emoji_mood_covers_expected_moods():
    assert set(EMOJI_MOOD.values()) == {
        "excited", "giggle", "surprised", "sad", "angry",
        "sleepy", "whisper", "gentle", "bored", "storyteller",
        "pouty", "shy", "proud", "worried", "scared", "confused",
        "flirty", "apologetic", "deadpan",
        "charming", "confident", "knowing", "playful", "warm",
        "focused", "calm",
    }


def test_parse_lines_splits_on_newline():
    assert parse_lines("a\nb\nc") == ["a", "b", "c"]


def test_parse_lines_strips_each_line():
    assert parse_lines("  a  \n\tb\t") == ["a", "b"]


def test_parse_lines_drops_blank_and_whitespace_only():
    assert parse_lines("a\n\n   \n\t\nb") == ["a", "b"]


def test_parse_lines_preserves_order():
    assert parse_lines("3\n1\n2") == ["3", "1", "2"]


def test_parse_lines_empty_input():
    assert parse_lines("") == []
    assert parse_lines("   \n  \n") == []


def test_parse_lines_single_line_no_newline():
    assert parse_lines("hello world") == ["hello world"]


def test_extract_mood_leading_emoji():
    assert extract_mood("😄สวัสดี") == ("สวัสดี", "excited")


def test_extract_mood_emoji_mid_line():
    assert extract_mood("วันนี้ 😢 เศร้าจัง") == ("วันนี้  เศร้าจัง", "sad")


def test_extract_mood_no_emoji():
    assert extract_mood("ข้อความธรรมดา") == ("ข้อความธรรมดา", None)


def test_extract_mood_unmapped_emoji_left_in_place():
    # 🍕 ไม่อยู่ในตาราง -> ไม่ตัด, mood None
    assert extract_mood("กินพิซซ่า 🍕 กัน") == ("กินพิซซ่า 🍕 กัน", None)


def test_extract_mood_first_mapped_emoji_wins():
    # 😄 (excited) มาก่อน 😢 (sad)
    assert extract_mood("😄 เย้ 😢") == ("เย้ 😢", "excited")


def test_extract_mood_only_removes_one_occurrence():
    assert extract_mood("😴 ง่วง 😴 มาก") == ("ง่วง 😴 มาก", "sleepy")


def test_extract_mood_line_is_only_emoji():
    assert extract_mood("😄") == ("", "excited")


def test_extract_mood_unmapped_before_mapped():
    # 🍕 ไม่ใช่ key -> ข้าม, เจอ 😡 -> angry, ตัดเฉพาะ 😡
    assert extract_mood("🍕 ของโปรด 😡") == ("🍕 ของโปรด", "angry")


# --- first_line_over_limit (TTS-1003: per-line char limit) ---

def test_first_line_over_limit_none_when_all_within():
    assert first_line_over_limit(["a" * 300, "b" * 10, "c" * 299], 300) is None


def test_first_line_over_limit_total_over_but_per_line_ok():
    # รวม 3 บรรทัด = 450 > 300 แต่ต่อบรรทัดไม่เกิน -> ผ่าน (พฤติกรรมใหม่)
    assert first_line_over_limit(["x" * 150, "y" * 150, "z" * 150], 300) is None


def test_first_line_over_limit_flags_first_offender_with_length():
    assert first_line_over_limit(["ok", "x" * 301, "y" * 400], 300) == (2, 301)


def test_first_line_over_limit_boundary_301():
    assert first_line_over_limit(["z" * 301], 300) == (1, 301)


def test_first_line_over_limit_exactly_limit_ok():
    assert first_line_over_limit(["z" * 300], 300) is None


def test_first_line_over_limit_empty():
    assert first_line_over_limit([], 300) is None


def test_first_line_over_limit_accepts_generator():
    assert first_line_over_limit((s for s in ["short", "w" * 999]), 300) == (2, 999)


# --- MOOD_EMOJI (TTS-1005: reverse map for /transcribe line prefixes) ---

def test_mood_emoji_round_trips_through_extract_mood():
    for mood, emoji in MOOD_EMOJI.items():
        assert extract_mood(f"{emoji} ข้อความ") == ("ข้อความ", mood)


def test_mood_emoji_keys_are_real_presets():
    for mood in MOOD_EMOJI:
        assert mood in MOOD_PRESETS


def test_mood_emoji_covers_every_evocative_mood():
    assert set(MOOD_EMOJI) == set(EMOJI_MOOD.values())


def test_emoji_mood_keys_are_single_codepoint():
    # extract_mood() iterate ทีละ char -> ทุก key ต้องเป็น codepoint เดี่ยว
    for emoji in EMOJI_MOOD:
        assert len(emoji) == 1, f"{emoji!r} is not a single codepoint"


def test_emoji_mood_has_no_duplicate_keys():
    # dict literal กันซ้ำอยู่แล้ว แต่ assert ความตั้งใจว่า emoji ใหม่ไม่ทับของเดิม
    for mood in ("pouty", "shy", "proud", "worried"):
        assert mood in set(EMOJI_MOOD.values())


def test_extract_mood_new_moods_round_trip():
    for mood in ("pouty", "shy", "proud", "worried"):
        assert extract_mood(f"{MOOD_EMOJI[mood]} ข้อความ") == ("ข้อความ", mood)


def test_extract_mood_flirty_apologetic_deadpan_round_trip():
    for mood in ("flirty", "apologetic", "deadpan"):
        assert extract_mood(f"{MOOD_EMOJI[mood]} ข้อความ") == ("ข้อความ", mood)


# --- [mood:xxx] tag (--stdin format ของ qwen_clone_tts.py วางลง /say ตรง ๆ) ---

def test_extract_mood_strips_bracket_tag():
    assert extract_mood("[mood:storyteller] กาลครั้งหนึ่ง") == (
        "กาลครั้งหนึ่ง", "storyteller")


def test_extract_mood_bracket_tag_is_case_insensitive():
    assert extract_mood("[mood:EXCITED] เย้") == ("เย้", "excited")


def test_extract_mood_unknown_bracket_tag_still_stripped():
    # ชื่อ mood ไม่รู้จัก (ไม่อยู่ใน MOOD_EMOJI) -> ตัด tag ทิ้งเสมอ กัน TTS
    # อ่านคำว่า "mood" ทับ แต่คืน mood=None (fallback ปกติ)
    assert extract_mood("[mood:bogus] สวัสดี") == ("สวัสดี", None)


def test_extract_mood_bracket_tag_wins_over_later_emoji():
    # tag ที่ต้นบรรทัดกำหนด mood ชัดเจน (excited) ชนะ emoji 😢 (sad) ที่ตามมา
    # แต่ emoji ก็ยังถูกตัดออกจากข้อความที่พูดเหมือนเดิม
    assert extract_mood("[mood:excited] เย้ 😢") == ("เย้", "excited")


def test_extract_mood_no_tag_still_falls_back_to_emoji():
    assert extract_mood("😄 สวัสดี") == ("สวัสดี", "excited")


def test_extract_mood_tag_only_no_body():
    assert extract_mood("[mood:sleepy]") == ("", "sleepy")

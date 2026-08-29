"""Unit test สำหรับ say_moods pure logic (TTS-1002)"""
from say_moods import EMOJI_MOOD, extract_mood, parse_lines
from qwen_clone_tts import MOOD_PRESETS


def test_emoji_mood_values_are_real_presets():
    for emoji, mood in EMOJI_MOOD.items():
        assert mood in MOOD_PRESETS, f"{emoji!r} -> unknown mood {mood!r}"


def test_emoji_mood_covers_expected_moods():
    assert set(EMOJI_MOOD.values()) == {
        "excited", "giggle", "surprised", "sad", "angry",
        "sleepy", "whisper", "gentle", "bored", "storyteller",
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

"""Unit test สำหรับ transcribe_mood pure logic (TTS-1005)"""
from transcribe_mood import MOOD_KEYWORDS, detect_mood
from say_moods import MOOD_EMOJI


def test_detect_mood_thai_giggle():
    assert detect_mood("555 ขำมากเลยวันนี้") == "giggle"


def test_detect_mood_thai_sad():
    assert detect_mood("วันนี้เศร้าจังเลย ร้องไห้เลย") == "sad"


def test_detect_mood_english_angry():
    assert detect_mood("I am so furious right now") == "angry"


def test_detect_mood_case_insensitive():
    assert detect_mood("WOW that is unbelievable") == "surprised"


def test_detect_mood_no_keyword_returns_none():
    assert detect_mood("วันนี้อากาศดีนะ ไปเดินเล่นกัน") is None


def test_detect_mood_earlier_entry_wins():
    # "555" (giggle, entry 0) มาก่อน "เศร้า" (sad, entry 1)
    assert detect_mood("555 แต่ก็เศร้านะ") == "giggle"


def test_every_keyword_mood_has_canonical_emoji():
    for _needles, mood in MOOD_KEYWORDS:
        assert mood in MOOD_EMOJI, f"{mood!r} has no MOOD_EMOJI entry"

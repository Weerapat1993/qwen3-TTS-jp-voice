"""Unit test สำหรับ tts_daemon cache key + lang (TTS-1006) + out_path guard (TTS-1008)"""
from tts_daemon import _cache_key, handle_request


def test_cache_key_auto_equals_legacy_no_lang():
    # request เดิม (ไม่มี lang) ต้อง hash เท่ากับ lang="auto" -> cache เดิมยัง hit
    legacy = _cache_key("สวัสดี", None, "Liino")
    explicit_auto = _cache_key("สวัสดี", None, "Liino", "auto")
    assert legacy == explicit_auto


def test_cache_key_non_auto_differs():
    auto = _cache_key("hello", None, "Liino", "auto")
    ja = _cache_key("hello", None, "Liino", "japanese")
    en = _cache_key("hello", None, "Liino", "english")
    assert len({auto, ja, en}) == 3


def test_cache_key_stable_for_same_inputs():
    assert _cache_key("x", "instruct", "Liino", "korean") == \
        _cache_key("x", "instruct", "Liino", "korean")


def test_handle_request_rejects_relative_out_path():
    # relative out_path ต้องถูกปฏิเสธก่อนโหลดโมเดล/เข้าคิว (model_holder ไม่ถูกแตะ)
    resp = handle_request({"model": None},
                          {"text": "hello", "out_path": "outputs/x.wav"})
    assert resp["ok"] is False
    assert "absolute" in resp["error"]
    assert resp["out_path"] == "outputs/x.wav"

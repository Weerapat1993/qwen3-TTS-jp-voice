"""Unit test สำหรับ qwen_clone_tts language resolution (TTS-1006)"""
import json
import os

import pytest

from qwen_clone_tts import LANG_CODES, MODEL_PATH, resolve_lang


def test_resolve_lang_none_is_auto():
    assert resolve_lang(None) == "auto"


def test_resolve_lang_empty_is_auto():
    assert resolve_lang("") == "auto"


def test_resolve_lang_lowercases_and_strips():
    assert resolve_lang("  Japanese ") == "japanese"


def test_resolve_lang_passthrough_valid():
    assert resolve_lang("english") == "english"


def test_resolve_lang_rejects_unknown():
    with pytest.raises(ValueError):
        resolve_lang("thai")


def test_lang_codes_has_auto_first_and_is_sorted_rest():
    assert LANG_CODES[0] == "auto"
    assert list(LANG_CODES[1:]) == sorted(LANG_CODES[1:])


@pytest.mark.skipif(
    not os.path.isfile(os.path.join(MODEL_PATH, "config.json")),
    reason="model config not present")
def test_lang_codes_match_model_config():
    cfg = json.load(open(os.path.join(MODEL_PATH, "config.json")))
    model_langs = set(
        cfg["talker_config"]["codec_language_id"].keys())
    assert set(LANG_CODES) - {"auto"} == model_langs

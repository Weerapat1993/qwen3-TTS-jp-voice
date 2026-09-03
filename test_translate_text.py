"""Unit test สำหรับ translate_text (TTS-1013)

mock mlx_lm ทั้งโมดูลด้วย fake module ใน sys.modules — กันโมเดลจริง ~4.5GB
โหลด/ดาวน์โหลดตอน test translate_text.py import mlx_lm แบบ lazy ในฟังก์ชัน
(_load()/translate()) เท่านั้น จึง monkeypatch sys.modules["mlx_lm"] ก่อน
เรียกจับที่จุดนั้นได้ทัน โดยไม่ต้อง mock ตัว translate_text เอง
"""
import sys
import types

import pytest

import translate_text as tt
from translate_text import TARGET_LANG_NAMES, build_prompt, translate


@pytest.fixture(autouse=True)
def reset_singleton(monkeypatch):
    """reset model/tokenizer cache ทุกเทส กัน state จาก test ก่อนหน้าเลอะกัน"""
    monkeypatch.setattr(tt, "_model", None)
    monkeypatch.setattr(tt, "_tokenizer", None)


class _FakeTokenizer:
    def __init__(self):
        self.last_messages = None

    def apply_chat_template(self, messages, add_generation_prompt=True):
        self.last_messages = messages
        return [1, 2, 3]


def _install_fake_mlx_lm(monkeypatch, generate_return="translated text"):
    """ใส่ fake module ชื่อ mlx_lm ลง sys.modules — translate_text.py ทำ
    `from mlx_lm import load` / `from mlx_lm import generate` แบบ lazy
    ในฟังก์ชัน จึงจับได้ที่จุดนี้โดยไม่ต้องแตะ import ของโมดูลจริง
    คืน (fake_tokenizer, calls) ให้ assert เนื้อหา prompt/kwargs ที่ส่งเข้าไป"""
    fake_tokenizer = _FakeTokenizer()
    calls = {"load_model_name": None, "generate_kwargs": None}

    def fake_load(model_name):
        calls["load_model_name"] = model_name
        return object(), fake_tokenizer

    def fake_generate(model, tokenizer, prompt, max_tokens=256, verbose=False):
        calls["generate_kwargs"] = {
            "prompt": prompt, "max_tokens": max_tokens, "verbose": verbose}
        return generate_return

    fake_module = types.SimpleNamespace(load=fake_load, generate=fake_generate)
    monkeypatch.setitem(sys.modules, "mlx_lm", fake_module)
    return fake_tokenizer, calls


# ---------- build_prompt ----------

def test_build_prompt_english():
    p = build_prompt("こんにちは", "en")
    assert "English" in p
    assert "こんにちは" in p


def test_build_prompt_thai():
    p = build_prompt("hello", "th")
    assert "Thai" in p
    assert "hello" in p


def test_build_prompt_unknown_target_raises():
    with pytest.raises(ValueError):
        build_prompt("hi", "fr")


def test_target_lang_names_has_en_and_th():
    assert set(TARGET_LANG_NAMES) == {"en", "th"}


# ---------- translate ----------

def test_translate_empty_text_raises(monkeypatch):
    _install_fake_mlx_lm(monkeypatch)
    with pytest.raises(ValueError):
        translate("   ", "en")


def test_translate_unknown_target_raises_before_loading_model(monkeypatch):
    load_calls = []

    def fake_load(model_name):
        load_calls.append(model_name)
        raise AssertionError("should not load model for invalid target_lang")

    fake_module = types.SimpleNamespace(load=fake_load, generate=None)
    monkeypatch.setitem(sys.modules, "mlx_lm", fake_module)
    with pytest.raises(ValueError):
        translate("hello", "fr")
    assert load_calls == []


def test_translate_returns_stripped_generated_text(monkeypatch):
    _install_fake_mlx_lm(monkeypatch, generate_return="  แปลแล้ว  ")
    assert translate("hello world", "th") == "แปลแล้ว"


def test_translate_uses_chat_template_with_target_lang_prompt(monkeypatch):
    tokenizer, _ = _install_fake_mlx_lm(monkeypatch)
    translate("hello", "en")
    assert tokenizer.last_messages[0]["role"] == "user"
    assert "English" in tokenizer.last_messages[0]["content"]
    assert "hello" in tokenizer.last_messages[0]["content"]


def test_translate_loads_pinned_model_name(monkeypatch):
    _, calls = _install_fake_mlx_lm(monkeypatch)
    translate("hello", "en")
    assert calls["load_model_name"] == tt.MT_MODEL


def test_translate_caches_model_across_calls(monkeypatch):
    load_calls = []

    def fake_load(model_name):
        load_calls.append(model_name)
        return object(), _FakeTokenizer()

    def fake_generate(model, tokenizer, prompt, max_tokens=256, verbose=False):
        return "ok"

    fake_module = types.SimpleNamespace(load=fake_load, generate=fake_generate)
    monkeypatch.setitem(sys.modules, "mlx_lm", fake_module)
    translate("hello", "en")
    translate("world", "th")
    assert len(load_calls) == 1


def test_translate_max_tokens_has_floor_for_short_text(monkeypatch):
    _, calls = _install_fake_mlx_lm(monkeypatch)
    translate("hi", "en")
    assert calls["generate_kwargs"]["max_tokens"] == tt.MIN_MAX_TOKENS


def test_translate_max_tokens_capped_for_long_text(monkeypatch):
    _, calls = _install_fake_mlx_lm(monkeypatch)
    translate("x" * 3000, "en")
    assert calls["generate_kwargs"]["max_tokens"] == tt.MAX_MAX_TOKENS

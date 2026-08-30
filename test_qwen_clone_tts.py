"""Unit test สำหรับ qwen_clone_tts language resolution (TTS-1006)
+ daemon out_path abspath (TTS-1008)"""
import json
import os
import socket

import pytest

import qwen_clone_tts
from qwen_clone_tts import LANG_CODES, MODEL_PATH, resolve_lang, _try_daemon


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


class _FakeSock:
    """socket ปลอม — เก็บ payload ที่ client ส่ง, ตอบ response สำเร็จ 1 บรรทัด"""

    def __init__(self):
        self.sent = b""
        self._replied = False

    def settimeout(self, _t):
        pass

    def connect(self, _p):
        pass

    def sendall(self, data):
        self.sent += data

    def recv(self, _n):
        if self._replied:
            return b""
        self._replied = True
        return (json.dumps(
            {"ok": True, "out_path": "/echoed/x.wav", "gen_s": 1.0}) + "\n"
        ).encode("utf-8")

    def close(self):
        pass


def test_try_daemon_sends_absolute_out_path(monkeypatch, capsys):
    fake = _FakeSock()
    monkeypatch.setattr(qwen_clone_tts.os.path, "exists", lambda _p: True)
    monkeypatch.setattr(socket, "socket", lambda *a, **k: fake)

    ok = _try_daemon("hi", "outputs/rel.wav", None)

    assert ok is True
    payload = json.loads(fake.sent.decode("utf-8").strip())
    assert payload["out_path"] == os.path.abspath("outputs/rel.wav")
    assert os.path.isabs(payload["out_path"])


def test_try_daemon_leaves_absolute_out_path_unchanged(monkeypatch):
    fake = _FakeSock()
    monkeypatch.setattr(qwen_clone_tts.os.path, "exists", lambda _p: True)
    monkeypatch.setattr(socket, "socket", lambda *a, **k: fake)

    _try_daemon("hi", "/tmp/already/abs.wav", None)

    payload = json.loads(fake.sent.decode("utf-8").strip())
    assert payload["out_path"] == "/tmp/already/abs.wav"


@pytest.mark.skipif(
    not os.path.isfile(os.path.join(MODEL_PATH, "config.json")),
    reason="model config not present")
def test_lang_codes_match_model_config():
    cfg = json.load(open(os.path.join(MODEL_PATH, "config.json")))
    model_langs = set(
        cfg["talker_config"]["codec_language_id"].keys())
    assert set(LANG_CODES) - {"auto"} == model_langs

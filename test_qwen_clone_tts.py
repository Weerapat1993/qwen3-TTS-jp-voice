"""Unit test สำหรับ qwen_clone_tts language resolution (TTS-1006)
+ daemon out_path abspath (TTS-1008)"""
import json
import os
import shutil
import socket
import subprocess

import pytest

import qwen_clone_tts
from qwen_clone_tts import (LANG_CODES, MODEL_PATH, MOOD_PRESETS,
                            resolve_instruct, resolve_lang, _try_daemon,
                            split_mood_segments)


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


# ---------- resolve_instruct (mood > instruct > voice_default >
# MOOD_PRESETS["default"]) ----------

def test_resolve_instruct_2args_backward_compat():
    # ผู้เรียกเดิม (Hermes/CLI/tune_voice.py) ส่งแค่ 2 args — ต้องยังทำงาน
    assert resolve_instruct(None, None) == MOOD_PRESETS["default"]
    assert resolve_instruct("excited", None) == MOOD_PRESETS["excited"]
    assert resolve_instruct(None, "custom instruct") == "custom instruct"


def test_resolve_instruct_mood_wins_over_instruct_and_voice_default():
    assert resolve_instruct("excited", "custom", "voice default") \
        == MOOD_PRESETS["excited"]


def test_resolve_instruct_explicit_instruct_wins_over_voice_default():
    assert resolve_instruct(None, "custom", "voice default") == "custom"


def test_resolve_instruct_voice_default_wins_over_mood_preset_default():
    assert resolve_instruct(None, None, "voice default") == "voice default"


def test_resolve_instruct_falls_back_to_mood_preset_default():
    assert resolve_instruct(None, None, None) == MOOD_PRESETS["default"]


def test_resolve_instruct_unknown_mood_raises():
    with pytest.raises(ValueError):
        resolve_instruct("nope", None, "voice default")


def test_split_mood_segments_no_tag_returns_single_none_segment():
    assert split_mood_segments("Hello world") == [(None, "Hello world")]


def test_split_mood_segments_single_tag_covers_whole_text():
    assert split_mood_segments("[mood:excited]Hello world") == \
        [("excited", "Hello world")]


def test_split_mood_segments_leading_text_then_tag():
    result = split_mood_segments("Hello [mood:excited] world")
    assert result == [(None, "Hello"), ("excited", "world")]


def test_split_mood_segments_multiple_tags_interleaved():
    text = "[mood:excited]Hi![mood:sleepy]So tired..."
    assert split_mood_segments(text) == \
        [("excited", "Hi!"), ("sleepy", "So tired...")]


def test_split_mood_segments_drops_empty_segment_between_adjacent_tags():
    text = "[mood:excited][mood:sleepy]only this"
    assert split_mood_segments(text) == [("sleepy", "only this")]


def test_split_mood_segments_drops_whitespace_only_segment():
    text = "[mood:excited]   \n  [mood:sleepy]only this"
    assert split_mood_segments(text) == [("sleepy", "only this")]


def test_split_mood_segments_lowercases_mood_key():
    assert split_mood_segments("[mood:EXCITED]hi") == [("excited", "hi")]


def test_split_mood_segments_unknown_mood_raises():
    with pytest.raises(ValueError):
        split_mood_segments("[mood:exicted]Hello")


def test_split_mood_segments_reports_all_unknown_moods_at_once():
    with pytest.raises(ValueError) as exc_info:
        split_mood_segments("[mood:foo]a[mood:bar]b")
    msg = str(exc_info.value)
    assert "foo" in msg
    assert "bar" in msg


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


def test_run_multi_sends_per_segment_instruct_via_daemon(monkeypatch, tmp_path):
    """_run_multi ต้องส่ง instruct ที่ต่างกันต่อ segment ผ่าน daemon
    (quiet=True ทุกครั้ง) แล้วเรียก ffmpeg concat ครั้งเดียวรวมทุก part"""
    sent_payloads = []

    class _SeqFakeSock:
        def __init__(self):
            self._replied = False

        def settimeout(self, _t):
            pass

        def connect(self, _p):
            pass

        def sendall(self, data):
            sent_payloads.append(json.loads(data.decode("utf-8").strip()))

        def recv(self, _n):
            if self._replied:
                return b""
            self._replied = True
            return (json.dumps(
                {"ok": True, "out_path": "/ignored.wav", "gen_s": 0.1}) + "\n"
            ).encode("utf-8")

        def close(self):
            pass

    monkeypatch.setattr(qwen_clone_tts.os.path, "exists", lambda _p: True)
    monkeypatch.setattr(socket, "socket", lambda *a, **k: _SeqFakeSock())
    monkeypatch.setattr(shutil, "which", lambda _n: "/usr/bin/ffmpeg")

    concat_calls = []

    class _FakeCompleted:
        returncode = 0
        stderr = ""

    def fake_run(cmd, **kwargs):
        concat_calls.append(cmd)
        return _FakeCompleted()

    monkeypatch.setattr(subprocess, "run", fake_run)

    out_path = str(tmp_path / "out.wav")
    segments = [("excited", "Hello there"), ("sleepy", "Good night")]
    rc = qwen_clone_tts._run_multi("Liino", segments, None, out_path)

    assert rc == 0
    assert len(sent_payloads) == 2
    assert sent_payloads[0]["instruct"] == MOOD_PRESETS["excited"]
    assert sent_payloads[1]["instruct"] == MOOD_PRESETS["sleepy"]
    assert sent_payloads[0]["text"] == "Hello there"
    assert sent_payloads[1]["text"] == "Good night"
    assert len(concat_calls) == 1
    assert "concat" in concat_calls[0]


def test_run_multi_aborts_whole_run_if_daemon_fails_mid_job(monkeypatch, tmp_path):
    """job แรกสำเร็จผ่าน daemon, job ที่สองล้มเหลว -> ทั้งรันต้อง fail
    ไม่ยอมให้ ffmpeg concat ไฟล์บางส่วนออกมา"""
    call_count = {"n": 0}

    class _FlakySock:
        def settimeout(self, _t):
            pass

        def connect(self, _p):
            pass

        def sendall(self, data):
            pass

        def recv(self, _n):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return (json.dumps(
                    {"ok": True, "out_path": "/x.wav", "gen_s": 0.1}) + "\n"
                ).encode("utf-8")
            return b""  # job ที่ 2 เป็นตันไป: daemon หลุด/ไม่ตอบ

        def close(self):
            pass

    monkeypatch.setattr(qwen_clone_tts.os.path, "exists", lambda _p: True)
    monkeypatch.setattr(socket, "socket", lambda *a, **k: _FlakySock())
    monkeypatch.setattr(shutil, "which", lambda _n: "/usr/bin/ffmpeg")

    def fail_if_called(*a, **k):
        raise AssertionError("ffmpeg concat must not run after a job failure")

    monkeypatch.setattr(subprocess, "run", fail_if_called)

    out_path = str(tmp_path / "out.wav")
    segments = [("excited", "one"), ("sleepy", "two")]
    rc = qwen_clone_tts._run_multi("Liino", segments, None, out_path)

    assert rc == 1


def test_run_multi_falls_back_to_mood_flag_for_untagged_segment(
        monkeypatch, tmp_path):
    """segment ที่ไม่มี [mood:xxx] tag (mood_key=None) ต้อง fallback ไปใช้
    --mood ของ --stdin แทน (mood > per-voice default) เหมือน single-segment
    path ไม่ใช่ข้าม --mood ไปตกที่ voice_default/MOOD_PRESETS["default"] เฉยๆ"""
    sent_payloads = []

    class _SeqFakeSock:
        def __init__(self):
            self._replied = False

        def settimeout(self, _t):
            pass

        def connect(self, _p):
            pass

        def sendall(self, data):
            sent_payloads.append(json.loads(data.decode("utf-8").strip()))

        def recv(self, _n):
            if self._replied:
                return b""
            self._replied = True
            return (json.dumps(
                {"ok": True, "out_path": "/ignored.wav", "gen_s": 0.1}) + "\n"
            ).encode("utf-8")

        def close(self):
            pass

    monkeypatch.setattr(qwen_clone_tts.os.path, "exists", lambda _p: True)
    monkeypatch.setattr(socket, "socket", lambda *a, **k: _SeqFakeSock())
    monkeypatch.setattr(shutil, "which", lambda _n: "/usr/bin/ffmpeg")

    class _FakeCompleted:
        returncode = 0
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda cmd, **k: _FakeCompleted())

    out_path = str(tmp_path / "out.wav")
    segments = [(None, "Hello there"), ("sleepy", "Good night")]
    rc = qwen_clone_tts._run_multi("Liino", segments, None, out_path,
                                   mood="excited")

    assert rc == 0
    assert sent_payloads[0]["instruct"] == MOOD_PRESETS["excited"]
    assert sent_payloads[1]["instruct"] == MOOD_PRESETS["sleepy"]


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


def test_try_daemon_quiet_suppresses_stdout_and_stderr(monkeypatch, capsys):
    fake = _FakeSock()
    monkeypatch.setattr(qwen_clone_tts.os.path, "exists", lambda _p: True)
    monkeypatch.setattr(socket, "socket", lambda *a, **k: fake)

    ok = _try_daemon("hi", "outputs/x.wav", None, quiet=True)

    assert ok is True
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_try_daemon_default_not_quiet_still_prints_ok(monkeypatch, capsys):
    fake = _FakeSock()
    monkeypatch.setattr(qwen_clone_tts.os.path, "exists", lambda _p: True)
    monkeypatch.setattr(socket, "socket", lambda *a, **k: fake)

    ok = _try_daemon("hi", "outputs/x.wav", None)

    assert ok is True
    captured = capsys.readouterr()
    assert captured.out.startswith("OK ")


@pytest.mark.skipif(
    not os.path.isfile(os.path.join(MODEL_PATH, "config.json")),
    reason="model config not present")
def test_lang_codes_match_model_config():
    cfg = json.load(open(os.path.join(MODEL_PATH, "config.json")))
    model_langs = set(
        cfg["talker_config"]["codec_language_id"].keys())
    assert set(LANG_CODES) - {"auto"} == model_langs

"""Unit test สำหรับ voice_store (TTS-1009)

ครอบ sanitize_name, reserved gate, path helpers, list_voices, instruction io,
rename/delete, prepare_ref_audio. prepare_ref_audio ต้องมี ffmpeg/ffprobe จริง
จึง skip เมื่อไม่มีใน PATH (แนวเดียวกับ test_stt_transcribe.py)
"""
import os
import shutil
import subprocess

import pytest

import voice_store as vs
from voice_store import VoiceStoreError, is_reserved, sanitize_name

_ffmpeg_missing = (shutil.which("ffmpeg") is None
                   or shutil.which("ffprobe") is None)
requires_ffmpeg = pytest.mark.skipif(
    _ffmpeg_missing, reason="ffmpeg/ffprobe not on PATH")


@pytest.fixture
def voices_dir(tmp_path, monkeypatch):
    d = tmp_path / "voices"
    d.mkdir()
    monkeypatch.setattr(vs, "VOICES_DIR", str(d))
    return d


def _touch(p, content=""):
    p.write_text(content, encoding="utf-8")


# ---------- sanitize_name / is_reserved ----------

@pytest.mark.parametrize("raw,expected", [
    ("Liino", "liino"),
    ("  Wyitz  ", "wyitz"),
    ("my_voice_2", "my_voice_2"),
    ("ABC123", "abc123"),
])
def test_sanitize_name_ok(raw, expected):
    assert sanitize_name(raw) == expected


@pytest.mark.parametrize("raw", [
    "../etc", "a/b", "has space", "emoji\U0001f600", "", "   ",
    "a" * 33, "dash-name", "dot.name", None,
])
def test_sanitize_name_rejects(raw):
    with pytest.raises(VoiceStoreError):
        sanitize_name(raw)


def test_is_reserved():
    assert is_reserved("liino") is True
    assert is_reserved("LIINO") is True
    assert is_reserved("wyitz") is False


# ---------- path helpers / instruction io / list ----------

def test_voice_paths_shape(voices_dir):
    wav, txt, ins = vs.voice_paths("wyitz")
    assert wav.endswith("/wyitz.wav")
    assert txt.endswith("/wyitz.txt")
    assert ins.endswith("/wyitz.instruct.txt")
    assert os.path.isabs(wav)


def test_voice_exists(voices_dir):
    assert vs.voice_exists("wyitz") is False
    _touch(voices_dir / "wyitz.wav", "x")
    assert vs.voice_exists("wyitz") is True


def test_instruction_round_trip(voices_dir):
    assert vs.read_instruction("wyitz") is None
    vs.write_instruction("wyitz", "  calm, warm, slow pacing  ")
    assert vs.read_instruction("wyitz") == "calm, warm, slow pacing"
    vs.write_instruction("wyitz", "   ")
    assert vs.read_instruction("wyitz") is None
    assert not (voices_dir / "wyitz.instruct.txt").exists()


def test_list_voices(voices_dir):
    _touch(voices_dir / ".gitkeep")
    _touch(voices_dir / "liino.wav", "x")
    _touch(voices_dir / "liino.txt", "hello")
    _touch(voices_dir / "wyitz.wav", "x")
    _touch(voices_dir / "wyitz.instruct.txt", "grumpy, clipped")
    got = vs.list_voices()
    assert [v["name"] for v in got] == ["liino", "wyitz"]
    assert got[0] == {"name": "liino", "has_transcript": True,
                      "instruction": None}
    assert got[1] == {"name": "wyitz", "has_transcript": False,
                      "instruction": "grumpy, clipped"}


def test_list_voices_missing_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(vs, "VOICES_DIR", str(tmp_path / "nope"))
    assert vs.list_voices() == []


# ---------- rename / delete ----------

def test_rename_voice_moves_all_files(voices_dir):
    _touch(voices_dir / "old.wav", "w")
    _touch(voices_dir / "old.txt", "t")
    _touch(voices_dir / "old.instruct.txt", "i")
    vs.rename_voice("old", "new")
    assert not (voices_dir / "old.wav").exists()
    assert (voices_dir / "new.wav").read_text() == "w"
    assert (voices_dir / "new.txt").read_text() == "t"
    assert (voices_dir / "new.instruct.txt").read_text() == "i"


def test_rename_voice_partial_files_ok(voices_dir):
    _touch(voices_dir / "old.wav", "w")
    vs.rename_voice("old", "new")
    assert (voices_dir / "new.wav").exists()
    assert not (voices_dir / "new.txt").exists()


def test_rename_voice_rejects(voices_dir):
    _touch(voices_dir / "old.wav", "w")
    _touch(voices_dir / "taken.wav", "w")
    with pytest.raises(VoiceStoreError):
        vs.rename_voice("missing", "new")
    with pytest.raises(VoiceStoreError):
        vs.rename_voice("old", "taken")
    with pytest.raises(VoiceStoreError):
        vs.rename_voice("old", "liino")
    with pytest.raises(VoiceStoreError):
        vs.rename_voice("liino", "new")


def test_delete_voice(voices_dir):
    _touch(voices_dir / "gone.wav", "w")
    _touch(voices_dir / "gone.txt", "t")
    removed = vs.delete_voice("gone")
    assert set(removed) == {"gone.wav", "gone.txt"}
    assert not (voices_dir / "gone.wav").exists()


def test_delete_voice_rejects(voices_dir):
    with pytest.raises(VoiceStoreError):
        vs.delete_voice("liino")
    with pytest.raises(VoiceStoreError):
        vs.delete_voice("missing")


# ---------- get_default_voice / set_default_voice / is_protected (TTS-1010) ----------

def test_get_default_voice_no_marker_falls_back(voices_dir):
    assert vs.get_default_voice() == "liino"


def test_set_default_voice_then_get(voices_dir):
    _touch(voices_dir / "wyitz.wav", "w")
    vs.set_default_voice("wyitz")
    assert vs.get_default_voice() == "wyitz"
    assert (voices_dir / ".default").read_text(encoding="utf-8").strip() == "wyitz"


def test_set_default_voice_rejects_missing(voices_dir):
    with pytest.raises(VoiceStoreError):
        vs.set_default_voice("missing")


def test_get_default_voice_marker_points_to_deleted_voice_falls_back(voices_dir):
    _touch(voices_dir / "wyitz.wav", "w")
    vs.set_default_voice("wyitz")
    (voices_dir / "wyitz.wav").unlink()
    assert vs.get_default_voice() == "liino"


def test_is_protected_reserved_always_true(voices_dir):
    assert vs.is_protected("liino") is True
    assert vs.is_protected("LIINO") is True


def test_is_protected_current_default(voices_dir):
    _touch(voices_dir / "wyitz.wav", "w")
    assert vs.is_protected("wyitz") is False
    vs.set_default_voice("wyitz")
    assert vs.is_protected("wyitz") is True


def test_is_protected_non_default_non_reserved(voices_dir):
    _touch(voices_dir / "wyitz.wav", "w")
    _touch(voices_dir / "other.wav", "w")
    vs.set_default_voice("wyitz")
    assert vs.is_protected("other") is False


# ---------- prepare_ref_audio ----------

@requires_ffmpeg
def test_prepare_ref_audio_rejects_short_clip(tmp_path):
    src = tmp_path / "short.wav"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi",
         "-i", "sine=frequency=440:duration=2", str(src)], check=True)
    with pytest.raises(VoiceStoreError):
        vs.prepare_ref_audio(str(src), str(tmp_path / "out.wav"))


@requires_ffmpeg
def test_prepare_ref_audio_converts_and_trims(tmp_path):
    src = tmp_path / "long.wav"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi",
         "-i", "sine=frequency=440:duration=20:sample_rate=44100",
         "-ac", "2", str(src)], check=True)
    dst = tmp_path / "ref.wav"
    dur = vs.prepare_ref_audio(str(src), str(dst))
    assert 19.5 < dur < 20.5
    assert dst.exists()
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=channels,sample_rate", "-of", "csv=p=0", str(dst)],
        capture_output=True, text=True, check=True).stdout
    assert "1" in probe and "24000" in probe
    assert vs.probe_duration_seconds(str(dst)) <= 12.3


@requires_ffmpeg
def test_prepare_ref_audio_rejects_non_audio(tmp_path):
    src = tmp_path / "notaudio.wav"
    src.write_text("this is not audio", encoding="utf-8")
    with pytest.raises(VoiceStoreError):
        vs.prepare_ref_audio(str(src), str(tmp_path / "out.wav"))


@requires_ffmpeg
def test_prepare_ref_audio_no_partial_output_on_failure(tmp_path):
    # ต้นทางเสียงได้ (ผ่าน probe) แต่ ffmpeg เขียน output ไม่ได้ (dir ไม่มีจริง)
    src = tmp_path / "ok.wav"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi",
         "-i", "sine=frequency=440:duration=5", str(src)], check=True)
    dst = tmp_path / "missing_dir" / "out.wav"
    with pytest.raises(VoiceStoreError):
        vs.prepare_ref_audio(str(src), str(dst))
    assert not dst.exists()

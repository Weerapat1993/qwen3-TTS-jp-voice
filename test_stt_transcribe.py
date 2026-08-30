"""Unit test สำหรับ stt_transcribe (TTS-1005)

ครอบเฉพาะ config resolution + probe_duration; transcribe() ต้องมีโมเดล Whisper
จริง + ไฟล์เสียงจริง จึงทดสอบใน manual validation (ดู plan Task 4)
"""
import importlib
import shutil
import subprocess

import pytest

import stt_transcribe

_ffmpeg_missing = shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None


@pytest.fixture(autouse=True)
def _restore_module():
    yield
    importlib.reload(stt_transcribe)


def test_whisper_model_default_when_env_unset(monkeypatch):
    monkeypatch.delenv("TRANSCRIBE_WHISPER_MODEL", raising=False)
    reloaded = importlib.reload(stt_transcribe)
    assert reloaded.WHISPER_MODEL == "mlx-community/whisper-large-v3-turbo"


def test_whisper_model_env_override(monkeypatch):
    monkeypatch.setenv("TRANSCRIBE_WHISPER_MODEL", "foo/bar-whisper")
    reloaded = importlib.reload(stt_transcribe)
    assert reloaded.WHISPER_MODEL == "foo/bar-whisper"


@pytest.mark.skipif(_ffmpeg_missing, reason="ffmpeg/ffprobe not on PATH")
def test_probe_duration_on_generated_wav(tmp_path):
    wav = tmp_path / "sine.wav"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi",
         "-i", "sine=frequency=440:duration=3", str(wav)],
        check=True)
    assert 2.8 < stt_transcribe.probe_duration(str(wav)) < 3.2


def test_probe_duration_missing_file_raises():
    with pytest.raises(RuntimeError):
        stt_transcribe.probe_duration("/nonexistent/nope.wav")

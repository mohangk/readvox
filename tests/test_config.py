from __future__ import annotations

from tts_app.config import load_settings


def test_tts_model_env_replaces_legacy_qwen_model(monkeypatch):
    monkeypatch.setenv("TTS_MODEL", "tts-model")

    settings = load_settings()

    assert settings.qwen_model == "tts-model"


def test_legacy_qwen_model_is_ignored(monkeypatch):
    monkeypatch.delenv("TTS_MODEL", raising=False)
    monkeypatch.setenv("QWEN_MODEL", "legacy-model")

    settings = load_settings()

    assert settings.qwen_model == "qwen3-tts-instruct-flash-realtime"


def test_ocr_model_env_replaces_legacy_qwen_ocr_model(monkeypatch):
    monkeypatch.setenv("OCR_MODEL", "ocr-model")

    settings = load_settings()

    assert settings.ocr_model == "ocr-model"


def test_legacy_qwen_ocr_model_is_ignored(monkeypatch):
    monkeypatch.delenv("OCR_MODEL", raising=False)
    monkeypatch.setenv("QWEN_OCR_MODEL", "legacy-ocr-model")

    settings = load_settings()

    assert settings.ocr_model == "qwen-vl-ocr"


def test_default_voice_config_does_not_read_legacy_qwen_voice(monkeypatch):
    monkeypatch.delenv("TTS_DEFAULT_ENGLISH_VOICE", raising=False)
    monkeypatch.setenv("QWEN_VOICE", "Legacy")

    settings = load_settings()

    assert settings.default_english_voice == "Kai"


def test_provider_timeouts_are_configurable_and_reject_unbounded_values(monkeypatch):
    import pytest
    monkeypatch.setenv('QWEN_AUDIO_TIMEOUT_SECONDS', '12.5')
    assert load_settings().qwen_audio_timeout == 12.5
    for value in ['0', '-1', 'inf', 'nan']:
        monkeypatch.setenv('QWEN_AUDIO_TIMEOUT_SECONDS', value)
        with pytest.raises(ValueError, match='finite and positive'):
            load_settings()

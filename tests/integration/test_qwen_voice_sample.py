from __future__ import annotations

import os
from pathlib import Path
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from tts_app.api import create_app


pytestmark = [
    pytest.mark.live_provider,
    pytest.mark.skipif(
        os.environ.get("RUN_QWEN_INTEGRATION") != "1",
        reason="set RUN_QWEN_INTEGRATION=1 to call the live Qwen provider",
    ),
]


def test_saved_profile_integrates_with_qwen_generation(unpopulated_settings):
    api_key = os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("QWEN_API_KEY")
    if not api_key:
        pytest.fail("DASHSCOPE_API_KEY or QWEN_API_KEY is required when RUN_QWEN_INTEGRATION=1")
    settings = replace(unpopulated_settings, provider_name="qwen", qwen_api_key=api_key)
    clone_manifest = os.environ.get("QWEN_LIVE_CLONE_MANIFEST")
    if clone_manifest:
        from tts_app.voice_catalog_install import install_clone_manifest
        voices = install_clone_manifest(Path(clone_manifest), settings=settings,
                                          accepted_keys=['readvox-kai-v1'])
        voice = voices[0]
    else:
        from tts_app.voice_catalog_sync import sync_voice_catalog
        sync_voice_catalog(settings)
    client = TestClient(create_app(settings, run_background_inline=True))
    text = "Readvox checks the live provider with calm, clear narration."
    if clone_manifest:
        created=client.post('/api/voice-profiles',json=dict(name='Live Kai check',voice_id=voice['id'],
            language='en',speed=1.0,instructions='',preview_text=text))
        assert created.status_code==201,created.text
        profile=created.json()
    else:
        profile = client.get("/api/voice-profiles").json()[0]
        profile["instructions"] = "Read calmly and clearly."
        profile["preview_text"] = text
        saved = client.put(f"/api/voice-profiles/{profile['id']}", json=profile)
        assert saved.status_code == 200
    assert client.get("/api/generations").json() == []
    assert len(text) <= settings.segment_max_chars
    response = client.post("/api/generations/text", json={
        "text": text, "profile_id": profile["id"], "autoplay": False,
    })
    assert response.status_code == 200, response.text
    generation_id = response.json()["generation_id"]
    detail = client.app.state.storage.get_generation(generation_id)
    assert detail["generation"]["status"] == "completed", detail["generation"]["error"]
    assert detail["generation"]["settings"]["model"] == client.app.state.storage.get_voice(profile["voice_id"])["model"]
    assert detail["generation"]["settings"]["instructions"] == profile["instructions"]
    for field in ("voice", "speed", "language"):
        assert detail["generation"]["settings"][field] == profile[field]
    assert detail["generation"]["settings"]["profile_id"] == profile["id"]
    assert len(detail["audio_segments"]) == 1
    assert detail["audio_segments"][0]["byte_size"] > 1_000

import sys
import types

import pytest

from observateur_actif.speech import (
    DEFAULT_VOICE, SpeechError, build_speech_text, generate_audio,
)
from observateur_actif.storyboard import DocumentaryProject


def make_project():
    return DocumentaryProject.model_validate({
        "title": "Test",
        "target_duration_minutes": 10,
        "scenes": [
            {"id": "s1", "duration_seconds": 5, "narration": "La nuit tombe.",
             "video_prompt": "Night shot", "motion_description": "Camera moves.",
             "claim_status": "legend"},
            {"id": "s2", "duration_seconds": 5, "narration": "Le vent se lève.",
             "video_prompt": "Trees", "motion_description": "Trees move.",
             "claim_status": "hypothesis"}
        ]
    })


def test_build_speech_text_uses_scene_order():
    text = build_speech_text(make_project())
    assert text == "La nuit tombe. Le vent se lève."


def test_generate_audio_saves_mp3_and_uses_documentary_voice(tmp_path, monkeypatch):
    calls = {}

    class FakeCommunicate:
        def __init__(self, text, **kwargs):
            calls["text"] = text
            calls.update(kwargs)

        async def save(self, path):
            from pathlib import Path
            Path(path).write_bytes(b"fake-mp3")

    monkeypatch.setitem(sys.modules, "edge_tts", types.SimpleNamespace(
        Communicate=FakeCommunicate
    ))
    # Patch the imported module object used by speech.py.
    import observateur_actif.speech as speech
    monkeypatch.setattr(speech, "edge_tts", sys.modules["edge_tts"])

    output = generate_audio(make_project(), tmp_path / "nested" / "voice.mp3")
    assert output.read_bytes() == b"fake-mp3"
    assert calls["voice"] == DEFAULT_VOICE
    assert calls["rate"] == "-8%"
    assert calls["pitch"] == "-8Hz"
    assert calls["text"].startswith("La nuit tombe.")


def test_empty_project_narration_is_rejected():
    project = DocumentaryProject.model_validate({
        "title": "Vide", "target_duration_minutes": 10, "scenes": [{"id": "s1", "duration_seconds": 5, "narration": "   ", "video_prompt": "Empty", "motion_description": "Still", "claim_status": "legend"}]
    })
    with pytest.raises(SpeechError):
        build_speech_text(project)

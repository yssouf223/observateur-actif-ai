import sys
import asyncio
import types

import pytest

from observateur_actif.speech import (
    DEFAULT_VOICE, SpeechError, build_speech_text, generate_audio,
    _word_boundaries_to_srt,
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
    assert build_speech_text(make_project()) == "La nuit tombe. Le vent se lève."


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
    import observateur_actif.speech as speech
    monkeypatch.setattr(speech, "edge_tts", sys.modules["edge_tts"])

    output = generate_audio(make_project(), tmp_path / "nested" / "voice.mp3")
    assert output.read_bytes() == b"fake-mp3"
    assert calls["voice"] == DEFAULT_VOICE
    assert calls["rate"] == "-8%"
    assert calls["pitch"] == "-8Hz"
    assert calls["text"].startswith("La nuit tombe.")


def test_word_boundaries_create_real_timestamps_and_captions():
    from observateur_actif.speech import _word_boundaries_to_srt
    # Offsets/durations use Edge-TTS 100-nanosecond ticks.
    srt = _word_boundaries_to_srt([
        (0, 3_000_000, "La"),
        (3_000_000, 4_000_000, "nuit"),
        (7_000_000, 5_000_000, "tombe."),
        (15_000_000, 3_000_000, "Le"),
        (18_000_000, 4_000_000, "vent"),
    ])
    assert "00:00:00,000 --> 00:00:01,200" in srt
    assert "La nuit tombe." in srt
    assert "00:00:01,500 --> 00:00:02,200" in srt
    assert "Le vent" in srt


def test_empty_word_boundaries_are_rejected():
    from observateur_actif.speech import _word_boundaries_to_srt
    with pytest.raises(SpeechError):
        _word_boundaries_to_srt([])


def test_empty_project_narration_is_rejected():
    project = DocumentaryProject.model_validate({
        "title": "Vide", "target_duration_minutes": 10, "scenes": [{
            "id": "s1", "duration_seconds": 5, "narration": "   ",
            "video_prompt": "Empty", "motion_description": "Still",
            "claim_status": "legend"
        }]
    })
    with pytest.raises(SpeechError):
        build_speech_text(project)


def test_edge_tts_stream_writes_audio_and_word_timed_srt(tmp_path, monkeypatch):
    import observateur_actif.speech as speech

    class FakeCommunicate:
        def __init__(self, text, **kwargs):
            self.text = text
            self.kwargs = kwargs
            FakeCommunicate.last_kwargs = kwargs

        async def stream(self):
            yield {"type": "audio", "data": b"fake-mp3"}
            yield {"type": "WordBoundary", "offset": 0, "duration": 2_000_000, "text": "Bonjour"}
            yield {"type": "WordBoundary", "offset": 2_000_000, "duration": 3_000_000, "text": "monde."}

    monkeypatch.setattr(speech.edge_tts, "Communicate", FakeCommunicate)
    audio = tmp_path / "voice.mp3"
    srt = asyncio.run(speech._stream_audio_and_timing(
        "Bonjour monde.", audio, DEFAULT_VOICE, "-8%", "-8Hz"
    ))
    assert audio.read_bytes() == b"fake-mp3"
    assert "Bonjour monde." in srt
    assert "-->" in srt
    assert FakeCommunicate.last_kwargs["boundary"] == "WordBoundary"

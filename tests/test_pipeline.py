from pathlib import Path
from unittest.mock import patch

import pytest

from observateur_actif.pipeline import ProductionError, produce_project
from observateur_actif.storyboard import DocumentaryProject


def make_project(approved=True):
    return DocumentaryProject.model_validate({
        "title": "Forêt mystérieuse",
        "target_duration_minutes": 10,
        "scenes": [{
            "id": "scene-01", "duration_seconds": 5,
            "narration": "La forêt se réveille lentement.",
            "video_prompt": "Cinematic moving forest",
            "motion_description": "Camera glides forward through moving mist.",
            "claim_status": "legend",
            "review_approved": approved,
            "reviewer": "Rédaction",
            "reviewed_at": "2026-11-27"
        }]
    })


def test_pipeline_refuses_unreviewed_scenes(tmp_path):
    with pytest.raises(ProductionError, match="Arrêt éditorial"):
        produce_project(make_project(False), tmp_path / "project.json", tmp_path,
                        api_key="secret")


def test_pipeline_runs_video_voice_subtitles_and_montage(tmp_path):
    project_file = tmp_path / "project.json"
    project = make_project()
    clip = tmp_path / "scenes" / "scene-01.mp4"
    clip.parent.mkdir()
    clip.write_bytes(b"clip")

    def fake_speech(project, audio, subtitles):
        Path(audio).write_bytes(b"audio")
        Path(subtitles).write_text("srt", encoding="utf-8")
        return Path(audio), Path(subtitles)

    def fake_montage(project, audio, video, subtitles_file=None):
        Path(video).write_bytes(b"video")
        return Path(video)

    with patch("observateur_actif.pipeline.generate_video") as gen, \
         patch("observateur_actif.pipeline.generate_audio_with_subtitles", side_effect=fake_speech), \
         patch("observateur_actif.pipeline.assemble_documentary", side_effect=fake_montage):
        result = produce_project(
            project, project_file, tmp_path / "output", api_key="test-key"
        )

    gen.assert_called_once()
    assert result["video"].read_bytes() == b"video"
    assert result["subtitles"].read_text() == "srt"
    assert result["report"].is_file()
    assert project.scenes[0].generated_video_path.endswith("scene-01.mp4")


def test_pipeline_reuses_existing_generated_scene(tmp_path):
    project = make_project()
    clip = tmp_path / "existing.mp4"
    clip.write_bytes(b"clip")

    def fake_speech(project, audio, subtitles):
        Path(audio).write_bytes(b"audio")
        Path(subtitles).write_text("srt", encoding="utf-8")
        return Path(audio), Path(subtitles)

    def fake_montage(project, audio, video, subtitles_file=None):
        Path(video).write_bytes(b"video")
        return Path(video)

    project.scenes[0].generated_video_path = str(clip)
    with patch("observateur_actif.pipeline.generate_video") as gen, \
         patch("observateur_actif.pipeline.generate_audio_with_subtitles", side_effect=fake_speech), \
         patch("observateur_actif.pipeline.assemble_documentary", side_effect=fake_montage):
        produce_project(project, tmp_path / "project.json", tmp_path / "out", api_key="key")
    gen.assert_not_called()

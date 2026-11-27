from pathlib import Path
import json
from unittest.mock import patch

import pytest

from observateur_actif.pipeline import ProductionError, produce_project
from observateur_actif.storyboard import DocumentaryProject


def make_project(approved=True):
    return DocumentaryProject.model_validate({
        "title": "Forêt mystérieuse",
        "target_duration_minutes": 10,
        "scenes": [
            {
                "id": f"scene-{i:02d}", "duration_seconds": 12,
                "narration": "La forêt se réveille lentement.",
                "video_prompt": "Cinematic moving forest",
                "motion_description": "Camera glides forward through moving mist.",
                "claim_status": "legend",
                "review_approved": approved,
                "reviewer": "Rédaction",
                "reviewed_at": "2026-11-27"
            }
            for i in range(1, 51)
        ]
    })


def test_pipeline_refuses_unreviewed_scenes(tmp_path):
    with pytest.raises(ProductionError, match="Arrêt éditorial"):
        produce_project(make_project(False), tmp_path / "project.json", tmp_path,
                        api_key="secret")


def test_pipeline_runs_video_voice_subtitles_and_montage(tmp_path):
    project_file = tmp_path / "project.json"
    project = make_project()

    def fake_speech(project, audio, subtitles):
        Path(audio).write_bytes(b"audio")
        Path(subtitles).write_text("srt", encoding="utf-8")
        return Path(audio), Path(subtitles)

    def fake_montage(project, audio, video, subtitles_file=None):
        Path(video).write_bytes(b"video")
        return Path(video)

    with patch("observateur_actif.pipeline.generate_video") as gen, \
         patch("observateur_actif.pipeline.inspect_clip_motion", return_value={"status": "motion_check_passed"}), \
         patch("observateur_actif.pipeline.generate_audio_with_subtitles", side_effect=fake_speech), \
         patch("observateur_actif.pipeline.assemble_documentary", side_effect=fake_montage), patch("observateur_actif.pipeline.write_quality_report", side_effect=lambda video, report: (Path(report).write_text(json.dumps({"duration_seconds": 600}), encoding="utf-8") or Path(report))):
        result = produce_project(
            project, project_file, tmp_path / "output", api_key="test-key"
        )

    assert gen.call_count == 50
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
         patch("observateur_actif.pipeline.assemble_documentary", side_effect=fake_montage), patch("observateur_actif.pipeline.write_quality_report", side_effect=lambda video, report: (Path(report).write_text(json.dumps({"duration_seconds": 600}), encoding="utf-8") or Path(report))):
        produce_project(project, tmp_path / "project.json", tmp_path / "out", api_key="key")
    assert gen.call_count == 49

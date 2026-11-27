from pathlib import Path
from unittest.mock import patch

import pytest

from observateur_actif.montage import MontageError, assemble_documentary
from observateur_actif.storyboard import DocumentaryProject


def project_with_clips(tmp_path):
    clips = []
    for name in ("scene1.mp4", "scene2.mp4"):
        path = tmp_path / name
        path.write_bytes(b"clip")
        clips.append(str(path))
    return DocumentaryProject.model_validate({
        "title": "Documentaire test",
        "target_duration_minutes": 10,
        "scenes": [
            {"id": f"s{i}", "duration_seconds": 5, "narration": f"Voix {i}.",
             "video_prompt": "Moving shot", "motion_description": "Camera moves.",
             "claim_status": "legend", "generated_video_path": clip}
            for i, clip in enumerate(clips, 1)
        ]
    })


def test_assemble_maps_clips_voice_and_soft_subtitles(tmp_path):
    project = project_with_clips(tmp_path)
    narration = tmp_path / "voice.mp3"
    subtitles = tmp_path / "voice.srt"
    narration.write_bytes(b"mp3")
    subtitles.write_text("1\n00:00:00,000 --> 00:00:01,000\nBonjour\n", encoding="utf-8")
    output = tmp_path / "final.mp4"

    def fake_run(command, **kwargs):
        Path(command[-1]).write_bytes(b"mp4")

    with patch("observateur_actif.montage.shutil.which", return_value="/usr/bin/ffmpeg"), \
         patch("observateur_actif.montage.subprocess.run", side_effect=fake_run) as run:
        result = assemble_documentary(
            project, narration, output, subtitles_file=subtitles
        )

    args = run.call_args.args[0]
    assert result.read_bytes() == b"mp4"
    assert "1280:720" in args[args.index("-filter_complex") + 1]
    assert "mov_text" in args
    assert "-shortest" in args


def test_optional_music_is_mixed_below_voice(tmp_path):
    project = project_with_clips(tmp_path)
    narration = tmp_path / "voice.mp3"
    music = tmp_path / "music.mp3"
    narration.write_bytes(b"mp3")
    music.write_bytes(b"music")
    output = tmp_path / "final.mp4"

    def fake_run(command, **kwargs):
        Path(command[-1]).write_bytes(b"mp4")

    with patch("observateur_actif.montage.shutil.which", return_value="/usr/bin/ffmpeg"), \
         patch("observateur_actif.montage.subprocess.run", side_effect=fake_run) as run:
        assemble_documentary(project, narration, output, music_file=music)

    graph = run.call_args.args[0][run.call_args.args[0].index("-filter_complex") + 1]
    assert "volume=0.12" in graph
    assert "amix=inputs=2:duration=first" in graph


def test_missing_generated_scene_clip_is_rejected(tmp_path):
    project = project_with_clips(tmp_path)
    project.scenes[0].generated_video_path = None
    narration = tmp_path / "voice.mp3"
    narration.write_bytes(b"mp3")
    with patch("observateur_actif.montage.shutil.which", return_value="/usr/bin/ffmpeg"):
        with pytest.raises(MontageError, match="n'a pas de vidéo générée"):
            assemble_documentary(project, narration, tmp_path / "final.mp4")


def test_missing_ffmpeg_is_reported(tmp_path):
    project = project_with_clips(tmp_path)
    narration = tmp_path / "voice.mp3"
    narration.write_bytes(b"mp3")
    with patch("observateur_actif.montage.shutil.which", return_value=None):
        with pytest.raises(MontageError, match="FFmpeg est introuvable"):
            assemble_documentary(project, narration, tmp_path / "final.mp4")

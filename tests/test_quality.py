import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from observateur_actif.quality import QualityError, inspect_video, inspect_clip_motion, write_quality_report


def probe_result(width=1920, height=1080, video_codec="h264", audio_codec="aac"):
    return {
        "streams": [
            {"codec_type": "video", "codec_name": video_codec, "width": width, "height": height},
            {"codec_type": "audio", "codec_name": audio_codec},
            {"codec_type": "subtitle", "codec_name": "mov_text"},
        ],
        "format": {"duration": "612.5"},
    }


def test_inspect_video_checks_codecs_resolution_and_streams(tmp_path):
    video = tmp_path / "doc.mp4"
    video.write_bytes(b"video")
    completed = Mock(stdout=json.dumps(probe_result()))
    with patch("observateur_actif.quality.shutil.which", return_value="/usr/bin/ffprobe"), \
         patch("observateur_actif.quality.subprocess.run", return_value=completed):
        report = inspect_video(video)
    assert report["status"] == "technical_checks_passed"
    assert report["duration_seconds"] == 612.5
    assert report["subtitle_stream_present"] is True


def test_rejects_wrong_resolution(tmp_path):
    video = tmp_path / "doc.mp4"
    video.write_bytes(b"video")
    completed = Mock(stdout=json.dumps(probe_result(width=1280, height=720)))
    with patch("observateur_actif.quality.shutil.which", return_value="/usr/bin/ffprobe"), \
         patch("observateur_actif.quality.subprocess.run", return_value=completed):
        with pytest.raises(QualityError, match="Résolution inattendue"):
            inspect_video(video)


def test_rejects_missing_narration_audio(tmp_path):
    video = tmp_path / "doc.mp4"
    video.write_bytes(b"video")
    data = probe_result()
    data["streams"] = [data["streams"][0]]
    with patch("observateur_actif.quality.shutil.which", return_value="/usr/bin/ffprobe"), \
         patch("observateur_actif.quality.subprocess.run", return_value=Mock(stdout=json.dumps(data))):
        with pytest.raises(QualityError, match="flux audio"):
            inspect_video(video)


def test_write_report(tmp_path):
    video = tmp_path / "doc.mp4"
    video.write_bytes(b"video")
    with patch("observateur_actif.quality.shutil.which", return_value="/usr/bin/ffprobe"), \
         patch("observateur_actif.quality.subprocess.run", return_value=Mock(stdout=json.dumps(probe_result()))):
        report = write_quality_report(video, tmp_path / "quality.json")
    assert json.loads(report.read_text())["status"] == "technical_checks_passed"


def test_rejects_missing_subtitle_stream(tmp_path):
    video = tmp_path / "doc.mp4"
    video.write_bytes(b"video")
    data = probe_result()
    data["streams"] = data["streams"][:2]
    with patch("observateur_actif.quality.shutil.which", return_value="/usr/bin/ffprobe"), \
         patch("observateur_actif.quality.subprocess.run", return_value=Mock(stdout=json.dumps(data))):
        with pytest.raises(QualityError, match="piste de sous-titres"):
            inspect_video(video)


def test_motion_check_accepts_a_clip_without_long_freezes(tmp_path):
    clip = tmp_path / "moving.mp4"
    clip.write_bytes(b"video")
    completed = Mock(returncode=0, stderr="frame=300 fps=25")
    with patch("observateur_actif.quality.shutil.which", return_value="/usr/bin/ffmpeg"), \
         patch("observateur_actif.quality.subprocess.run", return_value=completed):
        report = inspect_clip_motion(clip)
    assert report["status"] == "motion_check_passed"


def test_motion_check_rejects_a_static_clip(tmp_path):
    clip = tmp_path / "still.mp4"
    clip.write_bytes(b"video")
    completed = Mock(returncode=0, stderr="lavfi.freezedetect.freeze_duration: 4.500")
    with patch("observateur_actif.quality.shutil.which", return_value="/usr/bin/ffmpeg"), \
         patch("observateur_actif.quality.subprocess.run", return_value=completed):
        with pytest.raises(QualityError, match="Mouvement insuffisant"):
            inspect_clip_motion(clip)

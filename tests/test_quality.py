import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from observateur_actif.quality import QualityError, inspect_video, write_quality_report


def probe_result(width=1280, height=720, video_codec="h264", audio_codec="aac"):
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
    completed = Mock(stdout=json.dumps(probe_result(width=1920, height=1080)))
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

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from observateur_actif.youtube import YouTubePublishError, next_saturday_1600_utc, publish_video


def test_next_saturday_at_1600_utc():
    now = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)
    assert next_saturday_1600_utc(now) == datetime(2026, 11, 28, 16, 0, tzinfo=timezone.utc)


def test_after_saturday_1600_schedules_following_week():
    now = datetime(2026, 11, 28, 17, 0, tzinfo=timezone.utc)
    assert next_saturday_1600_utc(now) == datetime(2026, 12, 5, 16, 0, tzinfo=timezone.utc)


def test_publish_requires_oauth_secrets(tmp_path, monkeypatch):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    for name in ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN", "YOUTUBE_CHANNEL_ID"):
        monkeypatch.delenv(name, raising=False)
    with patch("observateur_actif.youtube.inspect_video", return_value={}):
        with pytest.raises(YouTubePublishError, match="Secrets YouTube manquants"):
            publish_video(video, title="Test", description="", tags=[],
                          publish_at=datetime(2026, 12, 5, 16, tzinfo=timezone.utc))


def test_publish_refuses_past_time(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    with patch("observateur_actif.youtube.inspect_video", return_value={}):
        with pytest.raises(YouTubePublishError, match="dans le futur"):
            publish_video(video, title="Test", description="", tags=[],
                          publish_at=datetime(2020, 1, 1, tzinfo=timezone.utc))

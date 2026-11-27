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


def test_successful_upload_is_private_until_future_publish_time(tmp_path, monkeypatch):
    import sys
    import types
    from datetime import datetime, timedelta, timezone

    captured = {}

    class FakeCredentials:
        def __init__(self, **kwargs):
            captured["scopes"] = kwargs["scopes"]

    class FakeRequest:
        def next_chunk(self):
            return None, {"id": "youtube-video-123", "status": {"privacyStatus": "private", "publishAt": captured["body"]["status"]["publishAt"]}}

    class FakeYouTube:
        def channels(self):
            return types.SimpleNamespace(
                list=lambda **kwargs: types.SimpleNamespace(
                    execute=lambda: {"items": [{"id": "channel-123"}]}
                )
            )

        def videos(self):
            def insert(**kwargs):
                captured["body"] = kwargs["body"]
                return FakeRequest()
            return types.SimpleNamespace(insert=insert)

    google = types.ModuleType("google")
    google.__path__ = []
    oauth2 = types.ModuleType("google.oauth2")
    oauth2.__path__ = []
    credentials_module = types.ModuleType("google.oauth2.credentials")
    credentials_module.Credentials = FakeCredentials
    api = types.ModuleType("googleapiclient")
    api.__path__ = []
    discovery = types.ModuleType("googleapiclient.discovery")
    discovery.build = lambda *args, **kwargs: FakeYouTube()
    http = types.ModuleType("googleapiclient.http")
    http.MediaFileUpload = lambda *args, **kwargs: "media-upload"

    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.oauth2", oauth2)
    monkeypatch.setitem(sys.modules, "google.oauth2.credentials", credentials_module)
    monkeypatch.setitem(sys.modules, "googleapiclient", api)
    monkeypatch.setitem(sys.modules, "googleapiclient.discovery", discovery)
    monkeypatch.setitem(sys.modules, "googleapiclient.http", http)
    monkeypatch.setenv("YOUTUBE_CLIENT_ID", "client")
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "secret")
    monkeypatch.setenv("YOUTUBE_REFRESH_TOKEN", "refresh")
    monkeypatch.setenv("YOUTUBE_CHANNEL_ID", "channel-123")
    monkeypatch.setenv("YOUTUBE_API_PROJECT_VERIFIED", "true")

    video = tmp_path / "final.mp4"
    video.write_bytes(b"mp4")
    publish_at = datetime.now(timezone.utc) + timedelta(days=1)
    with patch("observateur_actif.youtube.inspect_video", return_value={}):
        result = publish_video(
            video, title="Documentaire", description="Description",
            tags=["Observateur Actif"], publish_at=publish_at,
        )

    assert result["video_id"] == "youtube-video-123"
    assert captured["body"]["status"]["privacyStatus"] == "private"
    assert captured["body"]["status"]["publishAt"].endswith("Z")
    assert captured["body"]["snippet"]["categoryId"] == "27"
    assert "https://www.googleapis.com/auth/youtube.upload" in captured["scopes"]
    assert "https://www.googleapis.com/auth/youtube.readonly" in captured["scopes"]

from unittest.mock import Mock, patch

import pytest

from observateur_actif.video import AgnesError, MODEL, generate_video


def response(status=200, payload=None, content=b""):
    item = Mock()
    item.status_code = status
    item.ok = 200 <= status < 400
    item.json.return_value = payload or {}
    item.text = "provider error"
    item.iter_content.return_value = [content] if content else [b"fake-mp4"]
    item.__enter__ = Mock(return_value=item)
    item.__exit__ = Mock(return_value=False)
    return item


def test_missing_key_fails_before_network(monkeypatch, tmp_path):
    monkeypatch.delenv("AGNES_API_KEY", raising=False)
    with pytest.raises(AgnesError, match="Clé manquante"):
        generate_video("A moving river", tmp_path / "clip.mp4")


def test_invalid_duration_fails_before_network(tmp_path):
    with pytest.raises(AgnesError, match="durée"):
        generate_video("A moving river", tmp_path / "clip.mp4", api_key="test", seconds=20)


def test_create_poll_download_flow(tmp_path):
    created = response(payload={"video_id": "video-123"})
    completed = response(payload={
        "status": "completed",
        "url": "https://cdn.example.org/video.mp4",
    })
    downloaded = response(content=b"fake-mp4")

    with patch("observateur_actif.video.requests.post", return_value=created) as post, \
         patch("observateur_actif.video.requests.get", side_effect=[completed, downloaded]) as get, \
         patch("observateur_actif.video.time.sleep"):
        output = generate_video(
            "A documentary camera flies over a misty valley",
            tmp_path / "clip.mp4",
            api_key="secret-test-key",
            poll_interval=0,
        )

    assert output.read_bytes() == b"fake-mp4"
    assert post.call_args.kwargs["json"]["model"] == MODEL
    assert post.call_args.kwargs["json"]["aspect_ratio"] == "16:9"
    assert get.call_args_list[0].kwargs["params"]["video_id"] == "video-123"


def test_queue_full_retries_then_succeeds(tmp_path):
    busy = response(status=503, payload={"message": "video queue is full, please retry later"})
    created = response(payload={"video_id": "video-123"})
    completed = response(payload={
        "status": "completed",
        "url": "https://cdn.example.org/video.mp4",
    })
    downloaded = response(content=b"fake-mp4")

    with patch("observateur_actif.video.requests.post", side_effect=[busy, created]) as post, \
         patch("observateur_actif.video.requests.get", side_effect=[completed, downloaded]), \
         patch("observateur_actif.video.time.sleep") as sleep:
        output = generate_video(
            "A moving river", tmp_path / "clip.mp4", api_key="test", poll_interval=0
        )

    assert output.read_bytes() == b"fake-mp4"
    assert post.call_count == 2
    sleep.assert_any_call(30)


def test_queue_full_stops_after_limited_retries(tmp_path):
    busy = response(status=503, payload={"message": "video queue is full"})
    with patch("observateur_actif.video.requests.post", return_value=busy) as post, \
         patch("observateur_actif.video.requests.get") as get, \
         patch("observateur_actif.video.time.sleep"):
        with pytest.raises(AgnesError, match="video queue is full"):
            generate_video("A moving river", tmp_path / "clip.mp4", api_key="test")
        assert post.call_count == 3
        get.assert_not_called()

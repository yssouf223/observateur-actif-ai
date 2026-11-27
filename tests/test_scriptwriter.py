import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from observateur_actif.scriptwriter import ScriptWriterError, draft_project


def docs_file(tmp_path):
    path = tmp_path / "sources.json"
    path.write_text(json.dumps([
        {"fetch_status": "success", "url": "https://a.example.org/story",
         "title": "Ancient Saharan rock art discovered by archaeologists", "publisher": "Publisher A", "fetched_at": "2026-11-27",
         "text": "Researchers document prehistoric rock art in the Sahara, an archaeological record of ancient African communities."},
        {"fetch_status": "success", "url": "https://b.example.net/story",
         "title": "New study examines prehistoric rock art in the Sahara", "publisher": "Publisher B", "fetched_at": "2026-11-27",
         "text": "An independent archaeological study compares ancient rock art sites in North Africa and the Sahara."},
    ]), encoding="utf-8")
    return path


def valid_draft():
    return {
        "title": "Mystère documentaire",
        "target_duration_minutes": 10,
        "scenes": [
            {"id": f"scene-{i}", "duration_seconds": 12,
             "narration": "Une phrase documentaire suffisamment longue.",
             "video_prompt": "A cinematic moving camera shot.",
             "motion_description": "The camera moves continuously through the scene.",
             "claim_status": "unconfirmed", "source_ids": [f"source-{1 if i % 2 else 2}"]}
            for i in range(1, 51)
        ]
    }


def test_draft_requires_two_independent_sources(tmp_path):
    path = tmp_path / "sources.json"
    path.write_text(json.dumps([{
        "fetch_status": "success", "url": "https://a.example.org",
        "publisher": "Publisher A", "text": "Source."
    }]), encoding="utf-8")
    with pytest.raises(ScriptWriterError, match="deux documents"):
        draft_project(path, tmp_path / "project.json", api_key="test")


def test_draft_project_forces_human_approval_off(tmp_path):
    sources = docs_file(tmp_path)
    draft = valid_draft()
    draft["scenes"][0]["review_approved"] = True
    draft["scenes"][0]["reviewer"] = "Model"
    draft["scenes"][0]["reviewed_at"] = "2026-11-27"
    response = Mock(ok=True)
    response.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": json.dumps(draft)}]}}]
    }
    with patch("observateur_actif.scriptwriter.requests.post", return_value=response):
        output = draft_project(sources, tmp_path / "project.json", api_key="test")
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["release_approved"] is False
    assert result["scenes"][0]["review_approved"] is False
    assert result["scenes"][0]["reviewer"] is None


def test_draft_requires_gemini_key(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("AGNES_API_KEY", raising=False)
    with pytest.raises(ScriptWriterError, match="AGNES_API_KEY"):
        draft_project(docs_file(tmp_path), tmp_path / "project.json")

 
def test_draft_uses_agnes_chat_completions_when_no_gemini_key(tmp_path, monkeypatch):
    sources = docs_file(tmp_path)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("AGNES_API_KEY", "agnes-test-key")
    monkeypatch.setenv("SCRIPT_PROVIDER", "agnes")
    draft = valid_draft()
    response = Mock(ok=True)
    response.json.return_value = {
        "choices": [{"message": {"content": json.dumps(draft)}}]
    }
    with patch("observateur_actif.scriptwriter.requests.post", return_value=response) as post:
        output = draft_project(sources, tmp_path / "project.json")
    assert output.is_file()
    assert post.call_args.args[0].endswith("/v1/chat/completions")
    assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer agnes-test-key"
    assert post.call_args.kwargs["json"]["model"] == "agnes-2.5-flash"
    assert post.call_args.kwargs["json"]["response_format"] == {"type": "json_object"}


def test_draft_prompt_excludes_topics_from_history(tmp_path, monkeypatch):
    sources = docs_file(tmp_path)
    monkeypatch.setenv("AGNES_API_KEY", "agnes-test-key")
    monkeypatch.setenv("SCRIPT_PROVIDER", "agnes")
    history = tmp_path / "topic_history.json"
    history.write_text(json.dumps([{"title": "Lac Nyos", "notes": "Sujet exclu."}]), encoding="utf-8")
    response = Mock(ok=True)
    response.json.return_value = {
        "choices": [{"message": {"content": json.dumps(valid_draft())}}]
    }
    with patch("observateur_actif.scriptwriter.requests.post", return_value=response) as post:
        draft_project(
            sources, tmp_path / "project.json",
            topic_history_file=history,
        )
    prompt = post.call_args.kwargs["json"]["messages"][0]["content"]
    assert "Lac Nyos" in prompt
    assert "NE PAS RÉUTILISER" in prompt


def test_draft_repairs_malformed_json_from_agnes(tmp_path, monkeypatch):
    sources = docs_file(tmp_path)
    monkeypatch.setenv("AGNES_API_KEY", "agnes-test-key")
    monkeypatch.setenv("SCRIPT_PROVIDER", "agnes")
    raw = json.dumps(valid_draft(), ensure_ascii=False)
    raw = raw.replace(
        '"narration": "Une phrase documentaire suffisamment longue."',
        '"narration": "Une phrase "documentaire" suffisamment longue."',
        1,
    )
    response = Mock(ok=True)
    response.json.return_value = {
        "choices": [{"message": {"content": raw}}]
    }
    with patch("observateur_actif.scriptwriter.requests.post", return_value=response):
        output = draft_project(sources, tmp_path / "project.json")
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["scenes"][0]["narration"]
    assert result["release_approved"] is False


def test_draft_rejects_off_topic_political_or_terrorism_sources(tmp_path, monkeypatch):
    path = tmp_path / "off_topic.json"
    path.write_text(json.dumps([
        {"fetch_status": "success", "url": "https://a.example.org/story",
         "title": "The future of jihadism in Africa", "publisher": "Publisher A",
         "text": "A current political analysis of jihadist groups and conflict in the Sahel."},
        {"fetch_status": "success", "url": "https://b.example.net/story",
         "title": "The Moon Watchers", "publisher": "Publisher B",
         "text": "NASA astronomy observations of the Moon."}
    ]), encoding="utf-8")
    monkeypatch.setenv("AGNES_API_KEY", "agnes-test-key")
    with pytest.raises(ScriptWriterError, match="mystère historique"):
        draft_project(path, tmp_path / "project.json")


def test_draft_rejects_story_using_only_one_of_two_sources(tmp_path, monkeypatch):
    sources = docs_file(tmp_path)
    monkeypatch.setenv("AGNES_API_KEY", "agnes-test-key")
    draft = valid_draft()
    for scene in draft["scenes"]:
        scene["source_ids"] = ["source-1"]
    response = Mock(ok=True)
    response.json.return_value = {
        "choices": [{"message": {"content": json.dumps(draft)}}]
    }
    with patch("observateur_actif.scriptwriter.requests.post", return_value=response):
        with pytest.raises(ScriptWriterError, match="deux sources indépendantes"):
            draft_project(sources, tmp_path / "project.json")

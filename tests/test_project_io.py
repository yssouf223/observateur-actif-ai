import json
import pytest
from observateur_actif.project_io import load_project


def valid_project():
    return {
        "title": "La forêt mystérieuse",
        "target_duration_minutes": 10,
        "aspect_ratio": "16:9",
        "language": "fr",
        "sources": [
            {
                "id": "src1", "title": "Rapport scientifique",
                "url": "https://example.org/report", "publisher": "Institut de recherche",
                "accessed_at": "2026-11-27", "reliability_note": "Source institutionnelle"
            },
            {
                "id": "src2", "title": "Étude universitaire",
                "url": "https://university.example/study", "publisher": "Université",
                "accessed_at": "2026-11-27", "reliability_note": "Publication à examiner"
            }
        ],
        "scenes": [{
            "id": "scene1", "duration_seconds": 5,
            "narration": "La forêt se réveille.",
            "video_prompt": "A moving aerial shot over a forest at dawn",
            "motion_description": "La caméra avance et la brume se déplace.",
            "claim_status": "verified", "source_ids": ["src1", "src2"],
            "review_approved": True, "reviewer": "éditeur humain",
            "reviewed_at": "2026-11-27"
        }]
    }


def test_load_valid_project(tmp_path):
    path = tmp_path / "project.json"
    path.write_text(json.dumps(valid_project()), encoding="utf-8")
    project = load_project(path)
    assert project.title == "La forêt mystérieuse"
    assert project.scenes[0].source_ids == ["src1", "src2"]


def test_load_project_rejects_verified_claim_without_two_sources(tmp_path):
    data = valid_project()
    data["scenes"][0]["source_ids"] = []
    path = tmp_path / "project.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="sans deux sources"):
        load_project(path)


def test_load_project_rejects_unknown_source_id(tmp_path):
    data = valid_project()
    data["scenes"][0]["source_ids"] = ["missing", "src2"]
    path = tmp_path / "project.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="sources inconnues"):
        load_project(path)


def test_load_project_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_project(tmp_path / "absent.json")

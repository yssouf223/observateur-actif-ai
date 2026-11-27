from observateur_actif.project_review import export_project_review
from observateur_actif.storyboard import DocumentaryProject


def test_review_export_lists_sources_and_keeps_approval_false(tmp_path):
    project = DocumentaryProject.model_validate({
        "title": "Mystère de test",
        "target_duration_minutes": 10,
        "sources": [{
            "id": "source-1", "title": "Article source",
            "url": "https://example.org/article", "publisher": "Example",
            "accessed_at": "2026-11-27", "reliability_note": "À vérifier"
        }],
        "scenes": [{
            "id": "scene-1", "duration_seconds": 10,
            "narration": "Une narration de test.",
            "video_prompt": "Cinematic moving shot.",
            "motion_description": "Camera slowly moves forward.",
            "claim_status": "unconfirmed", "source_ids": ["source-1"]
        }]
    })
    output = export_project_review(project, tmp_path / "review.md")
    text = output.read_text(encoding="utf-8")
    assert "Article source" in text
    assert "https://example.org/article" in text
    assert "Approbation de publication : NON" in text
    assert "Approuvée : NON" in text

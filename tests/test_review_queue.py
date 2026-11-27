from observateur_actif.claim_review import ClaimRegistry
from observateur_actif.review_queue import build_review_queue


def test_review_queue_shows_pending_claim_and_source_review_checks():
    registry = ClaimRegistry.model_validate({
        "sources": [{
            "id": "s1",
            "title": "Article source",
            "url": "https://example.org/story",
            "publisher": "Example News",
            "accessed_at": "2026-11-27",
            "supports_claim": False,
        }],
        "claims": [{
            "id": "c1",
            "statement": "Une phrase candidate suffisamment longue pour être examinée.",
            "status": "unconfirmed",
            "source_ids": ["s1"],
            "review_decision": "pending",
        }],
    })
    report = build_review_queue(registry)
    assert "c1" in report
    assert "Article source" in report
    assert "lire le contexte complet" in report
    assert "indépendante" in report


def test_review_queue_reports_no_pending_claims():
    registry = ClaimRegistry.model_validate({
        "sources": [],
        "claims": [{
            "id": "c1",
            "statement": "Une affirmation rejetée après examen humain.",
            "status": "unconfirmed",
            "source_ids": [],
            "review_decision": "rejected",
            "reviewer": "éditeur",
            "reviewed_at": "2026-11-27",
        }],
    })
    assert "Aucune affirmation en attente" in build_review_queue(registry)

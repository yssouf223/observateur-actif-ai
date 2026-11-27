import pytest
from pydantic import ValidationError

from observateur_actif.claim_review import (
    ClaimRegistry,
    EditorialStatus,
    ReviewDecision,
)


def source(source_id, publisher, url, supports=True):
    return {
        "id": source_id,
        "title": f"Document {source_id}",
        "url": url,
        "publisher": publisher,
        "accessed_at": "2026-11-27",
        "supports_claim": supports,
    }


def verified_claim(**overrides):
    value = {
        "id": "claim-1",
        "statement": "Une affirmation documentaire suffisamment détaillée.",
        "status": "verified",
        "source_ids": ["s1", "s2"],
        "review_decision": "approved",
        "reviewer": "éditeur humain",
        "reviewed_at": "2026-11-27",
    }
    value.update(overrides)
    return value


def test_verified_claim_requires_human_approval():
    with pytest.raises(ValidationError, match="validation humaine"):
        ClaimRegistry(
            sources=[source("s1", "Éditeur A", "https://a.example/a"),
                     source("s2", "Éditeur B", "https://b.example/b")],
            claims=[verified_claim(review_decision="pending")],
        )


def test_verified_claim_requires_two_independent_publishers_and_domains():
    with pytest.raises(ValidationError, match="deux éditeurs et domaines distincts"):
        ClaimRegistry(
            sources=[source("s1", "Même éditeur", "https://a.example/a"),
                     source("s2", "Même éditeur", "https://b.example/b")],
            claims=[verified_claim()],
        )


def test_verified_claim_accepts_two_distinct_supporting_sources_after_review():
    registry = ClaimRegistry(
        sources=[source("s1", "Éditeur A", "https://a.example/a"),
                 source("s2", "Éditeur B", "https://b.example/b")],
        claims=[verified_claim()],
    )
    assert registry.claims[0].status == EditorialStatus.VERIFIED


def test_pending_unconfirmed_claim_can_have_one_source():
    registry = ClaimRegistry(
        sources=[source("s1", "Éditeur A", "https://a.example/a")],
        claims=[{
            "id": "claim-2",
            "statement": "Une piste qui reste à examiner attentivement.",
            "status": "unconfirmed",
            "source_ids": ["s1"],
        }],
    )
    assert registry.claims[0].review_decision == ReviewDecision.PENDING


def test_unknown_source_is_rejected():
    with pytest.raises(ValidationError, match="Sources inconnues"):
        ClaimRegistry(
            sources=[],
            claims=[{
                "id": "claim-3",
                "statement": "Une affirmation sans référence documentaire.",
                "source_ids": ["absent"],
            }],
        )


def test_malformed_source_url_is_rejected():
    with pytest.raises(ValidationError, match="URL HTTP"):
        ClaimRegistry(
            sources=[source("s1", "Éditeur A", "javascript:alert(1)")],
            claims=[{
                "id": "claim-4",
                "statement": "Une affirmation avec une source mal formée.",
                "source_ids": ["s1"],
            }],
        )


def test_duplicate_source_ids_are_rejected():
    with pytest.raises(ValidationError, match="identifiants des sources"):
        ClaimRegistry(
            sources=[source("s1", "A", "https://a.example"),
                     source("s1", "B", "https://b.example")],
            claims=[{
                "id": "claim-5",
                "statement": "Une affirmation avec des sources en doublon.",
            }],
        )


def test_counter_source_does_not_count_as_support():
    with pytest.raises(ValidationError, match="deux éditeurs et domaines distincts"):
        ClaimRegistry(
            sources=[source("s1", "A", "https://a.example"),
                     source("s2", "B", "https://b.example", supports=False)],
            claims=[verified_claim()],
        )

import pytest
from pydantic import ValidationError

from observateur_actif.storyboard import (
    ClaimStatus,
    DocumentaryProject,
    Scene,
    Source,
)


def make_scene(status=ClaimStatus.VERIFIED, source_ids=None, **review):
    return Scene(
        id="scene-01",
        duration_seconds=8,
        narration="La vallée s'éveille.",
        video_prompt="Vue cinématographique d'une vallée au lever du soleil.",
        motion_description="La caméra avance lentement tandis que la brume se déplace.",
        claim_status=status,
        source_ids=source_ids or [],
        **review,
    )


def make_source(source_id="source-01", publisher="Organisme A", url="https://a.example/report"):
    return Source(
        id=source_id,
        title="Rapport documentaire",
        url=url,
        publisher=publisher,
        accessed_at="2026-11-27",
        reliability_note="Source à examiner.",
    )


def make_review():
    return {"review_approved": True, "reviewer": "éditeur humain", "reviewed_at": "2026-11-27"}


def test_verified_scene_requires_human_review_and_two_sources():
    with pytest.raises(ValidationError, match="validation éditoriale humaine"):
        DocumentaryProject(
            title="Test", target_duration_minutes=10,
            sources=[
                make_source("source-01", "Organisme A", "https://a.example/report"),
                make_source("source-02", "Université B", "https://b.example/study"),
            ],
            scenes=[make_scene(source_ids=["source-01", "source-02"])],
        )


def test_unknown_source_is_rejected():
    with pytest.raises(ValidationError, match="sources inconnues"):
        DocumentaryProject(
            title="Test", target_duration_minutes=10,
            sources=[make_source()],
            scenes=[make_scene(source_ids=["missing-source"], **make_review())],
        )


def test_verified_scene_with_independent_sources_and_review_is_valid():
    project = DocumentaryProject(
        title="Test",
        target_duration_minutes=10,
        sources=[
            make_source("source-01", "Organisme A", "https://a.example/report"),
            make_source("source-02", "Université B", "https://b.example/study"),
        ],
        scenes=[make_scene(source_ids=["source-01", "source-02"], **make_review())],
    )
    assert len(project.scenes[0].source_ids) == 2


def test_verified_scene_rejects_same_publisher():
    with pytest.raises(ValidationError, match="deux éditeurs"):
        DocumentaryProject(
            title="Test", target_duration_minutes=10,
            sources=[
                make_source("source-01", "Même éditeur", "https://a.example/report"),
                make_source("source-02", "Même éditeur", "https://b.example/study"),
            ],
            scenes=[make_scene(source_ids=["source-01", "source-02"], **make_review())],
        )


def test_non_16_9_project_is_rejected():
    with pytest.raises(ValidationError):
        DocumentaryProject(
            title="Test", target_duration_minutes=10, aspect_ratio="9:16",
            sources=[make_source()],
            scenes=[make_scene(status=ClaimStatus.LEGEND)],
        )


def test_scene_duration_is_bounded():
    with pytest.raises(ValidationError):
        Scene(
            id="too-long", duration_seconds=30, narration="Texte",
            video_prompt="Prompt", motion_description="Mouvement",
            claim_status=ClaimStatus.LEGEND,
        )


def test_unconfirmed_scene_does_not_need_review():
    project = DocumentaryProject(
        title="Test", target_duration_minutes=10,
        scenes=[make_scene(status=ClaimStatus.UNCONFIRMED)],
    )
    assert project.scenes[0].review_approved is False

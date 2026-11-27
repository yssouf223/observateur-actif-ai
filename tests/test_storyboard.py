import pytest
from pydantic import ValidationError

from observateur_actif.storyboard import (
    ClaimStatus,
    DocumentaryProject,
    Scene,
    Source,
)


def make_scene(status=ClaimStatus.VERIFIED, source_ids=None):
    return Scene(
        id="scene-01",
        duration_seconds=8,
        narration="La vallée s'éveille.",
        video_prompt="Vue cinématographique d'une vallée au lever du soleil.",
        motion_description="La caméra avance lentement tandis que la brume se déplace.",
        claim_status=status,
        source_ids=source_ids or [],
    )


def make_source():
    return Source(
        id="source-01",
        title="Rapport documentaire",
        url="https://example.org/report",
        publisher="Organisme de recherche",
        accessed_at="2026-11-27",
        reliability_note="Source institutionnelle à examiner.",
    )


def test_verified_scene_requires_source():
    with pytest.raises(ValidationError):
        DocumentaryProject(
            title="Test",
            target_duration_minutes=10,
            sources=[],
            scenes=[make_scene()],
        )


def test_unknown_source_is_rejected():
    with pytest.raises(ValidationError):
        DocumentaryProject(
            title="Test",
            target_duration_minutes=10,
            sources=[make_source()],
            scenes=[make_scene(source_ids=["missing-source"])],
        )


def test_verified_scene_with_known_source_is_valid():
    project = DocumentaryProject(
        title="Test",
        target_duration_minutes=10,
        sources=[make_source()],
        scenes=[make_scene(source_ids=["source-01"])],
    )
    assert project.scenes[0].source_ids == ["source-01"]


def test_non_16_9_project_is_rejected():
    with pytest.raises(ValidationError):
        DocumentaryProject(
            title="Test",
            target_duration_minutes=10,
            aspect_ratio="9:16",
            sources=[make_source()],
            scenes=[make_scene(source_ids=["source-01"])],
        )


def test_scene_duration_is_bounded():
    with pytest.raises(ValidationError):
        Scene(
            id="too-long",
            duration_seconds=30,
            narration="Texte",
            video_prompt="Prompt",
            motion_description="Mouvement",
            claim_status=ClaimStatus.LEGEND,
        )

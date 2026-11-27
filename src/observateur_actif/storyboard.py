"""Schéma de storyboard : chaque scène doit être une vraie séquence animée."""

from enum import Enum
from urllib.parse import urlparse

from pydantic import BaseModel, Field, model_validator


class ClaimStatus(str, Enum):
    VERIFIED = "verified"
    HYPOTHESIS = "hypothesis"
    TESTIMONY = "testimony"
    ORAL_TRADITION = "oral_tradition"
    LEGEND = "legend"
    UNCONFIRMED = "unconfirmed"


class Source(BaseModel):
    id: str
    title: str
    url: str
    publisher: str
    published_at: str | None = None
    accessed_at: str
    reliability_note: str


class Scene(BaseModel):
    id: str
    duration_seconds: int = Field(ge=3, le=15)
    narration: str = Field(min_length=1)
    video_prompt: str = Field(min_length=1)
    motion_description: str = Field(min_length=1)
    claim_status: ClaimStatus
    source_ids: list[str] = Field(default_factory=list)
    review_approved: bool = False
    reviewer: str | None = None
    reviewed_at: str | None = None
    generated_video_path: str | None = None

    @model_validator(mode="after")
    def require_motion(self):
        if not self.motion_description.strip():
            raise ValueError("Chaque scène doit décrire un mouvement réel.")
        if not self.video_prompt.strip():
            raise ValueError("Chaque scène doit avoir un prompt vidéo.")
        return self


class DocumentaryProject(BaseModel):
    title: str
    target_duration_minutes: int = Field(ge=10, le=15)
    aspect_ratio: str = "16:9"
    language: str = "fr"
    sources: list[Source] = Field(default_factory=list)
    scenes: list[Scene] = Field(min_length=1)
    release_approved: bool = False
    release_reviewer: str | None = None
    release_approved_at: str | None = None

    @model_validator(mode="after")
    def validate_storyboard(self):
        if self.aspect_ratio != "16:9":
            raise ValueError("Le format documentaire doit être 16:9.")
        if self.release_approved and (not self.release_reviewer or not self.release_approved_at):
            raise ValueError("La publication approuvée exige release_reviewer et release_approved_at.")
        known_source_ids = {source.id for source in self.sources}
        if len(known_source_ids) != len(self.sources):
            raise ValueError("Les identifiants des sources doivent être uniques.")
        sources_by_id = {source.id: source for source in self.sources}
        for scene in self.scenes:
            unknown_ids = set(scene.source_ids) - known_source_ids
            if unknown_ids:
                raise ValueError(
                    f"La scène {scene.id} référence des sources inconnues : "
                    f"{', '.join(sorted(unknown_ids))}."
                )
            if scene.claim_status == ClaimStatus.VERIFIED:
                supporting = [sources_by_id[source_id] for source_id in scene.source_ids]
                if len(supporting) < 2:
                    raise ValueError(
                        f"La scène {scene.id} est vérifiée sans deux sources indépendantes associées."
                    )
                if not scene.review_approved or not scene.reviewer or not scene.reviewed_at:
                    raise ValueError(
                        f"La scène {scene.id} est vérifiée sans validation éditoriale humaine."
                    )
                publishers = {source.publisher.strip().casefold() for source in supporting}
                hosts = {
                    (urlparse(source.url).hostname or "").casefold()
                    for source in supporting
                }
                if len(publishers) < 2 or len(hosts) < 2:
                    raise ValueError(
                        f"La scène {scene.id} exige deux sources de deux éditeurs "
                        "et domaines distincts pour être déclarée vérifiée."
                    )
        return self

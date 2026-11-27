"""Schéma de storyboard : chaque scène doit être une vraie séquence animée."""

from enum import Enum
from pydantic import BaseModel, Field, model_validator


class ClaimStatus(str, Enum):
    VERIFIED = "verified"
    HYPOTHESIS = "hypothesis"
    TESTIMONY = "testimony"
    ORAL_TRADITION = "oral_tradition"
    LEGEND = "legend"
    UNCONFIRMED = "unconfirmed"


class Source(BaseModel):
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
    generated_video_path: str | None = None

    @model_validator(mode="after")
    def require_motion(self):
        if not self.motion_description.strip():
            raise ValueError("Chaque scène doit décrire un mouvement réel.")
        return self


class DocumentaryProject(BaseModel):
    title: str
    target_duration_minutes: int = Field(ge=10, le=15)
    aspect_ratio: str = "16:9"
    language: str = "fr"
    sources: list[Source] = Field(default_factory=list)
    scenes: list[Scene] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_storyboard(self):
        if self.aspect_ratio != "16:9":
            raise ValueError("Le format documentaire doit être 16:9.")
        known_sources = {source.title for source in self.sources}
        for scene in self.scenes:
            if scene.claim_status == ClaimStatus.VERIFIED and not scene.source_ids:
                raise ValueError(
                    f"La scène {scene.id} est déclarée vérifiée sans source associée."
                )
        return self

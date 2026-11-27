"""Registre d'affirmations et garde-fous de vérification éditoriale.

Ce module valide la traçabilité et la décision humaine ; il ne vérifie pas
automatiquement la vérité d'une affirmation.
"""
from __future__ import annotations

from enum import Enum
from pathlib import Path
from urllib.parse import urlparse
import json

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class EditorialStatus(str, Enum):
    VERIFIED = "verified"
    HYPOTHESIS = "hypothesis"
    TESTIMONY = "testimony"
    ORAL_TRADITION = "oral_tradition"
    LEGEND = "legend"
    UNCONFIRMED = "unconfirmed"


class ReviewDecision(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class EvidenceSource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    url: str = Field(min_length=1)
    publisher: str = Field(min_length=1)
    accessed_at: str = Field(min_length=1)
    supports_claim: bool = True

    @model_validator(mode="after")
    def validate_http_url(self):
        parsed = urlparse(self.url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("L'URL de chaque source doit être une URL HTTP(S) absolue.")
        if parsed.username or parsed.password:
            raise ValueError("Les identifiants intégrés dans une URL sont interdits.")
        return self


class ClaimRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    statement: str = Field(min_length=12)
    status: EditorialStatus = EditorialStatus.UNCONFIRMED
    source_ids: list[str] = Field(default_factory=list)
    notes: str = ""
    review_decision: ReviewDecision = ReviewDecision.PENDING
    reviewer: str | None = None
    reviewed_at: str | None = None


class ClaimRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sources: list[EvidenceSource] = Field(default_factory=list)
    claims: list[ClaimRecord] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_registry(self):
        source_ids = [source.id for source in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("Les identifiants des sources doivent être uniques.")
        claim_ids = [claim.id for claim in self.claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("Les identifiants des affirmations doivent être uniques.")

        sources_by_id = {source.id: source for source in self.sources}
        for claim in self.claims:
            if len(claim.source_ids) != len(set(claim.source_ids)):
                raise ValueError(f"Sources répétées pour l'affirmation {claim.id}.")
            missing = set(claim.source_ids) - set(sources_by_id)
            if missing:
                raise ValueError(
                    f"Sources inconnues pour {claim.id} : {', '.join(sorted(missing))}."
                )
            if claim.status == EditorialStatus.VERIFIED:
                if claim.review_decision != ReviewDecision.APPROVED:
                    raise ValueError(
                        f"{claim.id} : une affirmation vérifiée exige une validation humaine approuvée."
                    )
                if not claim.reviewer or not claim.reviewed_at:
                    raise ValueError(
                        f"{claim.id} : reviewer et reviewed_at sont obligatoires pour verified."
                    )
                supporting = [
                    sources_by_id[source_id]
                    for source_id in claim.source_ids
                    if sources_by_id[source_id].supports_claim
                ]
                publishers = {source.publisher.strip().casefold() for source in supporting}
                hosts = {urlparse(source.url).hostname.casefold() for source in supporting}
                if len(supporting) < 2 or len(publishers) < 2 or len(hosts) < 2:
                    raise ValueError(
                        f"{claim.id} : verified exige au moins deux sources favorables "
                        "de deux éditeurs et domaines distincts."
                    )
        return self


def load_claim_registry(path: str | Path) -> ClaimRegistry:
    """Charger et valider un registre JSON d'affirmations."""
    registry_path = Path(path)
    if not registry_path.is_file():
        raise FileNotFoundError(f"Registre introuvable : {registry_path}")
    try:
        return ClaimRegistry.model_validate_json(
            registry_path.read_text(encoding="utf-8")
        )
    except (ValidationError, ValueError) as exc:
        raise ValueError(f"Registre d'affirmations invalide : {exc}") from exc

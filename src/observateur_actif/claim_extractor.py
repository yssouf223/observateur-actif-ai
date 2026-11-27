"""Extraction déterministe de phrases candidates depuis les textes de sources.

Les phrases sont des pistes éditoriales, jamais des faits vérifiés. Aucune IA
externe n'est appelée et aucune affirmation n'est automatiquement approuvée.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from urllib.parse import urlparse


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-ZÀÂÄÇÉÈÊËÎÏÔÖÙÛÜŸ0-9«\"'])")
_CLAIM_CUES = re.compile(
    r"\b(?:est|sont|était|étaient|fut|furent|a été|ont été|"
    r"aurait|auraient|serait|seraient|selon|affirme|déclare|"
    r"rapporte|indique|annonce|confirme|découvert|retrouvé|"
    r"disparu|disparition|mort|décès|attaque|explosion|"
    r"was|were|has been|have been|according to|reported|"
    r"discovered|found|disappeared|killed|died|announced)\b",
    re.IGNORECASE,
)


def _stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"


def _sentences(text: str) -> list[str]:
    normalized = " ".join(str(text).split())
    return [part.strip(" \t\r\n«»\"')]}") for part in _SENTENCE_SPLIT.split(normalized) if part.strip()]


def extract_claim_candidates(
    documents: list[dict], *, max_per_source: int = 30
) -> dict:
    """Construire un registre de phrases candidates traçables au texte source."""
    if not isinstance(documents, list):
        raise ValueError("Les documents doivent être une liste JSON.")
    if not 1 <= max_per_source <= 100:
        raise ValueError("max_per_source doit être compris entre 1 et 100.")

    sources: list[dict] = []
    claims: list[dict] = []
    seen_urls: set[str] = set()
    seen_statements: set[str] = set()
    now = datetime.now(timezone.utc).isoformat()

    for document in documents:
        if not isinstance(document, dict) or document.get("fetch_status", "success") != "success":
            continue
        url = str(document.get("url", "")).strip()
        body = str(document.get("text", "")).strip()
        if not url or not body or url in seen_urls:
            continue
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            continue
        seen_urls.add(url)
        source_id = _stable_id("src", url)
        sources.append({
            "id": source_id,
            "title": str(document.get("title") or document.get("lead_title") or "Source sans titre")[:500],
            "url": url,
            "publisher": str(document.get("publisher") or parsed.hostname)[:300],
            "accessed_at": str(document.get("fetched_at") or now),
            # La page contient la phrase, mais elle n'est pas une corroboration indépendante.
            "supports_claim": False,
        })

        accepted = 0
        for sentence in _sentences(body):
            if len(sentence) < 45 or len(sentence) > 600:
                continue
            if not _CLAIM_CUES.search(sentence):
                continue
            normalized = sentence.casefold()
            dedupe_key = f"{url}\n{normalized}"
            if dedupe_key in seen_statements:
                continue
            seen_statements.add(dedupe_key)
            claim_id = _stable_id("claim", dedupe_key)
            claims.append({
                "id": claim_id,
                "statement": sentence,
                "status": "unconfirmed",
                "source_ids": [source_id],
                "notes": (
                    "Phrase extraite automatiquement du texte source. "
                    "À vérifier dans le document original et à recouper avec "
                    "des sources indépendantes. Extraction non équivalente à une preuve."
                ),
                "review_decision": "pending",
            })
            accepted += 1
            if accepted >= max_per_source:
                break

    return {"sources": sources, "claims": claims}

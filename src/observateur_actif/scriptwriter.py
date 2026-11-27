"""Brouillon de storyboard documentaire via Gemini API en mode JSON."""

import json
import os
from pathlib import Path
import re

import requests

from observateur_actif.storyboard import DocumentaryProject


DEFAULT_MODEL = "gemini-3.8-flash"
API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"


class ScriptWriterError(RuntimeError):
    """Erreur de génération ou de validation du brouillon documentaire."""


def _slug_id(index: int) -> str:
    return f"scene-{index:03d}"


def draft_project(
    source_documents_file: str | Path,
    output_file: str | Path,
    *,
    topic: str = "",
    api_key: str | None = None,
    model: str = DEFAULT_MODEL,
) -> Path:
    """Créer un brouillon à partir d'au moins deux sources indépendantes.

    Le résultat reste toujours non approuvé : aucune publication ni génération
    vidéo ne peut être déclenchée avant revue humaine explicite.
    """
    key = (api_key or os.getenv("GEMINI_API_KEY", "")).strip()
    if not key:
        raise ScriptWriterError("GEMINI_API_KEY absent.")
    source_path = Path(source_documents_file)
    if not source_path.is_file():
        raise FileNotFoundError(f"Documents de recherche introuvables : {source_path}")
    try:
        documents = json.loads(source_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ScriptWriterError(f"JSON de recherche invalide : {exc}") from exc
    if not isinstance(documents, list):
        raise ScriptWriterError("Le fichier source doit contenir une liste de documents.")

    usable = [
        doc for doc in documents
        if isinstance(doc, dict)
        and doc.get("fetch_status") == "success"
        and str(doc.get("text", "")).strip()
        and str(doc.get("url", "")).startswith(("https://", "http://"))
    ]
    sources = []
    source_texts = []
    seen_hosts = set()
    seen_publishers = set()
    for index, doc in enumerate(usable, start=1):
        from urllib.parse import urlparse
        host = (urlparse(doc["url"]).hostname or "").lower()
        publisher = str(doc.get("publisher") or host).strip()
        if not host or host in seen_hosts or publisher.casefold() in seen_publishers:
            continue
        seen_hosts.add(host)
        seen_publishers.add(publisher.casefold())
        source_id = f"source-{len(sources) + 1}"
        sources.append({
            "id": source_id,
            "title": str(doc.get("title") or doc.get("lead_title") or "Source sans titre")[:500],
            "url": doc["url"],
            "publisher": publisher[:300],
            "accessed_at": str(doc.get("fetched_at") or "date de collecte non fournie"),
            "reliability_note": (
                "Texte extrait automatiquement ; source et contenu non vérifiés "
                "par une rédaction humaine."
            ),
        })
        source_texts.append({
            "source_id": source_id,
            "title": sources[-1]["title"],
            "publisher": publisher,
            "url": doc["url"],
            "published_at": doc.get("published_at"),
            "text": str(doc["text"])[:18000],
        })

    if len(sources) < 2:
        raise ScriptWriterError(
            "Au moins deux documents accessibles de deux éditeurs et domaines distincts sont requis."
        )

    source_bundle = json.dumps(source_texts, ensure_ascii=False)
    prompt = f"""
Tu es le rédacteur en chef et scénariste d'Observateur Actif, chaîne francophone
de documentaires d'enquête sur les mystères africains. Rédige un brouillon
documentaire sérieux, cinématographique, rigoureux et non sensationnaliste.

SUJET SOUHAITÉ : {topic or "Choisis le sujet le plus solide et le plus intéressant parmi les documents fournis."}

RÈGLES IMPÉRATIVES :
- Utilise exclusivement les informations présentes dans les documents fournis.
- N'invente aucun nom, date, lieu, citation, chiffre, témoignage ou événement.
- Ne prétends jamais qu'une affirmation est vérifiée : tous les statuts factuels doivent rester "unconfirmed", "hypothesis", "testimony", "oral_tradition" ou "legend".
- Une tradition orale, un récit spirituel ou une légende doit être explicitement présenté comme tel.
- Chaque scène factuelle doit référencer le ou les source_id qui soutiennent réellement son contenu.
- Si une information n'est pas documentée, ne l'ajoute pas comme fait. Signale les limites.
- Pas de dialogues fictifs, de citations reconstituées ni de scènes historiques présentées comme archives réelles.
- Voix off en français, masculine grave, calme, journalistique, sans emphase artificielle.
- Documentaire de 10 à 15 minutes, environ 1 300 à 1 700 mots de narration répartis sur 60 à 80 scènes.
- Chaque scène doit avoir un prompt vidéo en anglais pour un plan réellement animé, avec mouvement physique/caméra clairement décrit ; aucun diaporama, aucune image fixe, aucun texte incrusté.
- Les clips seront générés séparément en 4 à 12 secondes. Les scènes doivent donc prévoir des actions visuelles simples et cohérentes.
- Le projet doit être un BROUILLON : review_approved=false partout, reviewer=null, reviewed_at=null, release_approved=false.
- N'ajoute pas de source qui n'existe pas dans la liste.

Retourne UNIQUEMENT un objet JSON valide de cette forme :
{{
  "title": "Titre",
  "target_duration_minutes": 10,
  "scenes": [
    {{
      "id": "scene-001",
      "duration_seconds": 10,
      "narration": "Texte de narration en français.",
      "video_prompt": "Detailed cinematic text-to-video prompt in English.",
      "motion_description": "Describe actual continuous subject and camera movement.",
      "claim_status": "unconfirmed",
      "source_ids": ["source-1"],
      "review_approved": false,
      "reviewer": null,
      "reviewed_at": null
    }}
  ]
}}

DOCUMENTS SOURCÉS :
{source_bundle}
"""
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.25,
            "maxOutputTokens": 30000,
        },
    }
    try:
        response = requests.post(
            f"{API_ROOT}/{model}:generateContent",
            headers={"x-goog-api-key": key, "Content-Type": "application/json"},
            json=payload,
            timeout=240,
        )
        if not response.ok:
            detail = response.text[:1200]
            raise ScriptWriterError(f"Gemini API HTTP {response.status_code}: {detail}")
        data = response.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except ScriptWriterError:
        raise
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
        raise ScriptWriterError(f"Réponse Gemini absente ou illisible : {exc}") from exc

    cleaned = text.strip()
    cleaned = re.sub(r"^\`\`\`(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*\`\`\`$", "", cleaned)
    try:
        draft = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ScriptWriterError(f"Gemini n'a pas renvoyé un JSON valide : {exc}") from exc

    if not isinstance(draft, dict) or not isinstance(draft.get("scenes"), list):
        raise ScriptWriterError("Le brouillon Gemini ne contient pas de liste de scènes.")
    for index, scene in enumerate(draft["scenes"], start=1):
        scene["id"] = _slug_id(index)
        scene["review_approved"] = False
        scene["reviewer"] = None
        scene["reviewed_at"] = None
        if scene.get("claim_status") == "verified":
            scene["claim_status"] = "unconfirmed"
    draft["sources"] = sources
    draft["aspect_ratio"] = "16:9"
    draft["language"] = "fr"
    draft["release_approved"] = False
    draft["release_reviewer"] = None
    draft["release_approved_at"] = None

    try:
        project = DocumentaryProject.model_validate(draft)
    except Exception as exc:
        raise ScriptWriterError(f"Le storyboard généré ne respecte pas le schéma : {exc}") from exc

    total_seconds = sum(scene.duration_seconds for scene in project.scenes)
    if total_seconds < 600 or total_seconds > 900:
        raise ScriptWriterError(
            f"Durée storyboard incohérente : {total_seconds} secondes ; viser 600 à 900 secondes."
        )
    if len(project.scenes) < 40:
        raise ScriptWriterError("Storyboard trop court : au moins 40 scènes sont requises.")
    destination = Path(output_file)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(project.model_dump_json(indent=2), encoding="utf-8")
    return destination

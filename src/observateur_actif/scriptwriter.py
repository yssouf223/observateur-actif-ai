"""Brouillon de storyboard documentaire via Agnes ou Gemini en JSON."""

import json
import os
from pathlib import Path
import re

import requests

from observateur_actif.storyboard import DocumentaryProject


DEFAULT_MODEL = "agnes-2.5-flash"
AGNES_CHAT_URL = "https://apihub.agnes-ai.com/v1/chat/completions"
GEMINI_API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"


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
    model: str | None = None,
    topic_history_file: str | Path = "projects/topic_history.json",
) -> Path:
    """Créer un brouillon à partir d'au moins deux sources indépendantes.

    Le résultat reste toujours non approuvé : aucune publication ni génération
    vidéo ne peut être déclenchée avant revue humaine explicite.
    """
    forced_provider = os.getenv("SCRIPT_PROVIDER", "").strip().lower()
    gemini_key = (api_key or os.getenv("GEMINI_API_KEY", "")).strip()
    agnes_key = os.getenv("AGNES_API_KEY", "").strip()
    if model and model.startswith("gemini-"):
        provider = "gemini"
    elif model and model.startswith("agnes-"):
        provider = "agnes"
    elif forced_provider in {"agnes", "gemini"}:
        provider = forced_provider
    elif api_key or gemini_key:
        provider = "gemini"
    else:
        provider = "agnes"
    key = gemini_key if provider == "gemini" else agnes_key
    if not key:
        required = "GEMINI_API_KEY" if provider == "gemini" else "AGNES_API_KEY"
        raise ScriptWriterError(f"{required} absent.")
    selected_model = model or (DEFAULT_MODEL if provider == "agnes" else "gemini-3.8-flash")
    source_path = Path(source_documents_file)
    if not source_path.is_file():
        raise FileNotFoundError(f"Documents de recherche introuvables : {source_path}")
    try:
        documents = json.loads(source_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ScriptWriterError(f"JSON de recherche invalide : {exc}") from exc
    if not isinstance(documents, list):
        raise ScriptWriterError("Le fichier source doit contenir une liste de documents.")

    strong_topics = (
        "archaeolog", "archéolog", "excavat", "fouill", "ruins", "ruines",
        "ancient", "ancien", "civilisation", "civilization", "mystery", "mystère",
        "unexplained", "inexpliqué", "lost city", "cité perdue", "rock art",
        "art rupestre", "rupestre", "fossil", "fossile", "manuscript", "manuscrit",
        "temple", "grotte", "cave", "pyramid", "pyramide", "megalith", "mégalithe",
        "prehistor", "préhistoire", "kingdom", "royaume", "empire", "geoglyph",
        "géoglyphe", "historical", "histoire", "history", "pharaoh", "pharaon",
        "artefact", "artifact", "mummy", "momie", "stone circle", "cercle de pierres",
        "cave painting", "peinture rupestre", "mysterious", "mystérieux",
        "oral tradition", "tradition orale", "lost civilization", "civilisation perdue",
    )
    african_regions = (
        "africa", "african", "afrique", "sahara", "sahel", "mali", "niger",
        "nigeria", "ethiopia", "éthiopie", "egypt", "égypte", "sudan", "soudan",
        "somalia", "somalie", "kenya", "tanzania", "tanzanie", "ghana", "benin",
        "bénin", "togo", "guinea", "guinée", "senegal", "sénégal", "morocco",
        "maroc", "algeria", "algérie", "tunisia", "tunisie", "libya", "libye",
        "chad", "tchad", "cameroon", "cameroun", "congo", "rwanda", "uganda",
        "zimbabwe", "zambia", "botswana", "south africa", "afrique du sud",
        "mozambique", "madagascar", "mauritania", "mauritanie", "ivory coast",
        "côte d'ivoire", "burkina faso", "angola", "namibia", "namibie",
        "eritrea", "érythrée", "djibouti", "gabon", "liberia", "libéria",
    )
    off_topic = (
        "jihad", "jihadist", "djihad", "djihadiste", "terrorism", "terrorist",
        "terrorisme", "terroriste", "al-shabaab", "al-shabab", "jnim", "boko haram",
        "election", "elections", "élection", "élections", "football", "nutrition",
        "santé", "health", "ukraine",
    )

    def relevance(doc: dict) -> int:
        title = str(doc.get("title") or doc.get("lead_title") or "").casefold()
        body = str(doc.get("text", ""))[:7000].casefold()
        combined = title + " " + body
        topic_hits = sum(1 for keyword in strong_topics if keyword in combined)
        title_hits = sum(1 for keyword in strong_topics if keyword in title)
        region_hits = sum(1 for keyword in african_regions if keyword in combined)
        excluded_hits = sum(1 for keyword in off_topic if re.search(rf"\b{re.escape(keyword)}\b", combined))
        if topic_hits == 0 or region_hits == 0 or excluded_hits > 0:
            return 0
        return topic_hits * 3 + title_hits * 5 + region_hits * 2

    candidates = [
        doc for doc in documents
        if isinstance(doc, dict)
        and doc.get("fetch_status") == "success"
        and str(doc.get("text", "")).strip()
        and str(doc.get("url", "")).startswith(("https://", "http://"))
    ]
    if len(candidates) < 2:
        raise ScriptWriterError(
            "Au moins deux documents accessibles de deux éditeurs et domaines distincts sont requis."
        )
    usable = sorted(
        (doc for doc in candidates if relevance(doc) > 0),
        key=relevance,
        reverse=True,
    )[:6]
    if len(usable) < 2:
        raise ScriptWriterError(
            "Aucun sujet de mystère historique ou archéologique africain ne dispose "
            "d'au moins deux sources pertinentes. Aucun brouillon hors sujet ne sera créé."
        )
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
            "text": str(doc["text"])[:6000],
        })

    if len(sources) < 2:
        raise ScriptWriterError(
            "Au moins deux documents accessibles de deux éditeurs et domaines distincts sont requis."
        )

    history_path = Path(topic_history_file)
    topic_history = []
    if history_path.is_file():
        try:
            loaded_history = json.loads(history_path.read_text(encoding="utf-8"))
            if isinstance(loaded_history, list):
                topic_history = loaded_history[:100]
        except json.JSONDecodeError as exc:
            raise ScriptWriterError(f"Historique des sujets invalide : {exc}") from exc
    history_text = json.dumps(topic_history, ensure_ascii=False)
    source_bundle = json.dumps(source_texts, ensure_ascii=False)
    prompt = f"""
Tu es le rédacteur en chef et scénariste d'Observateur Actif, chaîne francophone
de documentaires d'enquête sur les mystères africains. Rédige un brouillon
documentaire sérieux, cinématographique, rigoureux et non sensationnaliste.

SUJET SOUHAITÉ : {topic or "Choisis le sujet le plus solide et le plus intéressant parmi les documents fournis."}

SUJETS DÉJÀ ABORDÉS OU EXCLUS (NE PAS RÉUTILISER LE MÊME ÉVÉNEMENT, LIEU OU HISTOIRE, MÊME AVEC UN AUTRE TITRE) :
{history_text}

RÈGLES IMPÉRATIVES :
- La chaîne traite exclusivement de mystères historiques réels, d'archéologie africaine, de civilisations anciennes, de lieux énigmatiques et de phénomènes inexpliqués documentés. Refuse l'actualité politique, le terrorisme, les conflits armés, les faits divers, la santé et le sport.
- Le sujet central doit être africain et historique/archéologique ; ne choisis pas une actualité de sécurité ou de propagande.
- Au moins deux éditeurs indépendants doivent documenter le MÊME sujet central. Utilise leurs source_ids dans les scènes correspondantes ; ne cite jamais une source sans rapport.
- Utilise exclusivement les informations présentes dans les documents fournis.
- N'invente aucun nom, date, lieu, citation, chiffre, témoignage ou événement.
- Ne prétends jamais qu'une affirmation est vérifiée : tous les statuts factuels doivent rester "unconfirmed", "hypothesis", "testimony", "oral_tradition" ou "legend".
- Une tradition orale, un récit spirituel ou une légende doit être explicitement présenté comme tel.
- Chaque scène factuelle doit référencer le ou les source_id qui soutiennent réellement son contenu.
- Si une information n'est pas documentée, ne l'ajoute pas comme fait. Signale les limites.
- Pas de dialogues fictifs, de citations reconstituées ni de scènes historiques présentées comme archives réelles.
- Voix off en français, masculine grave, calme, journalistique, sans emphase artificielle.
- Documentaire de 10 à 15 minutes, environ 1 300 à 1 700 mots de narration répartis sur 50 à 75 scènes.
- Chaque scène dure exactement 12 secondes : 50 scènes pour 10 minutes, 55 pour 11 minutes, jusqu'à 75 pour 15 minutes. Choisis un nombre de scènes cohérent avec la durée cible.
- Chaque scène doit avoir un prompt vidéo en anglais, concis (15 à 25 mots), pour un plan réellement animé, avec mouvement physique/caméra clairement décrit ; aucun diaporama, aucune image fixe, aucun texte incrusté.
- motion_description doit rester concise (8 à 15 mots) ; narration 25 à 35 mots par scène.
- Chaque scène doit durer exactement 12 secondes. Les scènes doivent donc prévoir des actions visuelles simples et cohérentes.
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
    if provider == "agnes":
        payload = {
            "model": selected_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.25,
            "max_tokens": 32000,
            "response_format": {"type": "json_object"},
        }
        endpoint = AGNES_CHAT_URL
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    else:
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.25,
                "maxOutputTokens": 32000,
            },
        }
        endpoint = f"{GEMINI_API_ROOT}/{selected_model}:generateContent"
        headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
    try:
        response = requests.post(
            endpoint,
            headers=headers,
            json=payload,
            timeout=300,
        )
        if not response.ok:
            detail = response.text[:1200]
            raise ScriptWriterError(f"{provider.title()} API HTTP {response.status_code}: {detail}")
        data = response.json()
        if provider == "agnes":
            text = data["choices"][0]["message"]["content"]
            if isinstance(text, list):
                text = "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in text)
        else:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
    except ScriptWriterError:
        raise
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
        raise ScriptWriterError(f"Réponse {provider.title()} absente ou illisible : {exc}") from exc

    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    first_object = cleaned.find("{")
    last_object = cleaned.rfind("}")
    if first_object >= 0 and last_object > first_object:
        cleaned = cleaned[first_object:last_object + 1]
    try:
        draft = json.loads(cleaned)
    except json.JSONDecodeError as original_error:
        try:
            from json_repair import repair_json
            repaired = repair_json(cleaned)
            draft = json.loads(repaired)
        except Exception as repair_error:
            raise ScriptWriterError(
                f"{provider.title()} n'a pas renvoyé un JSON exploitable : "
                f"{original_error}; réparation : {repair_error}"
            ) from repair_error

    if not isinstance(draft, dict) or not isinstance(draft.get("scenes"), list):
        raise ScriptWriterError(f"Le brouillon {provider.title()} ne contient pas de liste de scènes.")
    used_source_ids = {
        source_id
        for scene in draft["scenes"]
        if isinstance(scene, dict)
        for source_id in scene.get("source_ids", [])
    }
    if len(used_source_ids) < 2:
        raise ScriptWriterError(
            "Brouillon rejeté : au moins deux sources indépendantes doivent être "
            "réellement utilisées pour documenter le même sujet."
        )
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
    if any(scene.duration_seconds > 12 for scene in project.scenes):
        raise ScriptWriterError("Chaque scène doit durer au maximum 12 secondes pour correspondre au moteur vidéo.")
    target_seconds = project.target_duration_minutes * 60
    if total_seconds < 600 or total_seconds > 900 or not target_seconds * 0.9 <= total_seconds <= target_seconds * 1.1:
        raise ScriptWriterError(
            f"Durée storyboard incohérente : {total_seconds}s pour une cible de {target_seconds}s."
        )
    if len(project.scenes) < 40:
        raise ScriptWriterError("Storyboard trop court : au moins 40 scènes sont requises.")
    destination = Path(output_file)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(project.model_dump_json(indent=2), encoding="utf-8")
    return destination

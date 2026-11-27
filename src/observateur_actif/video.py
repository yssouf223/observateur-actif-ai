"""Client minimal pour l'API vidéo Agnes 2.5 Flash.

Aucun secret n'est stocké ici : la clé est lue depuis AGNES_API_KEY.
La génération est asynchrone : création, polling, puis téléchargement.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

BASE_URL = "https://apihub.agnes-ai.com"
MODEL = "agnes-video-2.5-flash"
CREATE_TIMEOUT = 60
DOWNLOAD_TIMEOUT = 120
QUEUE_RETRY_DELAYS = (60, 120)
MIN_CREATE_INTERVAL_SECONDS = 60.0
_LAST_CREATE_MONOTONIC: float | None = None


class AgnesError(RuntimeError):
    """Erreur lisible renvoyée par le fournisseur vidéo."""


def _api_error(response: requests.Response) -> AgnesError:
    try:
        payload = response.json()
        message = payload.get("message") or payload.get("error") or payload
    except ValueError:
        message = response.text[:500]
    return AgnesError(f"Agnes API HTTP {response.status_code}: {message}")


def _video_url(payload: dict) -> str | None:
    candidate = payload.get("video_url") or payload.get("url")
    if not candidate and isinstance(payload.get("metadata"), dict):
        candidate = payload["metadata"].get("url")
    if isinstance(candidate, str) and candidate.startswith("https://"):
        return candidate
    return None


def generate_video(
    prompt: str,
    output_path: str | Path,
    *,
    seconds: int = 5,
    aspect_ratio: str = "16:9",
    api_key: str | None = None,
    poll_interval: float = 10,
    timeout_seconds: int = 1200,
) -> Path:
    """Générer un clip 720p et l'enregistrer localement.

    Le client espace localement les demandes d'au moins une minute et réessaie
    une file saturée après 60 puis 120 secondes. Ce délai ne garantit pas la
    gratuité et ne constitue pas une limite officielle confirmée du fournisseur.
    """
    key = (api_key or os.getenv("AGNES_API_KEY", "")).strip()
    if not key:
        raise AgnesError(
            "Clé manquante. Définis AGNES_API_KEY dans ton fichier .env."
        )
    if not prompt.strip():
        raise AgnesError("Le prompt vidéo ne peut pas être vide.")
    if not 4 <= seconds <= 12:
        raise AgnesError("La durée doit être comprise entre 4 et 12 secondes.")
    if aspect_ratio != "16:9":
        raise AgnesError("Cette première version accepte uniquement le format 16:9.")

    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    body = {
        "model": MODEL,
        "prompt": prompt.strip(),
        "mode": "text",
        "seconds": str(seconds),
        "size": "720P",
        "aspect_ratio": aspect_ratio,
        "n": 1,
    }

    response = None
    global _LAST_CREATE_MONOTONIC
    for attempt in range(len(QUEUE_RETRY_DELAYS) + 1):
        if _LAST_CREATE_MONOTONIC is not None:
            wait = MIN_CREATE_INTERVAL_SECONDS - (
                time.monotonic() - _LAST_CREATE_MONOTONIC
            )
            if wait > 0:
                print(f"Protection locale : attente de {wait:.1f}s avant la prochaine demande vidéo.")
                time.sleep(wait)
        _LAST_CREATE_MONOTONIC = time.monotonic()
        try:
            response = requests.post(
                f"{BASE_URL}/v1/videos",
                headers=headers,
                json=body,
                timeout=CREATE_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise AgnesError(
                f"Impossible de contacter Agnes pour créer la vidéo : {exc}"
            ) from exc

        if response.ok:
            break

        try:
            error_payload = response.json()
            error_message = str(
                error_payload.get("message") or error_payload.get("error") or ""
            ).lower()
        except (ValueError, AttributeError):
            error_message = ""

        queue_is_full = response.status_code == 503 and "queue" in error_message and "full" in error_message
        if not queue_is_full or attempt >= len(QUEUE_RETRY_DELAYS):
            raise _api_error(response)

        delay = QUEUE_RETRY_DELAYS[attempt]
        print(
            f"File vidéo Agnes saturée ; nouvelle tentative "
            f"{attempt + 2}/{len(QUEUE_RETRY_DELAYS) + 1} dans {delay} secondes..."
        )
        time.sleep(delay)

    if response is None or not response.ok:
        raise AgnesError("Agnes n'a pas accepté la demande de génération.")

    try:
        created = response.json()
    except ValueError as exc:
        raise AgnesError("Agnes a renvoyé une réponse de création illisible.") from exc

    video_id = created.get("video_id") or created.get("task_id") or created.get("id")
    if not video_id:
        raise AgnesError(f"Réponse Agnes sans identifiant de vidéo : {created}")

    deadline = time.monotonic() + timeout_seconds
    result_url = _video_url(created)
    while not result_url and time.monotonic() < deadline:
        try:
            poll = requests.get(
                f"{BASE_URL}/agnesapi",
                headers={"Authorization": f"Bearer {key}"},
                params={"video_id": video_id, "model_name": MODEL},
                timeout=30,
            )
        except requests.RequestException:
            time.sleep(poll_interval)
            continue

        if poll.status_code in (429, 500, 502, 503, 504):
            time.sleep(poll_interval)
            continue
        if not poll.ok:
            raise _api_error(poll)
        try:
            status_data = poll.json()
        except ValueError as exc:
            raise AgnesError("Réponse de suivi Agnes illisible.") from exc

        status = str(status_data.get("status", "")).lower()
        if status == "failed":
            reason = status_data.get("error") or status_data.get("message") or "raison inconnue"
            raise AgnesError(f"La génération vidéo a échoué : {reason}")
        if status == "completed":
            result_url = _video_url(status_data)
            if not result_url:
                raise AgnesError("Agnes indique 'completed' mais ne fournit pas d'URL vidéo.")
        else:
            time.sleep(poll_interval)

    if not result_url:
        raise AgnesError(
            f"Délai dépassé après {timeout_seconds} secondes. "
            f"Identifiant de tâche : {video_id}. Tu peux réessayer le suivi plus tard."
        )

    parsed = urlparse(result_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise AgnesError("Agnes a renvoyé une URL de téléchargement non sécurisée.")

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with requests.get(result_url, stream=True, timeout=DOWNLOAD_TIMEOUT) as download:
            if not download.ok:
                raise _api_error(download)
            with destination.open("wb") as file:
                for chunk in download.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        file.write(chunk)
    except requests.RequestException as exc:
        destination.unlink(missing_ok=True)
        raise AgnesError(f"Échec du téléchargement de la vidéo : {exc}") from exc

    if not destination.exists() or destination.stat().st_size == 0:
        destination.unlink(missing_ok=True)
        raise AgnesError("Le fichier vidéo téléchargé est vide.")
    return destination

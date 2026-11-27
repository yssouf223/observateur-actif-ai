"""Publication YouTube sécurisée avec mise en ligne programmée."""

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path

from observateur_actif.quality import inspect_video


class YouTubePublishError(RuntimeError):
    """Erreur d'authentification ou de publication YouTube."""


def next_saturday_1600_utc(now: datetime | None = None) -> datetime:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("La date doit inclure un fuseau horaire.")
    current = current.astimezone(timezone.utc)
    days = (5 - current.weekday()) % 7
    target = (current + timedelta(days=days)).replace(
        hour=16, minute=0, second=0, microsecond=0
    )
    if target <= current:
        target += timedelta(days=7)
    return target


def publish_video(
    video_file: str | Path,
    *,
    title: str,
    description: str,
    tags: list[str],
    publish_at: datetime,
    expected_channel_id: str | None = None,
) -> dict:
    """Téléverser le MP4 et le programmer en privé pour publication à l'heure UTC."""
    path = Path(video_file)
    inspect_video(path)
    if publish_at.tzinfo is None:
        raise YouTubePublishError("publish_at doit être une date avec fuseau horaire.")
    publish_at = publish_at.astimezone(timezone.utc)
    if publish_at <= datetime.now(timezone.utc):
        raise YouTubePublishError("La date de publication doit être dans le futur.")
    if not title.strip() or len(title) > 100:
        raise YouTubePublishError("Le titre YouTube doit contenir entre 1 et 100 caractères.")

    client_id = os.getenv("YOUTUBE_CLIENT_ID", "").strip()
    client_secret = os.getenv("YOUTUBE_CLIENT_SECRET", "").strip()
    refresh_token = os.getenv("YOUTUBE_REFRESH_TOKEN", "").strip()
    channel_id = (expected_channel_id or os.getenv("YOUTUBE_CHANNEL_ID", "")).strip()
    missing = [
        name for name, value in (
            ("YOUTUBE_CLIENT_ID", client_id),
            ("YOUTUBE_CLIENT_SECRET", client_secret),
            ("YOUTUBE_REFRESH_TOKEN", refresh_token),
            ("YOUTUBE_CHANNEL_ID", channel_id),
        ) if not value
    ]
    if missing:
        raise YouTubePublishError(
            "Secrets YouTube manquants : " + ", ".join(missing)
        )

    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError as exc:
        raise YouTubePublishError(
            "Dépendances YouTube absentes. Installe le supplément [youtube]."
        ) from exc

    credentials = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"],
    )
    try:
        youtube = build("youtube", "v3", credentials=credentials, cache_discovery=False)
        channel_response = youtube.channels().list(part="id", mine=True).execute()
        channels = channel_response.get("items", [])
        if not channels or channels[0].get("id") != channel_id:
            raise YouTubePublishError(
                "Le compte OAuth connecté ne correspond pas à YOUTUBE_CHANNEL_ID."
            )

        body = {
            "snippet": {
                "title": title.strip(),
                "description": description.strip(),
                "tags": tags[:30],
                "categoryId": "27",
                "defaultLanguage": "fr",
                "defaultAudioLanguage": "fr",
            },
            "status": {
                "privacyStatus": "private",
                "publishAt": publish_at.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                "selfDeclaredMadeForKids": False,
            },
        }
        upload = MediaFileUpload(str(path), mimetype="video/mp4",
                                 chunksize=8 * 1024 * 1024, resumable=True)
        request = youtube.videos().insert(
            part="snippet,status", body=body, media_body=upload
        )
        response = None
        while response is None:
            _, response = request.next_chunk()
    except YouTubePublishError:
        raise
    except Exception as exc:
        raise YouTubePublishError(f"Échec de l'envoi ou de la programmation YouTube : {exc}") from exc

    video_id = response.get("id") if response else None
    if not video_id:
        raise YouTubePublishError("YouTube n'a pas renvoyé d'identifiant vidéo.")
    return {
        "video_id": video_id,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "channel_id": channel_id,
        "publish_at": publish_at.isoformat(),
        "privacy_status": "private_until_scheduled_publication",
    }

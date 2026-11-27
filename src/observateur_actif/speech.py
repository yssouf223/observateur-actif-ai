"""Synthèse vocale MP3 avec le service en ligne Edge-TTS."""

import asyncio
from pathlib import Path

import edge_tts

from observateur_actif.storyboard import DocumentaryProject

DEFAULT_VOICE = "fr-FR-HenriNeural"


class SpeechError(RuntimeError):
    """Erreur de génération de la narration audio."""


def build_speech_text(project: DocumentaryProject) -> str:
    """Assembler uniquement les répliques, dans l'ordre des scènes."""
    text = " ".join(scene.narration.strip() for scene in project.scenes)
    if not text.strip():
        raise SpeechError("Le projet ne contient aucun texte de narration.")
    return text


async def _save_audio(text: str, destination: Path, voice: str,
                      rate: str, pitch: str) -> None:
    communicator = edge_tts.Communicate(
        text, voice=voice, rate=rate, pitch=pitch
    )
    await communicator.save(str(destination))


def generate_audio(project: DocumentaryProject, output_file: str | Path,
                   voice: str = DEFAULT_VOICE, rate: str = "-8%",
                   pitch: str = "-8Hz") -> Path:
    """Générer un MP3 via Edge-TTS ; nécessite Internet."""
    destination = Path(output_file)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        asyncio.run(_save_audio(
            build_speech_text(project), destination, voice, rate, pitch
        ))
    except SpeechError:
        raise
    except Exception as exc:
        raise SpeechError(f"Edge-TTS n'a pas pu générer l'audio : {exc}") from exc
    if not destination.is_file() or destination.stat().st_size == 0:
        raise SpeechError("Edge-TTS n'a créé aucun fichier audio exploitable.")
    return destination

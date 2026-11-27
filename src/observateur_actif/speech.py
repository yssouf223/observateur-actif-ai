"""Synthèse vocale MP3 et sous-titres alignés sur les repères Edge-TTS."""

import asyncio
from pathlib import Path

import edge_tts

from observateur_actif.storyboard import DocumentaryProject

DEFAULT_VOICE = "fr-FR-HenriNeural"
TICKS_PER_MILLISECOND = 10_000


class SpeechError(RuntimeError):
    """Erreur de génération de la narration audio."""


def build_speech_text(project: DocumentaryProject) -> str:
    """Assembler uniquement les répliques, dans l'ordre des scènes."""
    text = " ".join(scene.narration.strip() for scene in project.scenes)
    if not text.strip():
        raise SpeechError("Le projet ne contient aucun texte de narration.")
    return text


def _timestamp(milliseconds: int) -> str:
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"


def _word_boundaries_to_srt(boundaries: list[tuple[int, int, str]]) -> str:
    """Regrouper les repères mot à mot en sous-titres courts et lisibles."""
    if not boundaries:
        raise SpeechError("Edge-TTS n'a fourni aucun repère temporel de mots.")
    groups: list[list[tuple[int, int, str]]] = []
    current: list[tuple[int, int, str]] = []
    current_text = ""
    for item in boundaries:
        start, duration, word = item
        candidate = f"{current_text} {word}".strip()
        current_end = current[-1][0] + current[-1][1] if current else start
        would_be_long = len(candidate) > 42
        would_be_slow = bool(current) and start - current[0][0] > 4_500 * TICKS_PER_MILLISECOND
        sentence_end = word.rstrip().endswith((".", "?", "!", "…"))
        if current and (would_be_long or would_be_slow):
            groups.append(current)
            current = []
            current_text = ""
        current.append((start, duration, word))
        current_text = f"{current_text} {word}".strip()
        if sentence_end:
            groups.append(current)
            current = []
            current_text = ""
    if current:
        groups.append(current)

    entries: list[str] = []
    for index, group in enumerate(groups, start=1):
        start_ms = max(0, group[0][0] // TICKS_PER_MILLISECOND)
        end_ticks = group[-1][0] + max(group[-1][1], 1)
        end_ms = max(start_ms + 1, end_ticks // TICKS_PER_MILLISECOND)
        caption = " ".join(item[2] for item in group).strip()
        entries.extend([
            str(index),
            f"{_timestamp(start_ms)} --> {_timestamp(end_ms)}",
            caption,
            "",
        ])
    return "\n".join(entries)


async def _stream_audio_and_timing(
    text: str, audio_path: Path, voice: str, rate: str, pitch: str
) -> str:
    communicator = edge_tts.Communicate(
        text, voice=voice, rate=rate, pitch=pitch, boundary="WordBoundary"
    )
    boundaries: list[tuple[int, int, str]] = []
    with audio_path.open("wb") as audio_file:
        async for event in communicator.stream():
            if event.get("type") == "audio":
                audio_file.write(event.get("data", b""))
            elif event.get("type") == "WordBoundary":
                boundaries.append((
                    int(event.get("offset", 0)),
                    int(event.get("duration", 0)),
                    str(event.get("text", "")),
                ))
    return _word_boundaries_to_srt(boundaries)


def generate_audio_with_subtitles(
    project: DocumentaryProject,
    output_file: str | Path,
    subtitles_file: str | Path,
    voice: str = DEFAULT_VOICE,
    rate: str = "-8%",
    pitch: str = "-8Hz",
) -> tuple[Path, Path]:
    """Générer le MP3 et le SRT à partir des vrais repères temporels Edge-TTS."""
    audio_path = Path(output_file)
    srt_path = Path(subtitles_file)
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    srt_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        srt_content = asyncio.run(_stream_audio_and_timing(
            build_speech_text(project), audio_path, voice, rate, pitch
        ))
        if not audio_path.is_file() or audio_path.stat().st_size == 0:
            raise SpeechError("Edge-TTS n'a créé aucun fichier audio exploitable.")
        srt_path.write_text(srt_content, encoding="utf-8")
    except SpeechError:
        audio_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        audio_path.unlink(missing_ok=True)
        raise SpeechError(f"Edge-TTS n'a pas pu générer l'audio/SRT : {exc}") from exc
    return audio_path, srt_path


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

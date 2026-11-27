"""Préparation des textes de voix off et des sous-titres SRT."""

from pathlib import Path

from observateur_actif.storyboard import DocumentaryProject


def _timestamp(milliseconds: int) -> str:
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"


def build_narration_text(project: DocumentaryProject) -> str:
    """Assembler la narration dans l'ordre des scènes, sans ajouter de faits."""
    sections = [
        f"DOCUMENTAIRE : {project.title}",
        "VOIX : française masculine, grave, posée et naturelle",
        "DIRECTION : diction claire, rythme documentaire, pauses entre les scènes",
        "",
    ]
    for index, scene in enumerate(project.scenes, start=1):
        sections.extend([
            f"SCÈNE {index} — {scene.duration_seconds} secondes",
            scene.narration.strip(),
            "",
        ])
    return "\n".join(sections).rstrip() + "\n"


def build_srt(project: DocumentaryProject) -> str:
    """Créer des sous-titres scène par scène à partir des durées du storyboard."""
    entries: list[str] = []
    cursor_ms = 0
    for index, scene in enumerate(project.scenes, start=1):
        end_ms = cursor_ms + scene.duration_seconds * 1_000
        entries.extend([
            str(index),
            f"{_timestamp(cursor_ms)} --> {_timestamp(end_ms)}",
            scene.narration.strip(),
            "",
        ])
        cursor_ms = end_ms
    return "\n".join(entries)


def export_narration(project: DocumentaryProject, text_path: str | Path,
                     srt_path: str | Path) -> tuple[Path, Path]:
    """Écrire les fichiers de voix off et de sous-titres."""
    text_destination = Path(text_path)
    srt_destination = Path(srt_path)
    text_destination.parent.mkdir(parents=True, exist_ok=True)
    srt_destination.parent.mkdir(parents=True, exist_ok=True)
    text_destination.write_text(build_narration_text(project), encoding="utf-8")
    srt_destination.write_text(build_srt(project), encoding="utf-8")
    return text_destination, srt_destination

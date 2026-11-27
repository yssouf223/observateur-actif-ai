"""Assemblage local des scènes vidéo, de la narration et des sous-titres."""

from pathlib import Path
import shutil
import subprocess

from observateur_actif.storyboard import DocumentaryProject


class MontageError(RuntimeError):
    """Erreur pendant l'assemblage du documentaire."""


def assemble_documentary(
    project: DocumentaryProject,
    narration_file: str | Path,
    output_file: str | Path,
    *,
    subtitles_file: str | Path | None = None,
    music_file: str | Path | None = None,
    ffmpeg: str = "ffmpeg",
) -> Path:
    """Assembler les clips validés en MP4 16:9 720p avec voix off.

    Les sous-titres sont intégrés comme piste sélectionnable (pas incrustés).
    Une musique facultative doit être fournie par l'utilisateur avec ses droits.
    """
    executable = shutil.which(ffmpeg)
    if not executable:
        raise MontageError("FFmpeg est introuvable. Installe FFmpeg puis relance la commande.")

    clips: list[Path] = []
    for scene in project.scenes:
        if not scene.generated_video_path:
            raise MontageError(
                f"La scène {scene.id} n'a pas de vidéo générée (generated_video_path)."
            )
        clip = Path(scene.generated_video_path)
        if not clip.is_file() or clip.stat().st_size == 0:
            raise MontageError(f"Clip vidéo absent ou vide pour la scène {scene.id} : {clip}")
        clips.append(clip)

    narration = Path(narration_file)
    if not narration.is_file() or narration.stat().st_size == 0:
        raise MontageError(f"Fichier de narration absent ou vide : {narration}")

    subtitles = Path(subtitles_file) if subtitles_file else None
    if subtitles and (not subtitles.is_file() or subtitles.stat().st_size == 0):
        raise MontageError(f"Fichier SRT absent ou vide : {subtitles}")

    music = Path(music_file) if music_file else None
    if music and (not music.is_file() or music.stat().st_size == 0):
        raise MontageError(f"Fichier musical absent ou vide : {music}")

    destination = Path(output_file)
    destination.parent.mkdir(parents=True, exist_ok=True)

    command = [executable, "-y"]
    for clip in clips:
        command.extend(["-i", str(clip)])
    narration_index = len(clips)
    command.extend(["-i", str(narration)])
    music_index = None
    if music:
        music_index = narration_index + 1
        command.extend(["-stream_loop", "-1", "-i", str(music)])
    subtitles_index = None
    if subtitles:
        subtitles_index = len(clips) + 1 + (1 if music else 0)
        command.extend(["-i", str(subtitles)])

    filters: list[str] = []
    labels: list[str] = []
    for index in range(len(clips)):
        label = f"v{index}"
        filters.append(
            f"[{index}:v:0]scale=1280:720:force_original_aspect_ratio=decrease,"
            f"pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=25,"
            f"format=yuv420p[{label}]"
        )
        labels.append(f"[{label}]")
    filters.append(
        "".join(labels) + f"concat=n={len(clips)}:v=1:a=0[vout]"
    )

    voice_label = f"{narration_index}:a:0"
    if music_index is not None:
        filters.append(f"[{music_index}:a:0]volume=0.12[music]")
        filters.append(
            f"[{voice_label}][music]amix=inputs=2:duration=first:"
            "dropout_transition=2[mixed]"
        )
        filters.append("[mixed]loudnorm=I=-16:TP=-1.5:LRA=11[aout]")
    else:
        filters.append(f"[{voice_label}]loudnorm=I=-16:TP=-1.5:LRA=11[aout]")

    command.extend([
        "-filter_complex", ";".join(filters),
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", "-shortest",
    ])
    if subtitles_index is not None:
        command.extend(["-map", f"{subtitles_index}:0", "-c:s", "mov_text"])
    else:
        command.append("-sn")
    command.append(str(destination))

    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        destination.unlink(missing_ok=True)
        details = (exc.stderr or exc.stdout or str(exc))[-2000:]
        raise MontageError(f"FFmpeg n'a pas pu assembler le documentaire : {details}") from exc
    except OSError as exc:
        destination.unlink(missing_ok=True)
        raise MontageError(f"Impossible de lancer FFmpeg : {exc}") from exc

    if not destination.is_file() or destination.stat().st_size == 0:
        destination.unlink(missing_ok=True)
        raise MontageError("FFmpeg n'a pas produit de fichier MP4 exploitable.")
    return destination

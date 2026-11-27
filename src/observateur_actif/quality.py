"""Contrôles techniques du MP4 final avec ffprobe."""

import json
import shutil
import subprocess
from pathlib import Path


class QualityError(RuntimeError):
    """Le fichier final ne satisfait pas les contrôles techniques."""


def inspect_video(video_file: str | Path, *, ffprobe: str = "ffprobe") -> dict:
    executable = shutil.which(ffprobe)
    if not executable:
        raise QualityError("ffprobe est introuvable ; installe FFmpeg complet.")
    path = Path(video_file)
    if not path.is_file() or path.stat().st_size == 0:
        raise QualityError(f"Vidéo finale absente ou vide : {path}")
    try:
        result = subprocess.run(
            [executable, "-v", "error", "-show_streams", "-show_format",
             "-of", "json", str(path)],
            check=True, capture_output=True, text=True,
        )
        data = json.loads(result.stdout)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        raise QualityError(f"Impossible d'analyser le MP4 : {exc}") from exc

    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    subtitles = [s for s in streams if s.get("codec_type") == "subtitle"]
    if not video:
        raise QualityError("Aucun flux vidéo détecté.")
    if not audio:
        raise QualityError("Aucun flux audio détecté : la narration est absente.")
    if not subtitles:
        raise QualityError("Aucune piste de sous-titres détectée dans le MP4 final.")
    width, height = video.get("width"), video.get("height")
    if width != 1280 or height != 720:
        raise QualityError(
            f"Résolution inattendue : {width}x{height}; attendu 1280x720."
        )
    duration = float(data.get("format", {}).get("duration", 0) or 0)
    if duration <= 0:
        raise QualityError("Durée du fichier MP4 invalide.")
    report = {
        "status": "technical_checks_passed",
        "file": str(path),
        "size_bytes": path.stat().st_size,
        "duration_seconds": round(duration, 3),
        "width": width,
        "height": height,
        "video_codec": video.get("codec_name"),
        "audio_codec": audio.get("codec_name"),
        "audio_present": True,
        "subtitle_stream_present": bool(subtitles),
        "subtitle_codec": subtitles[0].get("codec_name") if subtitles else None,
    }
    if video.get("codec_name") != "h264":
        raise QualityError(f"Codec vidéo inattendu : {video.get('codec_name')}; attendu h264.")
    if audio.get("codec_name") != "aac":
        raise QualityError(f"Codec audio inattendu : {audio.get('codec_name')}; attendu aac.")
    return report


def write_quality_report(video_file: str | Path, report_file: str | Path) -> Path:
    report = inspect_video(video_file)
    destination = Path(report_file)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    return destination

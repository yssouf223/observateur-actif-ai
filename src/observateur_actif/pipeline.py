"""Orchestration d'une production documentaire complète à partir d'un projet validé."""

import json
from pathlib import Path

from observateur_actif.montage import assemble_documentary
from observateur_actif.quality import write_quality_report
from observateur_actif.speech import generate_audio_with_subtitles
from observateur_actif.storyboard import DocumentaryProject
from observateur_actif.video import generate_video


class ProductionError(RuntimeError):
    """Production arrêtée par un contrôle de sécurité ou un fournisseur."""


def _save_project(project: DocumentaryProject, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(project.model_dump_json(indent=2), encoding="utf-8")


def produce_project(
    project: DocumentaryProject,
    project_file: str | Path,
    output_dir: str | Path,
    *,
    api_key: str,
    force_video: bool = False,
) -> dict[str, Path]:
    """Générer les scènes, la narration horodatée, le MP4 et le rapport.

    Le pipeline exige une approbation éditoriale humaine explicite de chaque
    scène. Il ne transforme jamais une hypothèse ou une légende en fait établi.
    """
    if not api_key.strip():
        raise ProductionError("Clé Agnes absente : génération vidéo impossible.")
    if any(scene.duration_seconds < 4 or scene.duration_seconds > 12 for scene in project.scenes):
        raise ProductionError("Chaque scène doit durer entre 4 et 12 secondes pour le fournisseur vidéo.")
    planned_seconds = sum(scene.duration_seconds for scene in project.scenes)
    target_seconds = project.target_duration_minutes * 60
    if not target_seconds * 0.9 <= planned_seconds <= target_seconds * 1.1:
        raise ProductionError(f"Durée storyboard incohérente : {planned_seconds}s pour une cible de {target_seconds}s.")
    unreviewed = [
        scene.id for scene in project.scenes
        if not scene.review_approved or not scene.reviewer or not scene.reviewed_at
    ]
    if unreviewed:
        raise ProductionError(
            "Arrêt éditorial : scènes non approuvées par un réviseur identifié : "
            + ", ".join(unreviewed)
        )

    root = Path(output_dir)
    scenes_dir = root / "scenes"
    scenes_dir.mkdir(parents=True, exist_ok=True)
    project_path = Path(project_file)
    generated: list[Path] = []

    for scene in project.scenes:
        clip_path = scenes_dir / f"{scene.id}.mp4"
        existing = Path(scene.generated_video_path) if scene.generated_video_path else None
        if not force_video and existing and existing.is_file() and existing.stat().st_size > 0:
            clip_path = existing
        else:
            generate_video(
                scene.video_prompt.strip() + " " + scene.motion_description.strip(),
                clip_path,
                seconds=scene.duration_seconds,
                aspect_ratio=project.aspect_ratio,
                api_key=api_key,
            )
        scene.generated_video_path = str(clip_path)
        generated.append(clip_path)
        _save_project(project, project_path)

    narration_path = root / "narration.mp3"
    subtitles_path = root / "narration.srt"
    generate_audio_with_subtitles(
        project, narration_path, subtitles_path
    )
    final_path = root / "documentary.mp4"
    assemble_documentary(
        project, narration_path, final_path, subtitles_file=subtitles_path
    )

    quality_path = root / "quality_report.json"
    write_quality_report(final_path, quality_path)
    report_path = root / "production_report.json"
    report = {
        "status": "assembled_pending_human_playback",
        "title": project.title,
        "scene_count": len(project.scenes),
        "video_resolution": "1280x720",
        "aspect_ratio": project.aspect_ratio,
        "clips": [str(path) for path in generated],
        "narration": str(narration_path),
        "subtitles": str(subtitles_path),
        "video": str(final_path),
        "editorial_approval": "human_review_recorded",
        "quality_control": "ffprobe_passed_human_playback_required",
        "quality_report": str(quality_path),
        "youtube_publication": "not_published",
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "video": final_path,
        "narration": narration_path,
        "subtitles": subtitles_path,
        "report": report_path,
    }

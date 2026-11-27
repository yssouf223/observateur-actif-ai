"""Export d'un dossier éditorial lisible pour revue humaine du storyboard."""

from pathlib import Path

from observateur_actif.storyboard import DocumentaryProject


def export_project_review(project: DocumentaryProject, output_file: str | Path) -> Path:
    """Exporter le script, les statuts et les sources sans approuver le projet."""
    sources = {source.id: source for source in project.sources}
    lines = [
        f"# Revue éditoriale — {project.title}",
        "",
        f"- Durée cible : {project.target_duration_minutes} minutes",
        f"- Scènes : {len(project.scenes)}",
        f"- Durée storyboard : {sum(scene.duration_seconds for scene in project.scenes)} secondes",
        f"- Approbation de publication : {'OUI' if project.release_approved else 'NON'}",
        "",
        "## Sources à contrôler",
        "",
    ]
    for source in project.sources:
        lines.extend([
            f"- **{source.publisher} — {source.title}**",
            f"  - URL : {source.url}",
            f"  - Collectée le : {source.accessed_at}",
            f"  - Note : {source.reliability_note}",
        ])
    lines.extend(["", "## Scènes", ""])
    for scene in project.scenes:
        lines.extend([
            f"### {scene.id}",
            f"- Durée : {scene.duration_seconds} s",
            f"- Statut éditorial : {scene.claim_status.value}",
            f"- Approuvée : {'OUI' if scene.review_approved else 'NON'}",
            f"- Réviseur : {scene.reviewer or 'aucun'}",
            f"- Sources : {', '.join(scene.source_ids) if scene.source_ids else 'aucune source associée'}",
            "",
            "**Narration**",
            "",
            scene.narration,
            "",
            "**Prompt vidéo**",
            "",
            scene.video_prompt,
            "",
            "**Mouvement**",
            "",
            scene.motion_description,
            "",
        ])
        for source_id in scene.source_ids:
            source = sources[source_id]
            lines.append(f"Source liée : [{source.title}]({source.url}) — {source.publisher}")
            lines.append("")
    lines.extend([
        "## Décision éditoriale",
        "",
        "Ne pas publier avant vérification des documents originaux, recoupement des affirmations, "
        "contrôle des images et validation humaine explicite de chaque scène et du projet.",
        "",
    ])
    destination = Path(output_file)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(lines), encoding="utf-8")
    return destination

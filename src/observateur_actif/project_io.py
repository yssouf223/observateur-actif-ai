"""Chargement et validation des projets documentaires JSON."""
from pathlib import Path
from pydantic import ValidationError
from observateur_actif.storyboard import DocumentaryProject

def load_project(path: str | Path) -> DocumentaryProject:
    """Charger un projet JSON et appliquer les règles de validation."""
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"Fichier projet introuvable : {source}")
    try:
        return DocumentaryProject.model_validate_json(source.read_text(encoding="utf-8"))
    except (ValidationError, ValueError) as exc:
        raise ValueError(f"Projet documentaire invalide : {exc}") from exc

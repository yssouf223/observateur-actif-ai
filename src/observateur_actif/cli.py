"""Commandes de diagnostic du projet."""

import shutil
import sys

import typer
from rich.console import Console
from rich.table import Table

from observateur_actif import __version__
from observateur_actif.config import Settings
from observateur_actif.video import AgnesError, generate_video

app = typer.Typer(help="Outils de préparation d'Observateur Actif AI.")
console = Console()


@app.command()
def version() -> None:
    """Afficher la version."""
    console.print(f"Observateur Actif AI [bold]{__version__}[/bold]")


@app.command()
def doctor() -> None:
    """Vérifier les prérequis locaux et la configuration."""
    table = Table(title="Diagnostic Observateur Actif AI")
    table.add_column("Contrôle")
    table.add_column("Résultat")
    table.add_column("Détail")

    table.add_row("Python", "OK" if sys.version_info >= (3, 11) else "À METTRE À JOUR",
                  sys.version.split()[0])
    ffmpeg = shutil.which("ffmpeg")
    table.add_row("FFmpeg", "OK" if ffmpeg else "MANQUANT",
                  ffmpeg or "Installer FFmpeg pour le montage vidéo")

    try:
        settings = Settings.load()
        settings.projects_dir.mkdir(parents=True, exist_ok=True)
        settings.output_dir.mkdir(parents=True, exist_ok=True)
        table.add_row("Configuration", "OK", f"Environnement : {settings.app_env}")
        table.add_row("Fournisseur vidéo", "DÉSACTIVÉ" if settings.video_provider == "disabled" else "CONFIGURÉ",
                      settings.video_provider)
        if settings.video_provider == "agnes":
            table.add_row("Clé Agnes", "PRÉSENTE", "Valeur masquée")
    except (ValueError, OSError) as exc:
        table.add_row("Configuration", "ERREUR", str(exc))

    console.print(table)
    console.print(
        "\n[dim]Ce diagnostic ne lance aucun appel externe et ne consomme aucun crédit vidéo.[/dim]"
    )


@app.command("video-test")
def video_test(
    prompt: str = typer.Option(..., "--prompt", help="Description de la scène animée."),
    seconds: int = typer.Option(5, "--seconds", min=4, max=12, help="Durée du clip (4 à 12 secondes)."),
) -> None:
    """Générer un clip de test Agnes en 720p, format 16:9."""
    try:
        settings = Settings.load()
        if settings.video_provider != "agnes" or not settings.agnes_api_key:
            raise AgnesError(
                "Configure .env avec VIDEO_PROVIDER=agnes et AGNES_API_KEY=ta_cle."
            )
        destination = settings.output_dir / "agnes_test.mp4"
        console.print("Envoi du prompt à Agnes ; la génération peut prendre plusieurs minutes…")
        result = generate_video(
            prompt,
            destination,
            seconds=seconds,
            aspect_ratio="16:9",
            api_key=settings.agnes_api_key,
        )
        console.print(f"[green]Clip téléchargé : {result}[/green]")
    except (AgnesError, ValueError) as exc:
        console.print(f"[red]Erreur : {exc}[/red]")
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    app()

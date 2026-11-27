"""Commandes de diagnostic du projet."""

import json
import shutil
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from observateur_actif import __version__
from observateur_actif.config import Settings
from observateur_actif.video import AgnesError, generate_video
from observateur_actif.project_io import load_project
from observateur_actif.research import ResearchError, collect_feeds, load_feed_config, save_leads
from observateur_actif.claim_review import load_claim_registry
from observateur_actif.source_fetcher import SourceFetchError, fetch_source, fetch_leads
from observateur_actif.claim_extractor import extract_claim_candidates
from observateur_actif.review_queue import write_review_queue
from observateur_actif.narration import export_narration
from observateur_actif.speech import SpeechError, generate_audio, generate_audio_with_subtitles

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
    console.print("\n[dim]Ce diagnostic ne lance aucun appel externe et ne consomme aucun crédit vidéo.[/dim]")


@app.command("research-rss")
def research_rss(
    feeds_file: str = typer.Option("config/research_feeds.json", "--feeds", help="Fichier JSON des flux RSS/Atom."),
    output_file: str = typer.Option("projects/research_leads.json", "--output", help="Fichier JSON de sortie."),
) -> None:
    """Collecter des pistes depuis des flux RSS/Atom (non vérifiées)."""
    try:
        leads = collect_feeds(load_feed_config(feeds_file))
        destination = save_leads(leads, output_file)
        console.print(f"[green]{len(leads)} piste(s) collectée(s).[/green]")
        console.print(f"Résultat : {destination}")
        console.print("[yellow]Aucune piste n'est considérée comme un fait vérifié.[/yellow]")
    except (ResearchError, FileNotFoundError, OSError) as exc:
        console.print(f"[red]Erreur de recherche : {exc}[/red]")
        raise typer.Exit(code=1) from exc


@app.command("fetch-source")
def fetch_source_command(
    url: str = typer.Argument(..., help="URL publique de l'article original."),
    output_file: str = typer.Option("projects/source_text.json", "--output", help="Fichier JSON de sortie."),
) -> None:
    """Extraire le texte d'une source publique sans la déclarer vérifiée."""
    try:
        document = fetch_source(url)
        destination = Path(output_file)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(document.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        console.print(f"[green]Texte extrait : {destination}[/green]")
        console.print(f"Titre : {document.title or '(sans titre)'}")
        console.print(f"Caractères : {len(document.text)}")
        console.print("[yellow]Source non vérifiée : recouper les affirmations avant utilisation.[/yellow]")
    except (SourceFetchError, OSError) as exc:
        console.print(f"[red]Erreur de lecture de la source : {exc}[/red]")
        raise typer.Exit(code=1) from exc


@app.command("fetch-leads")
def fetch_leads_command(
    input_file: str = typer.Option("projects/research_leads.json", "--input", help="Pistes JSON produites par research-rss."),
    output_file: str = typer.Option("projects/source_documents.json", "--output", help="Résultat des lectures de sources."),
    limit: int = typer.Option(5, "--limit", min=1, max=20, help="Nombre maximal d'articles à ouvrir."),
) -> None:
    """Ouvrir les sources originales d'un lot de pistes RSS."""
    try:
        leads = json.loads(Path(input_file).read_text(encoding="utf-8"))
        results = fetch_leads(leads, limit=limit)
        destination = Path(output_file)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(results, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        succeeded = sum(item["fetch_status"] == "success" for item in results)
        failed = len(results) - succeeded
        console.print(f"[green]{succeeded} source(s) lue(s).[/green] [yellow]{failed} échec(s).[/yellow]")
        console.print(f"Résultat : {destination}")
        console.print("[yellow]Tous les textes extraits restent non vérifiés.[/yellow]")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        console.print(f"[red]Impossible de traiter les pistes : {exc}[/red]")
        raise typer.Exit(code=1) from exc



@app.command("extract-claims")
def extract_claims_command(
    input_file: str = typer.Option("projects/source_documents.json", "--input", help="Textes de sources produits par fetch-leads."),
    output_file: str = typer.Option("projects/claim_candidates.json", "--output", help="Registre JSON des phrases candidates."),
    max_per_source: int = typer.Option(30, "--max-per-source", min=1, max=100, help="Nombre maximal de phrases candidates par source."),
) -> None:
    """Extraire des phrases candidates sans les déclarer vérifiées."""
    try:
        documents = json.loads(Path(input_file).read_text(encoding="utf-8"))
        registry = extract_claim_candidates(documents, max_per_source=max_per_source)
        destination = Path(output_file)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(registry, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        console.print(f"[green]{len(registry['claims'])} phrase(s) candidate(s) extraite(s).[/green]")
        console.print(f"{len(registry['sources'])} source(s) référencée(s) : {destination}")
        console.print("[yellow]Toutes les affirmations restent unconfirmed et pending ; revue humaine obligatoire.[/yellow]")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        console.print(f"[red]Impossible d'extraire les affirmations : {exc}[/red]")
        raise typer.Exit(code=1) from exc



@app.command("review-queue")
def review_queue_command(
    input_file: str = typer.Option("projects/claim_candidates.json", "--input", help="Registre JSON des affirmations candidates."),
    output_file: str = typer.Option("projects/editorial_review.md", "--output", help="Rapport Markdown pour la revue humaine."),
) -> None:
    """Créer un dossier de revue humaine des affirmations en attente."""
    try:
        destination = write_review_queue(input_file, output_file)
        console.print(f"[green]Dossier de revue créé : {destination}[/green]")
        console.print("Ouvrir chaque source originale et vérifier le contexte avant toute décision.")
    except (OSError, ValueError) as exc:
        console.print(f"[red]Impossible de créer la file de revue : {exc}[/red]")
        raise typer.Exit(code=1) from exc


@app.command("export-narration")
def export_narration_command(
    project_file: str = typer.Argument(..., help="Projet documentaire JSON."),
    text_file: str = typer.Option("output/narration.txt", "--text", help="Fichier de voix off."),
    subtitles_file: str = typer.Option("output/subtitles.srt", "--subtitles", help="Fichier de sous-titres SRT."),
) -> None:
    """Exporter le texte de voix off et les sous-titres synchronisés aux scènes."""
    try:
        project = load_project(project_file)
        text_path, srt_path = export_narration(project, text_file, subtitles_file)
        console.print(f"[green]Texte de narration : {text_path}[/green]")
        console.print(f"[green]Sous-titres SRT : {srt_path}[/green]")
        console.print("[yellow]Aucun fichier audio n'est généré par cette commande.[/yellow]")
    except (FileNotFoundError, OSError, ValueError) as exc:
        console.print(f"[red]Export impossible : {exc}[/red]")
        raise typer.Exit(code=1) from exc


@app.command("generate-audio")
def generate_audio_command(
    project_file: str = typer.Argument(..., help="Projet documentaire JSON."),
    output_file: str = typer.Option("output/narration.mp3", "--output", help="Fichier MP3 de sortie."),
    voice: str = typer.Option("fr-FR-HenriNeural", "--voice", help="Voix Microsoft Edge-TTS."),
    rate: str = typer.Option("-8%", "--rate", help="Vitesse de parole, par exemple -8%."),
    pitch: str = typer.Option("-8Hz", "--pitch", help="Hauteur de voix, par exemple -8Hz."),
    subtitles_file: str = typer.Option("output/narration.srt", "--subtitles", help="Sous-titres calés sur les repères vocaux."),
) -> None:
    """Générer la voix off MP3 et les sous-titres synchronisés avec Edge-TTS."""
    try:
        project = load_project(project_file)
        console.print(f"Génération audio et repères de sous-titres avec {voice}…")
        result, subtitles = generate_audio_with_subtitles(
            project, output_file, subtitles_file, voice=voice, rate=rate, pitch=pitch
        )
        console.print(f"[green]Narration MP3 créée : {result}[/green]")
        console.print(f"[green]Sous-titres synchronisés créés : {subtitles}[/green]")
    except (FileNotFoundError, OSError, ValueError, SpeechError) as exc:
        console.print(f"[red]Génération audio impossible : {exc}[/red]")
        raise typer.Exit(code=1) from exc


@app.command("validate-project")
def validate_project(project_file: str = typer.Argument(..., help="Chemin vers le fichier projet JSON.")) -> None:
    """Valider un projet documentaire et ses références aux sources."""
    try:
        project = load_project(project_file)
        console.print(f"[green]Projet valide : {project.title}[/green]")
        console.print(
            f"{len(project.scenes)} scène(s), {len(project.sources)} source(s), "
            f"format {project.aspect_ratio}, durée cible {project.target_duration_minutes} min."
        )
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc


@app.command("validate-claims")
def validate_claims(claims_file: str = typer.Argument(..., help="Chemin vers le registre JSON des affirmations.")) -> None:
    """Contrôler les sources et validations humaines d'un registre d'affirmations."""
    try:
        registry = load_claim_registry(claims_file)
        verified = sum(claim.status.value == "verified" for claim in registry.claims)
        pending = sum(claim.review_decision.value == "pending" for claim in registry.claims)
        console.print(f"[green]Registre valide : {len(registry.claims)} affirmation(s), {len(registry.sources)} source(s).[/green]")
        console.print(f"Affirmations déclarées vérifiées : {verified} | En attente de revue : {pending}")
        console.print("[yellow]Ce contrôle valide la structure et les règles éditoriales, pas la vérité des contenus.[/yellow]")
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc


@app.command("video-test")
def video_test(
    prompt: str = typer.Option(..., "--prompt", help="Description de la scène animée."),
    seconds: int = typer.Option(5, "--seconds", min=4, max=12, help="Durée du clip (4 à 12 secondes)."),
) -> None:
    """Générer un clip de test Agnes en 720p, format 16:9."""
    try:
        settings = Settings.load()
        if settings.video_provider != "agnes" or not settings.agnes_api_key:
            raise AgnesError("Configure .env avec VIDEO_PROVIDER=agnes et AGNES_API_KEY=ta_cle.")
        destination = settings.output_dir / "agnes_test.mp4"
        console.print("Envoi du prompt à Agnes ; la génération peut prendre plusieurs minutes…")
        result = generate_video(prompt, destination, seconds=seconds, aspect_ratio="16:9",
                                api_key=settings.agnes_api_key)
        console.print(f"[green]Clip téléchargé : {result}[/green]")
    except (AgnesError, ValueError) as exc:
        console.print(f"[red]Erreur : {exc}[/red]")
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    app()

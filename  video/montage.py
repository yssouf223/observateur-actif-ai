
import os
import json
import re
import subprocess
from pathlib import Path

# ==========================================
# OBSERVATEUR ACTIF AI
# MOTEUR DE MONTAGE VIDEO SHORTS
# ==========================================

DOSSIER = Path("data")
DOSSIER_AUDIO = Path("audio")
DOSSIER_VIDEO = Path("videos")

FICHIER_SCRIPTS = DOSSIER / "scripts_generes.json"
FICHIER_RAPPORT_AUDIO = DOSSIER_AUDIO / "rapport.json"

LARGEUR = 1080
HAUTEUR = 1920
FPS = 30


def commande(args):

    resultat = subprocess.run(
        args,
        capture_output=True,
        text=True
    )

    if resultat.returncode != 0:
        raise RuntimeError(resultat.stderr[-3000:])

    return resultat


def duree_audio(fichier):

    resultat = commande([
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        fichier
    ])

    return float(resultat.stdout.strip())


def decouper_narration(texte):

    phrases = re.split(
        r'(?<=[.!?])\s+',
        texte.strip()
    )

    morceaux = []

    for phrase in phrases:

        mots = phrase.split()

        for i in range(0, len(mots), 7):

            morceau = " ".join(mots[i:i + 7])

            if morceau:
                morceaux.append(morceau)

    return morceaux


def temps_srt(secondes):

    heures = int(secondes // 3600)
    minutes = int((secondes % 3600) // 60)
    secs = int(secondes % 60)
    millisecondes = int(
        (secondes - int(secondes)) * 1000
    )

    return (
        f"{heures:02}:"
        f"{minutes:02}:"
        f"{secs:02},"
        f"{millisecondes:03}"
    )


def creer_sous_titres(texte, duree, fichier):

    morceaux = decouper_narration(texte)

    if not morceaux:
        raise ValueError("Narration vide.")

    temps_par_morceau = duree / len(morceaux)

    lignes = []

    for i, morceau in enumerate(morceaux):

        debut = i * temps_par_morceau
        fin = (i + 1) * temps_par_morceau

        lignes.extend([
            str(i + 1),
            f"{temps_srt(debut)} --> {temps_srt(fin)}",
            morceau,
            ""
        ])

    fichier.write_text(
        "\n".join(lignes),
        encoding="utf-8"
    )


def creer_video(script, audio):

    identifiant = re.sub(
        r"[^a-zA-Z0-9_-]",
        "",
        str(script.get("id_histoire", "histoire"))
    )

    if not identifiant:
        raise ValueError("Identifiant invalide.")

    DOSSIER_VIDEO.mkdir(
        parents=True,
        exist_ok=True
    )

    fichier_audio = Path(audio)

    if not fichier_audio.exists():
        raise FileNotFoundError(audio)

    duree = duree_audio(str(fichier_audio))

    if duree <= 0:
        raise ValueError("Durée audio invalide.")

    titre = script.get(
        "titre", "Observateur Actif"
    )

    narration = script.get("narration", "")

    fichier_srt = DOSSIER_VIDEO / f"{identifiant}.srt"
    fichier_titre = DOSSIER_VIDEO / f"{identifiant}.txt"
    fichier_video = DOSSIER_VIDEO / f"{identifiant}.mp4"

    creer_sous_titres(
        narration,
        duree,
        fichier_srt
    )

    fichier_titre.write_text(
        titre[:100],
        encoding="utf-8"
    )

    # Fond provisoire en attendant le module
    # de téléchargement automatique des images.

    filtre = (
        "drawtext="
        "fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
        f"textfile={fichier_titre}:"
        "fontcolor=white:"
        "fontsize=54:"
        "line_spacing=16:"
        "x=(w-text_w)/2:"
        "y=180:"
        "box=1:"
        "boxcolor=black@0.45:"
        "boxborderw=25,"
        f"subtitles={fichier_srt}:"
        "force_style='FontName=DejaVu Sans,"
        "FontSize=18,PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,Outline=2,"
        "Alignment=2,MarginV=180'"
    )

    commande([
        "ffmpeg",
        "-y",
        "-f", "lavfi",
        "-i",
        f"color=c=0x101827:s={LARGEUR}x{HAUTEUR}:r={FPS}:d={duree}",
        "-i", str(fichier_audio),
        "-vf", filtre,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        "-shortest",
        str(fichier_video)
    ])

    print("Vidéo créée :", fichier_video)

    return str(fichier_video)


def executer():

    if not FICHIER_SCRIPTS.exists():
        print("Scripts introuvables.")
        return

    if not FICHIER_RAPPORT_AUDIO.exists():
        print("Rapport audio introuvable.")
        return

    with open(
        FICHIER_SCRIPTS,
        encoding="utf-8"
    ) as f:
        scripts = json.load(f).get("scripts", [])

    with open(
        FICHIER_RAPPORT_AUDIO,
        encoding="utf-8"
    ) as f:
        audios = json.load(f).get("audios", [])

    audio_par_id = {
        a["id_histoire"]: a["fichier_audio"]
        for a in audios
    }

    resultats = []

    for script in scripts:

        identifiant = script.get("id_histoire")

        if identifiant not in audio_par_id:
            continue

        try:

            video = creer_video(
                script,
                audio_par_id[identifiant]
            )

            resultats.append({
                "id_histoire": identifiant,
                "fichier_video": video,
                "statut": "BROUILLON_VIDEO"
            })

        except Exception as erreur:

            print("Erreur montage :", erreur)

    with open(
        DOSSIER_VIDEO / "rapport.json",
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            {
                "nombre_videos": len(resultats),
                "videos": resultats
            },
            f,
            ensure_ascii=False,
            indent=2
        )

    print("Montage terminé :", len(resultats))


if __name__ == "__main__":
    executer()

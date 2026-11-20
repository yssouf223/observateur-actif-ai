
import json
import subprocess
import re
import sys
from pathlib import Path

DOSSIER_DATA = Path("data")
DOSSIER_AUDIO = Path("audio")
DOSSIER_VIDEO = Path("videos")

FICHIER_SCRIPTS = DOSSIER_DATA / "scripts_generes.json"
FICHIER_IMAGES = DOSSIER_DATA / "images_rapport.json"


def executer_commande(commande):
    resultat = subprocess.run(
        commande,
        capture_output=True,
        text=True
    )

    if resultat.returncode != 0:
        raise RuntimeError(resultat.stderr[-3000:])

    return resultat


def nettoyer_nom(valeur):
    nom = re.sub(r"[^a-zA-Z0-9_-]", "", str(valeur))
    return nom or "histoire"


def charger_images(identifiant):
    if not FICHIER_IMAGES.exists():
        return []

    with open(FICHIER_IMAGES, encoding="utf-8") as fichier:
        rapport = json.load(fichier)

    for histoire in rapport.get("histoires", []):
        if histoire.get("id_histoire") == identifiant:
            return [
                image["fichier"]
                for image in histoire.get("images", [])
                if image.get("fichier")
                and Path(image["fichier"]).exists()
            ]

    return []


def creer_video(script):
    identifiant = nettoyer_nom(
        script.get("id_histoire", "histoire")
    )

    audio = DOSSIER_AUDIO / f"{identifiant}.wav"

    if not audio.exists():
        raise FileNotFoundError(f"Audio absent : {audio}")

    DOSSIER_VIDEO.mkdir(parents=True, exist_ok=True)

    sortie = DOSSIER_VIDEO / f"{identifiant}.mp4"

    images = charger_images(identifiant)

    if images:
        print("Montage avec", len(images), "images.")
        liste = DOSSIER_VIDEO / f"{identifiant}_images.txt"

        with open(liste, "w", encoding="utf-8") as fichier:
            for image in images:
                chemin = str(Path(image).resolve())
                chemin = chemin.replace("\\", "/").replace("'", "'\\''")
                fichier.write(f"file '{chemin}'\n")
                fichier.write("duration 5\n")

            chemin = str(Path(images[-1]).resolve())
            chemin = chemin.replace("\\", "/").replace("'", "'\\''")
            fichier.write(f"file '{chemin}'\n")

        commande = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(liste),
            "-i", str(audio),
            "-vf",
            "scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,format=yuv420p,fps=30",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-tune", "stillimage",
            "-c:a", "aac",
            "-b:a", "128k",
            "-shortest",
            "-movflags", "+faststart",
            str(sortie)
        ]

    else:
        print("Aucune image disponible : fond sombre utilisé.")

        commande = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", "color=c=black:s=1080x1920:r=30",
            "-i", str(audio),
            "-vf", "format=yuv420p",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-c:a", "aac",
            "-b:a", "128k",
            "-shortest",
            "-movflags", "+faststart",
            str(sortie)
        ]

    executer_commande(commande)

    if not sortie.exists() or sortie.stat().st_size == 0:
        raise RuntimeError("La vidéo n'a pas été créée.")

    print("Vidéo créée :", sortie)

    return str(sortie)


def executer():
    if not FICHIER_SCRIPTS.exists():
        raise FileNotFoundError("Scripts introuvables.")

    with open(FICHIER_SCRIPTS, encoding="utf-8") as fichier:
        donnees = json.load(fichier)

    scripts = donnees.get("scripts", [])

    if not scripts:
        raise RuntimeError("Aucun script à monter.")

    resultats = []

    for script in scripts:
        try:
            video = creer_video(script)

            resultats.append({
                "id_histoire": script.get("id_histoire"),
                "fichier_video": video,
                "statut": "VIDEO_CREEE"
            })

        except Exception as erreur:
            print("Erreur montage :", erreur)

    rapport = {
        "agent": "Observateur Actif AI",
        "nombre_videos": len(resultats),
        "videos": resultats
    }

    with open(
        DOSSIER_VIDEO / "rapport.json",
        "w",
        encoding="utf-8"
    ) as fichier:
        json.dump(rapport, fichier, ensure_ascii=False, indent=2)

    if not resultats:
        raise RuntimeError("Aucune vidéo n'a été créée.")

    print("Vidéos produites :", len(resultats))


if __name__ == "__main__":
    executer()

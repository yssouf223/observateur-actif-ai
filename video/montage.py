
import json
import subprocess
import re

from pathlib import Path

# ==========================================
# OBSERVATEUR ACTIF AI
# MOTEUR DE MONTAGE VIDEO V2
# ==========================================

DOSSIER_DATA = Path("data")
DOSSIER_AUDIO = Path("audio")
DOSSIER_VIDEO = Path("videos")

FICHIER_SCRIPTS = DOSSIER_DATA / "scripts_generes.json"
FICHIER_IMAGES = DOSSIER_DATA / "images_rapport.json"


# ==========================================
# EXECUTION DES COMMANDES
# ==========================================

def executer_commande(commande):

    resultat = subprocess.run(
        commande,
        capture_output=True,
        text=True
    )

    if resultat.returncode != 0:
        raise RuntimeError(
            resultat.stderr[-3000:]
        )

    return resultat


# ==========================================
# NETTOYAGE DES IDENTIFIANTS
# ==========================================

def nettoyer_nom(valeur):

    nom = re.sub(
        r"[^a-zA-Z0-9_-]",
        "",
        str(valeur)
    )

    return nom or "histoire"


# ==========================================
# MESURE DE LA DUREE AUDIO
# ==========================================

def obtenir_duree_audio(audio):

    resultat = executer_commande([
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(audio)
    ])

    try:
        duree = float(resultat.stdout.strip())
    except ValueError:
        raise RuntimeError(
            "Impossible de mesurer la durée audio."
        )

    if duree <= 0:
        raise RuntimeError(
            "La durée audio est invalide."
        )

    return duree


# ==========================================
# RECUPERATION DES IMAGES
# ==========================================

def charger_images(identifiant):

    if not FICHIER_IMAGES.exists():
        return []

    with open(
        FICHIER_IMAGES,
        encoding="utf-8"
    ) as fichier:

        rapport = json.load(fichier)

    for histoire in rapport.get("histoires", []):

        if histoire.get("id_histoire") == identifiant:

            images = []

            for image in histoire.get("images", []):

                chemin = image.get("fichier")

                if chemin and Path(chemin).exists():
                    images.append(str(Path(chemin).resolve()))

            return images

    return []


# ==========================================
# CREATION DU FICHIER DE SEQUENCE
# ==========================================

def creer_liste_images(images, duree, identifiant):

    DOSSIER_VIDEO.mkdir(
        parents=True,
        exist_ok=True
    )

    liste = DOSSIER_VIDEO / f"{identifiant}_images.txt"

    nombre_images = len(images)

    duree_par_image = duree / nombre_images

    with open(
        liste,
        "w",
        encoding="utf-8"
    ) as fichier:

        for image in images:

            chemin = str(
                Path(image).resolve()
            )

            chemin = chemin.replace("\\", "/")
            chemin = chemin.replace("'", "'\\''")

            fichier.write(
                f"file '{chemin}'\n"
            )

            fichier.write(
                f"duration {duree_par_image:.6f}\n"
            )

        # Répétition de la dernière image
        # pour respecter sa durée d'affichage.

        chemin = str(
            Path(images[-1]).resolve()
        )

        chemin = chemin.replace("\\", "/")
        chemin = chemin.replace("'", "'\\''")

        fichier.write(
            f"file '{chemin}'\n"
        )

    return liste


# ==========================================
# MONTAGE D'UNE VIDEO
# ==========================================

def creer_video(script):

    identifiant = nettoyer_nom(
        script.get("id_histoire", "histoire")
    )

    audio = DOSSIER_AUDIO / f"{identifiant}.wav"

    if not audio.exists():
        raise FileNotFoundError(
            f"Audio absent : {audio}"
        )

    duree = obtenir_duree_audio(audio)

    print(
        "Durée de la narration :",
        round(duree, 2),
        "secondes"
    )

    DOSSIER_VIDEO.mkdir(
        parents=True,
        exist_ok=True
    )

    sortie = DOSSIER_VIDEO / f"{identifiant}.mp4"

    images = charger_images(identifiant)

    if images:

        print(
            "Montage avec",
            len(images),
            "images."
        )

        liste = creer_liste_images(
            images,
            duree,
            identifiant
        )

        commande = [
            "ffmpeg",
            "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(liste),
            "-i", str(audio),
            "-t", str(duree),
            "-vf",
            "scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,"
            "format=yuv420p,"
            "fps=30",
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

        print(
            "Aucune image disponible : fond sombre utilisé."
        )

        commande = [
            "ffmpeg",
            "-y",
            "-f", "lavfi",
            "-i",
            f"color=c=black:s=1080x1920:r=30:d={duree}",
            "-i", str(audio),
            "-t", str(duree),
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

    if not sortie.exists():
        raise RuntimeError(
            "La vidéo n'a pas été créée."
        )

    if sortie.stat().st_size == 0:
        raise RuntimeError(
            "Le fichier vidéo est vide."
        )

    duree_video = obtenir_duree_audio(sortie)

    print(
        "Vidéo créée :",
        sortie
    )

    print(
        "Durée finale :",
        round(duree_video, 2),
        "secondes"
    )

    return str(sortie)


# ==========================================
# PRODUCTION DES VIDEOS
# ==========================================

def executer():

    DOSSIER_VIDEO.mkdir(
        parents=True,
        exist_ok=True
    )

    if not FICHIER_SCRIPTS.exists():
        raise FileNotFoundError(
            "Scripts introuvables."
        )

    with open(
        FICHIER_SCRIPTS,
        encoding="utf-8"
    ) as fichier:

        donnees = json.load(fichier)

    scripts = donnees.get("scripts", [])

    if not scripts:
        raise RuntimeError(
            "Aucun script à monter."
        )

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

            print(
                "Erreur montage :",
                erreur
            )

    rapport = {
        "agent": "Observateur Actif AI",
        "version": "V2",
        "nombre_videos": len(resultats),
        "videos": resultats
    }

    with open(
        DOSSIER_VIDEO / "rapport.json",
        "w",
        encoding="utf-8"
    ) as fichier:

        json.dump(
            rapport,
            fichier,
            ensure_ascii=False,
            indent=2
        )

    if not resultats:
        raise RuntimeError(
            "Aucune vidéo n'a été créée."
        )

    print(
        "Vidéos produites :",
        len(resultats)
    )


if __name__ == "__main__":
    executer()

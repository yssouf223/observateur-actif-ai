
import os
import json
import re
import subprocess

from pathlib import Path
from datetime import datetime, timezone

# ==========================================
# OBSERVATEUR ACTIF AI
# MOTEUR DE MONTAGE VIDEO V3
# ==========================================

RACINE = Path(__file__).resolve().parent.parent

DOSSIER_DATA = RACINE / "data"
DOSSIER_AUDIO = RACINE / "audio"
DOSSIER_VIDEO = RACINE / "videos"

FICHIER_SCRIPTS = DOSSIER_DATA / "scripts_generes.json"
FICHIER_IMAGES = DOSSIER_DATA / "images_rapport.json"

TIMEOUT_FFMPEG = 900
TIMEOUT_FFPROBE = 30


def executer_commande(commande, timeout=120):

    try:
        resultat = subprocess.run(
            commande,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False
        )

    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"Commande interrompue après {timeout} secondes."
        )

    if resultat.returncode != 0:
        raise RuntimeError(
            resultat.stderr[-3000:]
            or "La commande a échoué."
        )

    return resultat


def nettoyer_nom(valeur):

    nom = re.sub(
        r"[^a-zA-Z0-9_-]",
        "",
        str(valeur)
    )

    return nom or "histoire"


def obtenir_identifiant(script):

    identifiant = script.get(
        "id_histoire",
        script.get("id", "histoire")
    )

    return nettoyer_nom(identifiant)


def sauvegarder_rapport(rapport):

    DOSSIER_VIDEO.mkdir(
        parents=True,
        exist_ok=True
    )

    destination = DOSSIER_VIDEO / "rapport.json"
    temporaire = DOSSIER_VIDEO / "rapport.tmp"

    with open(
        temporaire,
        "w",
        encoding="utf-8"
    ) as fichier:

        json.dump(
            rapport,
            fichier,
            ensure_ascii=False,
            indent=2
        )

    os.replace(
        temporaire,
        destination
    )


def obtenir_duree(fichier):

    resultat = executer_commande(
        [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(fichier)
        ],
        timeout=TIMEOUT_FFPROBE
    )

    try:
        duree = float(resultat.stdout.strip())
    except (ValueError, TypeError):
        raise RuntimeError(
            "Impossible de mesurer la durée du média."
        )

    if duree <= 0:
        raise RuntimeError("Durée du média invalide.")

    return duree


def verifier_video(fichier):

    resultat = executer_commande(
        [
            "ffprobe",
            "-v", "error",
            "-show_entries",
            "stream=codec_type,width,height",
            "-of", "json",
            str(fichier)
        ],
        timeout=TIMEOUT_FFPROBE
    )

    try:
        donnees = json.loads(resultat.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(
            "Impossible de lire les informations de la vidéo."
        )

    flux = donnees.get("streams", [])

    video = [
        flux_video for flux_video in flux
        if flux_video.get("codec_type") == "video"
    ]

    audio = [
        flux_audio for flux_audio in flux
        if flux_audio.get("codec_type") == "audio"
    ]

    if not video:
        raise RuntimeError("Aucune piste vidéo détectée.")

    if not audio:
        raise RuntimeError("Aucune piste audio détectée.")

    if video[0].get("width") != 1080:
        raise RuntimeError("Largeur vidéo incorrecte.")

    if video[0].get("height") != 1920:
        raise RuntimeError("Hauteur vidéo incorrecte.")

    return True


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

                if not chemin:
                    continue

                chemin = Path(chemin)

                if not chemin.is_absolute():
                    chemin = RACINE / chemin

                if chemin.exists() and chemin.is_file():
                    images.append(str(chemin.resolve()))

            return images

    return []


def creer_liste_images(images, duree, identifiant):

    DOSSIER_VIDEO.mkdir(
        parents=True,
        exist_ok=True
    )

    liste = DOSSIER_VIDEO / f"{identifiant}_images.txt"

    duree_par_image = duree / len(images)

    with open(
        liste,
        "w",
        encoding="utf-8"
    ) as fichier:

        for image in images:

            chemin = Path(image).resolve().as_posix()

            chemin = chemin.replace("'", "'\\''")

            fichier.write(
                f"file '{chemin}'\n"
            )

            fichier.write(
                f"duration {duree_par_image:.6f}\n"
            )

        dernier = Path(images[-1]).resolve().as_posix()
        dernier = dernier.replace("'", "'\\''")

        fichier.write(
            f"file '{dernier}'\n"
        )

    return liste


def creer_video(script):

    identifiant = obtenir_identifiant(script)

    audio = DOSSIER_AUDIO / f"{identifiant}.wav"

    if not audio.exists():
        raise FileNotFoundError(
            f"Audio absent : {audio}"
        )

    duree = obtenir_duree(audio)

    print(
        "Durée de narration :",
        round(duree, 2),
        "secondes"
    )

    if duree < 45 or duree > 60:
        print(
            "ATTENTION : la narration ne respecte pas "
            "la durée cible de 45 à 60 secondes."
        )

    DOSSIER_VIDEO.mkdir(
        parents=True,
        exist_ok=True
    )

    sortie = DOSSIER_VIDEO / f"{identifiant}.mp4"
    temporaire = DOSSIER_VIDEO / f"{identifiant}.tmp.mp4"

    images = charger_images(identifiant)

    if temporaire.exists():
        temporaire.unlink()

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
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-t", str(duree),
            "-vf",
            "scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,"
            "setsar=1,"
            "fps=30,"
            "format=yuv420p",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-tune", "stillimage",
            "-threads", "2",
            "-c:a", "aac",
            "-b:a", "128k",
            "-shortest",
            "-movflags", "+faststart",
            str(temporaire)
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
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-t", str(duree),
            "-vf",
            "setsar=1,format=yuv420p",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-threads", "2",
            "-c:a", "aac",
            "-b:a", "128k",
            "-shortest",
            "-movflags", "+faststart",
            str(temporaire)
        ]

    executer_commande(
        commande,
        timeout=TIMEOUT_FFMPEG
    )

    if not temporaire.exists():
        raise RuntimeError(
            "FFmpeg n'a pas créé le fichier vidéo."
        )

    if temporaire.stat().st_size < 10000:
        raise RuntimeError(
            "Le fichier vidéo est trop petit."
        )

    verifier_video(temporaire)

    duree_video = obtenir_duree(temporaire)

    os.replace(
        temporaire,
        sortie
    )

    print("Vidéo validée :", sortie.name)
    print("Durée finale :", round(duree_video, 2), "secondes")
    print("Résolution : 1080 x 1920")

    return {
        "id_histoire": identifiant,
        "fichier_video": str(
            sortie.relative_to(RACINE)
        ),
        "duree_secondes": round(duree_video, 2),
        "resolution": "1080x1920",
        "taille_octets": sortie.stat().st_size,
        "nombre_images": len(images),
        "statut": "VIDEO_CREEE"
    }


def executer():

    print("=" * 55)
    print("OBSERVATEUR ACTIF AI")
    print("MOTEUR DE MONTAGE VIDEO V3")
    print("=" * 55)

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
    erreurs = []

    rapport = {
        "agent": "Observateur Actif AI",
        "version": "V3",
        "date_generation": datetime.now(
            timezone.utc
        ).isoformat(),
        "nombre_scripts": len(scripts),
        "nombre_videos": 0,
        "nombre_erreurs": 0,
        "videos": [],
        "erreurs": []
    }

    for numero, script in enumerate(scripts, start=1):

        print(
            f"\nMontage {numero}/{len(scripts)}"
        )

        try:

            video = creer_video(script)

            resultats.append(video)

        except Exception as erreur:

            message = str(erreur)

            print("ERREUR MONTAGE :", message)

            erreurs.append({
                "numero": numero,
                "message": message
            })

        rapport["nombre_videos"] = len(resultats)
        rapport["nombre_erreurs"] = len(erreurs)
        rapport["videos"] = resultats
        rapport["erreurs"] = erreurs

        sauvegarder_rapport(rapport)

    if not resultats:

        raise RuntimeError(
            "Aucune vidéo n'a été créée."
        )

    print("\n" + "=" * 55)
    print("PRODUCTION VIDEO TERMINEE")
    print("Vidéos créées :", len(resultats))
    print("Erreurs :", len(erreurs))
    print("=" * 55)


if __name__ == "__main__":
    executer()

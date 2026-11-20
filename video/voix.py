
import os
import sys
import json
import re
import subprocess

from pathlib import Path
from datetime import datetime, timezone

# ==========================================
# OBSERVATEUR ACTIF AI
# GENERATEUR DE VOIX OFF V3
# ==========================================

RACINE = Path(__file__).resolve().parent.parent

DOSSIER_MODELES = RACINE / "models" / "voices"
DOSSIER_AUDIO = RACINE / "audio"
FICHIER_SCRIPTS = RACINE / "data" / "scripts_generes.json"

VOIX = os.environ.get(
    "PIPER_VOICE",
    "fr_FR-siwis-medium"
)

TIMEOUT_TELECHARGEMENT = 300
TIMEOUT_AUDIO = 240
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


def sauvegarder_rapport(rapport):

    DOSSIER_AUDIO.mkdir(
        parents=True,
        exist_ok=True
    )

    destination = DOSSIER_AUDIO / "rapport.json"
    temporaire = DOSSIER_AUDIO / "rapport.tmp"

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

    os.replace(temporaire, destination)


def installer_voix():

    DOSSIER_MODELES.mkdir(
        parents=True,
        exist_ok=True
    )

    modele = DOSSIER_MODELES / f"{VOIX}.onnx"
    configuration = Path(str(modele) + ".json")

    if modele.exists() and configuration.exists():

        print("Voix française déjà installée.")

        return modele

    print("Téléchargement de la voix :", VOIX)

    executer_commande(
        [
            sys.executable,
            "-m",
            "piper.download_voices",
            VOIX,
            "--data-dir",
            str(DOSSIER_MODELES)
        ],
        timeout=TIMEOUT_TELECHARGEMENT
    )

    if not modele.exists() or not configuration.exists():

        raise RuntimeError(
            "Les fichiers du modèle vocal sont introuvables."
        )

    print("Modèle vocal installé.")

    return modele


def nom_fichier(identifiant):

    identifiant = re.sub(
        r"[^a-zA-Z0-9_-]",
        "",
        str(identifiant)
    )

    return identifiant or "histoire"


def obtenir_duree(fichier_audio):

    resultat = executer_commande(
        [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(fichier_audio)
        ],
        timeout=TIMEOUT_FFPROBE
    )

    try:
        duree = float(resultat.stdout.strip())
    except (ValueError, TypeError):
        raise RuntimeError(
            "Impossible de déterminer la durée du fichier audio."
        )

    if duree <= 0:
        raise RuntimeError("Durée audio invalide.")

    return duree


def generer_audio(script, modele):

    if not isinstance(script, dict):
        raise RuntimeError("Format de script invalide.")

    narration = script.get("narration", "")

    if not isinstance(narration, str):
        raise RuntimeError("La narration n'est pas du texte.")

    narration = narration.strip()

    if not narration:
        raise RuntimeError("Narration vide.")

    identifiant = nom_fichier(
        script.get(
            "id_histoire",
            script.get("id", "histoire")
        )
    )

    DOSSIER_AUDIO.mkdir(
        parents=True,
        exist_ok=True
    )

    sortie = DOSSIER_AUDIO / f"{identifiant}.wav"
    temporaire = DOSSIER_AUDIO / f"{identifiant}.tmp.wav"

    print("Génération audio :", sortie.name)

    if temporaire.exists():
        temporaire.unlink()

    executer_commande(
        [
            sys.executable,
            "-m",
            "piper",
            "-m",
            str(modele),
            "-f",
            str(temporaire),
            "--",
            narration
        ],
        timeout=TIMEOUT_AUDIO
    )

    if not temporaire.exists():
        raise RuntimeError(
            "Piper n'a pas créé le fichier audio."
        )

    if temporaire.stat().st_size < 1000:
        raise RuntimeError(
            "Le fichier audio est vide ou incomplet."
        )

    duree = obtenir_duree(temporaire)

    os.replace(temporaire, sortie)

    print(
        "Audio validé :",
        round(duree, 2),
        "secondes"
    )

    return {
        "id_histoire": script.get(
            "id_histoire",
            script.get("id")
        ),
        "fichier_audio": str(
            sortie.relative_to(RACINE)
        ),
        "duree_secondes": round(duree, 2),
        "taille_octets": sortie.stat().st_size,
        "statut": "AUDIO_CREE"
    }


def executer():

    print("=" * 55)
    print("OBSERVATEUR ACTIF AI")
    print("GENERATION DES VOIX OFF V3")
    print("=" * 55)

    DOSSIER_AUDIO.mkdir(
        parents=True,
        exist_ok=True
    )

    if not FICHIER_SCRIPTS.exists():

        raise FileNotFoundError(
            "Fichier des scripts Gemini introuvable."
        )

    with open(
        FICHIER_SCRIPTS,
        "r",
        encoding="utf-8"
    ) as fichier:

        donnees = json.load(fichier)

    scripts = donnees.get("scripts", [])

    if not scripts:

        raise RuntimeError(
            "Aucun script disponible pour la narration."
        )

    modele = installer_voix()

    resultats = []
    erreurs = []

    for numero, script in enumerate(scripts, start=1):

        print(
            f"\nNarration {numero}/{len(scripts)}"
        )

        try:

            audio = generer_audio(
                script,
                modele
            )

            resultats.append(audio)

        except Exception as erreur:

            message = str(erreur)

            print("ERREUR AUDIO :", message)

            erreurs.append({
                "numero": numero,
                "message": message
            })

    rapport = {
        "agent": "Observateur Actif AI",
        "version": "V3",
        "date_generation": datetime.now(
            timezone.utc
        ).isoformat(),
        "voix": VOIX,
        "nombre_scripts": len(scripts),
        "nombre_audios": len(resultats),
        "nombre_erreurs": len(erreurs),
        "audios": resultats,
        "erreurs": erreurs
    }

    sauvegarder_rapport(rapport)

    if not resultats:

        raise RuntimeError(
            "Aucun fichier audio n'a été généré."
        )

    print("\n" + "=" * 55)
    print("GENERATION AUDIO TERMINEE")
    print("Audios créés :", len(resultats))
    print("Erreurs :", len(erreurs))
    print("=" * 55)


if __name__ == "__main__":
    executer()

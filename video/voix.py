
import os
import json
import re
import subprocess
from pathlib import Path

DOSSIER_MODELES = Path("models/voices")
DOSSIER_AUDIO = Path("audio")
FICHIER_SCRIPTS = Path("data/scripts_generes.json")

VOIX = os.environ.get("PIPER_VOICE", "fr_FR-siwis-medium")


def executer_commande(commande):
    resultat = subprocess.run(
        commande,
        capture_output=True,
        text=True
    )

    if resultat.returncode != 0:
        raise RuntimeError(resultat.stderr[-2000:])

    return resultat


def installer_voix():
    DOSSIER_MODELES.mkdir(parents=True, exist_ok=True)

    modele = DOSSIER_MODELES / f"{VOIX}.onnx"
    configuration = Path(str(modele) + ".json")

    if modele.exists() and configuration.exists():
        print("Voix française déjà installée.")
        return modele

    print("Téléchargement de la voix :", VOIX)

    executer_commande([
        sys.executable,
        "-m",
        "piper.download_voices",
        VOIX,
        "--download-dir",
        str(DOSSIER_MODELES)
    ])

    if not modele.exists() or not configuration.exists():
        raise RuntimeError("Fichiers de la voix introuvables.")

    return modele


def nom_fichier(identifiant):
    identifiant = re.sub(
        r"[^a-zA-Z0-9_-]",
        "",
        str(identifiant)
    )
    return identifiant or "histoire"


def generer_audio(script, modele):
    narration = script.get("narration", "").strip()

    if not narration:
        return None

    identifiant = nom_fichier(
        script.get("id_histoire", "histoire")
    )

    DOSSIER_AUDIO.mkdir(parents=True, exist_ok=True)
    sortie = DOSSIER_AUDIO / f"{identifiant}.wav"

    print("Génération audio :", sortie)

    executer_commande([
        sys.executable,
        "-m",
        "piper",
        "-m",
        str(modele),
        "-f",
        str(sortie),
        "--",
        narration
    ])

    if not sortie.exists() or sortie.stat().st_size == 0:
        raise RuntimeError("Le fichier audio n'a pas été créé.")

    return str(sortie)


def executer():
    DOSSIER_AUDIO.mkdir(parents=True, exist_ok=True)

    if not FICHIER_SCRIPTS.exists():
        raise FileNotFoundError("Scripts Gemini introuvables.")

    with open(FICHIER_SCRIPTS, encoding="utf-8") as fichier:
        donnees = json.load(fichier)

    scripts = donnees.get("scripts", [])

    if not scripts:
        raise RuntimeError("Aucun script disponible pour la narration.")

    modele = installer_voix()
    resultats = []

    for script in scripts:
        try:
            audio = generer_audio(script, modele)

            if audio:
                resultats.append({
                    "id_histoire": script.get("id_histoire"),
                    "fichier_audio": audio,
                    "statut": "AUDIO_CREE"
                })

        except Exception as erreur:
            print("Erreur audio :", erreur)

    rapport = {
        "agent": "Observateur Actif AI",
        "nombre_audios": len(resultats),
        "audios": resultats
    }

    with open(
        DOSSIER_AUDIO / "rapport.json",
        "w",
        encoding="utf-8"
    ) as fichier:
        json.dump(rapport, fichier, ensure_ascii=False, indent=2)

    if not resultats:
        raise RuntimeError("Aucun fichier audio n'a été généré.")

    print("Audios générés :", len(resultats))


if __name__ == "__main__":
    import sys
    executer()

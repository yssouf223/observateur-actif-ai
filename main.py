
import json
import subprocess
import sys

from pathlib import Path
from datetime import datetime, timezone

# ==========================================
# OBSERVATEUR ACTIF AI
# ORCHESTRATEUR PRINCIPAL V2
# ==========================================

RACINE = Path(__file__).resolve().parent

DOSSIER_DATA = RACINE / "data"

DOSSIER_DATA.mkdir(
    parents=True,
    exist_ok=True
)

# ==========================================
# ORDRE DE PRODUCTION
# ==========================================

MODULES = [
    {
        "nom": "Recherche des histoires africaines",
        "fichier": "recherche/moteur.py",
        "sorties": [
            "data/histoires_brutes.json"
        ]
    },
    {
        "nom": "Analyse documentaire des sources",
        "fichier": "recherche/verification.py",
        "sorties": [
            "data/histoires_analysees.json"
        ]
    },
    {
        "nom": "Génération des scripts Gemini",
        "fichier": "intelligence/scripts.py",
        "sorties": [
            "data/scripts_generes.json"
        ],
        "validation": "scripts"
    },
    {
        "nom": "Recherche et téléchargement des images",
        "fichier": "recherche_images.py",
        "sorties": [
            "data/images_rapport.json"
        ]
    },
    {
        "nom": "Création des voix off",
        "fichier": "video/voix.py",
        "sorties": [
            "audio/rapport.json"
        ],
        "validation": "audio"
    },
    {
        "nom": "Montage des vidéos",
        "fichier": "video/montage.py",
        "sorties": [
            "videos/rapport.json"
        ],
        "validation": "video"
    }
]


# ==========================================
# JOURNAL D'EXÉCUTION
# ==========================================

def enregistrer_journal(resultats, statut):

    journal = {
        "agent": "Observateur Actif AI",
        "version": "V2",
        "date_execution": datetime.now(
            timezone.utc
        ).isoformat(),
        "statut_global": statut,
        "nombre_modules": len(MODULES),
        "modules_executes": len(resultats),
        "modules_termines": sum(
            1
            for resultat in resultats
            if resultat["statut"] == "TERMINE"
        ),
        "resultats": resultats
    }

    chemin = DOSSIER_DATA / "journal_execution.json"

    with open(
        chemin,
        "w",
        encoding="utf-8"
    ) as fichier:

        json.dump(
            journal,
            fichier,
            ensure_ascii=False,
            indent=2
        )


# ==========================================
# VALIDATION DES FICHIERS JSON
# ==========================================

def charger_json(chemin):

    if not chemin.exists():
        raise FileNotFoundError(
            f"Fichier absent : {chemin}"
        )

    with open(
        chemin,
        "r",
        encoding="utf-8"
    ) as fichier:

        return json.load(fichier)


def valider_sorties(module):

    for sortie in module.get("sorties", []):

        chemin = RACINE / sortie

        if not chemin.exists():
            raise FileNotFoundError(
                f"Fichier de sortie absent : {sortie}"
            )

        if chemin.stat().st_size == 0:
            raise RuntimeError(
                f"Fichier de sortie vide : {sortie}"
            )

        print("Fichier vérifié :", sortie)

    validation = module.get("validation")

    if validation == "scripts":

        donnees = charger_json(
            RACINE / "data/scripts_generes.json"
        )

        scripts = donnees.get("scripts", [])

        if not scripts:
            raise RuntimeError(
                "Gemini n'a généré aucun script."
            )

        print("Scripts disponibles :", len(scripts))

    elif validation == "audio":

        donnees = charger_json(
            RACINE / "audio/rapport.json"
        )

        audios = donnees.get("audios", [])

        if not audios:
            raise RuntimeError(
                "Aucun fichier audio enregistré."
            )

        for audio in audios:

            fichier = RACINE / audio["fichier_audio"]

            if not fichier.exists():
                raise FileNotFoundError(
                    f"Audio introuvable : {fichier}"
                )

            if fichier.stat().st_size == 0:
                raise RuntimeError(
                    f"Audio vide : {fichier}"
                )

        print("Audios vérifiés :", len(audios))

    elif validation == "video":

        donnees = charger_json(
            RACINE / "videos/rapport.json"
        )

        videos = donnees.get("videos", [])

        if not videos:
            raise RuntimeError(
                "Aucune vidéo produite."
            )

        for video in videos:

            fichier = RACINE / video["fichier_video"]

            if not fichier.exists():
                raise FileNotFoundError(
                    f"Vidéo introuvable : {fichier}"
                )

            if fichier.stat().st_size == 0:
                raise RuntimeError(
                    f"Vidéo vide : {fichier}"
                )

        print("Vidéos vérifiées :", len(videos))


# ==========================================
# EXÉCUTION DES MODULES
# ==========================================

def executer_module(module):

    nom = module["nom"]

    chemin = RACINE / module["fichier"]

    print("\n" + "=" * 60)
    print("MODULE :", nom)
    print("=" * 60)

    if not chemin.exists():

        return {
            "module": nom,
            "statut": "FICHIER_ABSENT"
        }

    debut = datetime.now(
        timezone.utc
    ).isoformat()

    try:

        resultat = subprocess.run(
            [
                sys.executable,
                str(chemin)
            ],
            cwd=RACINE,
            check=False,
            timeout=1200
        )

        if resultat.returncode != 0:

            return {
                "module": nom,
                "statut": "ERREUR",
                "code_retour": resultat.returncode,
                "date_debut": debut
            }

        valider_sorties(module)

        print("\nMODULE TERMINE :", nom)

        return {
            "module": nom,
            "statut": "TERMINE",
            "date_debut": debut,
            "date_fin": datetime.now(
                timezone.utc
            ).isoformat()
        }

    except subprocess.TimeoutExpired:

        return {
            "module": nom,
            "statut": "TIMEOUT",
            "date_debut": debut
        }

    except Exception as erreur:

        print("ERREUR :", str(erreur))

        return {
            "module": nom,
            "statut": "ERREUR_VALIDATION",
            "message": str(erreur),
            "date_debut": debut
        }


# ==========================================
# PROGRAMME PRINCIPAL
# ==========================================

def main():

    print("=" * 60)
    print("OBSERVATEUR ACTIF AI")
    print("AGENT AUTOMATIQUE DE DOCUMENTATION AFRICAINE")
    print("ORCHESTRATEUR V2")
    print("=" * 60)

    resultats = []

    for module in MODULES:

        resultat = executer_module(module)

        resultats.append(resultat)

        if resultat["statut"] != "TERMINE":

            print("\n" + "=" * 60)
            print("PROCESSUS INTERROMPU")
            print("Module défaillant :", module["nom"])
            print("=" * 60)

            enregistrer_journal(
                resultats,
                "ECHEC"
            )

            sys.exit(1)

    print("\n" + "=" * 60)
    print("PRODUCTION TERMINÉE")
    print("=" * 60)

    enregistrer_journal(
        resultats,
        "TERMINE"
    )

    print(
        "Journal :",
        DOSSIER_DATA / "journal_execution.json"
    )


if __name__ == "__main__":
    main()

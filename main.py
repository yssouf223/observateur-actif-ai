
import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone

RACINE = Path(__file__).resolve().parent
DOSSIER_DATA = RACINE / "data"
DOSSIER_DATA.mkdir(parents=True, exist_ok=True)

MODULES = [
    {
        "nom": "Recherche des histoires",
        "fichier": "recherche/moteur.py",
        "sortie": "data/histoires_brutes.json"
    },
    {
        "nom": "Analyse des articles",
        "fichier": "recherche/verification.py",
        "sortie": "data/histoires_analysees.json"
    },
    {
        "nom": "Génération des scripts Gemini",
        "fichier": "intelligence/scripts.py",
        "sortie": "data/scripts_generes.json"
    },
    {
        "nom": "Création des voix off",
        "fichier": "video/voix.py",
        "sortie": None
    },
    {
        "nom": "Recherche des images",
        "fichier": "recherche_images.py",
        "sortie": "data/images_rapport.json"
    },
    {
        "nom": "Montage des vidéos",
        "fichier": "video/montage.py",
        "sortie": None
    }
]


def enregistrer_journal(resultats, statut):
    journal = {
        "agent": "Observateur Actif AI",
        "date_execution": datetime.now(timezone.utc).isoformat(),
        "statut_global": statut,
        "nombre_modules": len(resultats),
        "modules_termines": sum(
            1 for resultat in resultats
            if resultat["statut"] == "TERMINE"
        ),
        "resultats": resultats
    }

    chemin = DOSSIER_DATA / "journal_execution.json"

    with open(chemin, "w", encoding="utf-8") as fichier:
        json.dump(
            journal,
            fichier,
            ensure_ascii=False,
            indent=2
        )


def executer_module(module):
    nom = module["nom"]
    chemin = RACINE / module["fichier"]

    print("\n" + "=" * 60)
    print("MODULE :", nom)
    print("=" * 60)

    if not chemin.exists():
        print("ERREUR : fichier introuvable :", chemin)
        return {
            "module": nom,
            "statut": "FICHIER_ABSENT"
        }

    try:
        resultat = subprocess.run(
            [sys.executable, str(chemin)],
            cwd=RACINE,
            check=False,
            timeout=900
        )

        if resultat.returncode != 0:
            print("ERREUR : le module a échoué.")
            return {
                "module": nom,
                "statut": "ERREUR",
                "code_retour": resultat.returncode
            }

        sortie = module.get("sortie")

        if sortie:
            fichier_sortie = RACINE / sortie

            if not fichier_sortie.exists():
                print("ERREUR : fichier de sortie absent :", sortie)
                return {
                    "module": nom,
                    "statut": "SORTIE_ABSENTE"
                }

            if fichier_sortie.stat().st_size == 0:
                print("ERREUR : fichier de sortie vide :", sortie)
                return {
                    "module": nom,
                    "statut": "SORTIE_VIDE"
                }

        print("MODULE TERMINE :", nom)

        return {
            "module": nom,
            "statut": "TERMINE"
        }

    except subprocess.TimeoutExpired:
        print("ERREUR : délai maximal dépassé.")
        return {
            "module": nom,
            "statut": "TIMEOUT"
        }

    except Exception as erreur:
        print("ERREUR :", str(erreur))
        return {
            "module": nom,
            "statut": "ERREUR",
            "message": str(erreur)
        }


def main():
    print("=" * 60)
    print("OBSERVATEUR ACTIF AI")
    print("AGENT AUTOMATIQUE DE RECHERCHE AFRICAINE")
    print("=" * 60)

    resultats = []

    for module in MODULES:
        resultat = executer_module(module)
        resultats.append(resultat)

        if resultat["statut"] != "TERMINE":
            print("\nPROCESSUS INTERROMPU.")
            print("Module défaillant :", module["nom"])

            enregistrer_journal(
                resultats,
                "ECHEC"
            )

            sys.exit(1)

    print("\n" + "=" * 60)
    print("TOUS LES MODULES ONT TERMINE")
    print("=" * 60)

    enregistrer_journal(
        resultats,
        "TERMINE"
    )

    print("Journal :", DOSSIER_DATA / "journal_execution.json")


if __name__ == "__main__":
    main()


import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone

DOSSIER = Path("data")
DOSSIER.mkdir(exist_ok=True)

def executer_module(nom, fichier):
    print("\n" + "=" * 55)
    print("EXECUTION :", nom)
    print("=" * 55)

    resultat = subprocess.run(
        [sys.executable, fichier],
        check=False
    )

    if resultat.returncode != 0:
        print("ERREUR :", nom)
        return False

    print("TERMINE :", nom)
    return True

def enregistrer_journal(resultats):
    journal = {
        "date_execution": datetime.now(timezone.utc).isoformat(),
        "agent": "Observateur Actif AI",
        "resultats": resultats
    }

    with open(DOSSIER / "journal_execution.json", "w", encoding="utf-8") as fichier:
        json.dump(journal, fichier, ensure_ascii=False, indent=2)

def main():
    print("OBSERVATEUR ACTIF AI")
    print("Démarrage du processus automatique")

    modules = [
        ("Recherche des histoires", "recherche/moteur.py"),
        ("Analyse des articles", "recherche/verification.py"),
        ("Génération des scripts Gemini", "intelligence/scripts.py"),
        ("Création des voix off", "video/voix.py"),
        ("Recherche des images", "recherche_images.py"),
        ("Montage des vidéos", "video/montage.py")
    ]

    resultats = []

    for nom, fichier in modules:
        if not Path(fichier).exists():
            print("FICHIER INTROUVABLE :", fichier)
            resultats.append({
                "module": nom,
                "statut": "FICHIER_ABSENT"
            })
            continue

        succes = executer_module(nom, fichier)

        resultats.append({
            "module": nom,
            "statut": "TERMINE" if succes else "ERREUR"
        })

        if not succes:
            print("Le processus continue avec le module suivant.")

    enregistrer_journal(resultats)

    print("\nPROCESSUS TERMINE")
    print("Consulte data/journal_execution.json")

if __name__ == "__main__":
    main()

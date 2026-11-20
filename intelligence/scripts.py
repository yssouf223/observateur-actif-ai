
import os
import re
import json
import sys
from datetime import datetime, timezone

from google import genai
from google.genai import types

# ==========================================
# OBSERVATEUR ACTIF AI
# GENERATEUR DE SCRIPTS YOUTUBE SHORTS
# ==========================================

API_KEY = os.environ.get("GEMINI_API_KEY")

MODELE = os.environ.get(
    "GEMINI_MODEL",
    "gemini-2.5-flash"
)

ENTREE = "data/histoires_analysees.json"
SORTIE = "data/scripts_generes.json"

SCORE_MINIMUM = 60
CONTENU_MINIMUM = 500

# Un seul Short par exécution.
# Plusieurs candidats peuvent être essayés si nécessaire.
NOMBRE_MAX_CANDIDATS = 5

if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY est absente.")

client = genai.Client(api_key=API_KEY)


INSTRUCTIONS = """
Tu es le scénariste documentaire professionnel
de la chaîne YouTube Observateur Actif.

ZONE :
Toute l'Afrique.

SUJETS PRIORITAIRES :
- Mystères historiques
- Lieux mystérieux
- Civilisations oubliées
- Royaumes anciens
- Histoires étranges
- Phénomènes insolites
- Découvertes archéologiques

MISSION :
Créer un script documentaire YouTube Shorts
de 45 à 60 secondes à partir des informations
documentaires fournies.

RÈGLES ABSOLUES :

1. Ne jamais inventer un fait, une date,
un personnage, un lieu ou un événement.

2. Utiliser uniquement les informations
présentes dans le dossier documentaire.

3. Ne jamais transformer une légende en fait établi.

4. Distinguer les faits historiques,
les hypothèses scientifiques et les traditions orales.

5. Ne jamais inventer de citation.

6. Ne pas présenter une hypothèse comme une certitude.

7. Si les informations sont insuffisantes,
refuser de produire un script.

8. Ne pas inventer de détails pour rendre
l'histoire plus spectaculaire.

9. Le récit doit rester fidèle aux sources.

DURÉE :
La narration doit contenir environ 100 à 130 mots
pour viser 45 à 60 secondes.

STYLE :
Documentaire professionnel, cinématographique,
mystérieux, captivant et rigoureux.

STRUCTURE :
- Accroche forte.
- Présentation du lieu ou de l'événement.
- Développement historique.
- Faits documentés.
- Conclusion intrigante.

RÉPONSE :
Retourner uniquement un JSON valide.

Format obligatoire :

{
  "titre": "",
  "accroche": "",
  "narration": "",
  "description": "",
  "hashtags": [],
  "sources": [],
  "statut_editorial": "A_VERIFIER",
  "motif_refus": ""
}

Ne jamais utiliser le statut VALIDE.
Ne jamais prétendre qu'une histoire est vérifiée
par plusieurs sources si ce n'est pas démontré.
"""


def charger_histoires():

    if not os.path.exists(ENTREE):
        raise FileNotFoundError(
            f"Fichier introuvable : {ENTREE}"
        )

    with open(ENTREE, "r", encoding="utf-8") as fichier:
        donnees = json.load(fichier)

    histoires = donnees.get("histoires", [])

    if not isinstance(histoires, list):
        raise ValueError(
            "Le champ histoires doit être une liste."
        )

    return histoires


def analyser_admissibilite(histoire):

    evaluation = histoire.get("evaluation") or {}
    article = histoire.get("source_analysee") or {}

    score = evaluation.get("score_collecte", 0)

    try:
        score = float(score)
    except (TypeError, ValueError):
        score = 0

    contenu = article.get("contenu", "")

    if not isinstance(contenu, str):
        contenu = ""

    raisons = []

    if score < SCORE_MINIMUM:
        raisons.append("SCORE_INSUFFISANT")

    if len(contenu.strip()) < CONTENU_MINIMUM:
        raisons.append("CONTENU_TROP_COURT")

    if article.get("accessible") is not True:
        raisons.append("ARTICLE_NON_ACCESSIBLE")

    return {
        "admissible": len(raisons) == 0,
        "score": score,
        "longueur": len(contenu),
        "raisons": raisons
    }


def nettoyer_json(texte):

    texte = (texte or "").strip()

    texte = re.sub(
        r"^```(?:json)?\s*",
        "",
        texte,
        flags=re.IGNORECASE
    )

    texte = re.sub(
        r"\s*```$",
        "",
        texte
    )

    return texte.strip()


def valider_script(resultat):

    if not isinstance(resultat, dict):
        raise ValueError("Réponse Gemini incorrecte.")

    champs = [
        "titre",
        "accroche",
        "narration",
        "description"
    ]

    for champ in champs:
        if not isinstance(resultat.get(champ), str):
            raise ValueError(
                f"Champ manquant ou incorrect : {champ}"
            )

    narration = resultat["narration"].strip()

    nombre_mots = len(narration.split())

    if nombre_mots < 95 or nombre_mots > 145:
        raise ValueError(
            f"Durée estimée incorrecte : {nombre_mots} mots."
        )

    if not resultat["titre"].strip():
        raise ValueError("Titre vide.")

    if not resultat["accroche"].strip():
        raise ValueError("Accroche vide.")

    resultat["hashtags"] = (
        resultat.get("hashtags")
        if isinstance(resultat.get("hashtags"), list)
        else []
    )

    resultat["sources"] = (
        resultat.get("sources")
        if isinstance(resultat.get("sources"), list)
        else []
    )

    return resultat


def generer_script(histoire):

    article = histoire.get("source_analysee") or {}

    informations = {
        "titre_initial": histoire.get("titre"),
        "description_initiale": histoire.get("description"),
        "date_publication": histoire.get("date_publication"),
        "date_page": article.get("date_page"),
        "domaine": article.get("domaine"),
        "contenu_article": article.get("contenu"),
        "url_source": histoire.get("source_url")
    }

    prompt = (
        INSTRUCTIONS
        + "\n\nDOSSIER DOCUMENTAIRE :\n"
        + json.dumps(
            informations,
            ensure_ascii=False,
            indent=2
        )
    )

    reponse = client.models.generate_content(
        model=MODELE,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.2,
            response_mime_type="application/json"
        )
    )

    if not reponse.text:
        raise RuntimeError(
            "Gemini a retourné une réponse vide."
        )

    resultat = json.loads(
        nettoyer_json(reponse.text)
    )

    resultat = valider_script(resultat)

    resultat["id_histoire"] = (
        histoire.get("id")
        or "histoire_sans_identifiant"
    )

    resultat["date_generation"] = datetime.now(
        timezone.utc
    ).isoformat()

    resultat["score_collecte"] = analyser_admissibilite(
        histoire
    )["score"]

    resultat["statut_editorial"] = "A_VERIFIER"
    resultat["statut_publication"] = "NON_PUBLIE"

    url = histoire.get("source_url")

    if url and url not in resultat["sources"]:
        resultat["sources"].append(url)

    return resultat


def enregistrer_resultats(scripts, statistiques, erreurs):

    resultat = {
        "agent": "Observateur Actif AI",
        "date_generation": datetime.now(
            timezone.utc
        ).isoformat(),
        "modele": MODELE,
        "nombre_scripts": len(scripts),
        "statistiques": statistiques,
        "erreurs": erreurs,
        "scripts": scripts
    }

    with open(SORTIE, "w", encoding="utf-8") as fichier:
        json.dump(
            resultat,
            fichier,
            ensure_ascii=False,
            indent=2
        )


def executer():

    os.makedirs("data", exist_ok=True)

    histoires = charger_histoires()

    statistiques = {
        "histoires_recues": len(histoires),
        "histoires_admissibles": 0,
        "histoires_rejetees": 0,
        "candidats_essayes": 0
    }

    erreurs = []
    scripts = []

    print("=" * 55)
    print("OBSERVATEUR ACTIF AI - GEMINI")
    print("=" * 55)

    print("Histoires disponibles :", len(histoires))

    candidats = []

    for histoire in histoires:

        evaluation = analyser_admissibilite(histoire)

        if evaluation["admissible"]:
            candidats.append((histoire, evaluation))

        else:
            statistiques["histoires_rejetees"] += 1

    statistiques["histoires_admissibles"] = len(candidats)

    # Priorité aux histoires ayant les meilleurs scores.
    candidats.sort(
        key=lambda element: element[1]["score"],
        reverse=True
    )

    print(
        "Histoires admissibles :",
        statistiques["histoires_admissibles"]
    )

    print(
        "Histoires rejetées :",
        statistiques["histoires_rejetees"]
    )

    if not candidats:
        enregistrer_resultats(
            scripts,
            statistiques,
            ["AUCUNE_HISTOIRE_ADMISSIBLE"]
        )

        print("Aucune histoire ne satisfait les critères.")
        print("Consulte les statistiques du rapport.")

        raise RuntimeError(
            "Aucune histoire admissible pour Gemini."
        )

    for histoire, evaluation in candidats:

        if statistiques["candidats_essayes"] >= NOMBRE_MAX_CANDIDATS:
            break

        statistiques["candidats_essayes"] += 1

        print("\nCandidat :", histoire.get("titre"))
        print("Score :", evaluation["score"])

        try:

            script = generer_script(histoire)

            scripts.append(script)

            print("Script généré avec succès.")

            # Un seul Short par exécution.
            break

        except Exception as erreur:

            message = str(erreur)

            print("Erreur Gemini :", message)

            erreurs.append({
                "titre": histoire.get("titre"),
                "erreur": message
            })

    enregistrer_resultats(
        scripts,
        statistiques,
        erreurs
    )

    print("\n==========================================")
    print("RÉSULTAT DE LA GÉNÉRATION")
    print("==========================================")

    print("Scripts générés :", len(scripts))
    print("Candidats essayés :", statistiques["candidats_essayes"])
    print("Rapport :", SORTIE)

    if not scripts:
        raise RuntimeError(
            "Gemini n'a pas réussi à générer un script."
        )


if __name__ == "__main__":
    executer()

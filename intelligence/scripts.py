
import os
import json
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

if not API_KEY:
    raise RuntimeError(
        "La variable GEMINI_API_KEY est absente."
    )

client = genai.Client(api_key=API_KEY)


INSTRUCTIONS = """
Tu es le scénariste documentaire de la chaîne YouTube
Observateur Actif.

Ta spécialité : les mystères africains, les civilisations
oubliées, les lieux mystérieux, les royaumes anciens,
les découvertes archéologiques et les histoires insolites.

MISSION :
Transformer une histoire documentée en un script
YouTube Shorts de 45 à 60 secondes.

REGLES OBLIGATOIRES :

1. Ne jamais inventer un événement, un personnage,
une date, un lieu ou une découverte.

2. Utiliser uniquement les informations présentes
dans les sources fournies.

3. Ne jamais présenter une légende comme un fait
historiquement établi.

4. Si les sources sont insuffisantes ou contradictoires,
refuser de produire un script publiable.

5. Distinguer clairement les faits, les hypothèses
scientifiques et les traditions orales.

6. Ne jamais inventer de citation.

7. Écrire en français naturel, vivant et accessible.

STRUCTURE DU SHORT :

- Accroche : 0 à 3 secondes.
- Présentation du mystère.
- Développement de l'histoire.
- Faits et éléments documentés.
- Conclusion intrigante.

DUREE :
45 à 60 secondes de narration.

STYLE :
Documentaire professionnel, mystérieux, captivant,
informatif et rigoureux.

REPONSE :
Retourner uniquement un JSON valide avec les champs :

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

Ne jamais mettre statut_editorial à "VALIDE"
sur la seule base d'un article.
"""


def charger_histoires():

    if not os.path.exists(ENTREE):
        print("Aucune histoire analysée disponible.")
        return []

    with open(
        ENTREE,
        "r",
        encoding="utf-8"
    ) as fichier:
        donnees = json.load(fichier)

    return donnees.get("histoires", [])


def histoire_admissible(histoire):

    evaluation = histoire.get("evaluation", {})

    article = histoire.get("source_analysee", {})

    score = evaluation.get("score_collecte", 0)

    contenu = article.get("contenu", "")

    return (
        score >= 60
        and len(contenu) >= 500
        and article.get("accessible", False)
    )


def generer_script(histoire):

    article = histoire.get("source_analysee", {})

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
        + "\n\nINFORMATIONS DOCUMENTAIRES :\n"
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
            temperature=0.3,
            response_mime_type="application/json"
        )
    )

    resultat = json.loads(reponse.text)

    resultat["id_histoire"] = histoire.get("id")

    resultat["date_generation"] = datetime.now(
        timezone.utc
    ).isoformat()

    resultat["statut_publication"] = "NON_PUBLIE"

    resultat["statut_editorial"] = "A_VERIFIER"

    # Une seule source ne suffit pas pour valider
    # automatiquement une histoire.

    return resultat


def executer():

    os.makedirs("data", exist_ok=True)

    histoires = charger_histoires()

    scripts = []

    print("Histoires disponibles :", len(histoires))

    for histoire in histoires:

        if not histoire_admissible(histoire):
            continue

        try:

            print(
                "Génération :",
                histoire.get("titre")
            )

            script = generer_script(histoire)

            scripts.append(script)

        except Exception as erreur:

            print("Erreur Gemini :", erreur)

    resultat = {
        "agent": "Observateur Actif AI",
        "date_generation": datetime.now(
            timezone.utc
        ).isoformat(),
        "nombre_scripts": len(scripts),
        "scripts": scripts
    }

    with open(
        SORTIE,
        "w",
        encoding="utf-8"
    ) as fichier:

        json.dump(
            resultat,
            fichier,
            ensure_ascii=False,
            indent=2
        )

    print("Scripts générés :", len(scripts))


if __name__ == "__main__":
    executer()

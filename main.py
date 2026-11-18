
import os
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from google import genai
from google.genai import types


# ==========================================
# OBSERVATEUR ACTIF AI
# Moteur de recherche journalistique africain
# ==========================================

CHANNEL = "Observateur Actif"
MODEL = "gemini-2.5-flash"

PROMPT = """
Tu es le journaliste d'investigation et documentaliste
de la chaîne YouTube Observateur Actif.

MISSION :
Effectuer une véritable recherche Internet sur toute
l'Afrique afin de découvrir des histoires mystérieuses,
réelles et documentées.

PRIORITÉS ÉDITORIALES :
1. Mystères historiques.
2. Lieux mystérieux.
3. Civilisations oubliées.

SUJETS À EXPLORER :
- Cités anciennes et villes disparues.
- Civilisations et royaumes oubliés.
- Découvertes archéologiques.
- Sites historiques mystérieux.
- Grottes, ruines, monuments et tombeaux.
- Manuscrits et objets historiques.
- Disparitions et événements historiques inexpliqués.
- Mystères africains anciens et contemporains.

MÉTHODE OBLIGATOIRE :

1. Effectue de véritables recherches Google sur Internet.
2. Explore toute l'Afrique, pas seulement l'Afrique de l'Ouest.
3. Recherche en français et en anglais.
4. Consulte les médias, universités, musées,
   institutions historiques et archéologiques,
   UNESCO et publications scientifiques.
5. Lis les informations disponibles dans les sources.
6. Compare les informations entre plusieurs sources.
7. Vérifie les dates, les lieux, les noms et les faits.
8. Distingue clairement les faits établis,
   les hypothèses et les légendes.
9. Ne transforme jamais une légende en fait historique.
10. N'invente jamais une histoire, une citation,
    une date ou une source.
11. Ne donne jamais une URL que tu n'as pas réellement
    trouvée dans tes recherches.

SÉLECTION :
Trouve jusqu'à 8 sujets intéressants.
Privilégie les découvertes récentes et les sujets
historiques qui méritent une enquête approfondie.

Pour chaque sujet, fournis :
- titre
- pays
- lieu précis si connu
- catégorie
- résumé factuel
- faits confirmés
- éléments incertains ou controversés
- intérêt journalistique
- sources : titre, URL et domaine
- niveau de corroboration

IMPORTANT :
Ne prétends pas qu'une histoire est vérifiée si les
sources sont insuffisantes.
Deux sites qui recopient le même article ne sont pas
deux sources indépendantes.
Si tu ne trouves pas assez de preuves, indique-le.

FORMAT DE SORTIE :
Retourne uniquement un objet JSON valide, sans Markdown,
avec cette structure :

{
  "histoires": [
    {
      "titre": "",
      "pays": "",
      "lieu": "",
      "categorie": "",
      "resume": "",
      "faits_confirmes": [],
      "elements_inc ertains": [],
      "interet_journalistique": "",
      "sources": [
        {
          "titre": "",
          "url": "",
          "domaine": ""
        }
      ],
      "niveau_corroboration": ""
    }
  ],
  "bilan_recherche": "",
  "pistes_a_approfondir": []
}

Ne fabrique aucune source.
"""


def get_grounding_sources(response):
    """Récupère les références réellement fournies
    par les résultats de recherche Google."""

    sources = []
    seen = set()

    for candidate in (response.candidates or []):
        metadata = getattr(
            candidate, "grounding_metadata", None
        )

        if not metadata:
            continue

        chunks = getattr(
            metadata, "grounding_chunks", []
        ) or []

        for chunk in chunks:
            web = getattr(chunk, "web", None)

            if not web:
                continue

            url = getattr(web, "uri", "") or ""
            title = getattr(web, "title", "") or ""

            if not url.startswith("http"):
                continue

            if url in seen:
                continue

            seen.add(url)

            domain = urlparse(url).netloc.lower()

            sources.append({
                "titre": title,
                "url": url,
                "domaine": domain
            })

    return sources


def extract_json(text):
    """Extrait le JSON même si le modèle ajoute
    accidentellement des balises Markdown."""

    text = text.strip()

    text = re.sub(
        r"^```(?:json)?\s*",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(r"\s*```$", "", text)

    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1:
        raise ValueError("Réponse JSON introuvable")

    return json.loads(text[start:end + 1])


def verify_candidate_sources(stories, grounding_sources):
    """Ne conserve comme références de recherche
    que les URL effectivement retournées par Google."""

    source_map = {
        source["url"]: source
        for source in grounding_sources
    }

    for story in stories:
        original_sources = story.get("sources", [])
        verified_sources = []

        for source in original_sources:
            url = source.get("url", "").strip()

            if url in source_map:
                verified_sources.append(
                    source_map[url]
                )

        story["sources"] = verified_sources

        domains = {
            source["domaine"]
            for source in verified_sources
        }

        if len(domains) >= 3:
            story["statut_sources"] = (
                "PLUSIEURS_DOMAINES_A_EXAMINER"
            )
        elif len(domains) >= 2:
            story["statut_sources"] = (
                "CORROBORATION_INSUFFISANTE"
            )
        else:
            story["statut_sources"] = (
                "SOURCES_INSUFFISANTES"
            )

        story["publication_autorisee"] = False
        story["verification_humaine_requise"] = True

    return stories


def main():
    print("======================================")
    print("OBSERVATEUR ACTIF AI")
    print("Recherche journalistique sur l'Afrique")
    print("======================================")

    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "Le secret GEMINI_API_KEY est introuvable."
        )

    client = genai.Client(api_key=api_key)

    print("\nRecherche Internet avec Google Search...")

    response = client.models.generate_content(
        model=MODEL,
        contents=PROMPT,
        config=types.GenerateContentConfig(
            tools=[
                types.Tool(
                    google_search=types.GoogleSearch()
                )
            ],
            temperature=0.2
        )
    )

    if not response.text:
        raise RuntimeError(
            "Gemini n'a retourné aucun texte."
        )

    print("Recherche terminée.")
    print("Extraction des sources...")

    grounding_sources = get_grounding_sources(response)

    print(
        "Sources retournées par Google :",
        len(grounding_sources)
    )

    try:
        research = extract_json(response.text)
        stories = research.get("histoires", [])

        stories = verify_candidate_sources(
            stories,
            grounding_sources
        )

        status = (
            "CANDIDATS_A_VERIFIER"
            if stories
            else "AUCUNE_HISTOIRE_EXPLOITABLE"
        )

        research_result = {
            "date_recherche": datetime.now(
                timezone.utc
            ).isoformat(),

            "chaine": CHANNEL,
            "zone": "Toute l'Afrique",
            "moteur_ia": "Google Gemini",
            "moteur_recherche": "Google Search",
            "modele": MODEL,

            "priorite_editoriale": [
                "Mystères historiques",
                "Lieux mystérieux",
                "Civilisations oubliées"
            ],

            "nombre_histoires": len(stories),
            "nombre_sources_recherche": len(
                grounding_sources
            ),

            "histoires": stories,
            "sources_recherche": grounding_sources,

            "bilan_recherche": research.get(
                "bilan_recherche", ""
            ),

            "pistes_a_approfondir": research.get(
                "pistes_a_approfondir", []
            ),

            "statut": status,
            "publication_autorisee": False,

            "avertissement": (
                "Les résultats sont des pistes "
                "journalistiques. Les sources et les faits "
                "doivent être vérifiés avant publication."
            )
        }

    except Exception as error:
        research_result = {
            "date_recherche": datetime.now(
                timezone.utc
            ).isoformat(),

            "chaine": CHANNEL,
            "statut": "ERREUR_FORMAT_REPONSE",
            "erreur": str(error),
            "reponse_brute": response.text,
            "sources_recherche": grounding_sources,
            "publication_autorisee": False
        }

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    output_file = output_dir / "daily_research.json"

    with output_file.open(
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            research_result,
            file,
            ensure_ascii=False,
            indent=2
        )

    print("\n======================================")
    print("RECHERCHE TERMINEE")
    print(
        "Histoires :",
        research_result.get("nombre_histoires", 0)
    )
    print(
        "Sources :",
        research_result.get("nombre_sources_recherche", 0)
    )
    print(
        "Statut :",
        research_result.get("statut")
    )
    print("Publication : DESACTIVEE")
    print("======================================")


if __name__ == "__main__":
    main()

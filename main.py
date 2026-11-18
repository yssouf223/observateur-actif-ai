
import os
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from google import genai


MODEL = "gemini-3.8-flash"
CHANNEL = "Observateur Actif"

PROMPT = """
Tu es le journaliste d'investigation de la chaîne
YouTube Observateur Actif.

Effectue une véritable enquête sur Internet concernant
les mystères africains réels et documentés.

ZONE : toute l'Afrique, les 54 pays.

PRIORITES :
1. Mystères historiques.
2. Lieux mystérieux.
3. Civilisations oubliées.

EXPLORE :
- Cités perdues et royaumes anciens.
- Découvertes archéologiques.
- Grottes, ruines et monuments mystérieux.
- Manuscrits et objets historiques.
- Disparitions historiques documentées.
- Phénomènes historiques inexpliqués.
- Découvertes récentes en Afrique.
- Mystères anciens et contemporains.

METHODE :
1. Effectue plusieurs recherches Google.
2. Recherche en français et en anglais.
3. Consulte les médias, universités, musées,
   institutions archéologiques et UNESCO.
4. Lis et compare les informations disponibles.
5. Vérifie les dates, lieux et personnages.
6. Distingue faits, hypothèses et légendes.
7. Cherche des sources indépendantes.
8. Ne confonds pas plusieurs articles qui recopient
   la même dépêche avec plusieurs preuves.
9. N'invente jamais de faits ni de références.
10. Si les preuves sont insuffisantes, dis-le.

Sélectionne jusqu'à 8 histoires intéressantes.
Privilégie les sujets sérieux et documentés.

Pour chaque histoire, retourne :
- titre
- pays
- lieu
- categorie
- resume
- faits_confirmes
- elements_inc ertains
- interet_journalistique
- sources (titre et URL)
- limites_de_verification

Retourne uniquement un JSON valide :

{
  "histoires": [],
  "bilan_recherche": "",
  "pistes_a_approfondir": []
}
"""


def extract_json(text):
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

    if start < 0 or end < 0:
        raise ValueError("JSON introuvable dans la réponse")

    return json.loads(text[start:end + 1])


def extract_citations(interaction):
    citations = []
    seen = set()

    for step in getattr(interaction, "steps", []) or []:
        if getattr(step, "type", "") != "model_output":
            continue

        for block in getattr(step, "content", []) or []:
            for annotation in (
                getattr(block, "annotations", []) or []
            ):
                if getattr(annotation, "type", "") != "url_citation":
                    continue

                url = getattr(annotation, "url", "") or ""

                if not url.startswith("http") or url in seen:
                    continue

                seen.add(url)

                citations.append({
                    "titre": getattr(annotation, "title", "") or "",
                    "url": url,
                    "domaine": urlparse(url).netloc.lower()
                })

    return citations


def main():
    print("======================================")
    print("OBSERVATEUR ACTIF AI")
    print("Recherche journalistique africaine")
    print("======================================")

    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "Secret GEMINI_API_KEY introuvable"
        )

    client = genai.Client(api_key=api_key)

    print("Recherche Google en cours...")

    interaction = client.interactions.create(
        model=MODEL,
        input=PROMPT,
        tools=[
            {"type": "google_search"}
        ]
    )

    response_text = interaction.output_text

    if not response_text:
        raise RuntimeError(
            "Gemini n'a retourné aucun texte"
        )

    print("Recherche terminée.")
    print("Lecture des références...")

    citations = extract_citations(interaction)

    print("Citations trouvées :", len(citations))

    try:
        research = extract_json(response_text)
        stories = research.get("histoires", [])

        citation_urls = {
            item["url"] for item in citations
        }

        for story in stories:
            original_sources = story.get("sources", [])

            matched_sources = []

            for source in original_sources:
                url = source.get("url", "").strip()

                if url in citation_urls:
                    matched_sources.append(source)

            story["sources_citees_dans_reponse"] = (
                matched_sources
            )

            domains = {
                urlparse(source["url"]).netloc.lower()
                for source in matched_sources
            }

            story["nombre_domaines_cites"] = len(domains)

            story["verification_humaine_requise"] = True
            story["publication_autorisee"] = False

            if len(domains) >= 3:
                story["statut_sources"] = (
                    "PLUSIEURS_DOMAINES_A_CONTROLER"
                )
            elif len(domains) == 2:
                story["statut_sources"] = (
                    "DEUX_DOMAINES_A_CONTROLER"
                )
            else:
                story["statut_sources"] = (
                    "CORROBORATION_INSUFFISANTE"
                )

        result = {
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
            "nombre_sources": len(citations),

            "histoires": stories,
            "sources_recherche": citations,

            "bilan_recherche": research.get(
                "bilan_recherche", ""
            ),

            "pistes_a_approfondir": research.get(
                "pistes_a_approfondir", []
            ),

            "statut": (
                "CANDIDATS_A_VERIFIER"
                if stories else "AUCUN_RESULTAT"
            ),

            "publication_autorisee": False
        }

    except Exception as error:
        result = {
            "date_recherche": datetime.now(
                timezone.utc
            ).isoformat(),
            "chaine": CHANNEL,
            "statut": "ERREUR_FORMAT_REPONSE",
            "erreur": str(error),
            "reponse_brute": response_text,
            "sources_recherche": citations,
            "publication_autorisee": False
        }

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    with open(
        output_dir / "daily_research.json",
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            result,
            file,
            ensure_ascii=False,
            indent=2
        )

    print("======================================")
    print("RECHERCHE TERMINEE")
    print("Histoires :", result.get("nombre_histoires", 0))
    print("Sources :", result.get("nombre_sources", 0))
    print("Statut :", result.get("statut"))
    print("Publication : DESACTIVEE")
    print("======================================")


if __name__ == "__main__":
    main()

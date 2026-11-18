
import os
import re
import json
import time
import html
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

# ==========================================================
# OBSERVATEUR ACTIF AI
# Recherche quotidienne de mystères historiques africains
# Publication YouTube : DÉSACTIVÉE
# ==========================================================

MODEL = "gemini-3.8-flash"
MAX_RESULTS = 35
MAX_ARTICLES_TO_READ = 12
MAX_TEXT_PER_ARTICLE = 5000

OUTPUT_DIR = Path("output")
OUTPUT_FILE = OUTPUT_DIR / "daily_research.json"

SEARCHES = [
    ("Africa ancient archaeology discovery", "en-US", "US", "en"),
    ("Africa forgotten kingdoms ancient civilizations", "en-US", "US", "en"),
    ("Africa mysterious historical places ruins", "en-US", "US", "en"),
    ("African archaeological discoveries ancient cities", "en-US", "US", "en"),
    ("mystères historiques Afrique civilisations anciennes", "fr-FR", "FR", "fr"),
    ("sites mystérieux Afrique découvertes archéologiques", "fr-FR", "FR", "fr"),
    ("royaumes oubliés Afrique histoire archéologie", "fr-FR", "FR", "fr"),
    ("découverte archéologique Afrique ancienne civilisation", "fr-FR", "FR", "fr"),
]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def clean_text(value):
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


class ArticleTextParser(HTMLParser):
    """Extraction simple du texte visible d'une page web."""

    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip_depth = 0
        self.skip_tags = {"script", "style", "noscript", "svg", "nav", "footer"}

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self.skip_tags:
            self.skip_depth += 1

    def handle_endtag(self, tag):
        if tag.lower() in self.skip_tags and self.skip_depth:
            self.skip_depth -= 1

    def handle_data(self, data):
        if not self.skip_depth:
            text = data.strip()
            if text:
                self.parts.append(text)


def fetch_url(url, timeout=15):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (compatible; ObservateurActifAI/1.0; "
                "+https://github.com/yssouf223/observateur-actif-ai)"
            )
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def read_rss(query, language, country, edition):
    params = {
        "q": query,
        "hl": language,
        "gl": country,
        "ceid": f"{country}:{edition}",
    }
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(params)

    try:
        raw = fetch_url(url)
        root = ET.fromstring(raw)
    except Exception as exc:
        print(f"[RSS] Échec pour « {query} » : {exc}")
        return []

    results = []

    for item in root.findall(".//item"):
        title = clean_text(item.findtext("title", ""))
        link = (item.findtext("link", "") or "").strip()
        pub_date = clean_text(item.findtext("pubDate", ""))
        description = clean_text(item.findtext("description", ""))

        source_element = item.find("source")
        source = clean_text(source_element.text if source_element is not None else "")

        if not title or not link:
            continue

        results.append({
            "title": title,
            "url": link,
            "date": pub_date,
            "publisher": source or "Éditeur non précisé",
            "rss_description": description[:1500],
            "article_text": "",
            "article_full_text_fetched": False,
            "search_query": query,
        })

    print(f"[RSS] {len(results)} résultat(s) : {query}")
    return results


def deduplicate(items):
    unique = []
    seen_urls = set()
    seen_titles = set()

    for item in items:
        url = item["url"].split("&utm_")[0].rstrip("/")
        title_key = re.sub(r"\W+", "", item["title"].lower())

        if url in seen_urls or title_key in seen_titles:
            continue

        seen_urls.add(url)
        seen_titles.add(title_key)
        item["url"] = url
        unique.append(item)

    return unique


def fetch_article_text(item):
    try:
        raw = fetch_url(item["url"], timeout=15)
        content_type = ""

        # Les pages HTML sont généralement encodées en UTF-8.
        page = raw.decode("utf-8", errors="replace")

        parser = ArticleTextParser()
        parser.feed(page)
        text = re.sub(r"\s+", " ", " ".join(parser.parts)).strip()

        if len(text) >= 500:
            item["article_text"] = text[:MAX_TEXT_PER_ARTICLE]
            item["article_full_text_fetched"] = True
            return

        item["fetch_note"] = "Page accessible, mais texte exploitable insuffisant."

    except Exception as exc:
        item["fetch_note"] = f"Article non récupéré : {str(exc)[:180]}"

    item["article_full_text_fetched"] = False


def extract_json(text):
    if not text:
        raise ValueError("Gemini n'a renvoyé aucun texte.")

    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}|\[.*\]", cleaned, re.DOTALL)
        if not match:
            raise ValueError("Réponse Gemini non reconnue comme JSON.")
        return json.loads(match.group(0))


def analyze_with_gemini(items):
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        return {
            "status": "NON_CONFIGURE",
            "error": "Le secret GEMINI_API_KEY est absent.",
            "stories": [],
        }

    from google import genai

    client = genai.Client(api_key=api_key)

    sources = []
    for index, item in enumerate(items, start=1):
        sources.append({
            "source_id": index,
            "title": item["title"],
            "publisher": item["publisher"],
            "date": item["date"],
            "url": item["url"],
            "rss_description": item["rss_description"],
            "article_text": item["article_text"],
            "article_full_text_fetched": item["article_full_text_fetched"],
        })

    prompt = f"""
Tu es le rédacteur en chef et documentaliste de la chaîne africaine
Observateur Actif.

MISSION :
Analyser les résultats de recherche fournis ci-dessous pour trouver
des sujets authentiques adaptés à des vidéos YouTube Shorts de 45 à 60 secondes.

THÈMES PRIORITAIRES :
1. Mystères historiques africains.
2. Lieux mystérieux en Afrique.
3. Civilisations et royaumes oubliés.
4. Découvertes archéologiques africaines.

RÈGLES STRICTES :
- Ne crée aucune histoire et n'invente aucun fait.
- N'ajoute aucune date, personne, citation ou découverte absente des sources.
- Distingue les faits établis, les hypothèses et les légendes.
- Une légende ou une tradition orale ne doit jamais être présentée comme un fait prouvé.
- Un titre sensationnel n'est pas une preuve.
- Si le contenu intégral d'un article n'a pas été récupéré, indique-le.
- Ne prétends pas avoir consulté une page si son texte n'est pas fourni.
- N'invente jamais de sources ou d'URL.
- Utilise uniquement les URL présentes dans les résultats ci-dessous.
- Si les éléments sont insuffisants, écarte le sujet.
- Ne transforme pas une simple coïncidence en mystère historique.
- Privilégie les sujets africains clairement localisables.

ÉVALUE CHAQUE SUJET :
- intérêt historique ;
- qualité des informations disponibles ;
- niveau de fiabilité ;
- présence d'incertitudes ;
- possibilité de raconter le sujet en 45 à 60 secondes.

RENVOIE UNIQUEMENT UN JSON VALIDE avec cette structure :

{{
  "editorial_summary": "Résumé bref de la recherche",
  "stories": [
    {{
      "title": "Titre factuel du sujet",
      "country": "Pays africain ou pays non déterminé",
      "location": "Lieu précis ou non déterminé",
      "category": "Mystère historique, lieu mystérieux ou civilisation oubliée",
      "short_summary": "Résumé factuel",
      "established_facts": ["Fait établi 1", "Fait établi 2"],
      "hypotheses_or_legends": ["Hypothèse ou légende, si présente"],
      "unknowns": ["Ce qui reste inconnu"],
      "reliability": "Élevée, moyenne ou faible",
      "editorial_decision": "À APPROFONDIR ou À ÉCARTER",
      "reason": "Justification de la décision",
      "source_ids": [1, 2],
      "source_urls": ["URL exacte fournie dans les résultats"]
    }}
  ]
}}

IMPORTANT :
- N'invente pas de corroboration indépendante.
- Si une seule source est disponible, dis-le.
- Si aucune histoire n'est suffisamment documentée, renvoie une liste stories vide.
- Ne rédige pas encore de scénario vidéo.

RÉSULTATS RSS ET EXTRAITS D'ARTICLES :
{json.dumps(sources, ensure_ascii=False)}
"""

    try:
        interaction = client.interactions.create(
            model=MODEL,
            input=prompt,
        )

        answer = interaction.output_text or ""
        parsed = extract_json(answer)

        if isinstance(parsed, list):
            parsed = {"editorial_summary": "", "stories": parsed}

        if not isinstance(parsed, dict):
            raise ValueError("Le JSON Gemini n'a pas le format attendu.")

        # Sécurité : seules les URL réellement fournies sont autorisées.
        allowed_urls = {item["url"] for item in items}
        safe_stories = []

        for story in parsed.get("stories", []):
            if not isinstance(story, dict):
                continue

            valid_urls = [
                url for url in story.get("source_urls", [])
                if url in allowed_urls
            ]

            valid_ids = [
                source_id for source_id in story.get("source_ids", [])
                if isinstance(source_id, int) and 1 <= source_id <= len(items)
            ]

            story["source_urls"] = valid_urls
            story["source_ids"] = valid_ids

            if not valid_urls:
                story["editorial_decision"] = "À ÉCARTER"
                story["reason"] = (
                    "Aucune URL source vérifiable parmi les résultats fournis."
                )

            safe_stories.append(story)

        return {
            "status": "SUCCÈS",
            "model": MODEL,
            "editorial_summary": parsed.get("editorial_summary", ""),
            "stories": safe_stories,
        }

    except Exception as exc:
        return {
            "status": "ÉCHEC_ANALYSE_GEMINI",
            "model": MODEL,
            "error": str(exc)[:1000],
            "stories": [],
        }


def main():
    print("=" * 60)
    print("OBSERVATEUR ACTIF AI — RECHERCHE QUOTIDIENNE")
    print("=" * 60)

    collected = []

    for query, language, country, edition in SEARCHES:
        collected.extend(read_rss(query, language, country, edition))
        time.sleep(1)

    collected = deduplicate(collected)[:MAX_RESULTS]

    print(f"\nTotal de résultats uniques : {len(collected)}")

    # Récupération limitée des pages pour éviter trop de requêtes.
    for index, item in enumerate(collected[:MAX_ARTICLES_TO_READ], start=1):
        print(f"[ARTICLE {index}/{min(len(collected), MAX_ARTICLES_TO_READ)}] "
              f"{item['title'][:90]}")
        fetch_article_text(item)
        time.sleep(0.5)

    analysis = analyze_with_gemini(collected)

    report = {
        "date_recherche": now_iso(),
        "chaine": "Observateur Actif",
        "zone": "Toute l'Afrique",
        "priorite_editoriale": [
            "Mystères historiques",
            "Lieux mystérieux",
            "Civilisations oubliées",
        ],
        "duree_shorts": "45 à 60 secondes",
        "nombre_resultats": len(collected),
        "nombre_articles_integralement_recuperes": sum(
            1 for item in collected if item["article_full_text_fetched"]
        ),
        "statut_recherche": (
            "RESULTATS_COLLECTES" if collected else "AUCUN_RESULTAT"
        ),
        "analyse_ia": analysis,
        "sources_brutes": collected,
        "publication_youtube": {
            "active": False,
            "raison": "Publication désactivée pendant la phase de vérification.",
        },
        "avertissement": (
            "Les résultats RSS sont des pistes de recherche. "
            "Ils ne constituent pas à eux seuls une vérification historique. "
            "Les faits doivent être contrôlés avec des sources fiables "
            "et indépendantes avant toute publication."
        ),
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("\n" + "=" * 60)
    print("RECHERCHE TERMINÉE")
    print(f"Résultats collectés : {len(collected)}")
    print(
        "Articles récupérés : "
        f"{report['nombre_articles_integralement_recuperes']}"
    )
    print(f"Analyse Gemini : {analysis['status']}")
    print(f"Rapport : {OUTPUT_FILE}")
    print("Publication YouTube : DÉSACTIVÉE")
    print("=" * 60)


if __name__ == "__main__":
    main()

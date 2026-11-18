
import os
import re
import json
import time
import html
import urllib.parse
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

from google import genai


# ============================================================
# OBSERVATEUR ACTIF AI
# Recherche documentaire quotidienne sur les mystères africains
# Publication YouTube volontairement désactivée
# ============================================================

CHANNEL = "Observateur Actif"
MODEL = "gemini-3.8-flash"
MAX_RESULTS_PER_QUERY = 4
MAX_ARTICLES_TO_OPEN = 12
MIN_ARTICLE_TEXT = 500
OUTPUT_FILE = "output/daily_research.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}


# Recherches réparties sur différentes régions africaines.
# La date limite est calculée automatiquement.
def build_searches():
    since = (datetime.now(timezone.utc) - timedelta(days=730)).date()
    date_filter = f"after:{since.isoformat()}"

    return [
        ("Afrique de l'Ouest - français",
         f"mystère historique découverte archéologique Afrique de l'Ouest {date_filter}"),
        ("Afrique de l'Ouest - anglais",
         f"West Africa archaeological discovery ancient civilization mystery {date_filter}"),
        ("Afrique du Nord - français",
         f"Égypte Maroc Algérie Tunisie site antique découverte archéologique {date_filter}"),
        ("Afrique du Nord - anglais",
         f"North Africa ancient ruins archaeological discovery historical mystery {date_filter}"),
        ("Afrique centrale - français",
         f"Afrique centrale civilisation oubliée site historique découverte {date_filter}"),
        ("Afrique centrale - anglais",
         f"Central Africa ancient kingdom archaeological discovery historical mystery {date_filter}"),
        ("Afrique de l'Est - anglais",
         f"East Africa ancient civilization lost city archaeological discovery {date_filter}"),
        ("Afrique australe - anglais",
         f"Southern Africa ancient ruins forgotten civilization archaeological discovery {date_filter}"),
        ("Afrique - français",
         f"mystère historique africain civilisation oubliée lieu mystérieux {date_filter}"),
        ("Afrique - anglais",
         f"African historical mystery ancient site forgotten civilization discovery {date_filter}"),
    ]


def clean_text(value):
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def fetch_url(url, timeout=18):
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        content = response.read()
        final_url = response.geturl()
        content_type = response.headers.get("Content-Type", "")
        return content, final_url, content_type


def parse_date(value):
    if not value:
        return None
    try:
        date = parsedate_to_datetime(value)
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        return date.astimezone(timezone.utc).isoformat()
    except Exception:
        return None


def google_news_search(query, region):
    encoded = urllib.parse.quote(query)
    url = (
        "https://news.google.com/rss/search?q="
        + encoded
        + "&hl=fr&gl=FR&ceid=FR:fr"
    )

    try:
        content, _, _ = fetch_url(url, timeout=20)
        root = ET.fromstring(content)
        results = []

        for item in root.findall(".//item"):
            title = clean_text(item.findtext("title", ""))
            link = (item.findtext("link", "") or "").strip()
            description = clean_text(item.findtext("description", ""))
            pub_date = parse_date(item.findtext("pubDate", ""))

            source_element = item.find("source")
            publisher = ""
            if source_element is not None:
                publisher = clean_text(source_element.text or "")

            if not title or not link:
                continue

            results.append({
                "title": title,
                "rss_url": link,
                "publisher": publisher,
                "description": description[:1200],
                "published_at": pub_date,
                "search_region": region,
                "search_query": query,
                "publisher_url": None,
                "article_text": "",
                "article_full_text_fetched": False,
                "fetch_status": "NON CONSULTÉ",
            })

        return results

    except Exception as error:
        print(f"Erreur RSS ({region}) : {error}")
        return []


class ArticleParser(HTMLParser):
    """Extraction simple du texte visible d'une page web."""

    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip_depth = 0
        self.article_depth = 0
        self.main_depth = 0
        self.in_article = False
        self.in_main = False
        self.meta_description = ""
        self.meta_og_description = ""

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag in ("script", "style", "noscript", "svg", "nav",
                   "footer", "header", "aside", "form"):
            self.skip_depth += 1

        if tag == "article":
            self.article_depth += 1
            self.in_article = True

        if tag == "main":
            self.main_depth += 1
            self.in_main = True

        if tag == "meta":
            name = (attrs.get("name") or "").lower()
            prop = (attrs.get("property") or "").lower()
            content = attrs.get("content", "")

            if name == "description":
                self.meta_description = content
            if prop == "og:description":
                self.meta_og_description = content

        if tag in ("p", "br", "div", "h1", "h2", "h3", "li"):
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg", "nav",
                   "footer", "header", "aside", "form"):
            self.skip_depth = max(0, self.skip_depth - 1)

        if tag == "article":
            self.article_depth = max(0, self.article_depth - 1)
            self.in_article = self.article_depth > 0

        if tag == "main":
            self.main_depth = max(0, self.main_depth - 1)
            self.in_main = self.main_depth > 0

        if tag in ("p", "br", "div", "h1", "h2", "h3", "li"):
            self.parts.append(" ")

    def handle_data(self, data):
        if self.skip_depth == 0:
            self.parts.append(data)


def resolve_and_read_article(item):
    """Tente de résoudre le lien Google News puis de lire l'article."""

    try:
        content, final_url, content_type = fetch_url(item["rss_url"])

        final_host = (urlparse(final_url).hostname or "").lower()

        if final_host.endswith("news.google.com"):
            item["fetch_status"] = "REDIRECTION GOOGLE NEWS NON RÉSOLUE"
            return item

        if "html" not in content_type.lower() and b"<html" not in content[:1000].lower():
            item["fetch_status"] = "FORMAT NON HTML"
            item["publisher_url"] = final_url
            return item

        charset_match = re.search(
            r"charset=([a-zA-Z0-9_-]+)", content_type, re.IGNORECASE
        )
        encoding = charset_match.group(1) if charset_match else "utf-8"

        try:
            page = content.decode(encoding, errors="replace")
        except Exception:
            page = content.decode("utf-8", errors="replace")

        parser = ArticleParser()
        parser.feed(page)

        text_content = re.sub(
            r"\s+", " ", " ".join(parser.parts)
        ).strip()

        # Priorité au contenu réellement récupéré sur la page.
        article_text = text_content

        if len(article_text) < MIN_ARTICLE_TEXT:
            item["fetch_status"] = "TEXTE INSUFFISANT"
            item["publisher_url"] = final_url
            item["description_page"] = clean_text(
                parser.meta_og_description or parser.meta_description
            )[:1500]
            return item

        item["publisher_url"] = final_url
        item["article_text"] = article_text[:9000]
        item["article_full_text_fetched"] = True
        item["fetch_status"] = "TEXTE RÉCUPÉRÉ"

    except urllib.error.HTTPError as error:
        item["fetch_status"] = f"ERREUR HTTP {error.code}"
    except Exception as error:
        item["fetch_status"] = f"ERREUR DE LECTURE : {str(error)[:150]}"

    return item


def extract_json(text):
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1 or end <= start:
        raise ValueError("Gemini n'a pas retourné un JSON valide.")

    return json.loads(text[start:end + 1])


def get_response_text(response):
    output_text = getattr(response, "output_text", None)
    if output_text:
        return output_text

    collected = []
    output = getattr(response, "output", None) or []

    for item in output:
        content = getattr(item, "content", None) or []
        for part in content:
            text_value = getattr(part, "text", None)
            if text_value:
                collected.append(text_value)

    return "\n".join(collected)


def analyze_with_gemini(items):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("La variable GEMINI_API_KEY est absente.")

    client = genai.Client(api_key=api_key)

    source_list = []
    for index, item in enumerate(items, start=1):
        source_list.append({
            "source_id": index,
            "title": item["title"],
            "publisher": item["publisher"],
            "publisher_url": item["publisher_url"],
            "rss_url": item["rss_url"],
            "published_at": item["published_at"],
            "search_region": item["search_region"],
            "description": item["description"][:700],
            "article_full_text_fetched": item["article_full_text_fetched"],
            "article_text": item["article_text"][:7000],
            "fetch_status": item["fetch_status"],
        })

    prompt = f"""
Tu es le documentaliste et vérificateur de faits de la chaîne YouTube
francophone Observateur Actif.

MISSION :
Repérer des histoires africaines réelles et documentées pour des vidéos
YouTube Shorts de 45 à 60 secondes.

PRIORITÉS :
1. Mystères historiques.
2. Lieux mystérieux.
3. Civilisations oubliées.

ZONE :
Tout le continent africain : Afrique du Nord, de l'Ouest, centrale,
de l'Est et australe.

RÈGLES ABSOLUES :
- Ne jamais inventer une histoire, un lieu, une date, un nom ou une citation.
- Ne pas confondre une hypothèse avec un fait établi.
- Ne pas présenter une légende comme un fait historique.
- Ne pas affirmer qu'une information est corroborée si les textes fournis
  ne le démontrent pas.
- Utiliser exclusivement les sources numérotées ci-dessous.
- Ne jamais inventer de source, d'URL ou de numéro source.
- Une page dont le texte intégral n'a pas été récupéré ne constitue pas
  une preuve suffisante.
- Si les informations sont insuffisantes, choisir
  "EN ATTENTE DE VÉRIFICATION".
- Si l'information est hors d'Afrique ou sans rapport avec les thèmes,
  l'écarter.
- Distinguer clairement les faits, les hypothèses et les légendes.
- Ne pas inventer de détails pour rendre une histoire plus spectaculaire.

IMPORTANT :
Si une source a article_full_text_fetched = false, tu ne peux pas
la considérer comme une source documentaire lue.
Ne prétends jamais avoir lu un article dont le texte est absent.

SOURCES DISPONIBLES :
{json.dumps(source_list, ensure_ascii=False)}

Réponds uniquement avec un JSON valide ayant exactement cette structure :

{{
  "resume_recherche": "Résumé honnête de la qualité des sources",
  "histoires": [
    {{
      "titre": "Titre factuel",
      "pays": "Pays africain",
      "region_afrique": "Région",
      "periode_historique": "Période ou date si connue",
      "resume_factuel": "Résumé prudent des faits documentés",
      "faits_confirmes": ["Fait réellement soutenu par les textes lus"],
      "hypotheses_ou_incertitudes": ["Ce qui reste incertain"],
      "nature": "Mystère historique, lieu mystérieux ou civilisation oubliée",
      "source_ids": [1, 2],
      "decision_editoriale": "EN ATTENTE DE VÉRIFICATION",
      "raison_decision": "Explication précise",
      "idee_accroche": "Accroche prudente pour un Short",
      "potentiel_short": "Faible, moyen ou élevé"
    }}
  ]
}}

Ne retourne pas plus de 5 histoires.
Si aucune histoire n'est suffisamment documentée, retourne une liste vide.
Ne transforme pas une simple manchette en fait historique.
"""

    response = client.interactions.create(
        model=MODEL,
        input=prompt
    )

    return extract_json(get_response_text(response))


def validate_analysis(analysis, items):
    """Les URL affichées proviennent toujours de nos propres sources."""

    valid_stories = []
    total_sources = len(items)

    for story in analysis.get("histoires", []):
        ids = story.get("source_ids", [])

        if not isinstance(ids, list):
            ids = []

        valid_ids = []
        for value in ids:
            if isinstance(value, int) and 1 <= value <= total_sources:
                if value not in valid_ids:
                    valid_ids.append(value)

        selected_sources = [items[i - 1] for i in valid_ids]

        read_sources = [
            source for source in selected_sources
            if source.get("article_full_text_fetched")
        ]

        domains = set()
        for source in read_sources:
            host = urlparse(source.get("publisher_url") or "").hostname
            if host:
                domains.add(host.lower().removeprefix("www."))

        story["source_ids"] = valid_ids
        story["sources"] = [
            {
                "source_id": i,
                "title": items[i - 1]["title"],
                "publisher": items[i - 1]["publisher"],
                "url": (
                    items[i - 1]["publisher_url"]
                    or items[i - 1]["rss_url"]
                ),
                "article_full_text_fetched":
                    items[i - 1]["article_full_text_fetched"],
            }
            for i in valid_ids
        ]

        story["nombre_articles_lus"] = len(read_sources)
        story["nombre_domaines_distincts"] = len(domains)

        # Aucun sujet ne devient automatiquement vérifié.
        story["decision_editoriale"] = "EN ATTENTE DE VÉRIFICATION"

        if not read_sources:
            story["raison_controle"] = (
                "Aucun texte intégral de source n'a été récupéré."
            )
        elif len(read_sources) < 2:
            story["raison_controle"] = (
                "Une seule source a été lue : corroboration insuffisante."
            )
        elif len(domains) < 2:
            story["raison_controle"] = (
                "Les sources lues ne proviennent pas de deux domaines distincts."
            )
        else:
            story["raison_controle"] = (
                "Plusieurs textes ont été récupérés, mais une vérification "
                "humaine de leur indépendance et de leurs affirmations reste nécessaire."
            )

        valid_stories.append(story)

    return valid_stories


def main():
    os.makedirs("output", exist_ok=True)

    now = datetime.now(timezone.utc)
    print("=" * 60)
    print("OBSERVATEUR ACTIF AI - RECHERCHE DOCUMENTAIRE")
    print("Date UTC :", now.isoformat())
    print("=" * 60)

    all_results = []
    seen = set()
    query_stats = []

    searches = build_searches()

    # Chaque recherche dispose de son propre quota.
    for region, query in searches:
        print(f"Recherche : {region}")
        results = google_news_search(query, region)

        added = 0
        for item in results:
            key = re.sub(r"\W+", "", item["title"].lower())

            if key and key not in seen:
                seen.add(key)
                all_results.append(item)
                added += 1

            if added >= MAX_RESULTS_PER_QUERY:
                break

        query_stats.append({
            "region": region,
            "resultats_recus": len(results),
            "resultats_ajoutes": added,
        })

        time.sleep(1)

    print("Résultats uniques :", len(all_results))

    # On tente de lire les articles les plus récents en premier.
    all_results.sort(
        key=lambda x: x.get("published_at") or "",
        reverse=True
    )

    for index, item in enumerate(all_results[:MAX_ARTICLES_TO_OPEN], start=1):
        print(f"Lecture article {index}/{min(len(all_results), MAX_ARTICLES_TO_OPEN)}")
        resolve_and_read_article(item)
        time.sleep(1)

    read_count = sum(
        1 for item in all_results
        if item["article_full_text_fetched"]
    )

    report = {
        "date_recherche": now.isoformat(),
        "chaine": CHANNEL,
        "zone": "Toute l'Afrique",
        "priorite_editoriale": [
            "Mystères historiques",
            "Lieux mystérieux",
            "Civilisations oubliées",
        ],
        "duree_shorts": "45 à 60 secondes",
        "nombre_recherches": len(searches),
        "statistiques_recherche": query_stats,
        "nombre_resultats": len(all_results),
        "nombre_articles_tentes": min(
            len(all_results), MAX_ARTICLES_TO_OPEN
        ),
        "nombre_articles_integralement_recuperes": read_count,
        "sources": all_results,
        "analyse_ia": {
            "status": "NON EFFECTUÉE",
            "modele": MODEL,
            "histoires": [],
        },
        "publication_youtube": {
            "active": False,
            "raison": "Publication désactivée jusqu'à validation humaine."
        },
    }

    try:
        analysis = analyze_with_gemini(all_results)
        stories = validate_analysis(analysis, all_results)

        report["analyse_ia"] = {
            "status": "SUCCÈS",
            "modele": MODEL,
            "resume_recherche": analysis.get("resume_recherche", ""),
            "nombre_histoires_proposees": len(stories),
            "histoires": stories,
        }

    except Exception as error:
        report["analyse_ia"] = {
            "status": "ÉCHEC",
            "modele": MODEL,
            "erreur": str(error)[:1000],
            "histoires": [],
        }
        print("Erreur analyse Gemini :", error)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)

    print("=" * 60)
    print("RECHERCHE TERMINÉE")
    print("Résultats :", len(all_results))
    print("Articles lus :", read_count)
    print("Analyse IA :", report["analyse_ia"]["status"])
    print("Rapport :", OUTPUT_FILE)
    print("Publication YouTube : DÉSACTIVÉE")
    print("=" * 60)


if __name__ == "__main__":
    main()

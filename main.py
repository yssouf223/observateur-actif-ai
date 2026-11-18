
import os
import re
import json
import time
import html
import logging
import requests
import xml.etree.ElementTree as ET

from datetime import datetime, timezone
from urllib.parse import quote, urlparse
from html.parser import HTMLParser
from google import genai

# ============================================================
# OBSERVATEUR ACTIF AI — V8
# Recherche Internet + analyse historique + dossier audiovisuel
# ============================================================

CHANNEL = "Observateur Actif"
MODEL = "gemini-3.8-flash"
OUTPUT_FILE = "output/daily_research.json"

MAX_RESULTS_PER_QUERY = 6
MAX_ARTICLES_TO_OPEN = 35
MAX_ARTICLES_FOR_AI = 15
MIN_ARTICLE_TEXT = 500
TIMEOUT = 25
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/125.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr,en;q=0.9"
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

AFRICAN_COUNTRIES = [
    "Algérie", "Algeria", "Angola", "Bénin", "Benin", "Botswana",
    "Burkina Faso", "Burundi", "Cabo Verde", "Cape Verde", "Cameroun",
    "Cameroon", "République centrafricaine", "Central African Republic",
    "Tchad", "Chad", "Comores", "Comoros", "République du Congo",
    "Republic of the Congo", "Congo", "République démocratique du Congo",
    "Democratic Republic of the Congo", "DR Congo", "Côte d'Ivoire",
    "Ivory Coast", "Djibouti", "Égypte", "Egypt", "Guinée équatoriale",
    "Equatorial Guinea", "Érythrée", "Eritrea", "Eswatini", "Éthiopie",
    "Ethiopia", "Gabon", "Gambie", "Gambia", "Ghana", "Guinée", "Guinea",
    "Guinée-Bissau", "Guinea-Bissau", "Kenya", "Lesotho", "Liberia",
    "Libéria", "Libye", "Libya", "Madagascar", "Malawi", "Mali",
    "Mauritanie", "Mauritania", "Maurice", "Mauritius", "Maroc", "Morocco",
    "Mozambique", "Namibie", "Namibia", "Niger", "Nigeria", "Rwanda",
    "Sao Tomé", "São Tomé", "Sénégal", "Senegal", "Seychelles",
    "Sierra Leone", "Somalie", "Somalia", "Afrique du Sud", "South Africa",
    "Soudan", "Sudan", "Soudan du Sud", "South Sudan", "Tanzanie",
    "Tanzania", "Togo", "Tunisie", "Tunisia", "Ouganda", "Uganda",
    "Zambie", "Zambia", "Zimbabwe"
]

AFRICAN_REGIONS = [
    "Africa", "Afrique", "African", "West Africa", "East Africa",
    "Central Africa", "North Africa", "Southern Africa", "Sahel",
    "Afrique de l'Ouest", "Afrique de l'Est", "Afrique centrale",
    "Afrique australe", "Afrique du Nord", "Sahara"
]

EXCLUDED_TERMS = [
    "football", "soccer", "basketball", "sport", "transfer", "transfert",
    "match", "mercato", "horoscope", "recette", "recipe", "weather forecast"
]

SEARCH_QUERIES = [
    "mystère historique Afrique archéologie découverte",
    "civilisation ancienne Afrique cité oubliée",
    "site archéologique Afrique découverte ancienne",
    "royaume africain oublié histoire archéologie",
    "Afrique préhistoire grotte sépulture ruines anciennes",
    "ancient African civilization archaeological discovery",
    "mysterious ancient site Africa archaeology",
    "African ancient kingdoms forgotten history",
    "archaeological discovery ancient Africa",
    "prehistoric Africa ancient human remains",
    "site:scidev.net Africa archaeology discovery",
    "site:scidev.net Afrique archéologie découverte",
    "site:scidev.net African ancient history"
]

RSS_SOURCES = [
    {
        "name": "Archaeology Magazine",
        "url": "https://www.archaeology.org/feed/"
    },
    {
        "name": "ScienceDaily Archaeology",
        "url": "https://www.sciencedaily.com/rss/fossils_ruins/archaeology.xml"
    },
    {
        "name": "HeritageDaily",
        "url": "https://www.heritagedaily.com/category/archaeology-news/feed"
    },
    {
        "name": "Archaeology Magazine Online",
        "url": "https://archaeologymag.com/feed/"
    }
]

DIAGNOSTICS = {
    "rss_ok": 0,
    "rss_errors": 0,
    "liens_directs": 0,
    "liens_google_resolus": 0,
    "liens_non_resolus": 0,
    "pages_ouvertes": 0,
    "pages_refusees": 0,
    "textes_trop_courts": 0,
    "erreurs_extraction": 0,
    "articles_hors_afrique": 0,
    "articles_complets": 0,
    "articles_directs_complets": 0,
    "articles_google_complets": 0
}


def log_failure(category, message):
    logging.warning("[%s] %s", category, message)


def clean_text(value):
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


class ArticleParser(HTMLParser):

    def __init__(self):
        super().__init__()
        self.paragraphs = []
        self.current = []
        self.in_paragraph = False
        self.skip_depth = 0
        self.meta_description = ""

        self.skip_tags = {
            "script", "style", "noscript", "svg", "nav",
            "footer", "header", "form", "iframe"
        }

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag in self.skip_tags:
            self.skip_depth += 1
            return

        if tag == "meta":
            name = (
                attrs.get("name", "")
                or attrs.get("property", "")
            ).lower()

            if name in (
                "description",
                "og:description",
                "twitter:description"
            ):
                self.meta_description = attrs.get("content", "")

        if tag == "p" and self.skip_depth == 0:
            self.in_paragraph = True
            self.current = []

    def handle_endtag(self, tag):

        if tag in self.skip_tags and self.skip_depth > 0:
            self.skip_depth -= 1
            return

        if tag == "p" and self.in_paragraph:
            paragraph = clean_text(" ".join(self.current))

            if len(paragraph) > 30:
                self.paragraphs.append(paragraph)

            self.current = []
            self.in_paragraph = False

    def handle_data(self, data):

        if (
            self.skip_depth == 0
            and self.in_paragraph
            and data.strip()
        ):
            self.current.append(data.strip())

    def get_text(self):

        if self.in_paragraph and self.current:
            self.paragraphs.append(
                clean_text(" ".join(self.current))
            )

        content = " ".join(self.paragraphs)

        if len(content) < 200 and self.meta_description:
            content += " " + self.meta_description

        return clean_text(content)


def concerns_africa(text):

    text_lower = (text or "").lower()

    return (
        any(
            country.lower() in text_lower
            for country in AFRICAN_COUNTRIES
        )
        or
        any(
            region.lower() in text_lower
            for region in AFRICAN_REGIONS
        )
    )


def read_rss(url, source_name):

    results = []

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=TIMEOUT
        )

        response.raise_for_status()

        root = ET.fromstring(response.content)

        for item in root.findall(".//item"):

            title = clean_text(
                item.findtext("title", "")
            )

            link = (
                item.findtext("link", "") or ""
            ).strip()

            pub_date = clean_text(
                item.findtext("pubDate", "")
            )

            description = clean_text(
                item.findtext("description", "")
            )

            if not title or not link:
                continue

            if any(
                term in title.lower()
                for term in EXCLUDED_TERMS
            ):
                continue

            results.append({
                "title": title,
                "rss_url": link,
                "date": pub_date,
                "source": source_name,
                "description": description,
                "method": "RSS_DIRECT"
            })

        DIAGNOSTICS["rss_ok"] += 1

        logging.info(
            "RSS %s : %s résultats",
            source_name,
            len(results)
        )

    except Exception as error:

        DIAGNOSTICS["rss_errors"] += 1

        log_failure(
            "RSS " + source_name,
            str(error)
        )

    return results


def search_google_news(query):

    url = (
        "https://news.google.com/rss/search?q="
        + quote(query)
        + "&hl=fr&gl=FR&ceid=FR:fr"
    )

    results = []

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=TIMEOUT
        )

        response.raise_for_status()

        root = ET.fromstring(response.content)

        for item in root.findall(".//item"):

            title = clean_text(
                item.findtext("title", "")
            )

            link = (
                item.findtext("link", "") or ""
            ).strip()

            pub_date = clean_text(
                item.findtext("pubDate", "")
            )

            source_element = item.find("source")

            source = clean_text(
                source_element.text
                if source_element is not None
                else ""
            )

            if not title or not link:
                continue

            if any(
                term in title.lower()
                for term in EXCLUDED_TERMS
            ):
                continue

            results.append({
                "title": title,
                "rss_url": link,
                "date": pub_date,
                "source": source or "Google News",
                "description": "",
                "method": "GOOGLE_NEWS"
            })

            if len(results) >= MAX_RESULTS_PER_QUERY:
                break

    except Exception as error:

        log_failure(
            "Google News",
            str(error)
        )

    return results


def collect_rss_results():

    all_results = []

    logging.info("Démarrage Google News.")

    for query in SEARCH_QUERIES:

        logging.info(
            "Recherche : %s",
            query
        )

        all_results.extend(
            search_google_news(query)
        )

        time.sleep(1)

    logging.info(
        "Démarrage des médias spécialisés."
    )

    for source in RSS_SOURCES:

        all_results.extend(
            read_rss(
                source["url"],
                source["name"]
            )
        )

        time.sleep(1)

    unique = []
    seen = set()

    for item in all_results:

        key = re.sub(
            r"\W+",
            "",
            item["title"].lower()
        )

        if key not in seen:
            seen.add(key)
            unique.append(item)

    return all_results, unique


def resolve_article_url(rss_url, expected_source=""):

    if not rss_url:
        return None

    try:

        response = requests.get(
            rss_url,
            headers=HEADERS,
            timeout=TIMEOUT,
            allow_redirects=True
        )

        response.raise_for_status()

        final_url = response.url

        host = (
            urlparse(final_url).hostname or ""
        ).lower()

        if (
            final_url.startswith("http")
            and "news.google.com" not in host
        ):
            DIAGNOSTICS["liens_google_resolus"] += 1
            return final_url

        content = response.text

        patterns = [
            r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)',
            r'<meta[^>]+property=["\']og:url["\'][^>]+content=["\']([^"\']+)',
            r'"url"\s*:\s*"(https?://[^"]+)"'
        ]

        for pattern in patterns:

            for candidate in re.findall(
                pattern,
                content,
                re.IGNORECASE
            ):

                candidate = html.unescape(candidate)

                domain = (
                    urlparse(candidate).hostname or ""
                ).lower()

                if (
                    candidate.startswith("http")
                    and "google.com" not in domain
                    and "gstatic.com" not in domain
                ):
                    DIAGNOSTICS["liens_google_resolus"] += 1
                    return candidate

        if expected_source:

            expected = expected_source.lower().replace(
                "www.",
                ""
            )

            for candidate in re.findall(
                r'href=["\'](https?://[^"\']+)',
                content,
                re.IGNORECASE
            ):

                domain = (
                    urlparse(candidate).hostname or ""
                ).lower()

                if expected in domain:

                    DIAGNOSTICS["liens_google_resolus"] += 1

                    return html.unescape(candidate)

    except Exception as error:

        log_failure(
            "Résolution Google News",
            str(error)
        )

    DIAGNOSTICS["liens_non_resolus"] += 1

    return None


def extract_article(url):

    if not url:
        return None

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=TIMEOUT,
            allow_redirects=True
        )

        if response.status_code in (401, 403, 429):

            DIAGNOSTICS["pages_refusees"] += 1

            log_failure(
                "Accès refusé",
                f"{response.status_code} : {url}"
            )

            return None

        response.raise_for_status()

        DIAGNOSTICS["pages_ouvertes"] += 1

        if (
            "html"
            not in response.headers.get(
                "Content-Type",
                ""
            ).lower()
        ):

            log_failure(
                "Format",
                f"Page non HTML : {url}"
            )

            return None

        parser = ArticleParser()

        parser.feed(response.text)

        text = parser.get_text()

        if len(text) < MIN_ARTICLE_TEXT:

            DIAGNOSTICS["textes_trop_courts"] += 1

            log_failure(
                "Texte trop court",
                f"{len(text)} caractères : {url}"
            )

            return None

        domain = (
            urlparse(response.url).hostname or ""
        ).lower()

        domain = re.sub(
            r"^www\.",
            "",
            domain
        )

        DIAGNOSTICS["articles_complets"] += 1

        return {
            "url": response.url,
            "domain": domain,
            "text": text[:14000]
        }

    except Exception as error:

        DIAGNOSTICS["erreurs_extraction"] += 1

        log_failure(
            "Extraction",
            f"{url} : {error}"
        )

        return None


def basic_screen(article):

    title = article.get(
        "title",
        ""
    ).lower()

    return (
        len(title) >= 15
        and not any(
            term in title
            for term in EXCLUDED_TERMS
        )
    )


def collect_articles():

    rss_results, unique_results = collect_rss_results()

    logging.info(
        "Résultats RSS : %s",
        len(rss_results)
    )

    logging.info(
        "Résultats uniques : %s",
        len(unique_results)
    )

    # Priorité aux flux spécialisés :
    # 25 directs, puis 10 Google News.

    direct = [
        x for x in unique_results
        if x.get("method") == "RSS_DIRECT"
    ][:25]

    google = [
        x for x in unique_results
        if x.get("method") == "GOOGLE_NEWS"
    ][:10]

    prioritized = direct + google

    articles = []
    attempts = 0

    for item in prioritized:

        if attempts >= MAX_ARTICLES_TO_OPEN:
            break

        if not basic_screen(item):
            continue

        attempts += 1

        logging.info(
            "Article %s/%s : %s",
            attempts,
            MAX_ARTICLES_TO_OPEN,
            item["title"]
        )

        if item["method"] == "RSS_DIRECT":

            url = item["rss_url"]

            DIAGNOSTICS["liens_directs"] += 1

        else:

            url = resolve_article_url(
                item["rss_url"],
                item.get("source", "")
            )

        if not url:
            continue

        extracted = extract_article(url)

        if not extracted:
            continue

        combined = (
            item["title"]
            + " "
            + item.get("description", "")
            + " "
            + extracted["text"]
        )

        if not concerns_africa(combined):

            DIAGNOSTICS["articles_hors_afrique"] += 1

            logging.info(
                "Article écarté : sujet africain non identifié."
            )

            continue

        articles.append({
            "id": len(articles) + 1,
            "title": item["title"],
            "date": item["date"],
            "rss_source": item["source"],
            "url": extracted["url"],
            "domain": extracted["domain"],
            "text": extracted["text"],
            "method": item["method"]
        })

        if item["method"] == "RSS_DIRECT":

            DIAGNOSTICS["articles_directs_complets"] += 1

        else:

            DIAGNOSTICS["articles_google_complets"] += 1

        logging.info(
            "Article récupéré : %s",
            item["title"]
        )

        time.sleep(1)

    logging.info(
        "Articles complets récupérés : %s",
        len(articles)
    )

    return {
        "rss_total": len(rss_results),
        "unique_total": len(unique_results),
        "attempts": attempts,
        "articles": articles
    }


def extract_json(text):

    text = (text or "").strip()

    text = re.sub(
        r"^```(?:json)?\s*",
        "",
        text
    )

    text = re.sub(
        r"\s*```$",
        "",
        text
    )

    start = text.find("{")
    end = text.rfind("}")

    if start < 0 or end <= start:
        raise ValueError(
            "Réponse JSON Gemini invalide."
        )

    return json.loads(
        text[start:end + 1]
    )


def analyze_articles(articles):

    if not GEMINI_API_KEY:

        raise RuntimeError(
            "GEMINI_API_KEY absente des secrets GitHub."
        )

    if len(articles) < 2:
        return None

    selected = articles[:MAX_ARTICLES_FOR_AI]

    sources_text = ""

    for article in selected:

        sources_text += f"""
ID SOURCE : {article['id']}
TITRE : {article['title']}
DATE : {article['date']}
MÉDIA : {article['rss_source']}
DOMAINE : {article['domain']}
URL : {article['url']}
CONTENU :
{article['text']}
--------------------------------------------------
"""

    prompt = f"""
Tu es le rédacteur en chef et réalisateur documentaire de {CHANNEL}.
Tu dois choisir UNE histoire africaine réelle, documentée et exploitable en Short.

ZONE : les 54 pays africains.
PRIORITÉS : mystères historiques, lieux mystérieux, civilisations oubliées,
royaumes anciens, cités anciennes, découvertes archéologiques, préhistoire africaine.

RÈGLES DOCUMENTAIRES :
- Accepte toutes les dates de publication et toutes les périodes historiques.
- N'invente aucun fait, pays, lieu, nom, date, citation, source ou URL.
- Utilise uniquement les textes complets fournis.
- Deux domaines web distincts sont obligatoires.
- Deux domaines distincts ne prouvent pas automatiquement l'indépendance éditoriale.
- Ne transforme jamais une hypothèse en certitude.
- Écarte les sujets dont les faits essentiels ne sont pas corroborés.
- Si aucune histoire ne satisfait ces critères, réponds selection=false.
- Ne demande pas une validation humaine, mais ne prétends pas certifier la vérité absolue.

SCRIPT :
- Français naturel, narration de 45 à 60 secondes.
- 90 à 130 mots pour le texte de narration.
- Accroche dès la première phrase, rythme captivant, conclusion mémorable.
- Les scènes doivent reprendre exactement la narration, sans ajouter de faits.
- Format vertical 9:16.

DOSSIER AUDIOVISUEL :
- Prépare 4 à 6 scènes couvrant toute la durée, sans chevauchement ni trou.
- durée_totale_secondes : entre 45 et 60.
- Chaque scène contient numero, debut, fin, duree, narration, visuel,
  prompt_image_video, mouvement_camera, transition, musique,
  effets_sonores, texte_ecran, type_visuel.
- Le texte narration des scènes doit reprendre le script dans le même ordre.
- Distingue image documentaire authentique et reconstitution artistique.
- Si une image authentique n'est pas fournie par les sources, ne la présente pas
  comme une photographie historique réelle : indique RECONSTITUTION.
- Prompts visuels cinématographiques, précis, adaptés au 9:16, sans texte incrusté.
- Prévois voix_off, musique_generale, sous_titres, idee_miniature.
- Prépare titre_youtube, description_youtube, hashtags, mots_cles,
  commentaire_epingle.
- Ne prétends pas avoir généré les images, la voix ou la vidéo : fournis seulement
  les instructions de production.

SOURCES DISPONIBLES :
{sources_text}

Réponds UNIQUEMENT avec un JSON valide.

Si aucune histoire ne convient :
{{
  "selection": false,
  "raison_rejet": "Explication précise"
}}

Si une histoire convient :
{{
  "selection": true,
  "titre": "Titre factuel",
  "pays": "Pays africain",
  "lieu": "Lieu précis",
  "categorie": "Catégorie",
  "periode_historique": "Période",
  "resume_historique": "Résumé factuel",
  "mystere": "Élément encore inexpliqué, s'il existe",
  "faits_etablis": ["Fait 1", "Fait 2", "Fait 3"],
  "elements_incertain": ["Incertitude ou hypothèse"],
  "sources_utilisees": [1, 2],
  "preuves_par_source": [
    {{"id_source": 1, "apport": "Ce que cette source confirme"}},
    {{"id_source": 2, "apport": "Ce que cette source confirme"}}
  ],
  "niveau_documentation": "BON",
  "accroche": "Phrase d'ouverture",
  "script": "Narration complète de 90 à 130 mots",
  "conclusion": "Conclusion",
  "duree_totale_secondes": 52,
  "scenes": [
    {{
      "numero": 1,
      "debut": 0,
      "fin": 9,
      "duree": 9,
      "narration": "Segment exact du script",
      "visuel": "Description du plan",
      "prompt_image_video": "Prompt détaillé pour créer le visuel vertical 9:16",
      "mouvement_camera": "Mouvement",
      "transition": "Transition",
      "musique": "Indication musicale",
      "effets_sonores": "Effets sonores",
      "texte_ecran": "Texte court à afficher",
      "type_visuel": "RECONSTITUTION"
    }}
  ],
  "voix_off": {{
    "langue": "Français",
    "voix": "Description de la voix",
    "ton": "Ton",
    "rythme": "Rythme",
    "consignes": "Consignes de diction"
  }},
  "musique_generale": {{
    "ambiance": "Ambiance",
    "instruments": ["Instrument 1"],
    "evolution": "Évolution sonore"
  }},
  "sous_titres": {{
    "style": "Style lisible",
    "position": "Zone basse sûre",
    "consignes": "Synchronisation mot à mot"
  }},
  "idee_miniature": {{
    "concept": "Concept",
    "texte": "Texte très court",
    "prompt": "Prompt de miniature 9:16"
  }},
  "titre_youtube": "Titre",
  "description_youtube": "Description",
  "hashtags": ["#HistoireAfrique"],
  "mots_cles": ["Afrique", "Histoire"],
  "commentaire_epingle": "Commentaire"
}}
"""

    try:

        client = genai.Client(
            api_key=GEMINI_API_KEY
        )

        response = client.interactions.create(
            model=MODEL,
            input=prompt
        )

        output = (
            getattr(response, "output_text", None)
            or str(response)
        )

        return extract_json(output)

    except Exception as error:

        logging.exception(
            "Erreur Gemini : %s",
            error
        )

        return None


def normalize_domain(domain):

    domain = (
        domain or ""
    ).lower().split(":")[0]

    return re.sub(
        r"^www\.",
        "",
        domain
    )


def validate_analysis(story, articles):

    if (
        not isinstance(story, dict)
        or story.get("selection") is not True
    ):
        return None

    required = [
        "titre",
        "pays",
        "categorie",
        "resume_historique",
        "faits_etablis",
        "sources_utilisees",
        "preuves_par_source",
        "script",
        "scenes",
        "duree_totale_secondes",
        "voix_off",
        "musique_generale",
        "sous_titres",
        "idee_miniature",
        "titre_youtube",
        "description_youtube",
        "hashtags",
        "mots_cles",
        "commentaire_epingle"
    ]

    for field in required:

        if not story.get(field):

            logging.warning(
                "Champ obligatoire manquant : %s",
                field
            )

            return None

    country = str(
        story["pays"]
    ).strip().lower()

    if not any(
        country == item.lower()
        for item in AFRICAN_COUNTRIES
    ):

        logging.warning(
            "Pays africain non reconnu : %s",
            story["pays"]
        )

        return None

    valid_articles = {
        article["id"]: article
        for article in articles[:MAX_ARTICLES_FOR_AI]
    }

    source_ids = story.get(
        "sources_utilisees"
    )

    if not isinstance(source_ids, list):
        return None

    source_ids = list(dict.fromkeys(
        value
        for value in source_ids
        if isinstance(value, int)
        and value in valid_articles
    ))

    selected_sources = [
        valid_articles[value]
        for value in source_ids
    ]

    if len(selected_sources) < 2:

        logging.warning(
            "Moins de deux sources utilisables."
        )

        return None

    domains = {
        normalize_domain(item["domain"])
        for item in selected_sources
    }

    if len(domains) < 2:

        logging.warning(
            "Les sources ne proviennent pas de deux domaines distincts."
        )

        return None

    proofs = story.get(
        "preuves_par_source",
        []
    )

    if not isinstance(proofs, list):
        return None

    proof_ids = {
        proof.get("id_source")
        for proof in proofs
        if isinstance(proof, dict)
    }

    if not set(source_ids).issubset(proof_ids):

        logging.warning(
            "Preuves manquantes pour une ou plusieurs sources."
        )

        return None

    facts = story.get("faits_etablis")

    if not isinstance(facts, list) or len(facts) < 2:
        return None

    script = str(
        story.get("script", "")
    ).strip()

    word_count = len(
        script.split()
    )

    if not 70 <= word_count <= 160:

        logging.warning(
            "Longueur du script hors limites : %s mots",
            word_count
        )

        return None

    if not 90 <= word_count <= 130:

        logging.warning(
            "Attention : le script contient %s mots (cible 90–130).",
            word_count
        )

    duration = story.get(
        "duree_totale_secondes"
    )

    if (
        not isinstance(duration, (int, float))
        or not 45 <= duration <= 60
    ):

        logging.warning(
            "Durée totale invalide."
        )

        return None

    scenes = story.get("scenes")

    if (
        not isinstance(scenes, list)
        or not 4 <= len(scenes) <= 6
    ):

        logging.warning(
            "Le dossier doit contenir 4 à 6 scènes."
        )

        return None

    required_scene_fields = [
        "numero",
        "debut",
        "fin",
        "duree",
        "narration",
        "visuel",
        "prompt_image_video",
        "mouvement_camera",
        "transition",
        "musique",
        "effets_sonores",
        "texte_ecran",
        "type_visuel"
    ]

    expected_start = 0
    scene_narration = []

    for index, scene in enumerate(
        scenes,
        start=1
    ):

        if not isinstance(scene, dict):
            return None

        if any(
            not scene.get(field)
            and field not in ("texte_ecran",)
            for field in required_scene_fields
        ):

            logging.warning(
                "Champ manquant dans la scène %s.",
                index
            )

            return None

        try:

            start = float(
                scene["debut"]
            )

            end = float(
                scene["fin"]
            )

            scene_duration = float(
                scene["duree"]
            )

        except (TypeError, ValueError):

            return None

        if (
            abs(start - expected_start) > 1.0
            or end <= start
        ):

            logging.warning(
                "Chronologie incorrecte dans la scène %s.",
                index
            )

            return None

        if abs(
            (end - start) - scene_duration
        ) > 1.5:

            logging.warning(
                "Durée incohérente dans la scène %s.",
                index
            )

            return None

        expected_start = end

        scene_narration.append(
            str(
                scene.get("narration", "")
            ).strip()
        )

    if abs(
        expected_start - float(duration)
    ) > 2.0:

        logging.warning(
            "Les scènes ne couvrent pas la durée totale."
        )

        return None

    if sum(
        len(part.split())
        for part in scene_narration
    ) < 60:

        logging.warning(
            "Narration des scènes trop courte."
        )

        return None

    story["sources"] = [
        {
            "id": source["id"],
            "titre": source["title"],
            "date": source["date"],
            "media": source["rss_source"],
            "domaine": source["domain"],
            "url": source["url"]
        }
        for source in selected_sources
    ]

    story["sources_utilisees"] = source_ids

    story["decision_editoriale"] = (
        "SÉLECTIONNÉE — DOSSIER AUDIOVISUEL PRÊT POUR PRODUCTION"
    )

    story["independance_des_sources"] = (
        "DEUX DOMAINES DISTINCTS IDENTIFIÉS — "
        "INDÉPENDANCE NON GARANTIE"
    )

    story["nombre_mots_script"] = word_count

    story["format_video"] = "Short vertical 9:16"

    story["avertissement_historique"] = (
        "Sélection automatique fondée sur les textes récupérés. "
        "Deux domaines distincts ne garantissent pas une indépendance "
        "éditoriale et cette sélection ne constitue pas une certification "
        "historique absolue."
    )

    story["date_selection"] = (
        datetime.now(timezone.utc).isoformat()
    )

    return story


def save_report(data):

    os.makedirs(
        os.path.dirname(OUTPUT_FILE),
        exist_ok=True
    )

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2
        )

    logging.info(
        "Rapport enregistré : %s",
        OUTPUT_FILE
    )


def main():

    start_time = datetime.now(
        timezone.utc
    )

    logging.info("=" * 60)

    logging.info(
        "OBSERVATEUR ACTIF AI - V8"
    )

    logging.info(
        "Recherche africaine multi-sources + dossier audiovisuel"
    )

    logging.info("=" * 60)

    report = {
        "date_recherche": start_time.isoformat(),
        "version": "V8",
        "chaine": CHANNEL,
        "zone": "Toute l'Afrique",
        "priorite_editoriale": [
            "Mystères historiques",
            "Lieux mystérieux",
            "Civilisations oubliées",
            "Royaumes anciens",
            "Découvertes archéologiques",
            "Préhistoire africaine"
        ],
        "duree_shorts": "45 à 60 secondes",
        "format_production": "Dossier audiovisuel complet 9:16",
        "sources_recherchees": [
            "Google News",
            "SciDev.Net via Google News",
            "Archaeology Magazine",
            "ScienceDaily Archaeology",
            "HeritageDaily",
            "Archaeology Magazine Online"
        ],
        "statistiques": {},
        "diagnostics": {},
        "histoires": [],
        "statut": "RECHERCHE EN COURS",
        "publication_youtube": {
            "active": False,
            "raison": "La publication YouTube reste désactivée."
        }
    }

    try:

        collection = collect_articles()

        articles = collection["articles"]

        report["statistiques"] = {
            "recherches_google_news": len(
                SEARCH_QUERIES
            ),
            "resultats_rss": collection["rss_total"],
            "resultats_uniques": collection["unique_total"],
            "articles_tentes": collection["attempts"],
            "textes_complets": len(articles),
            "articles_envoyes_a_ia": min(
                len(articles),
                MAX_ARTICLES_FOR_AI
            )
        }

        report["diagnostics"] = DIAGNOSTICS.copy()

        if len(articles) < 2:

            report["statut"] = (
                "RECHERCHE INSUFFISANTE"
            )

            report["message"] = (
                "Moins de deux textes complets ont été récupérés. "
                "Consulte les diagnostics."
            )

            return

        analysis = analyze_articles(
            articles
        )

        if not analysis:

            report["statut"] = (
                "ANALYSE IA IMPOSSIBLE"
            )

            report["message"] = (
                "Gemini n'a pas retourné une analyse exploitable."
            )

            return

        if analysis.get("selection") is not True:

            report["statut"] = (
                "AUCUNE HISTOIRE RETENUE"
            )

            report["raison_rejet"] = analysis.get(
                "raison_rejet",
                "Aucune histoire ne satisfait les critères."
            )

            return

        validated = validate_analysis(
            analysis,
            articles
        )

        if not validated:

            report["statut"] = (
                "AUCUNE HISTOIRE VALIDÉE AUTOMATIQUEMENT"
            )

            report["message"] = (
                "L'histoire proposée ne satisfait pas les critères "
                "documentaires ou audiovisuels."
            )

            return

        report["histoires"].append(
            validated
        )

        report["statut"] = (
            "SUCCÈS — DOSSIER AUDIOVISUEL PRÊT POUR PRODUCTION"
        )

        report["message"] = (
            "Une histoire et son dossier audiovisuel "
            "ont été générés automatiquement."
        )

        logging.info(
            "HISTOIRE SÉLECTIONNÉE : %s",
            validated["titre"]
        )

    except Exception as error:

        logging.exception(
            "Erreur générale : %s",
            error
        )

        report["statut"] = "ERREUR"

        report["erreur"] = str(error)

    finally:

        report["diagnostics"] = DIAGNOSTICS.copy()

        elapsed = (
            datetime.now(timezone.utc) - start_time
        ).total_seconds()

        report["duree_execution_secondes"] = round(
            elapsed,
            2
        )

        save_report(report)

        logging.info(
            "Durée totale : %.1f secondes",
            elapsed
        )

        logging.info(
            "Fin Observateur Actif AI V8."
        )


if __name__ == "__main__":
    main()

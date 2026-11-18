
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
# 1. CONFIGURATION
# ============================================================

CHANNEL = "Observateur Actif"
MODEL = "gemini-3.8-flash"

MAX_RESULTS_PER_QUERY = 6
MAX_ARTICLES_TO_OPEN = 35
MAX_ARTICLES_FOR_AI = 15
MIN_ARTICLE_TEXT = 500

OUTPUT_FILE = "output/daily_research.json"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

TIMEOUT = 25

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 Chrome/125.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,*/*;q=0.8"
    ),
    "Accept-Language": "fr,en;q=0.9"
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)


# ============================================================
# 2. PAYS AFRICAINS
# ============================================================

AFRICAN_COUNTRIES = [
    "Algérie", "Algeria", "Angola", "Bénin", "Benin",
    "Botswana", "Burkina Faso", "Burundi", "Cabo Verde",
    "Cape Verde", "Cameroun", "Cameroon",
    "République centrafricaine", "Central African Republic",
    "Tchad", "Chad", "Comores", "Comoros",
    "République du Congo", "Republic of the Congo",
    "Congo", "République démocratique du Congo",
    "Democratic Republic of the Congo", "DR Congo",
    "Côte d'Ivoire", "Ivory Coast", "Djibouti",
    "Égypte", "Egypt", "Guinée équatoriale",
    "Equatorial Guinea", "Érythrée", "Eritrea",
    "Eswatini", "Éthiopie", "Ethiopia", "Gabon",
    "Gambie", "Gambia", "Ghana", "Guinée", "Guinea",
    "Guinée-Bissau", "Guinea-Bissau", "Kenya",
    "Lesotho", "Liberia", "Libéria", "Libye", "Libya",
    "Madagascar", "Malawi", "Mali", "Mauritanie",
    "Mauritania", "Maurice", "Mauritius", "Maroc",
    "Morocco", "Mozambique", "Namibie", "Namibia",
    "Niger", "Nigeria", "Rwanda", "Sao Tomé",
    "São Tomé", "Sénégal", "Senegal", "Seychelles",
    "Sierra Leone", "Somalie", "Somalia",
    "Afrique du Sud", "South Africa", "Soudan",
    "Sudan", "Soudan du Sud", "South Sudan",
    "Tanzanie", "Tanzania", "Togo", "Tunisie",
    "Tunisia", "Ouganda", "Uganda", "Zambie",
    "Zambia", "Zimbabwe"
]

AFRICAN_REGIONS = [
    "Africa", "Afrique", "African",
    "West Africa", "East Africa",
    "Central Africa", "North Africa",
    "Southern Africa", "Sahel",
    "Afrique de l'Ouest", "Afrique de l'Est",
    "Afrique centrale", "Afrique australe",
    "Afrique du Nord", "Sahara"
]

EXCLUDED_TERMS = [
    "football", "soccer", "basketball",
    "sport", "transfer", "transfert",
    "match", "mercato", "horoscope",
    "recette", "recipe", "weather forecast"
]


# ============================================================
# 3. RECHERCHES GOOGLE NEWS
# ============================================================

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


# ============================================================
# 4. FLUX RSS SPÉCIALISÉS
# ============================================================

RSS_SOURCES = [
    {
        "name": "Archaeology Magazine",
        "url": "https://www.archaeology.org/feed/",
        "type": "archaeology"
    },
    {
        "name": "ScienceDaily Archaeology",
        "url": "https://www.sciencedaily.com/rss/fossils_ruins/archaeology.xml",
        "type": "science"
    },
    {
        "name": "HeritageDaily",
        "url": "https://www.heritagedaily.com/category/archaeology-news/feed",
        "type": "archaeology"
    },
    {
        "name": "Archaeology Magazine Online",
        "url": "https://archaeologymag.com/feed/",
        "type": "archaeology"
    }
]


# ============================================================
# 5. DIAGNOSTICS
# ============================================================

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

    logging.warning(
        "[%s] %s",
        category,
        message
    )


# ============================================================
# 6. NETTOYAGE DU TEXTE
# ============================================================

def clean_text(text):

    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


# ============================================================
# 7. EXTRACTION HTML
# ============================================================

class ArticleParser(HTMLParser):

    def __init__(self):
        super().__init__()

        self.paragraphs = []
        self.current_paragraph = []
        self.in_paragraph = False
        self.skip_depth = 0
        self.meta_description = ""

        self.skip_tags = {
            "script", "style", "noscript",
            "svg", "nav", "footer", "header",
            "form", "iframe"
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

            if name in [
                "description",
                "og:description",
                "twitter:description"
            ]:
                self.meta_description = attrs.get(
                    "content", ""
                )

        if tag == "p" and self.skip_depth == 0:
            self.in_paragraph = True
            self.current_paragraph = []

    def handle_endtag(self, tag):

        if tag in self.skip_tags and self.skip_depth > 0:
            self.skip_depth -= 1
            return

        if tag == "p" and self.in_paragraph:

            paragraph = clean_text(
                " ".join(self.current_paragraph)
            )

            if len(paragraph) > 30:
                self.paragraphs.append(paragraph)

            self.current_paragraph = []
            self.in_paragraph = False

    def handle_data(self, data):

        if self.skip_depth > 0:
            return

        if self.in_paragraph:

            text = data.strip()

            if text:
                self.current_paragraph.append(text)

    def get_text(self):

        if self.in_paragraph and self.current_paragraph:

            self.paragraphs.append(
                clean_text(" ".join(self.current_paragraph))
            )

        content = " ".join(self.paragraphs)

        if len(content) < 200 and self.meta_description:
            content += " " + self.meta_description

        return clean_text(content)


# ============================================================
# 8. FILTRAGE AFRICAIN
# ============================================================

def concerns_africa(text):

    text_lower = text.lower()

    for country in AFRICAN_COUNTRIES:

        if country.lower() in text_lower:
            return True

    for region in AFRICAN_REGIONS:

        if region.lower() in text_lower:
            return True

    return False


# ============================================================
# 9. LECTURE DES FLUX RSS DIRECTS
# ============================================================

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

            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            pub_date = item.findtext("pubDate", "").strip()

            description = item.findtext(
                "description", ""
            )

            if not title or not link:
                continue

            description = clean_text(
                re.sub(r"<[^>]+>", " ", description)
            )

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


# ============================================================
# 10. GOOGLE NEWS RSS
# ============================================================

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

            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            pub_date = item.findtext("pubDate", "").strip()

            source_element = item.find("source")

            source = ""

            if source_element is not None:
                source = source_element.text or ""

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


# ============================================================
# 11. COLLECTE DES RÉSULTATS
# ============================================================

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

    logging.info("Démarrage des médias spécialisés.")

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

        if key in seen:
            continue

        seen.add(key)
        unique.append(item)

    return all_results, unique


# ============================================================
# 12. RÉSOLUTION DES LIENS GOOGLE NEWS
# ============================================================

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

        final_domain = urlparse(
            final_url
        ).netloc.lower()

        if (
            final_url.startswith("http")
            and "news.google.com" not in final_domain
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

            matches = re.findall(
                pattern,
                content,
                re.IGNORECASE
            )

            for candidate in matches:

                candidate = html.unescape(candidate)

                domain = urlparse(
                    candidate
                ).netloc.lower()

                if (
                    candidate.startswith("http")
                    and "google.com" not in domain
                    and "gstatic.com" not in domain
                ):

                    DIAGNOSTICS["liens_google_resolus"] += 1

                    return candidate

        if expected_source:

            links = re.findall(
                r'href=["\'](https?://[^"\']+)',
                content,
                re.IGNORECASE
            )

            for candidate in links:

                domain = urlparse(
                    candidate
                ).netloc.lower()

                if expected_source.lower() in domain:

                    DIAGNOSTICS["liens_google_resolus"] += 1

                    return html.unescape(candidate)

    except Exception as error:

        log_failure(
            "Résolution Google News",
            str(error)
        )

    DIAGNOSTICS["liens_non_resolus"] += 1

    return None


# ============================================================
# 13. EXTRACTION D'UN ARTICLE
# ============================================================

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

        if response.status_code in [401, 403, 429]:

            DIAGNOSTICS["pages_refusees"] += 1

            log_failure(
                "Accès refusé",
                f"{response.status_code} : {url}"
            )

            return None

        response.raise_for_status()

        DIAGNOSTICS["pages_ouvertes"] += 1

        content_type = response.headers.get(
            "Content-Type", ""
        ).lower()

        if "html" not in content_type:

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

        domain = urlparse(
            response.url
        ).netloc.lower()

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


# ============================================================
# 14. FILTRAGE ÉDITORIAL
# ============================================================

def basic_screen(article):

    title = article.get(
        "title", ""
    ).lower()

    if len(title) < 15:
        return False

    if any(
        term in title
        for term in EXCLUDED_TERMS
    ):
        return False

    return True


# ============================================================
# 15. COLLECTE DES ARTICLES COMPLETS
# ============================================================

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

    # Priorité aux flux spécialisés
    direct_results = [
        item for item in unique_results
        if item.get("method") == "RSS_DIRECT"
    ]

    google_results = [
        item for item in unique_results
        if item.get("method") == "GOOGLE_NEWS"
    ]

    # Répartition des tentatives
    direct_results = direct_results[:25]
    google_results = google_results[:10]

    prioritized_results = (
        direct_results + google_results
    )

    logging.info(
        "Articles directs prioritaires : %s",
        len(direct_results)
    )

    logging.info(
        "Articles Google News : %s",
        len(google_results)
    )

    articles = []
    attempts = 0

    for item in prioritized_results:

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

        combined_text = (
            item["title"] + " "
            + item.get("description", "") + " "
            + extracted["text"]
        )

        if not concerns_africa(combined_text):

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


# ============================================================
# 16. ANALYSE GEMINI
# ============================================================

def analyze_articles(articles):

    if not GEMINI_API_KEY:

        raise RuntimeError(
            "GEMINI_API_KEY absente des secrets GitHub."
        )

    if len(articles) < 2:
        return None

    selected_articles = articles[:MAX_ARTICLES_FOR_AI]

    sources_text = ""

    for article in selected_articles:

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
Tu es le rédacteur en chef de {CHANNEL}.

MISSION :
Identifier une véritable histoire africaine
historique, archéologique ou liée à un lieu mystérieux.

ZONE :
Les 54 pays africains.

PRIORITÉS :
1. Mystères historiques.
2. Lieux mystérieux.
3. Civilisations oubliées.
4. Royaumes et empires anciens.
5. Cités anciennes et disparues.
6. Découvertes archéologiques.
7. Grottes, tombes et ruines.
8. Préhistoire africaine.

RÈGLES :
- Accepte les histoires anciennes et récentes.
- Aucune limite d'ancienneté historique.
- La date de publication ne détermine pas la valeur du sujet.
- N'invente aucun fait, lieu, personnage ou date.
- Utilise uniquement les informations présentes dans les sources.
- Le sujet doit réellement concerner l'Afrique.
- Deux domaines différents sont nécessaires.
- Deux domaines différents ne garantissent pas l'indépendance éditoriale.
- Ne présente pas une hypothèse comme un fait.
- Signale les théories controversées.
- Rejette les histoires insuffisamment documentées.
- Ne place pas les histoires en attente de validation humaine.
- Sélectionne automatiquement celles qui satisfont les critères.

SCRIPT :
- Durée de 45 à 60 secondes.
- Environ 90 à 130 mots.
- Accroche forte.
- Narration claire et captivante.
- Conclusion mémorable.
- Pas de faits inventés.

SOURCES :
{sources_text}

Réponds uniquement avec un JSON valide.

Si aucune histoire ne convient :

{{
  "selection": false,
  "raison_rejet": "Explication"
}}

Si une histoire convient :

{{
  "selection": true,
  "titre": "Titre",
  "pays": "Pays africain",
  "lieu": "Lieu précis",
  "categorie": "Mystère historique",
  "periode_historique": "Période",
  "resume_historique": "Résumé factuel",
  "mystere": "Élément mystérieux",
  "faits_etablis": [
    "Fait 1",
    "Fait 2",
    "Fait 3"
  ],
  "elements_incertain": [
    "Hypothèse ou incertitude"
  ],
  "sources_utilisees": [1, 2],
  "preuves_par_source": [
    {{
      "id_source": 1,
      "apport": "Information apportée"
    }},
    {{
      "id_source": 2,
      "apport": "Information apportée"
    }}
  ],
  "niveau_documentation": "BON",
  "accroche": "Accroche",
  "script": "Script de narration",
  "conclusion": "Conclusion",
  "idee_visuelle": "Description des images",
  "mots_cles": ["Afrique", "Histoire", "Archéologie"]
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

        output = getattr(
            response,
            "output_text",
            None
        )

        if not output:
            output = str(response)

        output = output.strip()

        output = re.sub(
            r"^```(?:json)?\s*",
            "",
            output
        )

        output = re.sub(
            r"\s*```$",
            "",
            output
        )

        start = output.find("{")
        end = output.rfind("}")

        if start == -1 or end == -1:

            raise ValueError(
                "JSON Gemini introuvable."
            )

        return json.loads(
            output[start:end + 1]
        )

    except Exception as error:

        logging.exception(
            "Erreur Gemini : %s",
            error
        )

        return None


# ============================================================
# 17. VALIDATION AUTOMATIQUE
# ============================================================

def validate_analysis(story, articles):

    if not isinstance(story, dict):
        return None

    if story.get("selection") is not True:
        return None

    required_fields = [
        "titre", "pays", "categorie",
        "resume_historique", "faits_etablis",
        "sources_utilisees", "preuves_par_source",
        "script"
    ]

    for field in required_fields:

        if not story.get(field):

            logging.warning(
                "Champ manquant : %s",
                field
            )

            return None

    country = story["pays"].strip()

    if not any(
        country.lower() == name.lower()
        for name in AFRICAN_COUNTRIES
    ):

        logging.warning(
            "Pays non reconnu : %s",
            country
        )

        return None

    valid_ids = {
        article["id"]: article
        for article in articles[:MAX_ARTICLES_FOR_AI]
    }

    source_ids = story.get(
        "sources_utilisees", []
    )

    if not isinstance(source_ids, list):
        return None

    source_ids = list(
        dict.fromkeys(source_ids)
    )

    selected_sources = []

    for source_id in source_ids:

        if source_id in valid_ids:

            selected_sources.append(
                valid_ids[source_id]
            )

    if len(selected_sources) < 2:
        return None

    domains = {
        source["domain"].lower()
        for source in selected_sources
    }

    if len(domains) < 2:
        return None

    proofs = story.get(
        "preuves_par_source", []
    )

    proof_ids = {
        proof.get("id_source")
        for proof in proofs
        if isinstance(proof, dict)
    }

    if not set(source_ids).issubset(proof_ids):
        return None

    facts = story.get("faits_etablis", [])

    if not isinstance(facts, list) or len(facts) < 2:
        return None

    script = story.get(
        "script", ""
    ).strip()

    word_count = len(script.split())

    if word_count < 70 or word_count > 160:
        return None

    story["sources"] = []

    for source in selected_sources:

        story["sources"].append({
            "id": source["id"],
            "titre": source["title"],
            "date": source["date"],
            "media": source["rss_source"],
            "domaine": source["domain"],
            "url": source["url"]
        })

    story["decision_editoriale"] = (
        "SÉLECTIONNÉE — PRÊTE POUR PRODUCTION"
    )

    story["independance_des_sources"] = (
        "DEUX DOMAINES DISTINCTS IDENTIFIÉS"
    )

    story["niveau_documentation"] = (
        "SÉLECTION AUTOMATIQUE RÉUSSIE"
    )

    story["nombre_mots_script"] = word_count

    story["avertissement_historique"] = (
        "Sélection automatique fondée sur les sources "
        "récupérées. Elle ne constitue pas une certification "
        "historique absolue."
    )

    story["date_selection"] = datetime.now(
        timezone.utc
    ).isoformat()

    return story


# ============================================================
# 18. ENREGISTREMENT DU RAPPORT
# ============================================================

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


# ============================================================
# 19. PROGRAMME PRINCIPAL
# ============================================================

def main():

    start_time = datetime.now(timezone.utc)

    logging.info("=" * 60)
    logging.info("OBSERVATEUR ACTIF AI - V7")
    logging.info("Recherche africaine multi-sources")
    logging.info("=" * 60)

    report = {
        "date_recherche": start_time.isoformat(),
        "version": "V7",
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
            "raison": (
                "La publication YouTube reste désactivée."
            )
        }
    }

    try:

        collection = collect_articles()

        articles = collection["articles"]

        report["statistiques"] = {
            "recherches_google_news": len(SEARCH_QUERIES),
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
                "Consulte les diagnostics pour identifier les blocages."
            )

            save_report(report)
            return

        analysis = analyze_articles(articles)

        if not analysis:

            report["statut"] = (
                "ANALYSE IA IMPOSSIBLE"
            )

            report["message"] = (
                "Gemini n'a pas retourné une analyse exploitable."
            )

            save_report(report)
            return

        if analysis.get("selection") is not True:

            report["statut"] = (
                "AUCUNE HISTOIRE RETENUE"
            )

            report["raison_rejet"] = analysis.get(
                "raison_rejet",
                "Aucune histoire ne satisfait les critères."
            )

            save_report(report)
            return

        validated_story = validate_analysis(
            analysis,
            articles
        )

        if not validated_story:

            report["statut"] = (
                "AUCUNE HISTOIRE VALIDÉE AUTOMATIQUEMENT"
            )

            report["message"] = (
                "L'histoire proposée ne satisfait pas "
                "les critères automatiques."
            )

            save_report(report)
            return

        report["histoires"].append(
            validated_story
        )

        report["statut"] = (
            "SUCCÈS — HISTOIRE PRÊTE POUR PRODUCTION"
        )

        report["message"] = (
            "Une histoire a été sélectionnée automatiquement."
        )

        logging.info(
            "HISTOIRE SÉLECTIONNÉE : %s",
            validated_story["titre"]
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
            elapsed, 2
        )

        save_report(report)

        logging.info(
            "Durée totale : %.1f secondes",
            elapsed
        )

        logging.info(
            "Fin Observateur Actif AI V7."
        )


if __name__ == "__main__":
    main()

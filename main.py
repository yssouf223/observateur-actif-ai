
import os
import re
import json
import time
import html
import logging
import requests
import xml.etree.ElementTree as ET

from datetime import datetime, timezone
from urllib.parse import quote
from html.parser import HTMLParser
from google import genai


# ============================================================
# CONFIGURATION
# ============================================================

CHANNEL = "Observateur Actif"
MODEL = "gemini-3.8-flash"

MAX_RESULTS_PER_QUERY = 6
MAX_ARTICLES_TO_OPEN = 25
MAX_ARTICLES_FOR_AI = 15
MIN_ARTICLE_TEXT = 700

OUTPUT_FILE = "output/daily_research.json"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
    )
}

TIMEOUT = 25

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)


# ============================================================
# RECHERCHES GOOGLE NEWS : TOUTE L'AFRIQUE
# ============================================================

SEARCH_QUERIES = [
    "mystère historique Afrique archéologie découverte",
    "civilisation ancienne Afrique cité oubliée",
    "site archéologique Afrique découverte ancienne",
    "royaume africain oublié histoire archéologie",
    "ancient African civilization archaeological discovery",
    "mysterious ancient site Africa archaeology",
    "African ancient kingdoms forgotten history",
    "descubrimiento arqueológico África civilización antigua",
    "descoberta arqueológica África civilização antiga",
    "Afrique préhistoire grotte sépulture ruines anciennes",
]


EXCLUDED_TERMS = [
    "football",
    "sport",
    "transfert",
    "match",
    "résultat sportif",
    "mercato",
    "célébrité",
    "people",
    "horoscope",
    "recette",
    "météo",
]


# ============================================================
# EXTRACTION DU TEXTE DES PAGES WEB
# ============================================================

class ArticleParser(HTMLParser):

    def __init__(self):
        super().__init__()
        self.text_parts = []
        self.skip_level = 0
        self.skip_tags = {
            "script", "style", "noscript",
            "svg", "nav", "footer", "header"
        }

    def handle_starttag(self, tag, attrs):
        if tag in self.skip_tags:
            self.skip_level += 1

    def handle_endtag(self, tag):
        if tag in self.skip_tags and self.skip_level > 0:
            self.skip_level -= 1

    def handle_data(self, data):
        if self.skip_level == 0:
            text = data.strip()
            if text:
                self.text_parts.append(text)

    def get_text(self):
        return " ".join(self.text_parts)


def clean_text(text):
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ============================================================
# RECHERCHE GOOGLE NEWS RSS
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

            title_lower = title.lower()

            if any(term in title_lower for term in EXCLUDED_TERMS):
                continue

            results.append({
                "title": title,
                "rss_url": link,
                "date": pub_date,
                "source": source,
                "query": query
            })

            if len(results) >= MAX_RESULTS_PER_QUERY:
                break

    except Exception as error:
        logging.warning(
            "Erreur RSS pour '%s' : %s",
            query,
            error
        )

    return results


# ============================================================
# RÉSOLUTION DES LIENS GOOGLE NEWS
# ============================================================

def resolve_article_url(rss_url):

    try:
        response = requests.get(
            rss_url,
            headers=HEADERS,
            timeout=TIMEOUT,
            allow_redirects=True
        )

        final_url = response.url

        if (
            final_url
            and "news.google.com" not in final_url
            and final_url.startswith("http")
        ):
            return final_url

        # Deuxième tentative : recherche de l'URL dans la page
        content = response.text

        patterns = [
            r'https?://[^"\\]+',
            r'href="(https?://[^"]+)"'
        ]

        for pattern in patterns:
            matches = re.findall(pattern, content)

            for match in matches:
                candidate = match.strip()

                if (
                    candidate.startswith("http")
                    and "google.com" not in candidate
                    and "gstatic.com" not in candidate
                ):
                    return candidate

    except Exception as error:
        logging.warning("Résolution du lien impossible : %s", error)

    return None


# ============================================================
# EXTRACTION D'UN ARTICLE COMPLET
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

        response.raise_for_status()

        content_type = response.headers.get(
            "Content-Type", ""
        ).lower()

        if "html" not in content_type:
            return None

        parser = ArticleParser()
        parser.feed(response.text)

        text = clean_text(parser.get_text())

        if len(text) < MIN_ARTICLE_TEXT:
            return None

        domain = re.sub(
            r"^www\.",
            "",
            requests.utils.urlparse(response.url).netloc
        )

        return {
            "url": response.url,
            "domain": domain,
            "text": text[:12000]
        }

    except Exception as error:
        logging.warning(
            "Extraction impossible pour %s : %s",
            url,
            error
        )

        return None


# ============================================================
# FILTRAGE ÉDITORIAL DE BASE
# ============================================================

def basic_screen(article):

    title = article.get("title", "").lower()

    if len(title) < 15:
        return False

    if any(term in title for term in EXCLUDED_TERMS):
        return False

    return True


# ============================================================
# COLLECTE DES ARTICLES
# ============================================================

def collect_articles():

    logging.info("Début des recherches sur toute l'Afrique.")

    rss_results = []

    for query in SEARCH_QUERIES:

        logging.info("Recherche : %s", query)

        results = search_google_news(query)
        rss_results.extend(results)

        time.sleep(1)

    # Suppression des doublons de liens RSS
    unique_results = []
    seen_titles = set()

    for item in rss_results:

        key = item["title"].lower().strip()

        if key not in seen_titles:
            seen_titles.add(key)
            unique_results.append(item)

    logging.info(
        "%s résultats RSS uniques trouvés.",
        len(unique_results)
    )

    articles = []
    attempts = 0

    for item in unique_results:

        if attempts >= MAX_ARTICLES_TO_OPEN:
            break

        if not basic_screen(item):
            continue

        attempts += 1

        logging.info(
            "Ouverture article %s/%s : %s",
            attempts,
            MAX_ARTICLES_TO_OPEN,
            item["title"]
        )

        url = resolve_article_url(item["rss_url"])

        if not url:
            continue

        extracted = extract_article(url)

        if not extracted:
            continue

        articles.append({
            "id": len(articles) + 1,
            "title": item["title"],
            "date": item["date"],
            "rss_source": item["source"],
            "url": extracted["url"],
            "domain": extracted["domain"],
            "text": extracted["text"]
        })

        time.sleep(1)

    logging.info(
        "%s articles complets récupérés.",
        len(articles)
    )

    return {
        "rss_total": len(rss_results),
        "unique_total": len(unique_results),
        "attempts": attempts,
        "articles": articles
    }


# ============================================================
# ANALYSE INTELLIGENTE AVEC GEMINI
# ============================================================

def analyze_articles(articles):

    if not GEMINI_API_KEY:
        raise RuntimeError(
            "La variable GEMINI_API_KEY est absente."
        )

    if len(articles) < 2:
        logging.warning(
            "Pas assez d'articles complets pour l'analyse."
        )
        return None

    selected_articles = articles[:MAX_ARTICLES_FOR_AI]

    sources_text = ""

    for article in selected_articles:

        sources_text += f"""

ID SOURCE : {article['id']}
TITRE : {article['title']}
DATE : {article['date']}
DOMAINE : {article['domain']}
URL : {article['url']}

CONTENU :
{article['text']}

--------------------------------------------------
"""

    prompt = f"""
Tu es le rédacteur en chef et documentaliste historique
de la chaîne YouTube {CHANNEL}.

MISSION :
Trouver une véritable histoire africaine, historique,
archéologique ou liée à un lieu mystérieux.

ZONE :
Toute l'Afrique, sans exception.

PRIORITÉS :
1. Mystères historiques.
2. Lieux mystérieux.
3. Civilisations oubliées.
4. Royaumes et empires anciens.
5. Cités anciennes et disparues.
6. Découvertes archéologiques.
7. Grottes, tombes, ruines et sites anciens.
8. Préhistoire africaine.

IMPORTANT :
- Une histoire peut être ancienne ou récente.
- La date de publication de l'article n'est pas une limite.
- L'histoire doit concerner réellement l'Afrique.
- Ne crée aucune histoire.
- N'invente aucun personnage, lieu, date ou découverte.
- Ne transforme pas une hypothèse en certitude.
- Écarte les actualités politiques ou sportives sans intérêt historique.
- Ne sélectionne pas un sujet uniquement parce que son titre est mystérieux.
- Utilise uniquement les informations réellement présentes dans les articles.
- Deux articles provenant de domaines différents sont nécessaires.
- Deux articles qui reprennent simplement la même dépêche ne constituent
  pas nécessairement deux confirmations indépendantes.
- Si les sources sont insuffisantes ou contradictoires, rejette l'histoire.
- Si une théorie est controversée, indique clairement qu'elle est controversée.
- Ne présente jamais une légende comme un fait historique établi.

SÉLECTION AUTOMATIQUE :
Tu dois prendre la décision éditoriale toi-même.
Il ne faut pas placer les histoires en attente d'une vérification humaine.
Si les critères documentaires sont satisfaits, sélectionne l'histoire
et marque-la comme prête pour la production.

FORMAT :
Le script doit durer entre 45 et 60 secondes.
Il doit contenir environ 90 à 130 mots.
Il doit être captivant, précis et compréhensible.
Commence par une accroche forte.
Termine par une conclusion mémorable.

ARTICLES DISPONIBLES :
{sources_text}

RÉPONDS UNIQUEMENT AVEC UN JSON VALIDE.
N'utilise pas de bloc Markdown.

Si aucune histoire ne satisfait les critères, réponds avec :
{{
  "selection": false,
  "raison_rejet": "Explication précise"
}}

Si une histoire satisfait les critères, utilise exactement cette structure :

{{
  "selection": true,
  "titre": "Titre de l'histoire",
  "pays": "Pays africain",
  "lieu": "Lieu précis",
  "categorie": "Mystère historique",
  "periode_historique": "Période ou date connue",
  "resume_historique": "Résumé factuel",
  "mystere": "Ce qui reste inexpliqué ou intéressant",
  "faits_etablis": [
    "Fait établi 1",
    "Fait établi 2",
    "Fait établi 3"
  ],
  "elements_incertain": [
    "Hypothèse ou incertitude clairement identifiée"
  ],
  "sources_utilisees": [1, 2],
  "preuves_par_source": [
    {{
      "id_source": 1,
      "apport": "Information apportée par cette source"
    }},
    {{
      "id_source": 2,
      "apport": "Information apportée par cette source"
    }}
  ],
  "niveau_documentation": "BON",
  "accroche": "Phrase d'ouverture",
  "script": "Texte complet de narration de 90 à 130 mots",
  "conclusion": "Phrase finale",
  "idee_visuelle": "Description des images à utiliser",
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

        # Nettoyage d'un éventuel bloc JSON Markdown
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
                "Gemini n'a pas retourné un JSON valide."
            )

        return json.loads(output[start:end + 1])

    except Exception as error:

        logging.exception(
            "Erreur pendant l'analyse Gemini : %s",
            error
        )

        return None


# ============================================================
# VALIDATION AUTOMATIQUE DE LA SÉLECTION
# ============================================================

AFRICAN_COUNTRIES = [
    "Algérie", "Angola", "Bénin", "Botswana",
    "Burkina Faso", "Burundi", "Cabo Verde",
    "Cameroun", "République centrafricaine",
    "Tchad", "Comores", "République du Congo",
    "République démocratique du Congo",
    "Côte d'Ivoire", "Djibouti", "Égypte",
    "Guinée équatoriale", "Érythrée", "Eswatini",
    "Éthiopie", "Gabon", "Gambie", "Ghana",
    "Guinée", "Guinée-Bissau", "Kenya", "Lesotho",
    "Liberia", "Libye", "Madagascar", "Malawi",
    "Mali", "Mauritanie", "Maurice", "Maroc",
    "Mozambique", "Namibie", "Niger", "Nigeria",
    "Rwanda", "Sao Tomé-et-Principe", "Sénégal",
    "Seychelles", "Sierra Leone", "Somalie",
    "Afrique du Sud", "Soudan du Sud", "Soudan",
    "Tanzanie", "Togo", "Tunisie", "Ouganda",
    "Zambie", "Zimbabwe"
]


def validate_analysis(story, articles):

    if not isinstance(story, dict):
        return None

    if story.get("selection") is not True:
        return None

    required_fields = [
        "titre",
        "pays",
        "categorie",
        "resume_historique",
        "faits_etablis",
        "sources_utilisees",
        "preuves_par_source",
        "script"
    ]

    for field in required_fields:
        if not story.get(field):
            logging.warning(
                "Champ obligatoire manquant : %s",
                field
            )
            return None

    country = story["pays"].strip()

    if not any(
        country.lower() == name.lower()
        for name in AFRICAN_COUNTRIES
    ):
        logging.warning(
            "Pays africain non reconnu : %s",
            country
        )
        return None

    valid_ids = {
        article["id"]: article
        for article in articles[:MAX_ARTICLES_FOR_AI]
    }

    source_ids = story.get("sources_utilisees", [])

    if not isinstance(source_ids, list):
        return None

    source_ids = list(dict.fromkeys(source_ids))

    if len(source_ids) < 2:
        logging.warning(
            "Moins de deux sources sélectionnées."
        )
        return None

    selected_sources = []

    for source_id in source_ids:

        if source_id not in valid_ids:
            continue

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
        logging.warning(
            "Les sources ne proviennent pas de deux domaines distincts."
        )
        return None

    proofs = story.get("preuves_par_source", [])

    proof_ids = {
        proof.get("id_source")
        for proof in proofs
        if isinstance(proof, dict)
    }

    if not set(source_ids).issubset(proof_ids):
        logging.warning(
            "Les preuves ne couvrent pas toutes les sources."
        )
        return None

    facts = story.get("faits_etablis", [])

    if not isinstance(facts, list) or len(facts) < 2:
        return None

    script = story.get("script", "").strip()

    word_count = len(script.split())

    if word_count < 70 or word_count > 160:
        logging.warning(
            "Script trop court ou trop long : %s mots.",
            word_count
        )
        return None

    # Sources réellement utilisées
    story["sources"] = []

    for source in selected_sources:

        story["sources"].append({
            "id": source["id"],
            "titre": source["title"],
            "date": source["date"],
            "domaine": source["domain"],
            "url": source["url"]
        })

    # Décision éditoriale : plus de blocage humain
    story["decision_editoriale"] = (
        "SÉLECTIONNÉE — PRÊTE POUR PRODUCTION"
    )

    story["independance_des_sources"] = (
        "DEUX DOMAINES DISTINCTS IDENTIFIÉS"
    )

    story["raison_controle"] = (
        "L'histoire satisfait les critères automatiques "
        "de sélection éditoriale et de documentation."
    )

    story["niveau_documentation"] = (
        "SÉLECTION AUTOMATIQUE RÉUSSIE"
    )

    story["nombre_mots_script"] = word_count

    story["avertissement_historique"] = (
        "La sélection automatique repose sur les articles "
        "et les éléments documentaires récupérés. Elle ne "
        "constitue pas une certification historique absolue."
    )

    story["date_selection"] = datetime.now(
        timezone.utc
    ).isoformat()

    return story


# ============================================================
# CRÉATION DU RAPPORT
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
# PROGRAMME PRINCIPAL
# ============================================================

def main():

    start_time = datetime.now(timezone.utc)

    logging.info("=" * 60)
    logging.info("OBSERVATEUR ACTIF AI - V5")
    logging.info("Recherche historique africaine automatique")
    logging.info("=" * 60)

    report = {
        "date_recherche": start_time.isoformat(),
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
        "statistiques": {},
        "histoires": [],
        "statut": "RECHERCHE TERMINÉE",
        "publication_youtube": {
            "active": False,
            "raison": (
                "La publication automatique sur YouTube "
                "n'est pas activée dans cette version."
            )
        }
    }

    try:

        collection = collect_articles()

        articles = collection["articles"]

        report["statistiques"] = {
            "recherches_effectuees": len(SEARCH_QUERIES),
            "resultats_rss": collection["rss_total"],
            "resultats_uniques": collection["unique_total"],
            "articles_tentes": collection["attempts"],
            "textes_complets": len(articles),
            "articles_envoyes_a_ia": min(
                len(articles),
                MAX_ARTICLES_FOR_AI
            )
        }

        if len(articles) < 2:

            report["statut"] = (
                "RECHERCHE INSUFFISANTE"
            )

            report["message"] = (
                "Moins de deux articles complets ont été "
                "récupérés. Aucune histoire n'a été sélectionnée."
            )

            save_report(report)
            return

        analysis = analyze_articles(articles)

        if not analysis:

            report["statut"] = (
                "ANALYSE IA IMPOSSIBLE"
            )

            report["message"] = (
                "L'analyse Gemini n'a pas pu être effectuée."
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
                "les critères automatiques de sélection."
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

        save_report(report)

    except Exception as error:

        logging.exception(
            "Erreur générale : %s",
            error
        )

        report["statut"] = "ERREUR"

        report["erreur"] = str(error)

        save_report(report)

    finally:

        elapsed = (
            datetime.now(timezone.utc) - start_time
        ).total_seconds()

        logging.info(
            "Durée totale : %.1f secondes",
            elapsed
        )

        logging.info(
            "Fin du programme Observateur Actif AI."
        )


if __name__ == "__main__":
    main()

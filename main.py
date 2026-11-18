
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


# ==========================================================
# OBSERVATEUR ACTIF AI - VERSION 4
# Recherche documentaire sur toute l'Afrique
# ==========================================================

CHANNEL = "Observateur Actif"
MODEL = "gemini-3.8-flash"

MAX_RESULTS_PER_QUERY = 5
MAX_ARTICLES_TO_OPEN = 20
MIN_ARTICLE_TEXT = 500

OUTPUT_FILE = "output/daily_research.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}

COOKIE = "CONSENT=YES+cb; SOCS=CAI"


# ==========================================================
# 1. RECHERCHES RÉGIONALES
# ==========================================================

def build_searches():

    since = (
        datetime.now(timezone.utc) - timedelta(days=1825)
    ).date().isoformat()

    date_filter = f"after:{since}"

    themes_fr = (
        '"mystère historique" OR archéologie OR '
        '"cité ancienne" OR "civilisation oubliée" OR '
        '"royaume ancien" OR "site antique" OR '
        '"ruines anciennes" OR "lieu mystérieux"'
    )

    themes_en = (
        '"historical mystery" OR archaeology OR '
        '"ancient city" OR "lost civilization" OR '
        '"ancient kingdom" OR "mysterious place" OR '
        '"ancient ruins" OR "archaeological site"'
    )

    return [
        (
            "Afrique de l'Ouest - français",
            f"(Mali OR Sénégal OR Burkina Faso OR Niger OR "
            f"Guinée OR Ghana OR Nigeria OR Bénin OR Togo OR "
            f"Côte d'Ivoire OR Gambie OR Mauritanie OR Liberia) "
            f"({themes_fr}) {date_filter}"
        ),
        (
            "Afrique de l'Ouest - anglais",
            f"(Mali OR Senegal OR Burkina Faso OR Niger OR "
            f"Guinea OR Ghana OR Nigeria OR Benin OR Togo OR "
            f"Gambia OR Mauritania OR Liberia) "
            f"({themes_en}) {date_filter}"
        ),
        (
            "Afrique du Nord - français",
            f"(Égypte OR Maroc OR Algérie OR Tunisie OR "
            f"Libye OR Soudan) ({themes_fr}) {date_filter}"
        ),
        (
            "Afrique du Nord - anglais",
            f"(Egypt OR Morocco OR Algeria OR Tunisia OR "
            f"Libya OR Sudan) ({themes_en}) {date_filter}"
        ),
        (
            "Afrique centrale - français",
            f"(RDC OR Congo OR Cameroun OR Gabon OR Tchad OR "
            f"Angola OR Centrafrique OR Burundi OR Rwanda) "
            f"({themes_fr}) {date_filter}"
        ),
        (
            "Afrique centrale - anglais",
            f"(DR Congo OR Congo OR Cameroon OR Gabon OR Chad OR "
            f"Angola OR Central African Republic OR Rwanda OR Burundi) "
            f"({themes_en}) {date_filter}"
        ),
        (
            "Afrique de l'Est - anglais",
            f"(Ethiopia OR Kenya OR Tanzania OR Uganda OR Rwanda OR "
            f"Somalia OR Eritrea OR Djibouti OR Madagascar OR "
            f"South Sudan) ({themes_en}) {date_filter}"
        ),
        (
            "Afrique de l'Est - français",
            f"(Éthiopie OR Kenya OR Tanzanie OR Ouganda OR Rwanda OR "
            f"Somalie OR Djibouti OR Madagascar OR Soudan du Sud) "
            f"({themes_fr}) {date_filter}"
        ),
        (
            "Afrique australe - anglais",
            f"(Zimbabwe OR Zambia OR South Africa OR Botswana OR "
            f"Namibia OR Mozambique OR Malawi OR Lesotho OR "
            f"Eswatini) ({themes_en}) {date_filter}"
        ),
        (
            "Afrique australe - français",
            f"(Zimbabwe OR Zambie OR Afrique du Sud OR Botswana OR "
            f"Namibie OR Mozambique OR Malawi OR Lesotho) "
            f"({themes_fr}) {date_filter}"
        ),
    ]


# ==========================================================
# 2. OUTILS INTERNET
# ==========================================================

def clean_text(value):

    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)

    return re.sub(r"\s+", " ", value).strip()


def fetch_url(url, data=None, headers=None, timeout=25):

    request_headers = dict(HEADERS)

    if headers:
        request_headers.update(headers)

    request = urllib.request.Request(
        url,
        data=data,
        headers=request_headers
    )

    with urllib.request.urlopen(
        request,
        timeout=timeout
    ) as response:

        content = response.read()
        final_url = response.geturl()
        content_type = response.headers.get(
            "Content-Type", ""
        )

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


# ==========================================================
# 3. GOOGLE NEWS RSS
# ==========================================================

def google_news_search(query, region):

    encoded = urllib.parse.quote(query)

    url = (
        "https://news.google.com/rss/search?q="
        + encoded
        + "&hl=fr&gl=FR&ceid=FR:fr"
    )

    try:

        content, _, _ = fetch_url(url)

        root = ET.fromstring(content)

        results = []

        for item in root.findall(".//item"):

            title = clean_text(
                item.findtext("title", "")
            )

            link = (
                item.findtext("link", "") or ""
            ).strip()

            description = clean_text(
                item.findtext("description", "")
            )

            pub_date = parse_date(
                item.findtext("pubDate", "")
            )

            source_element = item.find("source")

            publisher = ""

            if source_element is not None:
                publisher = clean_text(
                    source_element.text or ""
                )

            if not title or not link:
                continue

            results.append({
                "title": title,
                "rss_url": link,
                "publisher": publisher,
                "description": description[:1500],
                "published_at": pub_date,
                "search_region": region,
                "search_query": query,
                "publisher_url": None,
                "article_text": "",
                "article_full_text_fetched": False,
                "fetch_status": "NON CONSULTÉ"
            })

        return results

    except Exception as error:

        print(f"Erreur RSS ({region}) : {error}")

        return []


# ==========================================================
# 4. RÉSOLUTION DES LIENS GOOGLE NEWS
# ==========================================================

def resolve_google_news_url(link):

    parsed = urlparse(link)

    host = (parsed.hostname or "").lower()

    if host != "news.google.com":
        return link

    article_id = parsed.path.rstrip("/").split("/")[-1]

    if not article_id:
        raise ValueError("Identifiant Google News absent.")

    page_url = (
        "https://news.google.com/rss/articles/"
        + article_id
        + "?hl=fr&gl=FR&ceid=FR:fr"
    )

    page_headers = {
        "Cookie": COOKIE,
        "Referer": "https://news.google.com/"
    }

    page_content, final_url, _ = fetch_url(
        page_url,
        headers=page_headers
    )

    page = page_content.decode(
        "utf-8",
        errors="replace"
    )

    signature = re.search(
        r'data-n-a-sg="([^"]+)"',
        page
    )

    timestamp = re.search(
        r'data-n-a-ts="([^"]+)"',
        page
    )

    if not signature or not timestamp:

        final_host = (
            urlparse(final_url).hostname or ""
        ).lower()

        if final_host and not final_host.endswith("google.com"):
            return final_url

        raise ValueError(
            "Signature Google News introuvable."
        )

    sg = signature.group(1)
    ts = int(timestamp.group(1))

    inner = [
        "garturlreq",
        [
            [
                "X", "X", ["X", "X"],
                None, None, 1, 1, "US:en",
                None, 1, None, None, None,
                None, None, 0, 1
            ],
            "X", "X", 1,
            [1, 1, 1],
            1, 1, None, 0, 0, None, 0
        ],
        article_id,
        ts,
        sg
    ]

    body_object = {
        "f.req": json.dumps(
            [[[
                "Fbv4je",
                json.dumps(inner, separators=(",", ":")),
                None,
                "generic"
            ]]],
            separators=(",", ":")
        )
    }

    body = urllib.parse.urlencode(
        body_object
    ).encode("utf-8")

    post_headers = {
        "Cookie": COOKIE,
        "Referer": "https://news.google.com/",
        "Content-Type": (
            "application/x-www-form-urlencoded;charset=UTF-8"
        )
    }

    response_content, _, _ = fetch_url(
        "https://news.google.com/_/DotsSplashUi/data/batchexecute"
        "?rpcids=Fbv4je",
        data=body,
        headers=post_headers
    )

    raw = response_content.decode(
        "utf-8",
        errors="replace"
    )

    def find_response(obj):

        if isinstance(obj, list):

            if (
                len(obj) >= 3
                and obj[1] == "Fbv4je"
                and isinstance(obj[2], str)
            ):
                return obj[2]

            for child in obj:

                found = find_response(child)

                if found:
                    return found

        return None

    for line in raw.splitlines():

        line = line.strip()

        if not line.startswith("["):
            continue

        try:
            frames = json.loads(line)
        except Exception:
            continue

        payload = find_response(frames)

        if not payload:
            continue

        try:

            decoded = json.loads(payload)

            if (
                isinstance(decoded, list)
                and len(decoded) >= 2
                and decoded[0] == "garturlres"
            ):

                publisher_url = decoded[1]

                if not isinstance(publisher_url, str):
                    continue

                parsed_url = urlparse(publisher_url)

                if parsed_url.scheme not in ("http", "https"):
                    continue

                if not parsed_url.hostname:
                    continue

                if parsed_url.hostname.endswith("google.com"):
                    continue

                return publisher_url

        except Exception:
            continue

    raise ValueError(
        "Google News n'a pas retourné l'adresse de l'éditeur."
    )


# ==========================================================
# 5. EXTRACTION DES ARTICLES
# ==========================================================

class ArticleParser(HTMLParser):

    SKIP_TAGS = {
        "script", "style", "noscript", "svg",
        "nav", "footer", "header", "aside",
        "form", "iframe"
    }

    def __init__(self):

        super().__init__()

        self.parts = []
        self.skip_stack = []
        self.meta_description = ""
        self.meta_og_description = ""

    def handle_starttag(self, tag, attrs):

        attrs = dict(attrs)

        if tag in self.SKIP_TAGS:
            self.skip_stack.append(tag)

        if tag == "meta":

            name = (attrs.get("name") or "").lower()
            prop = (attrs.get("property") or "").lower()
            content = attrs.get("content", "")

            if name == "description":
                self.meta_description = content

            if prop == "og:description":
                self.meta_og_description = content

        if tag in (
            "p", "br", "div", "h1", "h2",
            "h3", "li", "article"
        ):
            self.parts.append(" ")

    def handle_endtag(self, tag):

        if tag in self.SKIP_TAGS:

            if tag in self.skip_stack:
                self.skip_stack.remove(tag)

        if tag in (
            "p", "br", "div", "h1", "h2",
            "h3", "li", "article"
        ):
            self.parts.append(" ")

    def handle_data(self, data):

        if not self.skip_stack:
            self.parts.append(data)


def resolve_and_read_article(item):

    try:

        publisher_url = resolve_google_news_url(
            item["rss_url"]
        )

        item["publisher_url"] = publisher_url

        content, final_url, content_type = fetch_url(
            publisher_url
        )

        final_host = (
            urlparse(final_url).hostname or ""
        ).lower()

        if not final_host:
            item["fetch_status"] = "ADRESSE FINALE INVALIDE"
            return item

        if final_host.endswith("google.com"):
            item["fetch_status"] = "REDIRECTION NON RÉSOLUE"
            return item

        charset_match = re.search(
            r"charset=([a-zA-Z0-9_-]+)",
            content_type,
            re.IGNORECASE
        )

        encoding = (
            charset_match.group(1)
            if charset_match
            else "utf-8"
        )

        page = content.decode(
            encoding,
            errors="replace"
        )

        parser = ArticleParser()
        parser.feed(page)

        article_text = re.sub(
            r"\s+",
            " ",
            " ".join(parser.parts)
        ).strip()

        item["publisher_url"] = final_url

        if len(article_text) < MIN_ARTICLE_TEXT:

            item["fetch_status"] = "TEXTE INSUFFISANT"

            item["description_page"] = clean_text(
                parser.meta_og_description
                or parser.meta_description
            )[:1500]

            return item

        item["article_text"] = article_text[:9000]
        item["article_full_text_fetched"] = True
        item["fetch_status"] = "TEXTE RÉCUPÉRÉ"

    except urllib.error.HTTPError as error:

        item["fetch_status"] = f"ERREUR HTTP {error.code}"

    except Exception as error:

        item["fetch_status"] = (
            f"ERREUR : {str(error)[:200]}"
        )

    return item


# ==========================================================
# 6. FILTRAGE ÉDITORIAL
# ==========================================================

EXCLUDED_TERMS = [
    "élection", "présidentielle", "ministre",
    "gouvernement", "parlement", "sanctions",
    "armée", "rebelles", "conflit armé",
    "football", "match", "championnat",
    "transfert", "can 2027", "basketball",
    "accident", "meurtre", "assassinat",
    "incendie", "inondation", "manifestation",
    "politique", "diplomatie", "économie",
    "élections", "guerre en cours"
]


def editorial_screen(item):

    title = item.get("title", "").lower()
    description = item.get("description", "").lower()

    combined = title + " " + description

    for term in EXCLUDED_TERMS:

        if term in combined:
            return False

    return True


# ==========================================================
# 7. ANALYSE GEMINI
# ==========================================================

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

    if start == -1 or end == -1 or end <= start:
        raise ValueError("Réponse JSON invalide.")

    return json.loads(text[start:end + 1])


def get_response_text(response):

    output_text = getattr(
        response,
        "output_text",
        None
    )

    if output_text:
        return output_text

    collected = []

    output = getattr(response, "output", None) or []

    for item in output:

        content = getattr(item, "content", None) or []

        for part in content:

            value = getattr(part, "text", None)

            if value:
                collected.append(value)

    return "\n".join(collected)


def analyze_with_gemini(items):

    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY est absent des secrets GitHub."
        )

    # Seuls les articles intégralement récupérés
    # sont transmis comme sources lues à Gemini.

    readable = [
        item for item in items
        if item["article_full_text_fetched"]
    ]

    source_list = []

    for index, item in enumerate(readable, start=1):

        source_list.append({
            "source_id": index,
            "title": item["title"],
            "publisher": item["publisher"],
            "publisher_url": item["publisher_url"],
            "published_at": item["published_at"],
            "country_region": item["search_region"],
            "article_text": item["article_text"][:6500]
        })

    client = genai.Client(api_key=api_key)

    prompt = f"""
Tu es le documentaliste et vérificateur historique
de la chaîne YouTube Observateur Actif.

MISSION :
Trouver de véritables mystères africains documentés
pour des vidéos YouTube Shorts de 45 à 60 secondes.

ZONE :
Les 54 pays d'Afrique.

THÈMES AUTORISÉS :
1. Mystères historiques.
2. Lieux mystérieux.
3. Civilisations oubliées.
4. Cités anciennes.
5. Découvertes archéologiques.
6. Royaumes africains anciens.
7. Sites historiques dont certains éléments
   restent inexpliqués.

SUJETS INTERDITS :
- Actualités politiques.
- Élections et sanctions.
- Guerres et conflits contemporains.
- Sport.
- Faits divers sans rapport avec l'histoire.
- Actualités économiques.
- Histoires inventées ou sensationnalistes.

RÈGLES ABSOLUES :

1. Ne jamais inventer une histoire.
2. Ne jamais inventer un pays, une date ou un personnage.
3. Ne jamais inventer une source ou une URL.
4. Ne pas confondre légende et réalité historique.
5. Une hypothèse doit être présentée comme une hypothèse.
6. Le sujet doit réellement concerner l'Afrique.
7. Utiliser uniquement les textes fournis.
8. Une source non lue ne constitue pas une preuve.
9. Une manchette ne constitue pas une preuve.
10. Deux articles qui reprennent le même communiqué
    ne sont pas nécessairement indépendants.
11. Ne jamais inventer une corroboration.
12. Écarter les sujets politiques contemporains.
13. Ne pas transformer une actualité en mystère historique.
14. Si les preuves sont insuffisantes, ne proposer
    aucune histoire.

CONTRÔLE DES SOURCES :

Une histoire ne peut être proposée que si :
- Au moins deux articles complets sont disponibles.
- Les articles proviennent de deux domaines différents.
- Les textes soutiennent réellement le même sujet.
- Le pays africain est identifiable.
- Le sujet correspond aux thèmes autorisés.

Même si ces conditions sont remplies,
la validation humaine reste obligatoire.

SOURCES :

{json.dumps(source_list, ensure_ascii=False)}

Retourne exclusivement un JSON valide :

{{
  "resume_recherche": "Résumé honnête",
  "histoires": [
    {{
      "titre": "Titre factuel",
      "pays": "Pays africain",
      "region_afrique": "Région",
      "periode_historique": "Période connue",
      "resume_factuel": "Résumé des faits documentés",
      "faits_confirmes": [],
      "hypotheses_ou_incertitudes": [],
      "nature": "Mystère historique",
      "source_ids": [1, 2],
      "raison_decision": "Justification",
      "idee_accroche": "Accroche prudente",
      "potentiel_short": "Faible, moyen ou élevé"
    }}
  ]
}}

Maximum : 5 histoires.

Si aucune histoire ne respecte toutes les conditions,
retourne obligatoirement :

{{
  "resume_recherche": "Aucun sujet suffisamment documenté",
  "histoires": []
}}
"""

    response = client.interactions.create(
        model=MODEL,
        input=prompt
    )

    return extract_json(
        get_response_text(response)
    )


# ==========================================================
# 8. VALIDATION DES HISTOIRES
# ==========================================================

AFRICAN_COUNTRIES = {
    "mali", "senegal", "sénégal", "burkina faso",
    "niger", "guinea", "guinée", "ghana", "nigeria",
    "benin", "bénin", "togo", "cote d'ivoire",
    "côte d'ivoire", "liberia", "libéria",
    "sierra leone", "gambia", "gambie",
    "mauritania", "mauritanie", "cape verde",
    "cap vert", "guinea-bissau", "guinée-bissau",
    "egypt", "égypte", "morocco", "maroc",
    "algeria", "algérie", "tunisia", "tunisie",
    "libya", "libye", "sudan", "soudan",
    "democratic republic of the congo",
    "rdc", "congo", "cameroon", "cameroun",
    "gabon", "chad", "tchad",
    "central african republic",
    "angola", "equatorial guinea",
    "guinée équatoriale", "ethiopia", "éthiopie",
    "kenya", "tanzania", "tanzanie", "uganda",
    "rwanda", "burundi", "somalia", "somalie",
    "eritrea", "érythrée", "djibouti",
    "south sudan", "soudan du sud",
    "south africa", "afrique du sud",
    "zimbabwe", "zambia", "zambie",
    "botswana", "namibia", "namibie",
    "mozambique", "madagascar", "malawi",
    "lesotho", "eswatini", "swaziland",
    "seychelles", "comoros", "comores",
    "mauritius", "maurice", "sao tome and principe",
    "são tomé-et-principe"
}


ALLOWED_NATURES = {
    "mystère historique",
    "lieu mystérieux",
    "civilisation oubliée",
    "découverte archéologique",
    "cité ancienne",
    "royaume ancien",
    "site historique"
}


def validate_analysis(analysis, readable_items, all_items):

    valid_stories = []

    for story in analysis.get("histoires", []):

        if not isinstance(story, dict):
            continue

        country = str(
            story.get("pays", "")
        ).strip().lower()

        if country not in AFRICAN_COUNTRIES:
            continue

        nature = str(
            story.get("nature", "")
        ).strip().lower()

        if nature not in ALLOWED_NATURES:
            continue

        ids = story.get("source_ids", [])

        if not isinstance(ids, list):
            continue

        valid_ids = []

        for value in ids:

            if (
                isinstance(value, int)
                and 1 <= value <= len(readable_items)
                and value not in valid_ids
            ):
                valid_ids.append(value)

        selected_sources = [
            readable_items[index - 1]
            for index in valid_ids
        ]

        domains = set()

        for source in selected_sources:

            host = urlparse(
                source.get("publisher_url") or ""
            ).hostname

            if host:
                domains.add(
                    host.lower().removeprefix("www.")
                )

        # Deux textes complets et deux domaines
        # différents sont obligatoires.

        if len(selected_sources) < 2:
            continue

        if len(domains) < 2:
            continue

        story["sources"] = [
            {
                "source_id": index,
                "title": source["title"],
                "publisher": source["publisher"],
                "url": source["publisher_url"],
                "article_full_text_fetched": True
            }
            for index, source in enumerate(
                selected_sources,
                start=1
            )
        ]

        story["nombre_articles_lus"] = len(selected_sources)
        story["nombre_domaines_distincts"] = len(domains)

        story["decision_editoriale"] = (
            "EN ATTENTE DE VÉRIFICATION HUMAINE"
        )

        story["raison_controle"] = (
            "Deux textes complets de domaines distincts "
            "ont été identifiés. Leur indépendance réelle "
            "et les faits doivent encore être vérifiés."
        )

        valid_stories.append(story)

    return valid_stories


# ==========================================================
# 9. PROGRAMME PRINCIPAL
# ==========================================================

def main():

    os.makedirs("output", exist_ok=True)

    now = datetime.now(timezone.utc)

    print("=" * 60)
    print("OBSERVATEUR ACTIF AI - VERSION 4")
    print("RECHERCHE DOCUMENTAIRE AFRICAINE")
    print("Date UTC :", now.isoformat())
    print("=" * 60)

    all_results = []
    seen = set()
    query_stats = []

    searches = build_searches()

    # Recherche régionale

    for region, query in searches:

        print("Recherche :", region)

        results = google_news_search(
            query,
            region
        )

        added = 0

        for item in results:

            key = re.sub(
                r"\W+",
                "",
                item["title"].lower()
            )

            if not key or key in seen:
                continue

            seen.add(key)

            # Premier filtrage automatique

            if not editorial_screen(item):
                continue

            all_results.append(item)
            added += 1

            if added >= MAX_RESULTS_PER_QUERY:
                break

        query_stats.append({
            "region": region,
            "resultats_recus": len(results),
            "resultats_ajoutes": added
        })

        time.sleep(1)

    all_results.sort(
        key=lambda item: item.get("published_at") or "",
        reverse=True
    )

    print("Résultats retenus :", len(all_results))

    # Extraction des textes

    for index, item in enumerate(
        all_results[:MAX_ARTICLES_TO_OPEN],
        start=1
    ):

        print(
            f"Lecture article {index}/"
            f"{min(len(all_results), MAX_ARTICLES_TO_OPEN)}"
        )

        resolve_and_read_article(item)

        print("Statut :", item["fetch_status"])

        time.sleep(2)

    read_items = [
        item for item in all_results
        if item["article_full_text_fetched"]
    ]

    read_count = len(read_items)

    # Rapport initial

    report = {

        "version": "4.0",

        "date_recherche": now.isoformat(),

        "chaine": CHANNEL,

        "zone": "Toute l'Afrique",

        "priorite_editoriale": [
            "Mystères historiques",
            "Lieux mystérieux",
            "Civilisations oubliées"
        ],

        "duree_shorts": "45 à 60 secondes",

        "nombre_recherches": len(searches),

        "statistiques_recherche": query_stats,

        "nombre_resultats": len(all_results),

        "nombre_articles_tentes": min(
            len(all_results),
            MAX_ARTICLES_TO_OPEN
        ),

        "nombre_articles_integralement_recuperes": read_count,

        "sources": all_results,

        "analyse_ia": {
            "status": "NON EFFECTUÉE",
            "modele": MODEL,
            "histoires": []
        },

        "publication_youtube": {
            "active": False,
            "raison": (
                "Publication désactivée jusqu'à "
                "validation humaine."
            )
        }
    }

    # Analyse Gemini

    try:

        analysis = analyze_with_gemini(
            all_results
        )

        stories = validate_analysis(
            analysis,
            read_items,
            all_results
        )

        report["analyse_ia"] = {

            "status": "SUCCÈS",

            "modele": MODEL,

            "resume_recherche": analysis.get(
                "resume_recherche", ""
            ),

            "nombre_histoires_proposees": len(stories),

            "histoires": stories
        }

    except Exception as error:

        report["analyse_ia"] = {

            "status": "ÉCHEC",

            "modele": MODEL,

            "erreur": str(error)[:1000],

            "histoires": []
        }

        print("Erreur Gemini :", error)

    # Enregistrement

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            report,
            file,
            ensure_ascii=False,
            indent=2
        )

    print("=" * 60)
    print("RECHERCHE TERMINÉE")
    print("Résultats :", len(all_results))
    print("Articles lus :", read_count)
    print(
        "Histoires proposées :",
        report["analyse_ia"].get(
            "nombre_histoires_proposees", 0
        )
    )
    print(
        "Analyse Gemini :",
        report["analyse_ia"]["status"]
    )
    print("Rapport :", OUTPUT_FILE)
    print("Publication YouTube : DÉSACTIVÉE")
    print("=" * 60)


if __name__ == "__main__":
    main()

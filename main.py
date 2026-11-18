
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
# OBSERVATEUR ACTIF AI
# Recherche documentaire quotidienne sur toute l'Afrique
# ==========================================================

CHANNEL = "Observateur Actif"
MODEL = "gemini-3.8-flash"

MAX_RESULTS_PER_QUERY = 5
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

COOKIE = "CONSENT=YES+cb; SOCS=CAI"


# ==========================================================
# 1. RECHERCHES RÉPARTIES PAR RÉGION
# ==========================================================

def build_searches():

    since = (
        datetime.now(timezone.utc) - timedelta(days=730)
    ).date().isoformat()

    date_filter = f"after:{since}"

    return [
        (
            "Afrique de l'Ouest - français",
            f"(Mali OR Sénégal OR Burkina Faso OR Niger OR "
            f"Guinée OR Ghana OR Nigeria OR Bénin OR Togo) "
            f"(archéologie OR civilisation ancienne OR ruines OR mystère) "
            f"{date_filter}"
        ),
        (
            "Afrique de l'Ouest - anglais",
            f"(Mali OR Senegal OR Burkina Faso OR Niger OR Ghana OR "
            f"Nigeria OR Benin OR Guinea) "
            f"(archaeology OR ancient civilization OR ruins OR mystery) "
            f"{date_filter}"
        ),
        (
            "Afrique du Nord - français",
            f"(Égypte OR Maroc OR Algérie OR Tunisie OR Libye OR Soudan) "
            f"(archéologie OR ruines OR civilisation ancienne OR découverte) "
            f"{date_filter}"
        ),
        (
            "Afrique du Nord - anglais",
            f"(Egypt OR Morocco OR Algeria OR Tunisia OR Libya OR Sudan) "
            f"(archaeology OR ancient ruins OR forgotten civilization) "
            f"{date_filter}"
        ),
        (
            "Afrique centrale - français",
            f"(RDC OR Congo OR Cameroun OR Gabon OR Tchad OR Angola) "
            f"(archéologie OR royaume ancien OR civilisation OR ruines) "
            f"{date_filter}"
        ),
        (
            "Afrique centrale - anglais",
            f"(DR Congo OR Cameroon OR Gabon OR Chad OR Angola OR Congo) "
            f"(archaeology OR ancient kingdom OR ruins OR mystery) "
            f"{date_filter}"
        ),
        (
            "Afrique de l'Est - anglais",
            f"(Ethiopia OR Kenya OR Tanzania OR Uganda OR Rwanda OR Somalia) "
            f"(archaeology OR ancient civilization OR lost city OR ruins) "
            f"{date_filter}"
        ),
        (
            "Afrique de l'Est - français",
            f"(Éthiopie OR Kenya OR Tanzanie OR Ouganda OR Rwanda OR Somalie) "
            f"(archéologie OR civilisation ancienne OR cité perdue) "
            f"{date_filter}"
        ),
        (
            "Afrique australe - anglais",
            f"(Zimbabwe OR Zambia OR South Africa OR Botswana OR Namibia "
            f"OR Mozambique) "
            f"(archaeology OR ancient ruins OR forgotten civilization) "
            f"{date_filter}"
        ),
        (
            "Afrique australe - français",
            f"(Zimbabwe OR Zambie OR Afrique du Sud OR Botswana OR "
            f"Namibie OR Mozambique) "
            f"(archéologie OR ruines anciennes OR civilisation oubliée) "
            f"{date_filter}"
        ),
    ]


# ==========================================================
# 2. OUTILS DE NETTOYAGE ET DE RÉCUPÉRATION
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


# ==========================================================
# 3. RECHERCHE GOOGLE NEWS RSS
# ==========================================================

def google_news_search(query, region):

    encoded = urllib.parse.quote(query)

    url = (
        "https://news.google.com/rss/search?q="
        + encoded
        + "&hl=fr&gl=FR&ceid=FR:fr"
    )

    try:

        content, _, _ = fetch_url(url, timeout=25)

        root = ET.fromstring(content)

        results = []

        for item in root.findall(".//item"):

            title = clean_text(item.findtext("title", ""))

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
                "fetch_status": "NON CONSULTÉ",
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
        "Referer": "https://news.google.com/",
    }

    page_content, final_url, _ = fetch_url(
        page_url,
        headers=page_headers,
        timeout=25
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

        # Google peut parfois effectuer une redirection normale.
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
        ),
    }

    response_content, _, _ = fetch_url(
        "https://news.google.com/_/DotsSplashUi/data/batchexecute"
        "?rpcids=Fbv4je",
        data=body,
        headers=post_headers,
        timeout=25
    )

    raw = response_content.decode(
        "utf-8",
        errors="replace"
    )

    # La réponse peut contenir plusieurs lignes.
    # On cherche la ligne contenant la réponse Fbv4je.

    for line in raw.splitlines():

        line = line.strip()

        if not line.startswith("["):
            continue

        try:
            frames = json.loads(line)
        except Exception:
            continue

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
# 5. EXTRACTION DU TEXTE DES ARTICLES
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
            publisher_url,
            timeout=25
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

        item["fetch_status"] = (
            f"ERREUR HTTP {error.code}"
        )

    except Exception as error:

        item["fetch_status"] = (
            f"ERREUR : {str(error)[:200]}"
        )

    return item


# ==========================================================
# 6. ANALYSE GEMINI
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

    output = getattr(
        response,
        "output",
        None
    ) or []

    for item in output:

        content = getattr(
            item,
            "content",
            None
        ) or []

        for part in content:

            value = getattr(
                part,
                "text",
                None
            )

            if value:
                collected.append(value)

    return "\n".join(collected)


def analyze_with_gemini(items):

    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY est absent des secrets GitHub."
        )

    client = genai.Client(
        api_key=api_key
    )

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
            "article_full_text_fetched":
                item["article_full_text_fetched"],
            "article_text": item["article_text"][:6500],
            "fetch_status": item["fetch_status"],
        })

    prompt = f"""
Tu es le documentaliste de la chaîne YouTube Observateur Actif.

OBJECTIF :
Trouver des histoires africaines réelles, historiques et documentées
pour des vidéos de 45 à 60 secondes.

THÈMES PRIORITAIRES :
1. Mystères historiques.
2. Lieux mystérieux.
3. Civilisations oubliées.

ZONE :
Les 54 pays du continent africain.

CONSIGNES STRICTES :

1. Ne jamais inventer une histoire.
2. Ne jamais inventer un pays, une date, un nom ou une découverte.
3. Ne jamais inventer une source ou une URL.
4. Ne pas confondre une légende et un fait historique.
5. Ne pas présenter une hypothèse comme une certitude.
6. Écarter les histoires concernant l'Amérique, l'Europe ou l'Asie,
   sauf si le sujet porte réellement sur un fait historique africain.
7. Le pays concerné doit être identifiable.
8. Utiliser uniquement les sources fournies.
9. Ne pas prétendre avoir lu un article dont le texte est absent.
10. Une simple manchette n'est pas une preuve.
11. Une source ne confirme pas automatiquement une autre source.
12. Ne jamais inventer une corroboration.
13. Si les preuves sont insuffisantes, ne proposer aucune histoire.

RÈGLE ESSENTIELLE :

Une source n'est considérée comme lue que si
article_full_text_fetched = true.

Si aucune source n'a son texte intégral disponible,
retourne obligatoirement une liste histoires vide.

Si les sources ne permettent pas d'établir les faits,
retourne également une liste vide.

SOURCES DISPONIBLES :

{json.dumps(source_list, ensure_ascii=False)}

Retourne uniquement un JSON valide avec cette structure :

{{
  "resume_recherche": "Résumé honnête de la recherche",
  "histoires": [
    {{
      "titre": "Titre factuel",
      "pays": "Pays africain",
      "region_afrique": "Région",
      "periode_historique": "Période connue",
      "resume_factuel": "Résumé des faits documentés",
      "faits_confirmes": [
        "Fait directement soutenu par les articles lus"
      ],
      "hypotheses_ou_incertitudes": [
        "Éléments qui restent incertains"
      ],
      "nature": "Mystère historique",
      "source_ids": [1, 2],
      "raison_decision": "Explication",
      "idee_accroche": "Accroche prudente",
      "potentiel_short": "Faible, moyen ou élevé"
    }}
  ]
}}

Maximum : 5 histoires.

Ne retourne aucune histoire si les sources ne sont pas suffisantes.
"""

    response = client.interactions.create(
        model=MODEL,
        input=prompt
    )

    return extract_json(
        get_response_text(response)
    )


# ==========================================================
# 7. VALIDATION DES SOURCES ET DES HISTOIRES
# ==========================================================

AFRICAN_COUNTRIES = {
    "mali", "senegal", "burkina faso", "niger",
    "guinea", "guinée", "ghana", "nigeria",
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
    "guinée équatoriale",

    "ethiopia", "éthiopie", "kenya",
    "tanzania", "tanzanie", "uganda",
    "rwanda", "burundi", "somalia",
    "somalie", "eritrea", "érythrée",
    "djibouti", "south sudan",
    "soudan du sud",

    "south africa", "afrique du sud",
    "zimbabwe", "zambia", "zambie",
    "botswana", "namibia", "namibie",
    "mozambique", "madagascar",
    "malawi", "lesotho", "eswatini",
    "swaziland"
}


def validate_analysis(analysis, items):

    valid_stories = []

    for story in analysis.get("histoires", []):

        if not isinstance(story, dict):
            continue

        country = str(
            story.get("pays", "")
        ).strip().lower()

        if country not in AFRICAN_COUNTRIES:
            continue

        ids = story.get("source_ids", [])

        if not isinstance(ids, list):
            ids = []

        valid_ids = []

        for value in ids:

            if (
                isinstance(value, int)
                and 1 <= value <= len(items)
                and value not in valid_ids
            ):
                valid_ids.append(value)

        selected_sources = [
            items[index - 1]
            for index in valid_ids
        ]

        read_sources = [
            source
            for source in selected_sources
            if source["article_full_text_fetched"]
        ]

        domains = set()

        for source in read_sources:

            host = urlparse(
                source.get("publisher_url") or ""
            ).hostname

            if host:
                domains.add(
                    host.lower().removeprefix("www.")
                )

        story["source_ids"] = valid_ids

        story["sources"] = [
            {
                "source_id": index,
                "title": items[index - 1]["title"],
                "publisher": items[index - 1]["publisher"],
                "url": (
                    items[index - 1]["publisher_url"]
                    or items[index - 1]["rss_url"]
                ),
                "article_full_text_fetched":
                    items[index - 1]["article_full_text_fetched"]
            }
            for index in valid_ids
        ]

        story["nombre_articles_lus"] = len(read_sources)

        story["nombre_domaines_distincts"] = len(domains)

        # Aucun sujet n'est automatiquement vérifié.
        story["decision_editoriale"] = (
            "EN ATTENTE DE VÉRIFICATION"
        )

        if len(read_sources) == 0:

            story["raison_controle"] = (
                "Aucun texte intégral n'a été récupéré."
            )

        elif len(read_sources) < 2:

            story["raison_controle"] = (
                "Une seule source lue : corroboration insuffisante."
            )

        elif len(domains) < 2:

            story["raison_controle"] = (
                "Les sources lues ne proviennent pas de "
                "deux domaines distincts."
            )

        else:

            story["raison_controle"] = (
                "Plusieurs articles ont été lus. "
                "Une vérification humaine de leur indépendance "
                "et des faits reste obligatoire."
            )

        valid_stories.append(story)

    return valid_stories


# ==========================================================
# 8. PROGRAMME PRINCIPAL
# ==========================================================

def main():

    os.makedirs("output", exist_ok=True)

    now = datetime.now(timezone.utc)

    print("=" * 60)
    print("OBSERVATEUR ACTIF AI")
    print("RECHERCHE DOCUMENTAIRE AFRICAINE")
    print("Date UTC :", now.isoformat())
    print("=" * 60)

    all_results = []

    seen = set()

    query_stats = []

    searches = build_searches()

    # Recherche répartie entre les dix requêtes.
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

            if key and key not in seen:

                seen.add(key)

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

    # Classement par date de publication.
    all_results.sort(
        key=lambda item: item.get("published_at") or "",
        reverse=True
    )

    print("Résultats uniques :", len(all_results))

    # Résolution et lecture des articles.
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

    read_count = sum(
        1
        for item in all_results
        if item["article_full_text_fetched"]
    )

    report = {

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

    # Analyse Gemini.
    try:

        analysis = analyze_with_gemini(
            all_results
        )

        stories = validate_analysis(
            analysis,
            all_results
        )

        report["analyse_ia"] = {

            "status": "SUCCÈS",

            "modele": MODEL,

            "resume_recherche": analysis.get(
                "resume_recherche",
                ""
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

    # Enregistrement du rapport.
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
        "Analyse Gemini :",
        report["analyse_ia"]["status"]
    )
    print("Rapport :", OUTPUT_FILE)
    print("Publication YouTube : DÉSACTIVÉE")
    print("=" * 60)


if __name__ == "__main__":
    main()

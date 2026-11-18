
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).parent
DATA = PROJECT / "data"
OUTPUT = PROJECT / "output"

HISTORY_FILE = DATA / "published_history.json"

# Recherche dans les cinq grandes régions africaines.
REGIONS = {
    "Afrique de l'Ouest": [
        "Mali", "Senegal", "Niger", "Nigeria", "Ghana",
        "Guinea", "Burkina Faso", "Benin", "Togo",
        "Mauritania", "Gambia", "Sierra Leone", "Liberia",
        "Ivory Coast"
    ],
    "Afrique du Nord": [
        "Egypt", "Sudan", "Morocco", "Algeria",
        "Tunisia", "Libya"
    ],
    "Afrique centrale": [
        "Cameroon", "Chad", "Congo", "Gabon",
        "Angola", "Central African Republic",
        "Democratic Republic of the Congo"
    ],
    "Afrique de l'Est": [
        "Ethiopia", "Kenya", "Tanzania", "Uganda",
        "Somalia", "Rwanda", "Burundi", "Eritrea",
        "Madagascar", "Mozambique"
    ],
    "Afrique australe": [
        "South Africa", "Zimbabwe", "Zambia",
        "Botswana", "Namibia", "Malawi",
        "Lesotho", "Eswatini"
    ]
}

# Termes liés à la ligne éditoriale.
THEMES = [
    "archaeology",
    "excavation",
    '"ancient ruins"',
    '"lost city"',
    '"ancient kingdom"',
    '"historical mystery"',
    "pyramid",
    "temple",
    "tomb",
    "manuscript",
    '"rock art"',
    "civilization"
]

AFRICA_TEXT = [
    "africa", "african", "mali", "sudan", "egypt",
    "ethiopia", "ghana", "nigeria", "niger", "senegal",
    "guinea", "burkina", "ivory coast", "cote d'ivoire",
    "benin", "togo", "gambia", "mauritania", "morocco",
    "algeria", "tunisia", "libya", "chad", "cameroon",
    "congo", "angola", "zimbabwe", "zambia", "botswana",
    "namibia", "kenya", "tanzania", "uganda", "rwanda",
    "burundi", "somalia", "eritrea", "mozambique",
    "madagascar", "malawi", "sierra leone", "liberia",
    "nubia", "kush", "meroe", "timbuktu", "djenne",
    "great zimbabwe", "nok culture", "carthage"
]

EDITORIAL_TERMS = [
    "archaeology", "archaeological", "ancient",
    "civilization", "civilisation", "kingdom",
    "empire", "ruins", "historical", "history",
    "mystery", "mysterious", "temple", "pyramid",
    "tomb", "manuscript", "excavation", "heritage",
    "culture", "city", "settlement", "rock art",
    "metallurgy", "medieval", "prehistoric"
]

ERRORS = []


def load_json(path, default):
    if not path.exists():
        return default

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def clean_text(value):
    value = re.sub(r"<[^>]+>", " ", str(value or ""))
    return re.sub(r"\s+", " ", value).strip()


def fetch_json(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "ObservateurActifAI/3.0"
        }
    )

    with urllib.request.urlopen(request, timeout=40) as response:
        body = response.read().decode(
            "utf-8",
            errors="replace"
        )

    return json.loads(body)


def africa_related(text):
    text = text.lower()

    return any(
        word in text
        for word in AFRICA_TEXT
    )


def editorial_related(text):
    text = text.lower()

    return any(
        word in text
        for word in EDITORIAL_TERMS
    )


def search_gdelt(region, countries):
    theme_query = "(" + " OR ".join(THEMES) + ")"

    country_query = "(" + " OR ".join(
        '"' + country + '"'
        if " " in country else country
        for country in countries
    ) + ")"

    # Les pays sont intégrés directement dans la requête.
    # Le titre n'a donc pas besoin de répéter le nom du pays.
    full_query = theme_query + " " + country_query

    params = {
        "query": full_query,
        "mode": "ArtList",
        "format": "json",
        "maxrecords": "75",
        "timespan": "3m",
        "sort": "DateDesc"
    }

    url = (
        "https://api.gdeltproject.org/api/v2/doc/doc?"
        + urllib.parse.urlencode(params)
    )

    try:
        data = fetch_json(url)
        articles = data.get("articles", [])

        print(
            "GDELT -",
            region,
            ":",
            len(articles),
            "articles reçus"
        )

        return articles

    except Exception as error:
        message = "GDELT - " + region + " : " + str(error)
        print(message)
        ERRORS.append(message)
        return []


def search_wikipedia(query):
    params = {
        "q": query,
        "limit": "20"
    }

    url = (
        "https://en.wikipedia.org/w/rest.php/v1/search/page?"
        + urllib.parse.urlencode(params)
    )

    try:
        data = fetch_json(url)
        return data.get("pages", [])

    except Exception as error:
        message = "Wikimedia : " + str(error)
        print(message)
        ERRORS.append(message)
        return []


def main():
    print("======================================")
    print("OBSERVATEUR ACTIF AI")
    print("MOTEUR DE RECHERCHE AFRICAIN")
    print("======================================")

    DATA.mkdir(exist_ok=True)
    OUTPUT.mkdir(exist_ok=True)

    history = load_json(HISTORY_FILE, [])

    used_urls = {
        item.get("url")
        for item in history
        if isinstance(item, dict)
    }

    candidates = {}

    # 1. RECHERCHE DANS LES MÉDIAS AVEC GDELT

    print("\n1. RECHERCHE DANS LES MÉDIAS")

    for region, countries in REGIONS.items():

        print("\nRégion :", region)

        articles = search_gdelt(region, countries)

        for article in articles:

            title = clean_text(
                article.get("title")
            )

            url = article.get("url", "").strip()

            if not title:
                continue

            if not url.startswith("https://"):
                continue

            candidates[url] = {
                "title": title,
                "url": url,
                "publisher": article.get(
                    "domain",
                    "Source inconnue"
                ),
                "published_at": article.get(
                    "seendate",
                    ""
                ),
                "region_recherchee": region,
                "source_type": "Article de presse - GDELT"
            }

        # Pause entre les requêtes.
        time.sleep(6)

    # 2. RECHERCHE DOCUMENTAIRE WIKIMEDIA

    print("\n2. RECHERCHE DOCUMENTAIRE")

    wiki_queries = [
        "African archaeology ancient sites",
        "ancient African kingdoms civilizations",
        "lost cities and ruins in Africa",
        "African historical mysteries",
        "African archaeological discoveries"
    ]

    for query in wiki_queries:

        print("Wikimedia :", query)

        pages = search_wikipedia(query)

        for page in pages:

            title = clean_text(
                page.get("title")
            )

            description = clean_text(
                page.get("description")
            )

            excerpt = clean_text(
                page.get("excerpt")
            )

            key = page.get("key", "")

            combined = (
                title + " " +
                description + " " +
                excerpt
            )

            if not title or not key:
                continue

            if not africa_related(combined):
                continue

            if not editorial_related(combined):
                continue

            url = (
                "https://en.wikipedia.org/wiki/"
                + urllib.parse.quote(
                    key.replace(" ", "_")
                )
            )

            candidates[url] = {
                "title": title,
                "description": description,
                "url": url,
                "publisher": "Wikipedia",
                "published_at": "",
                "source_type": "Documentation à corroborer"
            }

    # 3. ÉLIMINATION DES DOUBLONS

    new_candidates = [
        item
        for item in candidates.values()
        if item["url"] not in used_urls
    ]

    # 4. CLASSEMENT DES RÉSULTATS

    new_candidates.sort(
        key=lambda item: (
            item["source_type"] != "Article de presse - GDELT",
            item["title"].lower()
        )
    )

    # 5. SAUVEGARDE

    result = {
        "date_recherche": datetime.now(
            timezone.utc
        ).isoformat(),

        "chaine": "Observateur Actif",

        "zone": "Toute l'Afrique",

        "priorite_editoriale": [
            "Mystères historiques",
            "Lieux mystérieux",
            "Civilisations oubliées"
        ],

        "nombre_resultats": len(new_candidates),

        "nombre_articles_presse": sum(
            item["source_type"] == "Article de presse - GDELT"
            for item in new_candidates
        ),

        "nombre_documents": sum(
            item["source_type"] == "Documentation à corroborer"
            for item in new_candidates
        ),

        "erreurs_recherche": ERRORS,

        "statut": "CANDIDATS_A_VERIFIER",

        "publication_autorisee": False,

        "sujets": new_candidates,

        "regle_editoriale": (
            "Les sujets doivent être corroborés par plusieurs "
            "sources indépendantes avant toute publication. "
            "Aucune histoire ne doit être inventée."
        )
    }

    save_json(
        OUTPUT / "daily_research.json",
        result
    )

    print("\n======================================")
    print("RECHERCHE TERMINEE")
    print("======================================")

    print(
        "Total des résultats :",
        len(new_candidates)
    )

    print(
        "Articles de presse :",
        result["nombre_articles_presse"]
    )

    print(
        "Documents Wikimedia :",
        result["nombre_documents"]
    )

    print(
        "Erreurs rencontrées :",
        len(ERRORS)
    )

    print(
        "Fichier créé : output/daily_research.json"
    )

    print(
        "Publication automatique : DESACTIVEE"
    )


if __name__ == "__main__":
    main()

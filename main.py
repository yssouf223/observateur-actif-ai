
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

AFRICA = [
    "Africa", "African", "Mali", "Sudan", "Egypt", "Ethiopia",
    "Ghana", "Nigeria", "Niger", "Senegal", "Guinea",
    "Burkina Faso", "Ivory Coast", "Cote d'Ivoire", "Benin",
    "Togo", "Gambia", "Mauritania", "Morocco", "Algeria",
    "Tunisia", "Libya", "Chad", "Cameroon", "Congo",
    "Democratic Republic of the Congo", "Angola", "Zimbabwe",
    "Zambia", "Botswana", "Namibia", "South Africa",
    "Kenya", "Tanzania", "Uganda", "Rwanda", "Burundi",
    "Somalia", "Eritrea", "Djibouti", "Mozambique",
    "Madagascar", "Malawi", "Lesotho", "Eswatini",
    "Central African Republic", "Gabon", "Equatorial Guinea",
    "Sierra Leone", "Liberia"
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
    "nubia", "kush", "meroë", "meroe", "timbuktu",
    "djenné", "djenne", "great zimbabwe"
]

SEARCHES = [
    '("archaeological discovery" OR archaeology OR excavation OR "ancient ruins")',
    '("lost city" OR "forgotten kingdom" OR "ancient civilization")',
    '("historical mystery" OR "mysterious site" OR "ancient city")',
    '(pyramid OR temple OR tomb OR manuscript OR "rock art")'
]

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
        headers={"User-Agent": "ObservateurActifAI/2.0"}
    )
    with urllib.request.urlopen(request, timeout=40) as response:
        content_type = response.headers.get("Content-Type", "")
        body = response.read().decode("utf-8", errors="replace")

    if "json" not in content_type.lower():
        raise ValueError("Réponse non JSON : " + body[:180])

    return json.loads(body)

def africa_related(text):
    text = text.lower()
    return any(word in text for word in AFRICA_TEXT)

def search_gdelt(query):
    africa_group = "(" + " OR ".join(
        '"' + country + '"' if " " in country else country
        for country in AFRICA
    ) + ")"

    full_query = query + " " + africa_group

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
        return data.get("articles", [])
    except Exception as error:
        print("GDELT : recherche impossible :", str(error))
        return []

def search_wikipedia(query):
    params = {"q": query, "limit": "20"}
    url = (
        "https://en.wikipedia.org/w/rest.php/v1/search/page?"
        + urllib.parse.urlencode(params)
    )

    try:
        data = fetch_json(url)
        return data.get("pages", [])
    except Exception as error:
        print("Wikimedia :", str(error))
        return []

def main():
    print("OBSERVATEUR ACTIF AI - RECHERCHE AFRICAINE")

    DATA.mkdir(exist_ok=True)
    OUTPUT.mkdir(exist_ok=True)

    history = load_json(HISTORY_FILE, [])
    used_urls = {
        item.get("url")
        for item in history
        if isinstance(item, dict)
    }

    candidates = {}

    print("1. Recherche dans les médias avec GDELT")

    for query in SEARCHES:
        print("Recherche :", query)
        articles = search_gdelt(query)

        for article in articles:
            title = clean_text(article.get("title"))
            url = article.get("url", "").strip()
            domain = article.get("domain", "Source inconnue")

            if not title or not url.startswith("https://"):
                continue

            if not africa_related(title):
                continue

            candidates[url] = {
                "title": title,
                "url": url,
                "publisher": domain,
                "published_at": article.get("seendate", ""),
                "source_type": "Article de presse trouvé par GDELT"
            }

        time.sleep(6)

    print("2. Recherche documentaire avec Wikimedia")

    wiki_queries = [
        "African archaeology",
        "ancient African kingdoms",
        "lost cities Africa",
        "mysterious historical places Africa",
        "ancient African civilizations"
    ]

    for query in wiki_queries:
        for page in search_wikipedia(query):
            title = clean_text(page.get("title"))
            description = clean_text(page.get("description"))
            excerpt = clean_text(page.get("excerpt"))
            key = page.get("key", "")

            combined = title + " " + description + " " + excerpt

            if not title or not key:
                continue

            if not africa_related(combined):
                continue

            url = "https://en.wikipedia.org/wiki/" + urllib.parse.quote(
                key.replace(" ", "_")
            )

            candidates[url] = {
                "title": title,
                "description": description,
                "url": url,
                "publisher": "Wikipedia",
                "published_at": "",
                "source_type": "Piste documentaire à corroborer"
            }

    new_candidates = [
        item for item in candidates.values()
        if item["url"] not in used_urls
    ]

    result = {
        "date_recherche": datetime.now(timezone.utc).isoformat(),
        "chaine": "Observateur Actif",
        "zone": "Toute l'Afrique",
        "priorite_editoriale": [
            "Mystères historiques",
            "Lieux mystérieux",
            "Civilisations oubliées"
        ],
        "nombre_resultats": len(new_candidates),
        "statut": "CANDIDATS_A_VERIFIER",
        "publication_autorisee": False,
        "sujets": new_candidates,
        "regle_editoriale": (
            "Aucun sujet ne peut être considéré comme vrai "
            "sans vérification par plusieurs sources indépendantes."
        )
    }

    save_json(OUTPUT / "daily_research.json", result)

    print("Résultats trouvés :", len(candidates))
    print("Nouveaux sujets :", len(new_candidates))
    print("Fichier : output/daily_research.json")
    print("Publication automatique : désactivée")

if __name__ == "__main__":
    main()

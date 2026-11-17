
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

# Toute l'Afrique : priorité aux mystères historiques et archéologiques.
SEARCHES = [
    '"lost city" Africa OR African',
    '"ancient civilization" Africa OR African',
    '"archaeological discovery" Africa OR African',
    '"mysterious place" Africa OR African',
    '"ancient ruins" Africa OR African',
    '"forgotten kingdom" Africa OR African',
]

KEYWORDS = [
    "ancient", "archaeology", "archaeological", "civilization",
    "civilisation", "ruins", "kingdom", "empire", "mystery",
    "mysterious", "lost city", "forgotten", "historical",
    "history", "temple", "pyramid", "tomb", "manuscript",
    "settlement", "heritage", "africa", "african"
]


def load_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
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
            "User-Agent": "ObservateurActifAI/1.0 (documentary research bot)"
        }
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def search_gdelt(query):
    params = {
        "query": query,
        "mode": "ArtList",
        "format": "json",
        "maxrecords": "30",
        "timespan": "7d",
        "sort": "DateDesc",
    }
    url = (
        "https://api.gdeltproject.org/api/v2/doc/doc?"
        + urllib.parse.urlencode(params)
    )

    try:
        data = fetch_json(url)
        return data.get("articles", [])
    except Exception as error:
        print("Erreur GDELT :", error)
        return []


def search_wikipedia(query):
    params = {
        "q": query,
        "limit": "10"
    }
    url = (
        "https://en.wikipedia.org/w/rest.php/v1/search/page?"
        + urllib.parse.urlencode(params)
    )

    try:
        data = fetch_json(url)
        return data.get("pages", [])
    except Exception as error:
        print("Erreur Wikimedia :", error)
        return []


def relevant(title, description=""):
    text = (title + " " + description).lower()
    return any(word in text for word in KEYWORDS)


def collect_candidates():
    candidates = {}
    print("Recherche Internet : GDELT...")

    for query in SEARCHES:
        print("Requête :", query)
        articles = search_gdelt(query)

        for article in articles:
            title = clean_text(article.get("title"))
            url = article.get("url", "").strip()

            if not title or not url.startswith("https://"):
                continue

            if not relevant(title):
                continue

            candidates[url] = {
                "title": title,
                "url": url,
                "publisher": article.get("domain", "Source inconnue"),
                "published_at": article.get("seendate", ""),
                "source_type": "Presse en ligne - GDELT",
            }

        # Respecter un intervalle entre les requêtes.
        time.sleep(5)

    print("Recherche documentaire : Wikimedia...")

    wiki_queries = [
        "ancient African civilizations",
        "lost cities in Africa",
        "African archaeological sites",
        "ancient kingdoms of Africa",
        "mysterious historical places in Africa",
    ]

    for query in wiki_queries:
        for page in search_wikipedia(query):
            title = clean_text(page.get("title"))
            key = page.get("key", "")

            if not title or not key:
                continue

            url = "https://en.wikipedia.org/wiki/" + urllib.parse.quote(
                key.replace(" ", "_")
            )

            candidates[url] = {
                "title": title,
                "url": url,
                "publisher": "Wikipedia",
                "published_at": "",
                "source_type": "Documentation encyclopédique",
            }

    return list(candidates.values())


def main():
    print("===================================")
    print("OBSERVATEUR ACTIF AI")
    print("Moteur de recherche africain")
    print("===================================")

    DATA.mkdir(exist_ok=True)
    OUTPUT.mkdir(exist_ok=True)

    history = load_json(HISTORY_FILE, [])
    used_urls = {
        item.get("url")
        for item in history
        if isinstance(item, dict)
    }

    candidates = collect_candidates()

    new_candidates = [
        item for item in candidates
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
        "avertissement": (
            "Les résultats sont des pistes documentaires. "
            "Ils ne sont pas encore vérifiés."
        ),
        "sujets": new_candidates
    }

    save_json(OUTPUT / "daily_research.json", result)

    print("Résultats trouvés :", len(candidates))
    print("Nouveaux sujets :", len(new_candidates))
    print("Fichier créé : output/daily_research.json")
    print("Publication automatique : NON, vérification nécessaire.")


if __name__ == "__main__":
    main()

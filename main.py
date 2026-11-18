
import json
import re
import time
import html
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path


# ==========================================
# OBSERVATEUR ACTIF AI
# Recherche quotidienne de mystères africains
# ==========================================

CHANNEL = "Observateur Actif"
COUNTRY = "Toute l'Afrique"

THEMES = [
    "mystère historique",
    "lieu mystérieux",
    "civilisation oubliée",
    "archéologie",
    "ville ancienne",
    "royaume ancien",
    "site archéologique",
    "ruines anciennes",
    "art rupestre",
    "tombe ancienne",
    "manuscrit historique",
    "civilisation antique"
]

# Pays et lieux africains pour le ciblage géographique.
AFRICA_TERMS = [
    "africa", "african", "mali", "senegal", "niger",
    "guinea", "burkina faso", "ivory coast", "cote d'ivoire",
    "ghana", "togo", "benin", "nigeria", "cameroon",
    "chad", "sudan", "south sudan", "ethiopia", "eritrea",
    "somalia", "kenya", "uganda", "tanzania", "rwanda",
    "burundi", "congo", "democratic republic of the congo",
    "gabon", "angola", "zambia", "zimbabwe", "botswana",
    "namibia", "south africa", "mozambique", "malawi",
    "madagascar", "algeria", "morocco", "tunisia", "libya",
    "egypt", "mauritania", "gambia", "sierra leone",
    "liberia", "niger delta", "sahel", "sahara",
    "timbuktu", "tombouctou", "djenne", "djenné",
    "gao", "kidal", "segou", "sikasso", "kalana",
    "great zimbabwe", "aksum", "axum", "nubia",
    "carthage", "meroe", "kush", "benin city",
    "ife", "nok", "kilwa", "lalibela", "gobero",
    "tassili", "jebel irhoud", "mapungubwe",
    "djenne-djenno", "djenné-djenno"
]

HISTORY_TERMS = [
    "ancient", "archaeology", "archaeological",
    "excavation", "ruins", "civilization",
    "civilisation", "kingdom", "empire",
    "historical", "prehistoric", "medieval",
    "tomb", "temple", "pyramid", "manuscript",
    "rock art", "cave", "fossil", "remains",
    "heritage", "settlement", "lost city",
    "discovery", "discovered", "century",
    "years old", "burial", "monument",
    "fortress", "archaeologists", "relic"
]

KNOWN_HISTORICAL_PLACES = [
    "timbuktu", "tombouctou", "djenne", "djenné",
    "djenne-djenno", "djenné-djenno",
    "great zimbabwe", "aksum", "axum", "nubia",
    "carthage", "meroe", "kush", "benin city",
    "ife", "nok", "kilwa", "lalibela", "gobero",
    "tassili", "jebel irhoud", "mapungubwe",
    "olduvai", "giza", "saqqara", "abu simbel",
    "gondar", "mohenjo", "rhapt a"
]

GDELT_THEMES = [
    "archaeology",
    "excavation",
    '"ancient ruins"',
    '"lost city"',
    '"ancient kingdom"',
    '"historical mystery"',
    "pyramid",
    "temple",
    "tomb",
    '"rock art"',
    "civilization",
    "prehistoric"
]

AFRICAN_COUNTRIES = [
    "Mali", "Senegal", "Niger", "Guinea",
    '"Burkina Faso"', "Ghana", "Togo", "Benin",
    "Nigeria", "Cameroon", "Chad", "Sudan",
    "Ethiopia", "Kenya", "Uganda", "Tanzania",
    "Somalia", "Rwanda", "Burundi", "Congo",
    '"South Africa"', "Zimbabwe", "Zambia",
    "Botswana", "Namibia", "Angola",
    "Mozambique", "Madagascar", "Egypt",
    "Morocco", "Algeria", "Tunisia", "Libya",
    "Mauritania", "Gambia", "Liberia",
    '"Sierra Leone"', "Gabon", "Eritrea",
    '"South Sudan"', '"Ivory Coast"'
]


def normalize(text):
    text = html.unescape(str(text or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def contains_term(text, terms):
    text = normalize(text)
    return any(normalize(term) in text for term in terms)


def is_relevant_title(title):
    """
    Filtre prudent : un titre doit mentionner
    un repère africain et un élément historique,
    ou un lieu historique africain connu.
    """
    title = normalize(title)

    has_geography = contains_term(title, AFRICA_TERMS)
    has_history = contains_term(title, HISTORY_TERMS)
    has_known_place = contains_term(
        title, KNOWN_HISTORICAL_PLACES
    )

    return (
        (has_geography and has_history)
        or has_known_place
    )


def fetch_json(url, timeout=30):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "ObservateurActifAI/2.0 "
                "(African historical research)"
            ),
            "Accept": "application/json"
        }
    )

    with urllib.request.urlopen(
        request, timeout=timeout
    ) as response:
        return json.loads(response.read().decode("utf-8"))


# ==========================================
# RECHERCHE GDELT
# ==========================================

def search_gdelt():
    results = []
    errors = []

    theme_query = "(" + " OR ".join(GDELT_THEMES) + ")"
    country_query = "(" + " OR ".join(AFRICAN_COUNTRIES) + ")"

    query = theme_query + " " + country_query

    params = {
        "query": query,
        "mode": "ArtList",
        "format": "json",
        "maxrecords": "100",
        "timespan": "30d",
        "sort": "DateDesc"
    }

    url = (
        "https://api.gdeltproject.org/api/v2/doc/doc?"
        + urllib.parse.urlencode(params)
    )

    for attempt in range(3):
        try:
            data = fetch_json(url, timeout=45)
            articles = data.get("articles", [])

            for article in articles:
                title = article.get("title", "").strip()
                link = article.get("url", "").strip()

                if not title or not link:
                    continue

                if not is_relevant_title(title):
                    continue

                results.append({
                    "titre": title,
                    "url": link,
                    "source": article.get("domain", ""),
                    "date": article.get("seendate", ""),
                    "type": "Article de presse",
                    "zone": "Afrique - à confirmer",
                    "verification": "A_VERIFIER",
                    "origine": "GDELT"
                })

            return results, errors

        except urllib.error.HTTPError as error:
            message = "GDELT HTTP " + str(error.code)
            errors.append(message)

            if error.code == 429 and attempt < 2:
                time.sleep(30 * (attempt + 1))
                continue

            break

        except Exception as error:
            errors.append(
                "GDELT : " + str(error)[:250]
            )
            break

    return results, errors


# ==========================================
# RECHERCHE WIKIPEDIA
# ==========================================

def search_wikipedia():
    results = []
    errors = []

    search_query = (
        "Africa archaeology ancient kingdoms "
        "historical sites forgotten civilizations"
    )

    params = {
        "action": "query",
        "list": "search",
        "srsearch": search_query,
        "srnamespace": "0",
        "srlimit": "50",
        "format": "json"
    }

    url = (
        "https://en.wikipedia.org/w/api.php?"
        + urllib.parse.urlencode(params)
    )

    try:
        data = fetch_json(url, timeout=30)
        pages = data.get("query", {}).get("search", [])

        for page in pages:
            title = page.get("title", "").strip()
            snippet = page.get("snippet", "")
            text = title + " " + snippet

            has_africa = contains_term(
                text, AFRICA_TERMS
            )
            has_history = contains_term(
                text, HISTORY_TERMS
            )
            has_known_place = contains_term(
                text, KNOWN_HISTORICAL_PLACES
            )

            if not (
                (has_africa and has_history)
                or has_known_place
            ):
                continue

            page_title = urllib.parse.quote(
                title.replace(" ", "_")
            )

            results.append({
                "titre": title,
                "url": (
                    "https://en.wikipedia.org/wiki/"
                    + page_title
                ),
                "description": normalize(snippet),
                "type": "Document encyclopédique",
                "zone": "Afrique - à confirmer",
                "verification": "A_VERIFIER",
                "origine": "Wikimedia"
            })

    except Exception as error:
        errors.append(
            "Wikimedia : " + str(error)[:250]
        )

    return results, errors


# ==========================================
# SUPPRESSION DES DOUBLONS
# ==========================================

def remove_duplicates(items):
    unique = []
    seen_urls = set()
    seen_titles = set()

    for item in items:
        url = item.get("url", "").strip()
        title = normalize(item.get("titre", ""))

        if not url or not title:
            continue

        if url in seen_urls or title in seen_titles:
            continue

        seen_urls.add(url)
        seen_titles.add(title)
        unique.append(item)

    return unique


# ==========================================
# SAUVEGARDE DES RESULTATS
# ==========================================

def main():
    now = datetime.now(timezone.utc).isoformat()

    print("====================================")
    print("OBSERVATEUR ACTIF AI")
    print("Recherche quotidienne en Afrique")
    print("====================================")

    print("\n1. Recherche dans la presse...")
    press_results, press_errors = search_gdelt()

    print(
        "Articles de presse retenus :",
        len(press_results)
    )

    print("\n2. Recherche documentaire...")
    wiki_results, wiki_errors = search_wikipedia()

    print(
        "Documents encyclopédiques retenus :",
        len(wiki_results)
    )

    all_results = remove_duplicates(
        press_results + wiki_results
    )

    errors = press_errors + wiki_errors

    output = {
        "date_recherche": now,
        "chaine": CHANNEL,
        "zone": COUNTRY,
        "priorite_editoriale": [
            "Mystères historiques",
            "Lieux mystérieux",
            "Civilisations oubliées"
        ],
        "moteurs_utilises": [
            "GDELT",
            "Wikimedia"
        ],
        "nombre_resultats": len(all_results),
        "nombre_articles_presse": len(press_results),
        "nombre_documents": len(wiki_results),
        "erreurs_recherche": errors,
        "resultats": all_results,
        "statut": (
            "CANDIDATS_A_VERIFIER"
            if all_results
            else "AUCUN_RESULTAT"
        ),
        "publication_autorisee": False,
        "avertissement": (
            "Ces résultats sont des pistes de recherche. "
            "Les faits, les dates, les lieux et les sources "
            "doivent être vérifiés indépendamment avant "
            "toute rédaction ou publication."
        )
    }

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    output_file = output_dir / "daily_research.json"

    with output_file.open(
        "w", encoding="utf-8"
    ) as file:
        json.dump(
            output,
            file,
            ensure_ascii=False,
            indent=2
        )

    print("\n====================================")
    print("RECHERCHE TERMINEE")
    print("Résultats :", len(all_results))
    print("Erreurs :", len(errors))
    print("Publication : DESACTIVEE")
    print("Fichier :", output_file)
    print("====================================")


if __name__ == "__main__":
    main()


import os
import re
import json
import time
import hashlib
import unicodedata
import requests
import feedparser

from datetime import datetime, timezone
from urllib.parse import urlencode

# ==========================================
# OBSERVATEUR ACTIF AI
# MOTEUR DE RECHERCHE AFRICAIN V2
# ==========================================

AGENT = "Observateur Actif AI"

REPERTOIRE = "data"
FICHIER_SORTIE = os.path.join(
    REPERTOIRE, "histoires_brutes.json"
)

API_GOOGLE_NEWS = "https://news.google.com/rss/search"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; "
        "ObservateurActifAI/2.0; "
        "+https://github.com/)"
    )
}

# ==========================================
# PAYS ET RÉGIONS AFRICAINS
# ==========================================

PAYS = [
    "Algeria", "Algérie",
    "Angola",
    "Benin", "Bénin",
    "Botswana",
    "Burkina Faso",
    "Burundi",
    "Cameroon", "Cameroun",
    "Cape Verde", "Cap-Vert",
    "Central African Republic",
    "République centrafricaine",
    "Chad", "Tchad",
    "Comoros", "Comores",
    "Congo",
    "Democratic Republic of the Congo",
    "République démocratique du Congo",
    "Ivory Coast", "Côte d'Ivoire",
    "Djibouti",
    "Egypt", "Égypte",
    "Equatorial Guinea", "Guinée équatoriale",
    "Eritrea", "Érythrée",
    "Eswatini",
    "Ethiopia", "Éthiopie",
    "Gabon",
    "Gambia", "Gambie",
    "Ghana",
    "Guinea", "Guinée",
    "Guinea-Bissau", "Guinée-Bissau",
    "Kenya",
    "Lesotho",
    "Liberia", "Libéria",
    "Libya", "Libye",
    "Madagascar",
    "Malawi",
    "Mali",
    "Mauritania", "Mauritanie",
    "Mauritius", "Maurice",
    "Morocco", "Maroc",
    "Mozambique",
    "Namibia", "Namibie",
    "Niger",
    "Nigeria", "Nigéria",
    "Rwanda",
    "Sao Tome and Principe",
    "Sénégal", "Senegal",
    "Seychelles",
    "Sierra Leone",
    "Somalia", "Somalie",
    "South Africa", "Afrique du Sud",
    "South Sudan", "Soudan du Sud",
    "Sudan", "Soudan",
    "Tanzania", "Tanzanie",
    "Togo",
    "Tunisia", "Tunisie",
    "Uganda", "Ouganda",
    "Zambia", "Zambie",
    "Zimbabwe"
]

REGIONS = [
    "Afrique de l'Ouest",
    "West Africa",
    "Afrique centrale",
    "Central Africa",
    "Afrique de l'Est",
    "East Africa",
    "Afrique australe",
    "Southern Africa",
    "Afrique du Nord",
    "North Africa",
    "Sahel",
    "Sahara",
    "Horn of Africa",
    "Corne de l'Afrique",
    "Wassoulou",
    "Nubia",
    "Nubie",
    "Sahelian kingdoms"
]

SITES_HISTORIQUES = [
    "Great Zimbabwe",
    "Grand Zimbabwe",
    "Timbuktu",
    "Tombouctou",
    "Djenné",
    "Djenne",
    "Dogon",
    "Bandiagara",
    "Gao Empire",
    "Empire du Ghana",
    "Empire du Mali",
    "Songhai Empire",
    "Great Mosque of Djenne",
    "Lalibela",
    "Axum",
    "Aksum",
    "Meroe",
    "Méroé",
    "Carthage",
    "Leptis Magna",
    "Kilwa Kisiwani",
    "Benin City",
    "Kingdom of Benin",
    "Royaume du Bénin",
    "Kingdom of Kush",
    "Royaume de Koush",
    "Mapungubwe",
    "Gedi ruins",
    "Olduvai Gorge",
    "Gorges d'Olduvai",
    "Tassili n'Ajjer",
    "Sankore",
    "Gonja",
    "Oualata",
    "Aoudaghost",
    "Kumbi Saleh",
    "Nok culture",
    "Culture Nok",
    "Mbanza Kongo",
    "Fasil Ghebbi",
    "Djenne-Djenno"
]

MOTS_THEMES = [
    "mystère historique",
    "mystère archéologique",
    "civilisation oubliée",
    "royaume ancien",
    "cité antique",
    "ville disparue",
    "site archéologique",
    "découverte archéologique",
    "lieu mystérieux",
    "histoire étrange",
    "mystère ancien",
    "tradition ancienne",
    "vestiges historiques",
    "ancient mystery",
    "lost civilization",
    "forgotten kingdom",
    "ancient ruins",
    "archaeological discovery",
    "mysterious archaeological site",
    "ancient city",
    "historical mystery",
    "forgotten history",
    "ancient African kingdom",
    "enigmatic ruins"
]

# ==========================================
# CONSTRUCTION DES REQUÊTES
# ==========================================

def construire_requetes():

    requetes = set()

    # Recherches générales africaines.
    for mot in MOTS_THEMES:
        requetes.add(f'"{mot}" Africa')
        requetes.add(f'"{mot}" Afrique')

    # Recherches ciblées par pays.
    pays_cibles = [
        "Mali", "Senegal", "Ghana", "Nigeria",
        "Ethiopia", "Egypt", "Sudan", "Kenya",
        "Tanzania", "Zimbabwe", "South Africa",
        "Morocco", "Algeria", "Niger",
        "Mauritania", "Cameroon", "Benin",
        "Congo", "Uganda", "Madagascar",
        "Mozambique", "Angola", "Chad",
        "Burkina Faso", "Guinea", "Libya"
    ]

    themes_courts = [
        "ancient history archaeology",
        "historical mystery",
        "lost civilization",
        "ancient kingdom",
        "mysterious archaeological site"
    ]

    for pays in pays_cibles:
        for theme in themes_courts:
            requetes.add(f"{theme} {pays}")

    # Recherches par sites et civilisations historiques.
    for site in SITES_HISTORIQUES:
        requetes.add(f'"{site}" history archaeology')

    return sorted(requetes)


# ==========================================
# NORMALISATION ET FILTRAGE
# ==========================================

def normaliser(texte):

    texte = str(texte or "").lower()

    texte = unicodedata.normalize(
        "NFKD", texte
    )

    texte = "".join(
        caractere for caractere in texte
        if not unicodedata.combining(caractere)
    )

    texte = re.sub(r"[^a-z0-9\s]", " ", texte)

    return re.sub(r"\s+", " ", texte).strip()


PAYS_NORMALISES = [
    normaliser(pays) for pays in PAYS
]

REGIONS_NORMALISEES = [
    normaliser(region) for region in REGIONS
]

SITES_NORMALISES = [
    normaliser(site) for site in SITES_HISTORIQUES
]


def contient_expression(texte, expression):

    texte = normaliser(texte)
    expression = normaliser(expression)

    if not expression:
        return False

    return f" {expression} " in f" {texte} "


def evaluer_pertinence(titre, description, requete):

    texte = normaliser(
        titre + " " + description
    )

    requete_norm = normaliser(requete)

    score = 0
    raisons = []
    pays_detectes = []

    for pays, pays_norm in zip(PAYS, PAYS_NORMALISES):

        if contient_expression(texte, pays_norm):
            score += 3
            pays_detectes.append(pays)

    for region, region_norm in zip(
        REGIONS, REGIONS_NORMALISEES
    ):

        if contient_expression(texte, region_norm):
            score += 3
            raisons.append("REGION_AFRICAINE")

    for site, site_norm in zip(
        SITES_HISTORIQUES, SITES_NORMALISES
    ):

        if contient_expression(texte, site_norm):
            score += 4
            raisons.append("SITE_HISTORIQUE")

    if "africa" in texte or "afrique" in texte:
        score += 3
        raisons.append("REFERENCE_AFRIQUE")

    if any(
        mot in requete_norm
        for mot in [
            "africa", "afrique",
            "mali", "senegal", "ghana",
            "nigeria", "ethiopia", "egypt"
        ]
    ):
        score += 1

    # Un résultat doit contenir un indice géographique
    # africain dans son titre ou sa description.
    geographie_presente = (
        bool(pays_detectes)
        or any(
            contient_expression(texte, region)
            for region in REGIONS_NORMALISEES
        )
        or any(
            contient_expression(texte, site)
            for site in SITES_NORMALISES
        )
        or "africa" in texte
        or "afrique" in texte
    )

    return {
        "score_pertinence": score,
        "geographie_africaine": geographie_presente,
        "pays_detectes": sorted(set(pays_detectes)),
        "raisons": sorted(set(raisons))
    }


# ==========================================
# IDENTIFIANT UNIQUE
# ==========================================

def identifiant_unique(titre, lien):

    titre_norm = normaliser(titre)

    contenu = titre_norm + "|" + lien.strip().lower()

    return hashlib.sha256(
        contenu.encode("utf-8")
    ).hexdigest()


def cle_titre(titre):

    return normaliser(titre)


# ==========================================
# GOOGLE NEWS RSS
# ==========================================

def construire_url(requete, langue):

    if langue == "fr":
        parametres = {
            "q": requete,
            "hl": "fr",
            "gl": "FR",
            "ceid": "FR:fr"
        }

    else:
        parametres = {
            "q": requete,
            "hl": "en-US",
            "gl": "US",
            "ceid": "US:en"
        }

    return API_GOOGLE_NEWS + "?" + urlencode(parametres)


def rechercher_flux(requete, langue):

    url = construire_url(requete, langue)

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=35
    )

    response.raise_for_status()

    flux = feedparser.parse(response.content)

    return flux


# ==========================================
# RECHERCHE PRINCIPALE
# ==========================================

def rechercher():

    os.makedirs(REPERTOIRE, exist_ok=True)

    histoires = {}
    titres_vus = set()

    erreurs = []
    total_resultats = 0
    resultats_rejetes = 0

    requetes = construire_requetes()

    print("=" * 60)
    print(AGENT)
    print("MOTEUR DE RECHERCHE AFRICAIN V2")
    print("=" * 60)

    print("Nombre de requêtes :", len(requetes))
    print("Langues : français et anglais")
    print("Période : aucune limite de date")
    print("Zone : toute l'Afrique")

    for langue in ["fr", "en"]:

        for numero, requete in enumerate(requetes, 1):

            print(
                f"\n[{langue.upper()}] "
                f"{numero}/{len(requetes)} : {requete}"
            )

            try:

                flux = rechercher_flux(
                    requete,
                    langue
                )

                if flux.bozo and not flux.entries:
                    erreurs.append({
                        "requete": requete,
                        "langue": langue,
                        "erreur": "FLUX_RSS_INVALIDE"
                    })
                    continue

                for entree in flux.entries:

                    titre = entree.get(
                        "title", ""
                    ).strip()

                    lien = entree.get(
                        "link", ""
                    ).strip()

                    description = entree.get(
                        "summary", ""
                    ).strip()

                    if not titre or not lien:
                        continue

                    total_resultats += 1

                    pertinence = evaluer_pertinence(
                        titre,
                        description,
                        requete
                    )

                    if not pertinence["geographie_africaine"]:
                        resultats_rejetes += 1
                        continue

                    identifiant = identifiant_unique(
                        titre, lien
                    )

                    cle = cle_titre(titre)

                    # Déduplication par titre normalisé.
                    if cle in titres_vus:
                        continue

                    titres_vus.add(cle)

                    histoires[identifiant] = {
                        "id": identifiant,
                        "titre": titre,
                        "description": description,
                        "source_url": lien,
                        "date_publication": entree.get(
                            "published", ""
                        ),
                        "langue_source": langue,
                        "requete": requete,
                        "score_pertinence": pertinence[
                            "score_pertinence"
                        ],
                        "pays_detectes": pertinence[
                            "pays_detectes"
                        ],
                        "raisons_pertinence": pertinence[
                            "raisons"
                        ],
                        "statut": "A_ANALYSER",
                        "date_recherche": datetime.now(
                            timezone.utc
                        ).isoformat()
                    }

                time.sleep(0.5)

            except Exception as erreur:

                print("Erreur de recherche :", str(erreur))

                erreurs.append({
                    "requete": requete,
                    "langue": langue,
                    "erreur": str(erreur)[:500]
                })

    # Les histoires les plus pertinentes apparaissent en premier.
    liste_histoires = sorted(
        histoires.values(),
        key=lambda histoire: (
            histoire["score_pertinence"],
            histoire["date_publication"]
        ),
        reverse=True
    )

    resultat = {
        "agent": AGENT,
        "version": "V2",
        "date_recherche": datetime.now(
            timezone.utc
        ).isoformat(),
        "zone": "Toute l'Afrique",
        "nombre_requetes": len(requetes) * 2,
        "nombre_resultats_bruts": total_resultats,
        "nombre_histoires": len(liste_histoires),
        "nombre_resultats_rejetes": resultats_rejetes,
        "nombre_erreurs": len(erreurs),
        "histoires": liste_histoires,
        "erreurs": erreurs
    }

    with open(
        FICHIER_SORTIE,
        "w",
        encoding="utf-8"
    ) as fichier:

        json.dump(
            resultat,
            fichier,
            ensure_ascii=False,
            indent=2
        )

    print("\n" + "=" * 60)
    print("RECHERCHE TERMINÉE")
    print("=" * 60)

    print("Résultats bruts :", total_resultats)
    print("Histoires africaines retenues :", len(liste_histoires))
    print("Résultats rejetés :", resultats_rejetes)
    print("Erreurs :", len(erreurs))
    print("Fichier :", FICHIER_SORTIE)

    print("=" * 60)

    return resultat


if __name__ == "__main__":
    rechercher()


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
# MOTEUR DE RECHERCHE AFRICAIN V3
# ==========================================

AGENT = "Observateur Actif AI"

REPERTOIRE = "data"
FICHIER_SORTIE = os.path.join(
    REPERTOIRE, "histoires_brutes.json"
)

API_GOOGLE_NEWS = "https://news.google.com/rss/search"

TIMEOUT_REQUETE = 15
PAUSE_REQUETE = 0.3
SAUVEGARDE_TOUS_LES = 4

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; "
        "ObservateurActifAI/3.0)"
    )
}

# ==========================================
# PAYS AFRICAINS
# ==========================================

PAYS = [
    "Algeria", "Algérie", "Angola",
    "Benin", "Bénin", "Botswana",
    "Burkina Faso", "Burundi",
    "Cameroon", "Cameroun",
    "Cape Verde", "Cap-Vert",
    "Central African Republic",
    "République centrafricaine",
    "Chad", "Tchad", "Comoros", "Comores",
    "Congo", "Democratic Republic of the Congo",
    "République démocratique du Congo",
    "Ivory Coast", "Côte d'Ivoire",
    "Djibouti", "Egypt", "Égypte",
    "Equatorial Guinea", "Guinée équatoriale",
    "Eritrea", "Érythrée", "Eswatini",
    "Ethiopia", "Éthiopie", "Gabon",
    "Gambia", "Gambie", "Ghana",
    "Guinea", "Guinée", "Guinea-Bissau",
    "Guinée-Bissau", "Kenya", "Lesotho",
    "Liberia", "Libéria", "Libya", "Libye",
    "Madagascar", "Malawi", "Mali",
    "Mauritania", "Mauritanie", "Mauritius",
    "Maurice", "Morocco", "Maroc",
    "Mozambique", "Namibia", "Namibie",
    "Niger", "Nigeria", "Nigéria", "Rwanda",
    "Sao Tome and Principe", "Sénégal",
    "Senegal", "Seychelles", "Sierra Leone",
    "Somalia", "Somalie", "South Africa",
    "Afrique du Sud", "South Sudan",
    "Soudan du Sud", "Sudan", "Soudan",
    "Tanzania", "Tanzanie", "Togo",
    "Tunisia", "Tunisie", "Uganda", "Ouganda",
    "Zambia", "Zambie", "Zimbabwe"
]

REGIONS = [
    "Afrique de l'Ouest", "West Africa",
    "Afrique centrale", "Central Africa",
    "Afrique de l'Est", "East Africa",
    "Afrique australe", "Southern Africa",
    "Afrique du Nord", "North Africa",
    "Sahel", "Sahara", "Horn of Africa",
    "Corne de l'Afrique", "Nubia", "Nubie",
    "Wassoulou"
]

SITES_HISTORIQUES = [
    "Great Zimbabwe", "Timbuktu", "Tombouctou",
    "Djenné", "Djenne", "Dogon", "Bandiagara",
    "Gao Empire", "Empire du Ghana",
    "Empire du Mali", "Songhai Empire",
    "Lalibela", "Axum", "Aksum",
    "Meroe", "Méroé", "Carthage",
    "Leptis Magna", "Kilwa Kisiwani",
    "Benin City", "Kingdom of Benin",
    "Royaume du Bénin", "Kingdom of Kush",
    "Royaume de Koush", "Mapungubwe",
    "Gedi ruins", "Olduvai Gorge",
    "Gorges d'Olduvai", "Tassili n'Ajjer",
    "Sankore", "Oualata", "Aoudaghost",
    "Kumbi Saleh", "Nok culture",
    "Culture Nok", "Mbanza Kongo",
    "Fasil Ghebbi", "Djenne-Djenno"
]

# ==========================================
# REQUÊTES CIBLÉES
# 16 EN FRANÇAIS + 16 EN ANGLAIS
# ==========================================

REQUETES = {
    "fr": [
        '"mystère historique" Afrique',
        '"civilisation oubliée" Afrique',
        '"royaume ancien" Afrique histoire',
        '"découverte archéologique" Afrique',
        '"lieu mystérieux" Afrique histoire',
        '"cité antique" Afrique archéologie',
        '"Afrique de l Ouest" royaume ancien',
        '"Afrique centrale" archéologie histoire',
        '"Afrique de l Est" civilisation ancienne',
        '"Afrique australe" site archéologique',
        '"Afrique du Nord" mystère historique',
        'Mali Ghana Songhaï archéologie histoire',
        'Nubie Koush Méroé Égypte ancienne',
        'Zimbabwe Mapungubwe civilisation ancienne',
        'Tombouctou Djenné Gao histoire ancienne',
        'Dogon Bandiagara Tassili archéologie'
    ],

    "en": [
        '"historical mystery" Africa',
        '"lost civilization" Africa',
        '"ancient African kingdom" history',
        '"archaeological discovery" Africa',
        '"mysterious place" Africa history',
        '"ancient African city" archaeology',
        '"West Africa" ancient kingdom history',
        '"Central Africa" archaeology history',
        '"East Africa" ancient civilization',
        '"Southern Africa" archaeological site',
        '"North Africa" historical mystery',
        'Mali Ghana Songhai archaeology history',
        'Nubia Kush Meroe ancient Egypt',
        'Zimbabwe Mapungubwe ancient civilization',
        'Timbuktu Djenne Gao ancient history',
        'Dogon Bandiagara Tassili archaeology'
    ]
}

# ==========================================
# NORMALISATION
# ==========================================

def normaliser(texte):

    texte = str(texte or "").lower()

    texte = unicodedata.normalize(
        "NFKD", texte
    )

    texte = "".join(
        c for c in texte
        if not unicodedata.combining(c)
    )

    texte = re.sub(
        r"[^a-z0-9\s]", " ", texte
    )

    return re.sub(
        r"\s+", " ", texte
    ).strip()


PAYS_NORMALISES = [
    normaliser(p) for p in PAYS
]

REGIONS_NORMALISEES = [
    normaliser(r) for r in REGIONS
]

SITES_NORMALISES = [
    normaliser(s) for s in SITES_HISTORIQUES
]


def contient_expression(texte, expression):

    texte = " " + normaliser(texte) + " "
    expression = " " + normaliser(expression) + " "

    return expression.strip() in texte


# ==========================================
# ANALYSE DE LA PERTINENCE AFRICAINE
# ==========================================

def evaluer_pertinence(titre, description, requete):

    texte = normaliser(
        titre + " " + description
    )

    score = 0
    raisons = []
    pays_detectes = []

    for pays, pays_norm in zip(
        PAYS, PAYS_NORMALISES
    ):

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

    geographie_presente = (
        bool(pays_detectes)
        or "africa" in texte
        or "afrique" in texte
        or any(
            contient_expression(texte, r)
            for r in REGIONS_NORMALISEES
        )
        or any(
            contient_expression(texte, s)
            for s in SITES_NORMALISES
        )
    )

    return {
        "score_pertinence": score,
        "geographie_africaine": geographie_presente,
        "pays_detectes": sorted(set(pays_detectes)),
        "raisons": sorted(set(raisons))
    }


# ==========================================
# IDENTIFIANTS
# ==========================================

def identifiant_unique(titre, lien):

    contenu = (
        normaliser(titre)
        + "|"
        + lien.strip().lower()
    )

    return hashlib.sha256(
        contenu.encode("utf-8")
    ).hexdigest()


# ==========================================
# GOOGLE NEWS
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

    return (
        API_GOOGLE_NEWS
        + "?"
        + urlencode(parametres)
    )


def rechercher_flux(requete, langue):

    url = construire_url(
        requete,
        langue
    )

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=TIMEOUT_REQUETE
    )

    response.raise_for_status()

    return feedparser.parse(
        response.content
    )


# ==========================================
# SAUVEGARDE PROGRESSIVE
# ==========================================

def sauvegarder(
    histoires,
    erreurs,
    total,
    rejetes,
    requetes_terminees
):

    os.makedirs(
        REPERTOIRE,
        exist_ok=True
    )

    liste = sorted(
        histoires.values(),
        key=lambda h: (
            h["score_pertinence"],
            h["date_publication"]
        ),
        reverse=True
    )

    resultat = {
        "agent": AGENT,
        "version": "V3",
        "date_recherche": datetime.now(
            timezone.utc
        ).isoformat(),
        "zone": "Toute l'Afrique",
        "langues": ["français", "anglais"],
        "limite_date": None,
        "nombre_requetes": requetes_terminees,
        "nombre_resultats_bruts": total,
        "nombre_histoires": len(liste),
        "nombre_resultats_rejetes": rejetes,
        "nombre_erreurs": len(erreurs),
        "histoires": liste,
        "erreurs": erreurs
    }

    temporaire = FICHIER_SORTIE + ".tmp"

    with open(
        temporaire,
        "w",
        encoding="utf-8"
    ) as fichier:

        json.dump(
            resultat,
            fichier,
            ensure_ascii=False,
            indent=2
        )

    os.replace(
        temporaire,
        FICHIER_SORTIE
    )


# ==========================================
# RECHERCHE PRINCIPALE
# ==========================================

def rechercher():

    os.makedirs(
        REPERTOIRE,
        exist_ok=True
    )

    histoires = {}
    titres_vus = set()
    erreurs = []

    total = 0
    rejetes = 0
    requetes_terminees = 0

    requetes = REQUETES["fr"] + REQUETES["en"]

    print("=" * 60)
    print(AGENT)
    print("MOTEUR DE RECHERCHE AFRICAIN V3")
    print("=" * 60)

    print("Nombre de requêtes :", len(requetes))
    print("Langues : français et anglais")
    print("Période : aucune limite de date")
    print("Zone : toute l'Afrique")
    print("Sauvegarde progressive activée")

    for langue in ["fr", "en"]:

        liste_requetes = REQUETES[langue]

        for numero, requete in enumerate(
            liste_requetes,
            1
        ):

            print(
                f"\n[{langue.upper()}] "
                f"{numero}/{len(liste_requetes)} : "
                f"{requete}",
                flush=True
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

                    total += 1

                    pertinence = evaluer_pertinence(
                        titre,
                        description,
                        requete
                    )

                    if not pertinence[
                        "geographie_africaine"
                    ]:

                        rejetes += 1
                        continue

                    cle = normaliser(titre)

                    if cle in titres_vus:
                        continue

                    titres_vus.add(cle)

                    identifiant = identifiant_unique(
                        titre,
                        lien
                    )

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

                requetes_terminees += 1

            except Exception as erreur:

                print(
                    "Erreur de recherche :",
                    str(erreur)[:300]
                )

                erreurs.append({
                    "requete": requete,
                    "langue": langue,
                    "erreur": str(erreur)[:500]
                })

                requetes_terminees += 1

            if (
                requetes_terminees
                % SAUVEGARDE_TOUS_LES == 0
            ):

                sauvegarder(
                    histoires,
                    erreurs,
                    total,
                    rejetes,
                    requetes_terminees
                )

                print(
                    "Sauvegarde intermédiaire :",
                    len(histoires),
                    "histoires",
                    flush=True
                )

            time.sleep(PAUSE_REQUETE)

    sauvegarder(
        histoires,
        erreurs,
        total,
        rejetes,
        requetes_terminees
    )

    print("\n" + "=" * 60)
    print("RECHERCHE TERMINÉE")
    print("=" * 60)

    print("Requêtes exécutées :", requetes_terminees)
    print("Résultats bruts :", total)
    print("Histoires africaines retenues :", len(histoires))
    print("Résultats rejetés :", rejetes)
    print("Erreurs :", len(erreurs))
    print("Fichier :", FICHIER_SORTIE)

    return histoires


if __name__ == "__main__":
    rechercher()


import os
import re
import json
import time
import hashlib
import requests

from bs4 import BeautifulSoup
from urllib.parse import urlparse
from datetime import datetime, timezone

# ==========================================
# OBSERVATEUR ACTIF AI
# COLLECTE ET ANALYSE DOCUMENTAIRE V2
# ==========================================

DOSSIER = "data"

ENTREE = os.path.join(
    DOSSIER, "histoires_brutes.json"
)

SORTIE = os.path.join(
    DOSSIER, "histoires_analysees.json"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; "
        "ObservateurActifAI/2.0)"
    )
}

TIMEOUT = 25
LONGUEUR_MAX = 20000

MOTS_DOCUMENTAIRES = [
    "historique",
    "archéologique",
    "archaeological",
    "research",
    "recherche",
    "université",
    "university",
    "musée",
    "museum",
    "étude",
    "study",
    "excavation",
    "scientifique",
    "scientific",
    "historian",
    "historien",
    "journal",
    "publication",
    "archaeology",
    "archéologie",
    "anthropologie",
    "anthropology",
    "inscription",
    "manuscrit",
    "manuscript",
    "chronique",
    "chronicle"
]

MOTS_AFRIQUE = [
    "africa",
    "afrique",
    "africain",
    "africaine",
    "africains",
    "africaines",
    "mali",
    "senegal",
    "sénégal",
    "ghana",
    "nigeria",
    "nigéria",
    "ethiopia",
    "éthiopie",
    "egypt",
    "égypte",
    "sudan",
    "soudan",
    "kenya",
    "tanzania",
    "tanzanie",
    "zimbabwe",
    "morocco",
    "maroc",
    "algeria",
    "algérie",
    "niger",
    "mauritania",
    "mauritanie",
    "cameroon",
    "cameroun",
    "congo",
    "uganda",
    "ouest-africain",
    "west african",
    "central african",
    "east african",
    "southern african",
    "north african",
    "nubia",
    "nubie",
    "timbuktu",
    "tombouctou",
    "djenné",
    "djenne",
    "dogon",
    "bandiagara",
    "aksum",
    "axum",
    "méroé",
    "meroe",
    "great zimbabwe",
    "mapungubwe",
    "kilwa",
    "carthage",
    "carthage",
    "lalibela",
    "nok culture",
    "culture nok",
    "mbanza kongo"
]


def nettoyer_texte(texte):

    texte = str(texte or "")

    texte = re.sub(
        r"\s+",
        " ",
        texte
    )

    return texte.strip()


def normaliser(texte):

    texte = nettoyer_texte(texte).lower()

    return texte


def extraire_meta(soup, proprietes):

    for propriete in proprietes:

        balise = (
            soup.find(
                "meta",
                attrs={"property": propriete}
            )
            or soup.find(
                "meta",
                attrs={"name": propriete}
            )
        )

        if balise:

            valeur = balise.get("content", "").strip()

            if valeur:
                return valeur

    return ""


def extraire_article(url):

    resultat = {
        "url_originale": url,
        "url_finale": url,
        "domaine": "",
        "titre_page": "",
        "description_page": "",
        "auteur": "",
        "date_page": "",
        "contenu": "",
        "nombre_caracteres": 0,
        "accessible": False,
        "erreur": ""
    }

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=TIMEOUT,
            allow_redirects=True
        )

        response.raise_for_status()

        type_contenu = response.headers.get(
            "Content-Type", ""
        ).lower()

        if "text/html" not in type_contenu:
            raise ValueError(
                "La ressource n'est pas une page HTML."
            )

        resultat["url_finale"] = response.url

        resultat["domaine"] = (
            urlparse(response.url).netloc.lower()
        )

        soup = BeautifulSoup(
            response.content,
            "lxml"
        )

        # Titre
        if soup.title:

            resultat["titre_page"] = nettoyer_texte(
                soup.title.get_text(" ", strip=True)
            )

        # Description
        resultat["description_page"] = extraire_meta(
            soup,
            [
                "description",
                "og:description",
                "twitter:description"
            ]
        )

        # Auteur
        resultat["auteur"] = extraire_meta(
            soup,
            [
                "author",
                "article:author",
                "parsely-author",
                "dc.creator"
            ]
        )

        # Date de publication
        resultat["date_page"] = extraire_meta(
            soup,
            [
                "article:published_time",
                "datePublished",
                "date",
                "dc.date",
                "pubdate"
            ]
        )

        # Suppression des éléments inutiles
        for element in soup([
            "script",
            "style",
            "nav",
            "footer",
            "header",
            "aside",
            "form",
            "noscript",
            "svg"
        ]):

            element.decompose()

        # Priorité aux zones principales
        zone = (
            soup.find("article")
            or soup.find("main")
            or soup.body
            or soup
        )

        paragraphes = zone.find_all("p")

        contenu = " ".join(
            p.get_text(" ", strip=True)
            for p in paragraphes
        )

        contenu = nettoyer_texte(contenu)

        resultat["contenu"] = contenu[:LONGUEUR_MAX]

        resultat["nombre_caracteres"] = len(
            resultat["contenu"]
        )

        resultat["accessible"] = bool(
            resultat["titre_page"]
            or resultat["contenu"]
        )

    except Exception as erreur:

        resultat["erreur"] = str(erreur)[:1000]

    return resultat


def detecter_indice_africain(histoire, article):

    texte = normaliser(
        histoire.get("titre", "")
        + " "
        + histoire.get("description", "")
        + " "
        + article.get("titre_page", "")
        + " "
        + article.get("description_page", "")
        + " "
        + article.get("contenu", "")[:6000]
    )

    indices = [
        mot for mot in MOTS_AFRIQUE
        if mot in texte
    ]

    return sorted(set(indices))


def evaluer_source(histoire, article):

    contenu = article.get("contenu", "")
    titre = article.get("titre_page", "")
    domaine = article.get("domaine", "")

    score = 0
    observations = []

    # Accessibilité
    if article.get("accessible"):
        score += 20
    else:
        observations.append(
            "Page originale inaccessible"
        )

    # Quantité de contenu
    longueur = len(contenu)

    if longueur >= 3000:
        score += 25
    elif longueur >= 1500:
        score += 20
    elif longueur >= 500:
        score += 10
    else:
        observations.append(
            "Contenu documentaire insuffisant"
        )

    # Titre
    if titre:
        score += 10
    else:
        observations.append(
            "Titre de page absent"
        )

    # Domaine
    if domaine:
        score += 10

    else:
        observations.append(
            "Domaine de la source absent"
        )

    # Auteur
    if article.get("auteur"):
        score += 10
    else:
        observations.append(
            "Auteur non identifié"
        )

    # Date
    if article.get("date_page"):
        score += 5
    else:
        observations.append(
            "Date de publication non trouvée"
        )

    # Indices documentaires
    texte = normaliser(
        titre + " " + contenu
    )

    indices_documentaires = [
        mot for mot in MOTS_DOCUMENTAIRES
        if mot in texte
    ]

    if len(indices_documentaires) >= 3:
        score += 20
    elif indices_documentaires:
        score += 10
    else:
        observations.append(
            "Peu d'indices documentaires détectés"
        )

    indices_africains = detecter_indice_africain(
        histoire,
        article
    )

    if not indices_africains:
        observations.append(
            "Référence africaine non détectée dans le contenu"
        )

    return {
        "score_collecte": min(score, 100),
        "indices_documentaires": indices_documentaires,
        "indices_africains": indices_africains,
        "observations": observations,
        "statut": "A_CORROBORER",
        "nature_score": "QUALITE_COLLECTE_ET_CONTENU",
        "verification_historique": False
    }


def analyser():

    os.makedirs(DOSSIER, exist_ok=True)

    if not os.path.exists(ENTREE):

        raise FileNotFoundError(
            "Fichier de recherche introuvable."
        )

    with open(
        ENTREE,
        "r",
        encoding="utf-8"
    ) as fichier:

        donnees = json.load(fichier)

    histoires = donnees.get("histoires", [])

    resultats = []
    erreurs = []

    print("=" * 55)
    print("OBSERVATEUR ACTIF AI")
    print("ANALYSE DOCUMENTAIRE V2")
    print("=" * 55)

    print("Histoires à analyser :", len(histoires))

    for numero, histoire in enumerate(
        histoires,
        start=1
    ):

        print(
            f"\n[{numero}/{len(histoires)}]",
            histoire.get("titre", "")
        )

        url = histoire.get("source_url", "")

        if not url:

            print("URL absente.")

            erreurs.append({
                "id": histoire.get("id"),
                "erreur": "URL_ABSENTE"
            })

            continue

        article = extraire_article(url)

        evaluation = evaluer_source(
            histoire,
            article
        )

        histoire_analysee = {
            **histoire,
            "source_analysee": article,
            "evaluation": evaluation,
            "date_analyse": datetime.now(
                timezone.utc
            ).isoformat(),
            "statut": "A_CORROBORER"
        }

        resultats.append(histoire_analysee)

        print(
            "Score de collecte :",
            evaluation["score_collecte"]
        )

        print(
            "Contenu récupéré :",
            article["nombre_caracteres"],
            "caractères"
        )

        if not article["accessible"]:
            print("Attention : page inaccessible.")

        time.sleep(0.5)

    sortie = {
        "agent": "Observateur Actif AI",
        "version": "V2",
        "date_analyse": datetime.now(
            timezone.utc
        ).isoformat(),
        "nombre_histoires_recues": len(histoires),
        "nombre_histoires_analysees": len(resultats),
        "nombre_erreurs": len(erreurs),
        "histoires": resultats,
        "erreurs": erreurs
    }

    with open(
        SORTIE,
        "w",
        encoding="utf-8"
    ) as fichier:

        json.dump(
            sortie,
            fichier,
            ensure_ascii=False,
            indent=2
        )

    print("\n" + "=" * 55)
    print("ANALYSE TERMINÉE")
    print("=" * 55)

    print("Histoires reçues :", len(histoires))
    print("Histoires analysées :", len(resultats))
    print("Erreurs :", len(erreurs))
    print("Fichier :", SORTIE)


if __name__ == "__main__":
    analyser()

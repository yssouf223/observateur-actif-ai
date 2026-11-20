
import os
import json
import re
import requests
import hashlib

from bs4 import BeautifulSoup
from urllib.parse import urlparse
from datetime import datetime, timezone

# ==========================================
# OBSERVATEUR ACTIF AI
# MODULE DE COLLECTE ET DE CONTROLE DES SOURCES
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
        "ObservateurActifAI/1.0)"
    )
}

TIMEOUT = 15


def nettoyer_texte(texte):
    texte = re.sub(r"\s+", " ", texte)
    return texte.strip()


def extraire_article(url):

    resultat = {
        "url_finale": url,
        "domaine": "",
        "titre_page": "",
        "description_page": "",
        "contenu": "",
        "date_page": "",
        "accessible": False
    }

    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=TIMEOUT
        )

        response.raise_for_status()

        resultat["url_finale"] = response.url

        domaine = urlparse(response.url).netloc

        resultat["domaine"] = domaine.lower()

        soup = BeautifulSoup(
            response.text,
            "lxml"
        )

        if soup.title:
            resultat["titre_page"] = nettoyer_texte(
                soup.title.get_text(" ", strip=True)
            )

        description = soup.find(
            "meta",
            attrs={"name": "description"}
        )

        if description:
            resultat["description_page"] = (
                description.get("content", "")
            )

        date_meta = (
            soup.find(
                "meta",
                attrs={"property": "article:published_time"}
            )
            or soup.find(
                "meta",
                attrs={"name": "date"}
            )
            or soup.find(
                "meta",
                attrs={"property": "og:updated_time"}
            )
        )

        if date_meta:
            resultat["date_page"] = (
                date_meta.get("content", "")
            )

        # Supprimer les éléments inutiles
        for element in soup([
            "script",
            "style",
            "nav",
            "footer",
            "header",
            "aside",
            "form"
        ]):
            element.decompose()

        # Priorité au contenu principal
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

        resultat["contenu"] = nettoyer_texte(
            contenu
        )[:15000]

        resultat["accessible"] = True

    except Exception as erreur:

        resultat["erreur"] = str(erreur)

    return resultat


def evaluer_source(histoire, article):

    contenu = article.get("contenu", "")

    titre = article.get("titre_page", "")

    domaine = article.get("domaine", "")

    score = 0
    observations = []

    if article.get("accessible"):
        score += 20
    else:
        observations.append(
            "Page originale inaccessible"
        )

    if len(contenu) >= 1500:
        score += 25
    elif len(contenu) >= 500:
        score += 15
    else:
        observations.append(
            "Contenu insuffisant"
        )

    if titre:
        score += 10
    else:
        observations.append(
            "Titre de page absent"
        )

    if domaine:
        score += 10

    if article.get("date_page"):
        score += 10
    else:
        observations.append(
            "Date de publication non trouvée"
        )

    mots_factuels = [
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
        "excavation",
        "scientifique",
        "scientific",
        "historian",
        "historien"
    ]

    texte_complet = (
        titre + " " + contenu
    ).lower()

    indices = [
        mot for mot in mots_factuels
        if mot in texte_complet
    ]

    if indices:
        score += 15

    # Le score évalue la qualité de la collecte.
    # Il ne prouve jamais la véracité de l'histoire.

    return {
        "score_collecte": min(score, 100),
        "indices_documentaires": indices,
        "observations": observations,
        "statut": "A_CORROBORER"
    }


def analyser():

    os.makedirs(DOSSIER, exist_ok=True)

    if not os.path.exists(ENTREE):
        print("Fichier de recherche introuvable.")
        return

    with open(
        ENTREE,
        "r",
        encoding="utf-8"
    ) as fichier:
        donnees = json.load(fichier)

    resultats = []

    histoires = donnees.get("histoires", [])

    print("Analyse de", len(histoires), "histoires")

    for numero, histoire in enumerate(
        histoires, start=1
    ):

        print(
            f"\n[{numero}/{len(histoires)}]",
            histoire.get("titre", "")
        )

        article = extraire_article(
            histoire["source_url"]
        )

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

    sortie = {
        "agent": "Observateur Actif AI",
        "date_analyse": datetime.now(
            timezone.utc
        ).isoformat(),
        "nombre_analyse": len(resultats),
        "histoires": resultats
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

    print("\nANALYSE TERMINEE")
    print("Histoires analysées :", len(resultats))
    print("Fichier :", SORTIE)


if __name__ == "__main__":
    analyser()

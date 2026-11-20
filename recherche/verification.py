
import os
import re
import json
import time
import requests

from bs4 import BeautifulSoup
from urllib.parse import urlparse
from datetime import datetime, timezone

# ==========================================
# OBSERVATEUR ACTIF AI
# COLLECTE ET ANALYSE DOCUMENTAIRE V4
# ==========================================

RACINE = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)

DOSSIER = os.path.join(RACINE, "data")

ENTREE = os.path.join(
    DOSSIER, "histoires_brutes.json"
)

SORTIE = os.path.join(
    DOSSIER, "histoires_analysees.json"
)

MAX_HISTOIRES = 30

TIMEOUT_CONNEXION = 8
TIMEOUT_LECTURE = 15

PAUSE_REQUETE = 0.3
SAUVEGARDE_TOUS_LES = 5

LONGUEUR_MAX = 12000

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,*/*;q=0.8"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    "Connection": "keep-alive"
}

MOTS_DOCUMENTAIRES = [
    "historique", "archéologique", "archaeological",
    "research", "recherche", "université", "university",
    "musée", "museum", "étude", "study", "excavation",
    "scientifique", "scientific", "historian", "historien",
    "journal", "publication", "archaeology", "archéologie",
    "anthropologie", "anthropology", "inscription",
    "manuscrit", "manuscript", "chronique", "chronicle",
    "empire", "civilisation", "civilization",
    "archéologue", "archaeologist", "histoire", "history",
    "dynastie", "dynasty", "fouille", "excavation"
]

MOTS_AFRIQUE = [
    "africa", "afrique", "africain", "africaine",
    "africains", "africaines", "mali", "senegal",
    "sénégal", "ghana", "nigeria", "nigéria",
    "ethiopia", "éthiopie", "egypt", "égypte",
    "sudan", "soudan", "kenya", "tanzania", "tanzanie",
    "zimbabwe", "morocco", "maroc", "algeria", "algérie",
    "niger", "mauritania", "mauritanie", "cameroon",
    "cameroun", "congo", "uganda", "west african",
    "central african", "east african", "southern african",
    "north african", "nubia", "nubie", "timbuktu",
    "tombouctou", "djenné", "djenne", "dogon",
    "bandiagara", "aksum", "axum", "méroé", "meroe",
    "great zimbabwe", "mapungubwe", "kilwa",
    "carthage", "lalibela", "nok culture",
    "culture nok", "mbanza kongo", "benin city",
    "royaume du bénin", "kingdom of benin",
    "afrique de l'ouest", "west africa",
    "afrique centrale", "central africa",
    "afrique de l'est", "east africa",
    "afrique australe", "southern africa",
    "afrique du nord", "north africa"
]


def maintenant():
    return datetime.now(timezone.utc).isoformat()


def nettoyer_texte(texte):
    texte = str(texte or "")
    texte = re.sub(r"\s+", " ", texte)
    return texte.strip()


def normaliser(texte):
    return nettoyer_texte(texte).lower()


def sauvegarder(resultats, erreurs, histoires_recues, terminees):
    os.makedirs(DOSSIER, exist_ok=True)

    sortie = {
        "agent": "Observateur Actif AI",
        "version": "V4",
        "date_analyse": maintenant(),
        "nombre_histoires_recues": histoires_recues,
        "nombre_histoires_selectionnees": min(
            histoires_recues, MAX_HISTOIRES
        ),
        "nombre_histoires_analysees": len(resultats),
        "nombre_histoires_non_analysees": max(
            0,
            min(histoires_recues, MAX_HISTOIRES)
            - terminees
        ),
        "nombre_erreurs": len(erreurs),
        "histoires": resultats,
        "erreurs": erreurs,
        "progression": {
            "terminees": terminees,
            "maximum": min(histoires_recues, MAX_HISTOIRES)
        }
    }

    temporaire = SORTIE + ".tmp"

    with open(temporaire, "w", encoding="utf-8") as fichier:
        json.dump(
            sortie,
            fichier,
            ensure_ascii=False,
            indent=2
        )

    os.replace(temporaire, SORTIE)


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


def extraire_json_ld(soup, resultat):
    contenus = []

    for script in soup.find_all(
        "script",
        attrs={"type": "application/ld+json"}
    ):

        try:
            donnees = json.loads(
                script.string or script.get_text()
            )

            elements = (
                donnees if isinstance(donnees, list)
                else [donnees]
            )

            a_traiter = list(elements)

            while a_traiter:

                element = a_traiter.pop(0)

                if not isinstance(element, dict):
                    continue

                graphe = element.get("@graph")

                if isinstance(graphe, list):
                    a_traiter.extend(graphe)

                corps = element.get("articleBody")

                if isinstance(corps, str) and len(corps) > 200:
                    contenus.append(corps)

                if not resultat["auteur"]:
                    auteur = element.get("author", "")

                    if isinstance(auteur, dict):
                        resultat["auteur"] = auteur.get(
                            "name", ""
                        )

                    elif isinstance(auteur, list):
                        noms = [
                            x.get("name", "")
                            for x in auteur
                            if isinstance(x, dict)
                        ]

                        resultat["auteur"] = ", ".join(
                            x for x in noms if x
                        )

                    elif isinstance(auteur, str):
                        resultat["auteur"] = auteur

                if not resultat["date_page"]:
                    resultat["date_page"] = (
                        element.get("datePublished", "")
                    )

                if (
                    not resultat["titre_page"]
                    and isinstance(element.get("headline"), str)
                ):
                    resultat["titre_page"] = (
                        element["headline"]
                    )

        except (ValueError, TypeError):
            continue

    return contenus


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

        parsed = urlparse(url)

        if (
            parsed.scheme not in ("http", "https")
            or not parsed.netloc
        ):
            raise ValueError("URL invalide.")

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=(
                TIMEOUT_CONNEXION,
                TIMEOUT_LECTURE
            ),
            allow_redirects=True
        )

        response.raise_for_status()

        type_contenu = response.headers.get(
            "Content-Type", ""
        ).lower()

        if (
            "text/html" not in type_contenu
            and "application/xhtml+xml" not in type_contenu
            and type_contenu
        ):
            raise ValueError(
                "Format non HTML : " + type_contenu
            )

        resultat["url_finale"] = response.url

        resultat["domaine"] = urlparse(
            response.url
        ).netloc.lower()

        soup = BeautifulSoup(
            response.content,
            "lxml"
        )

        # TITRE DE LA PAGE

        if soup.title:
            resultat["titre_page"] = nettoyer_texte(
                soup.title.get_text(" ", strip=True)
            )

        h1 = soup.find("h1")

        if h1 and not resultat["titre_page"]:
            resultat["titre_page"] = nettoyer_texte(
                h1.get_text(" ", strip=True)
            )

        # DESCRIPTION

        resultat["description_page"] = extraire_meta(
            soup,
            [
                "description",
                "og:description",
                "twitter:description"
            ]
        )

        # AUTEUR

        resultat["auteur"] = extraire_meta(
            soup,
            [
                "author",
                "article:author",
                "parsely-author",
                "dc.creator"
            ]
        )

        # DATE

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

        # DONNEES STRUCTUREES

        contenus_json = extraire_json_ld(
            soup,
            resultat
        )

        # SUPPRESSION DES ELEMENTS INUTILES

        for element in soup([
            "script",
            "style",
            "nav",
            "footer",
            "header",
            "aside",
            "form",
            "noscript",
            "svg",
            "iframe",
            "button"
        ]):
            element.decompose()

        # ZONES EDITORIALES PRIORITAIRES

        selecteurs = [
            "article",
            "main",
            '[itemprop="articleBody"]',
            ".article-body",
            ".article-content",
            ".post-content",
            ".entry-content",
            ".story-body",
            ".content-body",
            ".article__body",
            ".post-body"
        ]

        zones = []

        for selecteur in selecteurs:

            for zone in soup.select(selecteur):

                zones.append(zone)

        if soup.body:
            zones.append(soup.body)

        candidats = []

        # EXTRACTION DES PARAGRAPHES

        for zone in zones:

            paragraphes = zone.find_all([
                "p",
                "h2",
                "h3",
                "blockquote"
            ])

            textes = []

            for paragraphe in paragraphes:

                texte = nettoyer_texte(
                    paragraphe.get_text(
                        " ",
                        strip=True
                    )
                )

                if len(texte) >= 40:
                    textes.append(texte)

            contenu_zone = " ".join(textes)

            if len(contenu_zone) >= 200:
                candidats.append(contenu_zone)

        # EXTRACTION ALTERNATIVE

        if not candidats:

            blocs = soup.find_all([
                "div",
                "section",
                "article"
            ])

            for bloc in blocs:

                texte = nettoyer_texte(
                    bloc.get_text(" ", strip=True)
                )

                if len(texte) >= 500:
                    candidats.append(texte)

        # CHOIX DU CONTENU LE PLUS COMPLET

        contenus = candidats + contenus_json

        if contenus:

            contenu = max(
                contenus,
                key=len
            )

        else:
            contenu = ""

        resultat["contenu"] = nettoyer_texte(
            contenu
        )[:LONGUEUR_MAX]

        resultat["nombre_caracteres"] = len(
            resultat["contenu"]
        )

        resultat["accessible"] = True

        if resultat["nombre_caracteres"] < 500:

            resultat["erreur"] = (
                "Page accessible, mais contenu "
                "éditorial insuffisant."
            )

    except requests.exceptions.Timeout:

        resultat["erreur"] = (
            "Délai de connexion dépassé."
        )

    except requests.exceptions.HTTPError as erreur:

        resultat["erreur"] = (
            "Erreur HTTP : " + str(erreur)[:300]
        )

    except requests.exceptions.RequestException as erreur:

        resultat["erreur"] = (
            "Erreur réseau : " + str(erreur)[:300]
        )

    except Exception as erreur:

        resultat["erreur"] = str(erreur)[:1000]

    return resultat


def detecter_indice_africain(histoire, article):

    texte = normaliser(
        histoire.get("titre", "") + " "
        + histoire.get("description", "") + " "
        + article.get("titre_page", "") + " "
        + article.get("description_page", "") + " "
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

    if article.get("accessible"):
        score += 20
    else:
        observations.append(
            "Page originale inaccessible"
        )

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

    if titre:
        score += 10
    else:
        observations.append(
            "Titre de page absent"
        )

    if domaine:
        score += 10
    else:
        observations.append(
            "Domaine de la source absent"
        )

    if article.get("auteur"):
        score += 10
    else:
        observations.append(
            "Auteur non identifié"
        )

    if article.get("date_page"):
        score += 5
    else:
        observations.append(
            "Date de publication non trouvée"
        )

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

    histoires = donnees.get(
        "histoires",
        []
    )

    if not isinstance(histoires, list):

        raise ValueError(
            "Format incorrect : histoires doit être une liste."
        )

    selection = histoires[:MAX_HISTOIRES]

    resultats = []
    erreurs = []
    urls_vues = set()

    print("=" * 55)
    print("OBSERVATEUR ACTIF AI")
    print("ANALYSE DOCUMENTAIRE V4")
    print("=" * 55)

    print("Histoires reçues :", len(histoires))
    print("Histoires sélectionnées :", len(selection))

    for numero, histoire in enumerate(
        selection,
        start=1
    ):

        titre = histoire.get(
            "titre",
            ""
        )

        print(
            f"\n[{numero}/{len(selection)}] {titre}"
        )

        url = nettoyer_texte(
            histoire.get("source_url", "")
        )

        if not url:

            erreurs.append({
                "id": histoire.get("id"),
                "erreur": "URL_ABSENTE"
            })

            print("URL absente.")

            continue

        if url in urls_vues:

            erreurs.append({
                "id": histoire.get("id"),
                "erreur": "URL_DUPLIQUEE"
            })

            print("URL déjà analysée.")

            continue

        urls_vues.add(url)

        article = extraire_article(url)

        evaluation = evaluer_source(
            histoire,
            article
        )

        histoire_analysee = {
            **histoire,
            "source_analysee": article,
            "evaluation": evaluation,
            "date_analyse": maintenant(),
            "statut": "A_CORROBORER"
        }

        resultats.append(
            histoire_analysee
        )

        print(
            "Score de collecte :",
            evaluation["score_collecte"]
        )

        print(
            "Contenu récupéré :",
            article["nombre_caracteres"],
            "caractères"
        )

        if article["erreur"]:
            print(
                "Information :",
                article["erreur"]
            )

        if not article["accessible"]:
            print(
                "Attention : page inaccessible."
            )

        if numero % SAUVEGARDE_TOUS_LES == 0:

            sauvegarder(
                resultats,
                erreurs,
                len(histoires),
                numero
            )

            print(
                "Sauvegarde progressive effectuée."
            )

        time.sleep(PAUSE_REQUETE)

    sauvegarder(
        resultats,
        erreurs,
        len(histoires),
        len(selection)
    )

    print("\n" + "=" * 55)
    print("ANALYSE TERMINÉE")
    print("=" * 55)

    print(
        "Histoires reçues :",
        len(histoires)
    )

    print(
        "Histoires analysées :",
        len(resultats)
    )

    print(
        "Erreurs :",
        len(erreurs)
    )

    print(
        "Fichier :",
        SORTIE
    )


if __name__ == "__main__":
    analyser()

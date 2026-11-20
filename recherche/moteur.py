
import os
import json
import time
import hashlib
import feedparser
from datetime import datetime, timezone
from urllib.parse import quote_plus

# ==========================================
# OBSERVATEUR ACTIF AI
# MOTEUR DE RECHERCHE AFRICAIN
# ==========================================

AGENT = "Observateur Actif AI"

REPERTOIRE = "data"
FICHIER_SORTIE = os.path.join(
    REPERTOIRE, "histoires_brutes.json"
)

# Recherches en français et en anglais.
# Aucun filtre de date : les histoires anciennes
# peuvent également être découvertes.

REQUETES = [
    '"mystère historique" Afrique',
    '"civilisation oubliée" Afrique',
    '"lieu mystérieux" Afrique',
    '"histoire étrange" Afrique',
    '"découverte archéologique" Afrique',
    '"phénomène inexpliqué" Afrique',
    '"royaume ancien" Afrique histoire',
    '"mystère africain" histoire',
    '"ancient African mysteries"',
    '"lost African civilizations"',
    '"mysterious places" Africa history',
    '"strange discoveries" Africa archaeology',
    '"unexplained phenomena" Africa',
    '"ancient kingdoms" Africa archaeology',
    '"forgotten African history"',
    '"mysterious archaeological sites" Africa'
]


def construire_url(requete, langue):
    q = quote_plus(requete)

    if langue == "fr":
        return (
            "https://news.google.com/rss/search?q="
            + q + "&hl=fr&gl=FR&ceid=FR:fr"
        )

    return (
        "https://news.google.com/rss/search?q="
        + q + "&hl=en-US&gl=US&ceid=US:en"
    )


def identifiant_unique(titre, lien):
    contenu = (titre + lien).lower().strip()
    return hashlib.sha256(
        contenu.encode("utf-8")
    ).hexdigest()


def rechercher():
    os.makedirs(REPERTOIRE, exist_ok=True)

    histoires = {}
    erreurs = []

    print("=" * 55)
    print(AGENT)
    print("RECHERCHE AUTOMATIQUE DES HISTOIRES AFRICAINES")
    print("=" * 55)

    for langue in ["fr", "en"]:

        for requete in REQUETES:

            print("\nRecherche :", requete)

            url = construire_url(requete, langue)

            try:
                flux = feedparser.parse(url)

                if flux.bozo and not flux.entries:
                    erreurs.append(requete)
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

                    identifiant = identifiant_unique(
                        titre, lien
                    )

                    if identifiant in histoires:
                        continue

                    date_publication = entree.get(
                        "published", ""
                    )

                    histoires[identifiant] = {
                        "id": identifiant,
                        "titre": titre,
                        "description": description,
                        "source_url": lien,
                        "date_publication": date_publication,
                        "langue_source": langue,
                        "requete": requete,
                        "statut": "A_ANALYSER",
                        "date_recherche": datetime.now(
                            timezone.utc
                        ).isoformat()
                    }

                time.sleep(1)

            except Exception as erreur:
                print("Erreur :", erreur)
                erreurs.append(requete)

    resultat = {
        "agent": AGENT,
        "date_recherche": datetime.now(
            timezone.utc
        ).isoformat(),
        "nombre_histoires": len(histoires),
        "nombre_erreurs": len(erreurs),
        "histoires": list(histoires.values())
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

    print("\n" + "=" * 55)
    print("RECHERCHE TERMINÉE")
    print("Histoires trouvées :", len(histoires))
    print("Requêtes en erreur :", len(erreurs))
    print("Résultat :", FICHIER_SORTIE)
    print("=" * 55)

    return resultat


if __name__ == "__main__":
    rechercher()

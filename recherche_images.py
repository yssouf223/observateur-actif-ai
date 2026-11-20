
import json
import re
import time
import html
import hashlib
import requests

from pathlib import Path

# ==========================================
# OBSERVATEUR ACTIF AI
# RECHERCHE ET TELECHARGEMENT IMAGES V2
# ==========================================

DOSSIER = Path("images/telechargements")
DATA = Path("data")

FICHIER_SCRIPTS = DATA / "scripts_generes.json"
FICHIER_RAPPORT = DATA / "images_rapport.json"

API = "https://commons.wikimedia.org/w/api.php"

MAX_IMAGES = 5
TIMEOUT_API = (5, 15)
TIMEOUT_IMAGE = (5, 20)
TAILLE_MINIMALE = 1000
TAILLE_MAXIMALE = 12 * 1024 * 1024

HEADERS = {
    "User-Agent": (
        "ObservateurActifAI/2.0 "
        "(African documentary project)"
    )
}

LICENCES_AUTORISEES = (
    "CC0",
    "CC BY",
    "PUBLIC DOMAIN",
    "PUBLIC DOMAIN MARK"
)


def nettoyer(texte):
    texte = re.sub(r"<[^>]+>", "", str(texte or ""))
    return html.unescape(texte).strip()


def licence_valide(licence):

    licence = nettoyer(licence).upper()
    licence = re.sub(r"\s+", " ", licence).strip()

    if not licence:
        return False

    # Refus explicite des restrictions
    if "NONCOMMERCIAL" in licence:
        return False

    if "NO DERIVATIVES" in licence:
        return False

    if "CC BY-NC" in licence or "CC BY-ND" in licence:
        return False

    if licence.startswith("CC BY-SA-NC"):
        return False

    if licence.startswith("CC BY-NC-SA"):
        return False

    if licence.startswith("CC BY-NC-ND"):
        return False

    # CC0
    if licence.startswith("CC0"):
        return True

    # Creative Commons Attribution
    if licence.startswith("CC BY"):
        return True

    # Domaine public
    if "PUBLIC DOMAIN" in licence:
        return True

    return False


def sauvegarder_rapport(rapport):

    temporaire = str(FICHIER_RAPPORT) + ".tmp"

    with open(temporaire, "w", encoding="utf-8") as fichier:
        json.dump(
            {"agent": "Observateur Actif AI",
             "version": "V2",
             "histoires": rapport},
            fichier,
            ensure_ascii=False,
            indent=2
        )

    Path(temporaire).replace(FICHIER_RAPPORT)


def rechercher_images(requete, limite=15):

    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": requete,
        "gsrnamespace": 6,
        "gsrlimit": limite,
        "prop": "imageinfo",
        "iiprop": "url|extmetadata",
        "iiurlwidth": 1600,
        "format": "json"
    }

    response = requests.get(
        API,
        params=params,
        headers=HEADERS,
        timeout=TIMEOUT_API
    )

    response.raise_for_status()

    pages = response.json().get(
        "query", {}
    ).get("pages", {})

    resultats = []

    for page in pages.values():

        infos = page.get("imageinfo", [])

        if not infos:
            continue

        info = infos[0]
        metadata = info.get("extmetadata", {})

        licence = nettoyer(
            metadata.get(
                "LicenseShortName", {}
            ).get("value", "")
        )

        if not licence_valide(licence):
            continue

        mime = info.get("mime", "")

        if mime not in (
            "image/jpeg",
            "image/png",
            "image/webp"
        ):
            continue

        url = info.get("thumburl") or info.get("url")

        if not url:
            continue

        titre = page.get("title", "")

        description = nettoyer(
            metadata.get(
                "ImageDescription", {}
            ).get("value", "")
        )

        auteur = nettoyer(
            metadata.get(
                "Artist", {}
            ).get("value", "")
        )

        credit = nettoyer(
            metadata.get(
                "Credit", {}
            ).get("value", "")
        )

        resultats.append({
            "titre": titre,
            "description": description[:1500],
            "url": url,
            "source": info.get("descriptionurl", ""),
            "licence": licence,
            "auteur": auteur,
            "credit": credit,
            "mime": mime
        })

    return resultats


def telecharger(image, destination):

    extensions = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp"
    }

    extension = extensions.get(image["mime"])

    if not extension:
        return None

    destination = destination.with_suffix(extension)

    response = requests.get(
        image["url"],
        headers=HEADERS,
        timeout=TIMEOUT_IMAGE,
        stream=True
    )

    response.raise_for_status()

    taille = 0

    try:
        with open(destination, "wb") as fichier:

            for morceau in response.iter_content(8192):

                if not morceau:
                    continue

                taille += len(morceau)

                if taille > TAILLE_MAXIMALE:
                    raise ValueError(
                        "Image dépassant la taille maximale."
                    )

                fichier.write(morceau)

        if taille < TAILLE_MINIMALE:
            raise ValueError("Image trop petite ou vide.")

        return str(destination)

    except Exception:
        destination.unlink(missing_ok=True)
        raise

    finally:
        response.close()


def executer():

    DOSSIER.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)

    if not FICHIER_SCRIPTS.exists():
        raise FileNotFoundError(
            "Scripts Gemini introuvables."
        )

    with open(
        FICHIER_SCRIPTS,
        encoding="utf-8"
    ) as fichier:
        donnees = json.load(fichier)

    scripts = donnees.get("scripts", [])

    if not scripts:
        raise RuntimeError(
            "Aucun script disponible pour rechercher des images."
        )

    rapport = []
    urls_telechargees = set()

    print("=" * 55)
    print("OBSERVATEUR ACTIF AI")
    print("RECHERCHE D'IMAGES V2")
    print("=" * 55)

    for numero_script, script in enumerate(scripts, 1):

        identifiant = re.sub(
            r"[^a-zA-Z0-9_-]",
            "",
            str(script.get("id_histoire", "histoire"))
        ) or "histoire"

        titre = script.get("titre", "")
        narration = script.get("narration", "")

        requete = titre.strip() or narration[:120].strip()

        if not requete:
            continue

        print(
            f"\nHistoire {numero_script}/{len(scripts)} :",
            titre
        )

        images = []

        try:

            resultats = rechercher_images(requete)

            for image in resultats:

                if len(images) >= MAX_IMAGES:
                    break

                empreinte = hashlib.sha256(
                    image["url"].encode("utf-8")
                ).hexdigest()

                if empreinte in urls_telechargees:
                    continue

                try:

                    chemin = telecharger(
                        image,
                        DOSSIER / f"{identifiant}_{len(images)+1}"
                    )

                    if chemin:

                        image["fichier"] = chemin
                        image["identifiant_licence"] = (
                            image["licence"]
                        )

                        images.append(image)
                        urls_telechargees.add(empreinte)

                        print(
                            "Image téléchargée :",
                            image["titre"]
                        )

                except Exception as erreur:

                    print(
                        "Erreur téléchargement :",
                        str(erreur)[:300]
                    )

                time.sleep(0.2)

        except Exception as erreur:

            print(
                "Erreur recherche :",
                str(erreur)[:500]
            )

        rapport.append({
            "id_histoire": identifiant,
            "titre": titre,
            "nombre_images": len(images),
            "images": images,
            "statut": (
                "IMAGES_TROUVEES"
                if images
                else "AUCUNE_IMAGE"
            )
        })

        sauvegarder_rapport(rapport)

        print(
            "Images obtenues :",
            len(images)
        )

    sauvegarder_rapport(rapport)

    print("\n" + "=" * 55)
    print("RECHERCHE D'IMAGES TERMINÉE")
    print("=" * 55)

    print("Histoires traitées :", len(rapport))
    print("Rapport :", FICHIER_RAPPORT)


if __name__ == "__main__":
    executer()

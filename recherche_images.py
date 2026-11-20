
import json
import re
import time
import html
import requests
from pathlib import Path

DOSSIER = Path("images/telechargements")
DATA = Path("data")
FICHIER_SCRIPTS = DATA / "scripts_generes.json"
FICHIER_RAPPORT = DATA / "images_rapport.json"

API = "https://commons.wikimedia.org/w/api.php"

HEADERS = {
    "User-Agent": "ObservateurActifAI/1.0 (African documentary project)"
}

def nettoyer(texte):
    texte = re.sub(r"<[^>]+>", "", str(texte or ""))
    return html.unescape(texte).strip()

def licence_valide(licence):
    licence = nettoyer(licence).upper()

    if "NC" in licence or "ND" in licence:
        return False

    return (
        licence.startswith("CC0")
        or licence.startswith("CC BY")
        or licence.startswith("PUBLIC DOMAIN")
        or licence.startswith("PD")
    )

def rechercher_images(requete, limite=10):
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
        timeout=40
    )
    response.raise_for_status()

    pages = response.json().get("query", {}).get("pages", {})
    resultats = []

    for page in pages.values():
        infos = page.get("imageinfo", [])
        if not infos:
            continue

        info = infos[0]
        metadata = info.get("extmetadata", {})

        licence = metadata.get(
            "LicenseShortName", {}
        ).get("value", "")

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

        resultats.append({
            "titre": page.get("title", ""),
            "url": url,
            "source": info.get("descriptionurl", ""),
            "licence": nettoyer(licence),
            "auteur": nettoyer(
                metadata.get("Artist", {}).get("value", "")
            ),
            "credit": nettoyer(
                metadata.get("Credit", {}).get("value", "")
            ),
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

    response = requests.get(
        image["url"],
        headers=HEADERS,
        timeout=45,
        stream=True
    )
    response.raise_for_status()

    destination = destination.with_suffix(extension)

    with open(destination, "wb") as fichier:
        for morceau in response.iter_content(8192):
            if morceau:
                fichier.write(morceau)

    if destination.stat().st_size < 1000:
        destination.unlink(missing_ok=True)
        return None

    return str(destination)

def executer():
    DOSSIER.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)

    if not FICHIER_SCRIPTS.exists():
        print("Scripts Gemini introuvables.")
        return

    with open(FICHIER_SCRIPTS, encoding="utf-8") as fichier:
        scripts = json.load(fichier).get("scripts", [])

    rapport = []

    for script in scripts:
        identifiant = re.sub(
            r"[^a-zA-Z0-9_-]",
            "",
            str(script.get("id_histoire", "histoire"))
        ) or "histoire"

        titre = script.get("titre", "")
        narration = script.get("narration", "")

        requete = titre or narration[:120]

        if not requete.strip():
            continue

        print("Recherche :", titre)

        images = []
        try:
            resultats = rechercher_images(requete)

            for numero, image in enumerate(resultats[:5], 1):
                try:
                    chemin = telecharger(
                        image,
                        DOSSIER / f"{identifiant}_{numero}"
                    )

                    if chemin:
                        image["fichier"] = chemin
                        images.append(image)

                except Exception as erreur:
                    print("Erreur téléchargement :", erreur)

                time.sleep(0.5)

        except Exception as erreur:
            print("Erreur recherche :", erreur)

        rapport.append({
            "id_histoire": identifiant,
            "titre": titre,
            "nombre_images": len(images),
            "images": images,
            "statut": "IMAGES_TROUVEES" if images else "AUCUNE_IMAGE"
        })

    with open(FICHIER_RAPPORT, "w", encoding="utf-8") as fichier:
        json.dump(
            {"histoires": rapport},
            fichier,
            ensure_ascii=False,
            indent=2
        )

    print("Recherche d'images terminée.")
    print("Rapport :", FICHIER_RAPPORT)

if __name__ == "__main__":
    executer()

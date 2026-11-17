
import json
import os
import random
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).parent
DATA = PROJECT / "data"
OUTPUT = PROJECT / "output"

TOPICS_FILE = DATA / "topics.json"
HISTORY_FILE = DATA / "published_history.json"


def load_json(path, default):
    if not path.exists():
        return default

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def validate_topic(topic):
    required = ["id", "title", "summary", "sources"]

    if not all(topic.get(field) for field in required):
        return False

    # Au moins deux sources documentaires distinctes
    sources = topic["sources"]

    if len(sources) < 2:
        return False

    for source in sources:
        if not source.get("url", "").startswith("https://"):
            return False

        if not source.get("publisher"):
            return False

    return True


def select_topic():
    topics = load_json(TOPICS_FILE, [])
    history = load_json(HISTORY_FILE, [])

    used_ids = {item["topic_id"] for item in history}

    eligible = [
        topic for topic in topics
        if validate_topic(topic)
        and topic["id"] not in used_ids
    ]

    if not eligible:
        raise RuntimeError(
            "Aucun sujet inédit et suffisamment documenté."
        )

    # Mélange pour éviter un ordre prévisible
    random.shuffle(eligible)
    return eligible[0]


def main():
    print("OBSERVATEUR ACTIF AI")
    print("Démarrage du moteur éditorial...")

    DATA.mkdir(exist_ok=True)
    OUTPUT.mkdir(exist_ok=True)

    topic = select_topic()

    result = {
        "date": datetime.now(timezone.utc).isoformat(),
        "channel": "Observateur Actif",
        "topic": topic,
        "status": "RESEARCH_VALIDATED",
        "publication_ready": False
    }

    save_json(OUTPUT / "selected_topic.json", result)

    print("Sujet sélectionné :", topic["title"])
    print("Sources documentaires :", len(topic["sources"]))
    print("Statut : recherche préliminaire validée")
    print("Publication : non autorisée à ce stade")


if __name__ == "__main__":
    main()

"""Collecte de pistes documentaires depuis des flux RSS/Atom.

Les éléments collectés sont des pistes à vérifier, jamais des faits validés.
"""
from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
from pathlib import Path
import re
import urllib.error
import urllib.request
import warnings
import xml.etree.ElementTree as ET


class ResearchError(RuntimeError):
    """Erreur de collecte ou de lecture des flux."""


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _child_text(element: ET.Element, names: set[str]) -> str:
    for child in element:
        if _local_name(child.tag) in names:
            return "".join(child.itertext()).strip()
    return ""


def _atom_link(element: ET.Element) -> str:
    for child in element:
        if _local_name(child.tag) == "link":
            href = child.attrib.get("href", "").strip()
            rel = child.attrib.get("rel", "alternate")
            if href and rel in ("alternate", ""):
                return href
    return ""


def _normalize_date(value: str) -> str | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def parse_feed(xml_content: bytes, *, feed_url: str, publisher: str) -> list[dict]:
    """Lire un flux RSS 2.0 ou Atom et retourner des pistes non vérifiées."""
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as exc:
        raise ResearchError(f"Flux XML invalide ({feed_url}) : {exc}") from exc

    items = []
    for element in root.iter():
        kind = _local_name(element.tag)
        if kind not in {"item", "entry"}:
            continue
        title = _child_text(element, {"title"})
        if kind == "item":
            link = _child_text(element, {"link"})
            summary = _child_text(element, {"description", "encoded", "summary"})
            date = _child_text(element, {"pubdate", "published", "updated", "date"})
        else:
            link = _atom_link(element)
            summary = _child_text(element, {"summary", "content"})
            date = _child_text(element, {"published", "updated"})
        if not title or not link:
            continue
        # Strip markup from summaries; preserve readable text only.
        summary = re.sub(r"<[^>]*>", " ", summary)
        summary = re.sub(r"\s+", " ", summary).strip()
        items.append({
            "title": title,
            "url": link,
            "publisher": publisher,
            "feed_url": feed_url,
            "published_at": _normalize_date(date),
            "summary": summary[:3000],
            "editorial_status": "lead_unverified",
            "verification_note": (
                "Piste issue d'un flux. Ouvrir la source originale et recouper "
                "les affirmations avant toute utilisation dans le documentaire."
            ),
        })
    return items


def collect_feeds(feeds: list[dict], *, timeout: int = 20) -> list[dict]:
    """Collecter les flux accessibles et ignorer les éditeurs momentanément indisponibles."""
    collected: list[dict] = []
    seen: set[str] = set()
    errors: list[str] = []
    for feed in feeds:
        publisher = str(feed.get("publisher", "")).strip()
        url = str(feed.get("url", "")).strip()
        if not publisher or not url or not url.startswith(("https://", "http://")):
            raise ResearchError("Chaque flux doit avoir un éditeur et une URL HTTP(S) valide.")
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "ObservateurActifAI/0.1 (+documentary research bot)"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                if response.status < 200 or response.status >= 300:
                    raise ResearchError(f"Flux indisponible ({response.status}) : {url}")
                payload = response.read(5 * 1024 * 1024 + 1)
            if len(payload) > 5 * 1024 * 1024:
                raise ResearchError(f"Flux trop volumineux (limite 5 Mo) : {url}")
            items = parse_feed(payload, feed_url=url, publisher=publisher)
        except (urllib.error.URLError, TimeoutError, OSError, ResearchError) as exc:
            message = f"{publisher} ({url}) : {exc}"
            errors.append(message)
            warnings.warn(f"Flux ignoré : {message}", RuntimeWarning, stacklevel=2)
            continue
        for item in items:
            key = item["url"].strip()
            if key not in seen:
                seen.add(key)
                collected.append(item)
    if not collected and errors:
        raise ResearchError(
            "Aucun flux RSS exploitable. Erreurs : " + " | ".join(errors)
        )
    return collected

def load_feed_config(path: str | Path) -> list[dict]:
    config_path = Path(path)
    if not config_path.is_file():
        raise FileNotFoundError(f"Configuration de flux introuvable : {config_path}")
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ResearchError(f"JSON de flux invalide : {exc}") from exc
    if not isinstance(data, list):
        raise ResearchError("Le fichier de flux doit contenir une liste JSON.")
    return data


def save_leads(items: list[dict], output_path: str | Path) -> Path:
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(items, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return destination

"""Téléchargement prudent et extraction du texte des sources originales.

Le contenu extrait reste non vérifié : ce module ne juge ni l'exactitude
ni l'indépendance éditoriale d'une publication.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
import ipaddress
import socket
from urllib.parse import urlsplit

import requests


class SourceFetchError(RuntimeError):
    """Erreur de validation, de téléchargement ou d'extraction d'une source."""


MAX_BYTES = 2 * 1024 * 1024
TIMEOUT_SECONDS = 15
USER_AGENT = "ObservateurActifAI/0.1 (documentary source review)"


@dataclass
class SourceDocument:
    url: str
    title: str
    text: str
    fetched_at: str
    editorial_status: str = "source_text_unverified"

    def to_dict(self) -> dict:
        return asdict(self)


class _TextExtractor(HTMLParser):
    """Extraction légère sans exécuter de JavaScript ni charger de ressources."""

    _IGNORED = {"script", "style", "noscript", "svg", "nav", "footer", "header"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self._ignored_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag in self._IGNORED:
            self._ignored_depth += 1
        elif tag == "title":
            self._in_title = True
        elif tag in {"p", "br", "div", "article", "section", "h1", "h2", "h3", "li"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self._IGNORED and self._ignored_depth:
            self._ignored_depth -= 1
        elif tag == "title":
            self._in_title = False
        elif tag in {"p", "div", "article", "section", "h1", "h2", "h3", "li"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        cleaned = " ".join(data.split())
        if not cleaned:
            return
        if self._in_title:
            self.title_parts.append(cleaned)
        else:
            self.parts.append(cleaned)


def _validate_public_url(url: str) -> str:
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("URL HTTP(S) requise")
        if parsed.username or parsed.password:
            raise ValueError("Identifiants intégrés dans l'URL interdits")
        if parsed.port not in {None, 80, 443}:
            raise ValueError("Ports non standards interdits")
        host = parsed.hostname.encode("idna").decode("ascii")
        addresses = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
        if not addresses:
            raise ValueError("Nom d'hôte sans adresse IP")
        for address in {item[4][0] for item in addresses}:
            ip = ipaddress.ip_address(address.split("%", 1)[0])
            if not ip.is_global:
                raise ValueError("Adresse IP locale, privée ou réservée interdite")
        return url
    except (ValueError, UnicodeError, OSError, socket.gaierror) as exc:
        raise SourceFetchError(f"URL refusée ou hôte inaccessible : {exc}") from exc


def fetch_source(url: str, *, timeout: int = TIMEOUT_SECONDS,
                 max_bytes: int = MAX_BYTES) -> SourceDocument:
    """Télécharger une page HTML publique et extraire son texte visible.

    Les redirections sont volontairement refusées afin de ne pas contourner
    la validation de sécurité de l'hôte cible.
    """
    safe_url = _validate_public_url(url)
    try:
        response = requests.get(
            safe_url,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
            timeout=timeout,
            allow_redirects=False,
            stream=True,
        )
    except requests.RequestException as exc:
        raise SourceFetchError(f"Échec du téléchargement : {exc}") from exc

    try:
        if response.status_code in {301, 302, 303, 307, 308}:
            raise SourceFetchError("Redirection refusée : vérifier manuellement l'URL finale.")
        if response.status_code < 200 or response.status_code >= 300:
            raise SourceFetchError(f"Le serveur a répondu HTTP {response.status_code}.")
        content_type = response.headers.get("Content-Type", "").lower()
        if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
            raise SourceFetchError(f"Type de contenu non HTML : {content_type or 'inconnu'}.")
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_content(chunk_size=16_384):
            if not chunk:
                continue
            total += len(chunk)
            if total > max_bytes:
                raise SourceFetchError(f"Page trop volumineuse (limite {max_bytes} octets).")
            chunks.append(chunk)
        raw = b"".join(chunks)
        encoding = response.encoding or "utf-8"
        html = raw.decode(encoding, errors="replace")
    finally:
        response.close()

    parser = _TextExtractor()
    try:
        parser.feed(html)
        parser.close()
    except Exception as exc:
        raise SourceFetchError(f"Impossible d'extraire le HTML : {exc}") from exc

    title = " ".join(parser.title_parts).strip()
    text = " ".join(" ".join(parser.parts).split())
    if not text:
        raise SourceFetchError("Aucun texte lisible trouvé dans cette page.")
    return SourceDocument(
        url=safe_url,
        title=title[:500],
        text=text[:100_000],
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )


def fetch_leads(leads: list[dict], *, limit: int = 5) -> list[dict]:
    """Lire séquentiellement un petit lot de pistes RSS.

    Les erreurs sont conservées piste par piste afin qu'une page inaccessible
    ne bloque pas les autres. Les doublons d'URL sont ignorés.
    """
    if not 1 <= limit <= 20:
        raise ValueError("La limite doit être comprise entre 1 et 20.")
    if not isinstance(leads, list):
        raise ValueError("Les pistes doivent être une liste JSON.")
    results: list[dict] = []
    seen: set[str] = set()
    attempted = 0
    for lead in leads:
        if not isinstance(lead, dict):
            continue
        url = str(lead.get("url", "")).strip()
        if not url or url in seen:
            continue
        seen.add(url)
        if attempted >= limit:
            break
        attempted += 1
        item = {
            "lead_title": str(lead.get("title", ""))[:500],
            "publisher": str(lead.get("publisher", ""))[:300],
            "published_at": lead.get("published_at"),
            "url": url,
        }
        try:
            document = fetch_source(url)
            item.update(document.to_dict())
            item["fetch_status"] = "success"
        except SourceFetchError as exc:
            item.update({
                "fetch_status": "failed",
                "fetch_error": str(exc)[:1000],
                "editorial_status": "source_text_unverified",
            })
        results.append(item)
    return results

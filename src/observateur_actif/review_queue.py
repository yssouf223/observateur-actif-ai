"""Génération d'une file de revue éditoriale lisible par un humain."""
from __future__ import annotations

from pathlib import Path
import json

from observateur_actif.claim_review import ClaimRegistry


def build_review_queue(registry: ClaimRegistry) -> str:
    """Produire un rapport Markdown des affirmations à examiner."""
    sources = {source.id: source for source in registry.sources}
    pending = [
        claim for claim in registry.claims
        if claim.review_decision.value == "pending"
    ]
    lines = [
        "# File de revue éditoriale — Observateur Actif",
        "",
        f"Affirmations en attente : **{len(pending)}**",
        "",
        "> Ce document est une aide à la revue, pas une validation des faits.",
        "> Ne jamais approuver une affirmation sur la seule base de son extraction.",
        "",
    ]
    for index, claim in enumerate(pending, start=1):
        lines.extend([
            f"## {index}. {claim.id}",
            "",
            f"**Affirmation candidate :** {claim.statement}",
            "",
            f"**Statut actuel :** {claim.status.value}",
            "",
            f"**Décision :** {claim.review_decision.value}",
            "",
            "**Sources à consulter :**",
            "",
        ])
        if not claim.source_ids:
            lines.append("- Aucune source référencée.")
        for source_id in claim.source_ids:
            source = sources[source_id]
            lines.append(
                f"- [{source.title}]({source.url}) — {source.publisher} "
                f"(consultée le {source.accessed_at}; "
                f"source favorable déclarée : {'oui' if source.supports_claim else 'non / à évaluer'})"
            )
        lines.extend([
            "",
            "**Contrôles du réviseur :**",
            "",
            "- [ ] Ouvrir la source originale et lire le contexte complet.",
            "- [ ] Vérifier date, lieu, personnes et chiffres mentionnés.",
            "- [ ] Chercher une source indépendante, primaire si possible.",
            "- [ ] Vérifier si les sources se citent mutuellement ou reprennent la même dépêche.",
            "- [ ] Distinguer fait, hypothèse, témoignage, tradition orale ou légende.",
            "- [ ] Décider : approuver, rejeter ou laisser en attente.",
            "",
            "**Notes du réviseur :**",
            "",
            "_À compléter manuellement._",
            "",
            "---",
            "",
        ])
    if not pending:
        lines.append("Aucune affirmation en attente de revue.")
    return "\n".join(lines)


def write_review_queue(input_file: str | Path, output_file: str | Path) -> Path:
    """Valider le registre puis écrire le rapport de revue."""
    source_path = Path(input_file)
    if not source_path.is_file():
        raise FileNotFoundError(f"Registre introuvable : {source_path}")
    registry = ClaimRegistry.model_validate_json(source_path.read_text(encoding="utf-8"))
    destination = Path(output_file)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(build_review_queue(registry), encoding="utf-8")
    return destination

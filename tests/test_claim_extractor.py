from observateur_actif.claim_extractor import extract_claim_candidates


def test_extracts_candidate_sentences_without_marking_them_verified():
    docs = [{
        "url": "https://example.org/report",
        "title": "Rapport",
        "publisher": "Example News",
        "text": (
            "Une introduction générale qui ne contient pas de fait précis. "
            "Selon les archives locales, le village a été fondé en 1890. "
            "Cette phrase est trop courte."
        ),
        "fetch_status": "success",
        "fetched_at": "2026-11-27T00:00:00+00:00",
    }]
    result = extract_claim_candidates(docs)
    assert len(result["sources"]) == 1
    assert len(result["claims"]) == 1
    claim = result["claims"][0]
    assert "village a été fondé" in claim["statement"]
    assert claim["status"] == "unconfirmed"
    assert claim["review_decision"] == "pending"
    assert result["sources"][0]["supports_claim"] is False


def test_skips_failed_documents_and_duplicate_urls():
    doc = {
        "url": "https://example.org/report",
        "title": "Rapport",
        "publisher": "Example",
        "text": "Selon le rapport, une ancienne forteresse a été découverte près du fleuve.",
        "fetch_status": "success",
    }
    result = extract_claim_candidates([
        {**doc, "fetch_status": "failed"},
        doc,
        doc,
    ])
    assert len(result["sources"]) == 1
    assert len(result["claims"]) == 1


def test_candidate_limit_is_bounded():
    import pytest
    with pytest.raises(ValueError, match="compris entre 1 et 100"):
        extract_claim_candidates([], max_per_source=101)


def test_rejects_non_list_input():
    import pytest
    with pytest.raises(ValueError, match="liste JSON"):
        extract_claim_candidates({})

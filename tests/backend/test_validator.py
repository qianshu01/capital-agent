# tests/backend/test_validator.py
from backend.research.validator import validate_bundle

def _valid_bundle():
    return {
        "entity": {
            "name": "Premji Invest", "type": "sfo", "country": "IN",
            "region": "South Asia", "controlling_family": "Premji",
            "ticker": None, "exchange": None,
            "estimated_aum_usd": 10_000_000_000.0, "aum_basis": "disclosed",
            "sectors": ["tech"], "deployment": "mixed",
            "accessibility": "restricted",
            "provenance": "chat_discovered", "confidence_score": 4,
        },
        "evidence": [
            {"question_key": "where_capital_sits",
             "answer": "Single-family office in Bangalore.",
             "confidence": 5, "source_urls": ["https://premjiinvest.com/about"]},
            {"question_key": "how_much_capital",
             "answer": "Disclosed AUM of $10B per official site.",
             "confidence": 5, "source_urls": ["https://premjiinvest.com/about"]},
            {"question_key": "who_controls",
             "answer": "Azim Premji (founder), Atul Gupta (CIO).",
             "confidence": 5, "source_urls": ["https://linkedin.com/in/atul-gupta"]},
            {"question_key": "how_deployed",
             "answer": "Mixed direct + external manager allocations.",
             "confidence": 4, "source_urls": ["https://premjiinvest.com/strategy"]},
            {"question_key": "direct_or_external",
             "answer": "~60% direct per latest disclosed split.",
             "confidence": 3, "source_urls": ["https://livemint.com/x"]},
        ],
        "sources": [
            {"url": "https://premjiinvest.com/about", "source_type": "firecrawl",
             "note": "official site", "retrieved_at": "2026-05-23T00:00:00Z"},
            {"url": "https://linkedin.com/in/atul-gupta", "source_type": "apollo",
             "note": "CIO LinkedIn", "retrieved_at": "2026-05-23T00:00:00Z"},
            {"url": "https://premjiinvest.com/strategy", "source_type": "firecrawl",
             "note": "strategy page", "retrieved_at": "2026-05-23T00:00:00Z"},
            {"url": "https://livemint.com/x", "source_type": "exa",
             "note": "press", "retrieved_at": "2026-05-23T00:00:00Z"},
        ],
    }

def test_valid_bundle_passes():
    assert validate_bundle(_valid_bundle()) == []

def test_fewer_than_5_questions_rejected():
    b = _valid_bundle()
    b["evidence"] = b["evidence"][:4]
    errors = validate_bundle(b)
    assert any("at least 5" in e for e in errors)

def test_unreferenced_source_url_rejected():
    b = _valid_bundle()
    b["evidence"][0]["source_urls"] = ["https://not-in-sources.com"]
    errors = validate_bundle(b)
    assert any("not in sources" in e for e in errors)

def test_generic_who_controls_rejected():
    b = _valid_bundle()
    b["evidence"][2]["answer"] = "The family office team handles allocations."
    errors = validate_bundle(b)
    assert any("generic" in e.lower() for e in errors)

def test_how_much_capital_without_figure_rejected():
    b = _valid_bundle()
    b["evidence"][1]["answer"] = "Substantial assets under management."
    errors = validate_bundle(b)
    assert any("how_much_capital" in e for e in errors)

def test_how_much_capital_explicit_no_estimate_accepted():
    b = _valid_bundle()
    b["evidence"][1]["answer"] = (
        "no public estimate; reasoning: privately held, no filings."
    )
    assert validate_bundle(b) == []

def test_bad_provenance_rejected():
    b = _valid_bundle()
    b["entity"]["provenance"] = "guessed"
    errors = validate_bundle(b)
    assert any("provenance" in e for e in errors)

def test_bad_confidence_rejected():
    b = _valid_bundle()
    b["entity"]["confidence_score"] = 99
    errors = validate_bundle(b)
    assert any("confidence_score" in e for e in errors)

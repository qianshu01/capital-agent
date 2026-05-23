"""Server-side bundle validator. Returns list of error strings ([] = ok)."""
from __future__ import annotations
import re
from backend.research.constants import (
    QUESTION_KEYS, PROVENANCE_VALUES, BANNED_GENERIC, MIN_EVIDENCE_QUESTIONS,
)

_BANNED_RE = re.compile(BANNED_GENERIC, re.IGNORECASE)
_DOLLAR_RE = re.compile(r"\$")
_NO_ESTIMATE_RE = re.compile(r"no public estimate; reasoning:", re.IGNORECASE)

def validate_bundle(bundle: dict) -> list[str]:
    errors: list[str] = []
    entity = bundle.get("entity") or {}
    evidence = bundle.get("evidence") or []
    sources = bundle.get("sources") or []

    # provenance + confidence_score
    if entity.get("provenance") not in PROVENANCE_VALUES:
        errors.append(
            f"entity.provenance must be one of {sorted(PROVENANCE_VALUES)}"
        )
    cs = entity.get("confidence_score")
    if not isinstance(cs, int) or not (1 <= cs <= 5):
        errors.append("entity.confidence_score must be int in 1..5")

    # evidence coverage
    if len(evidence) < MIN_EVIDENCE_QUESTIONS:
        errors.append(
            f"evidence must cover at least {MIN_EVIDENCE_QUESTIONS} questions; "
            f"got {len(evidence)}"
        )
    seen = set()
    by_key: dict[str, dict] = {}
    for ev in evidence:
        k = ev.get("question_key")
        if k not in QUESTION_KEYS:
            errors.append(f"unknown question_key: {k!r}")
            continue
        if k in seen:
            errors.append(f"duplicate question_key: {k}")
        seen.add(k)
        by_key[k] = ev

    # citation integrity
    source_urls = {s.get("url") for s in sources}
    for ev in evidence:
        for u in ev.get("source_urls") or []:
            if u not in source_urls:
                errors.append(
                    f"evidence[{ev.get('question_key')}] cites URL not in sources: {u}"
                )

    # who_controls cannot be generic
    wc = by_key.get("who_controls")
    if wc and _BANNED_RE.search(wc.get("answer") or ""):
        errors.append(
            "who_controls answer is generic; must name at least one individual"
        )

    # how_much_capital must have $ or explicit no-estimate marker
    hmc = by_key.get("how_much_capital")
    if hmc:
        ans = hmc.get("answer") or ""
        if not (_DOLLAR_RE.search(ans) or _NO_ESTIMATE_RE.search(ans)):
            errors.append(
                "how_much_capital must include a $-figure OR "
                "'no public estimate; reasoning: ...'"
            )

    return errors

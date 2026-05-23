"""Shared constants. Edit here, used everywhere in research/."""

QUESTION_KEYS: list[str] = [
    "where_capital_sits",
    "how_much_capital",
    "who_controls",
    "how_deployed",
    "direct_or_external",
    "accessibility",
    "why_invest",
]

PROVENANCE_VALUES = {"curated", "chat_discovered", "chat_enriched"}

BANNED_GENERIC = (
    r"family office team|the family|investment team|family members|"
    r"management team|the office|in-house team|allocation team"
)

MIN_EVIDENCE_QUESTIONS = 5

"""Source definitions. Each source writes to its own CSV + JSON files."""

from dataclasses import dataclass, field
from pathlib import Path

from .core import DATA_DIR, TRILEGAL_BASE


@dataclass(frozen=True)
class Source:
    key: str                 # CLI identifier, e.g. "industries"
    label: str               # plural human label, e.g. "industries"
    singular: str            # singular human label, e.g. "industry"
    index_url: str           # listing page URL
    detail_path: str         # URL segment detail pages live under
    csv_path: Path           # dedupe ledger (bookkeeping columns)
    json_path: Path          # full new-items dump
    content_csv_path: Path   # readable: title, snippet, clients
    summary_queries: list = field(default_factory=list)


INDUSTRIES = Source(
    key="industries",
    label="industries",
    singular="industry",
    index_url=f"{TRILEGAL_BASE}/industries/",
    detail_path="industries",
    csv_path=DATA_DIR / "trilegal_industries_master.csv",
    json_path=DATA_DIR / "trilegal_industries_new.json",
    content_csv_path=DATA_DIR / "trilegal_industries_content.csv",
    summary_queries=[
        "What does the firm do in this industry and what services does it offer?",
        "What is the regulatory and market context for this sector?",
        "Who are the clients and what kind of matters are handled?",
        "What is the firm's experience and track record in this sector?",
    ],
)

# NOTE: index is /expertise/ (singular) but detail pages are /expertises/<slug>/ (plural)
EXPERTISE = Source(
    key="expertise",
    label="expertise",
    singular="practice",
    index_url=f"{TRILEGAL_BASE}/expertise/",
    detail_path="expertises",
    csv_path=DATA_DIR / "trilegal_expertise_master.csv",
    json_path=DATA_DIR / "trilegal_expertise_new.json",
    content_csv_path=DATA_DIR / "trilegal_expertise_content.csv",
    summary_queries=[
        "What does this practice area cover and what services are offered?",
        "What is the regulatory and legal context for this practice?",
        "Who are the clients and what kind of matters are handled?",
        "What is the firm's experience, track record, and standing in this area?",
    ],
)

ALL_SOURCES = {s.key: s for s in (INDUSTRIES, EXPERTISE)}

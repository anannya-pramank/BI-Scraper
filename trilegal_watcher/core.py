"""Shared scraping core used by all Trilegal source watchers."""

import requests
from bs4 import BeautifulSoup
from pathlib import Path
from datetime import datetime
import hashlib
import csv
import json
import re


# ================= CONFIG =================

DATA_DIR      = Path("trilegal")
TRILEGAL_BASE = "https://trilegal.com"
HARD_CAP      = 80_000

HEADERS = {
    "User-Agent":      "Mozilla/5.0 (compatible; TrilegalBot/1.0)",
    "Accept-Language": "en-US,en;q=0.9",
}

_st_model = None


# ================= SEMANTIC EXTRACTION =================

def _get_model():
    global _st_model
    if _st_model is None:
        from sentence_transformers import SentenceTransformer
        print("  Loading semantic model …")
        _st_model = SentenceTransformer("all-MiniLM-L6-v2")
        print("  Model ready.")
    return _st_model


def semantic_extract(full_text: str, summary_queries: list) -> str:
    chunks = [c.strip() for c in re.split(r"\n{2,}", full_text) if len(c.strip()) > 80]

    if not chunks:
        return full_text[:HARD_CAP]

    total = sum(len(c) for c in chunks)
    if total <= HARD_CAP:
        return full_text

    try:
        import numpy as np
        model = _get_model()

        chunk_embs = model.encode(chunks,         show_progress_bar=False, batch_size=64)
        query_embs = model.encode(summary_queries, show_progress_bar=False)

        chunk_unit = chunk_embs / (np.linalg.norm(chunk_embs, axis=1, keepdims=True) + 1e-8)
        scores     = np.zeros(len(chunks))

        for q_emb in query_embs:
            q_unit = q_emb / (np.linalg.norm(q_emb) + 1e-8)
            scores = np.maximum(scores, chunk_unit @ q_unit)

        threshold = 0.35 * scores.max()
        selected  = []
        used      = 0

        for idx in range(len(chunks)):
            if scores[idx] >= threshold and used + len(chunks[idx]) <= HARD_CAP:
                selected.append(idx)
                used += len(chunks[idx])

        if not selected:
            selected = sorted(int(i) for i in np.argsort(scores)[::-1][:10])
            used = sum(len(chunks[i]) for i in selected)

        result = "\n\n".join(chunks[i] for i in selected)
        print(f"  Semantic selection: {len(selected)}/{len(chunks)} chunks "
              f"({used:,} chars from {total:,} total, threshold={threshold:.3f})")
        return result

    except Exception as e:
        print(f"  [Semantic extract fallback] {e}")
        return full_text[:HARD_CAP]


# ================= HELPERS =================

def make_id(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:16]


def clean(el) -> str:
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True))


def absolute_url(href: str) -> str:
    href = href.strip()
    return href if href.startswith("http") else TRILEGAL_BASE + "/" + href.lstrip("/")


def get_soup(url: str, timeout: int = 30) -> BeautifulSoup:
    resp = requests.get(url, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


# ================= DETAIL EXTRACTION =================

def extract_detail(detail_url: str, summary_queries: list) -> dict:
    """Fetch a Trilegal detail page and pull intro, body text, and client list."""
    try:
        resp = requests.get(detail_url, headers=HEADERS, timeout=30)
        if resp.status_code != 200:
            return {"intro": "", "body_text": "", "clients": []}

        soup = BeautifulSoup(resp.text, "html.parser")
        container = soup.find("main") or soup.find("article") or soup

        paras = []
        clients = []
        in_client_list = False

        for el in container.find_all(["h1", "h2", "h3", "p", "li"]):
            text = clean(el)
            low  = text.lower()

            # Stop at related-items / footer area
            if el.name in ("h2", "h3") and ("related" in low or "quick links" in low):
                break

            if el.name == "p":
                if text:
                    paras.append(text)
                if "clients in this space" in low or "some of our clients" in low:
                    in_client_list = True
                else:
                    in_client_list = False
            elif el.name == "li" and in_client_list:
                if text:
                    clients.append(text)

        intro = paras[0] if paras else ""
        body_text = "\n\n".join(paras)

        return {
            "intro":     intro,
            "body_text": semantic_extract(body_text, summary_queries),
            "clients":   clients,
        }

    except Exception as e:
        print(f"  [Detail extract error] {detail_url}: {e}")
        return {"intro": "", "body_text": "", "clients": []}


# ================= INDEX SCRAPER =================

def scrape_index(index_url: str, detail_path: str) -> list:
    """Collect detail-page links from a listing page.

    detail_path is the URL segment the detail pages live under, e.g.
    'industries' or 'expertises'. Single-segment slugs only, so the
    index page itself and nested paths are skipped.
    """
    soup = get_soup(index_url)

    pattern = re.compile(
        r"^https?://trilegal\.com/" + re.escape(detail_path) + r"/(.+?)/?$"
    )

    results = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        m = pattern.match(href)
        if not m:
            continue
        slug = m.group(1).strip("/")
        if not slug or "/" in slug:
            continue

        url = absolute_url(href)
        if url in seen:
            continue
        seen.add(url)

        raw = clean(a)
        teaser = re.sub(r"see more\.*\s*$", "", raw, flags=re.I).strip()

        results.append({
            "slug":       slug,
            "teaser":     teaser,
            "detail_url": url,
        })

    return results


# ================= CSV / JSON HELPERS =================

def ensure_csv(csv_path: Path, fieldnames: list):
    DATA_DIR.mkdir(exist_ok=True)
    if not csv_path.exists():
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(fieldnames)


def load_ids(csv_path: Path) -> set:
    if not csv_path.exists():
        return set()
    with csv_path.open(encoding="utf-8") as f:
        return {r["id"] for r in csv.DictReader(f)}


def append_to_csv(csv_path: Path, rows: list, fieldnames: list):
    with csv_path.open("a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore").writerows(rows)


CONTENT_FIELDS = ["title", "snippet", "clients", "detail_url"]


def append_content_csv(csv_path: Path, items: list):
    """Readable companion CSV: one row per item with title, snippet, and
    marquee clients all in the same file. Appends new rows; header written once.

    - snippet: the detail page's intro paragraph, falling back to the card teaser.
    - clients: the marquee client list joined with '; ' into a single cell.
    """
    ensure_csv(csv_path, CONTENT_FIELDS)
    rows = []
    for it in items:
        snippet = (it.get("intro") or it.get("teaser") or "").strip()
        clients = "; ".join(it.get("clients") or [])
        rows.append({
            "title":      it.get("title", ""),
            "snippet":    snippet,
            "clients":    clients,
            "detail_url": it.get("detail_url", ""),
        })
    append_to_csv(csv_path, rows, CONTENT_FIELDS)


def write_json(json_path: Path, items: list):
    json_path.write_text(
        json.dumps(
            {"generated_at": datetime.utcnow().isoformat(),
             "count":        len(items),
             "items":        items},
            indent=2, ensure_ascii=False,
        ),
        encoding="utf-8",
    )


# ================= GENERIC RUNNER =================

def run_source(source) -> int:
    """Scrape one source (industries or expertise) and persist new items.

    `source` is a Source dataclass instance. Returns count of new items.
    """
    csv_fields = ["id", "slug", "title", "detail_url", "scraped_at"]
    ensure_csv(source.csv_path, csv_fields)
    existing_ids = load_ids(source.csv_path)

    print(f"Scraping Trilegal {source.label} index …")
    scraped = scrape_index(source.index_url, source.detail_path)
    print(f"  {len(scraped)} {source.label} links on page")

    new_items = []
    for entry in scraped:
        item_id = make_id(entry["detail_url"])
        if item_id in existing_ids:
            continue

        print(f"\n  NEW {source.singular}: {entry['slug']}")
        detail = extract_detail(entry["detail_url"], source.summary_queries)
        title = entry["slug"].replace("-", " ").title()

        new_items.append({
            "id":         item_id,
            "slug":       entry["slug"],
            "title":      title,
            "detail_url": entry["detail_url"],
            "teaser":     entry["teaser"],
            "intro":      detail["intro"],
            "body_text":  detail["body_text"],
            "clients":    detail["clients"],
            "scraped_at": datetime.utcnow().isoformat(),
        })

    print(f"\n  New {source.label}: {len(new_items)}")
    if new_items:
        append_to_csv(source.csv_path, new_items, csv_fields)
        write_json(source.json_path, new_items)
        append_content_csv(source.content_csv_path, new_items)

    return len(new_items)

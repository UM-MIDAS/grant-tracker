"""
Federal Register Monitor — RFIs & Advisory Committee Nominations
Searches both published documents AND public inspection (pre-publication)
documents, appends new items to a CSV, and posts a Slack digest.

No API key required — the Federal Register API is fully public.

Secrets required (set in GitHub → Settings → Secrets and variables → Actions):
  SLACK_WEBHOOK  — Slack incoming webhook URL (shared with other monitors)
"""

import os
import sys
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── CONFIGURATION ──────────────────────────────────────────────────────────────

SLACK_WEBHOOK = os.environ["SLACK_WEBHOOK"]

PUBLISHED_ENDPOINT  = "https://www.federalregister.gov/api/v1/documents.json"
PUBLIC_INSP_ENDPOINT = "https://www.federalregister.gov/api/v1/public-inspection-documents.json"

CSV_PATH = Path("data/federal_register.csv")

DAYS_LOOKBACK = 14
PER_PAGE      = 1000  # API max
MAX_PAGES     = 20

REPO_URL = "https://github.com/" + os.environ.get("GITHUB_REPOSITORY", "your-org/your-repo")
CSV_URL  = f"{REPO_URL}/blob/main/data/federal_register.csv"

# Search terms — the API searches across title and full text.
# These cover RFIs and advisory committee nomination calls.
SEARCH_TERMS = [
    "request for information",
    "requests for information",
    "advisory committee",
    "call for nominations",
    "nominations",
    "call for experts",
]

# Document types to include.
# NOTICE covers the vast majority of RFIs and advisory committee items.
# RULE and PRORULE occasionally contain relevant RFI-style content.
DOCUMENT_TYPES = ["NOTICE"]

# Fields to request from the API — only fetch what we need
FIELDS = [
    "document_number",
    "title",
    "publication_date",
    "agencies",
    "type",
    "abstract",
    "html_url",
    "pdf_url",
    "public_inspection_pdf_url",
    "comments_close_on",
    "effective_on",
    "docket_ids",
    "citation",
]

# ── PUBLISHED DOCUMENTS FETCH ──────────────────────────────────────────────────

def fetch_published(term: str) -> list:
    """Fetch published Federal Register documents matching a search term."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=DAYS_LOOKBACK)).strftime("%Y-%m-%d")
    results, page = [], 1

    while page <= MAX_PAGES:
        params = {
            "conditions[term]":                   term,
            "conditions[type][]":                 DOCUMENT_TYPES,
            "conditions[publication_date][gte]":  cutoff,
            "per_page":                           PER_PAGE,
            "page":                               page,
            "order":                              "newest",
        }
        # Add fields
        for f in FIELDS:
            params[f"fields[]"] = f

        resp = requests.get(PUBLISHED_ENDPOINT, params=params, timeout=30)
        resp.raise_for_status()
        data  = resp.json()
        batch = data.get("results", [])
        results.extend(batch)

        total_pages = data.get("total_pages", 1)
        if page >= total_pages or not batch:
            break
        page += 1

    return results


def fetch_public_inspection(term: str) -> list:
    """
    Fetch public inspection documents (pre-publication PDFs).
    These appear in the Register before the official published version
    and represent the earliest possible awareness of new items.
    """
    params = {
        "conditions[term]":    term,
        "conditions[type][]":  DOCUMENT_TYPES,
        "per_page":            PER_PAGE,
    }
    for f in ["document_number", "title", "agencies", "type",
              "filing_date", "public_inspection_pdf_url", "html_url"]:
        params["fields[]"] = f

    resp = requests.get(PUBLIC_INSP_ENDPOINT, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json().get("results", [])


# ── FIELD EXTRACTION ───────────────────────────────────────────────────────────

def get_agency_names(doc: dict) -> str:
    agencies = doc.get("agencies") or []
    return " | ".join(
        a.get("name", "") for a in agencies if a.get("name")
    )


def extract_published(doc: dict) -> dict:
    doc_num = doc.get("document_number", "")
    return {
        "Document Number":   doc_num,
        "Title":             doc.get("title", ""),
        "Type":              doc.get("type", ""),
        "Source":            "Published",
        "Agency":            get_agency_names(doc),
        "Publication Date":  doc.get("publication_date", ""),
        "Filing Date":       "",  # only available for public inspection
        "Response Deadline": doc.get("comments_close_on", ""),
        "Effective Date":    doc.get("effective_on", ""),
        "Citation":          doc.get("citation", ""),
        "Docket IDs":        " | ".join(doc.get("docket_ids") or []),
        "Abstract":          doc.get("abstract", ""),
        "HTML URL":          doc.get("html_url", ""),
        "PDF URL":           doc.get("pdf_url", ""),
        "Public Inspection PDF": doc.get("public_inspection_pdf_url", ""),
        "_document_number":  doc_num,
    }


def extract_public_inspection(doc: dict) -> dict:
    doc_num = doc.get("document_number", "")
    return {
        "Document Number":   doc_num,
        "Title":             doc.get("title", ""),
        "Type":              doc.get("type", ""),
        "Source":            "Public Inspection (Pre-Publication)",
        "Agency":            get_agency_names(doc),
        "Publication Date":  "",  # not yet published
        "Filing Date":       doc.get("filing_date", ""),
        "Response Deadline": "",
        "Effective Date":    "",
        "Citation":          "",
        "Docket IDs":        "",
        "Abstract":          "",
        "HTML URL":          doc.get("html_url", ""),
        "PDF URL":           "",
        "Public Inspection PDF": doc.get("public_inspection_pdf_url", ""),
        "_document_number":  doc_num,
    }


# ── DEDUPLICATION WITHIN RESULTS ───────────────────────────────────────────────

def dedupe_incoming(records: list[dict]) -> list[dict]:
    """Remove duplicates within the freshly fetched batch by document number."""
    seen, unique = set(), []
    for r in records:
        key = r.get("_document_number", "")
        if key and key not in seen:
            seen.add(key)
            unique.append(r)
    return unique


# ── CSV UPDATE ─────────────────────────────────────────────────────────────────

def load_existing_csv() -> pd.DataFrame:
    if CSV_PATH.exists():
        return pd.read_csv(CSV_PATH, dtype=str)
    return pd.DataFrame()


def append_new_rows(existing: pd.DataFrame, incoming: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    if existing.empty:
        return incoming, len(incoming)
    if "_document_number" in existing.columns:
        known_ids = set(existing["_document_number"].dropna())
    else:
        known_ids = set(existing["Document Number"].dropna())
    new_rows  = incoming[~incoming["_document_number"].isin(known_ids)]
    updated   = pd.concat([existing, new_rows], ignore_index=True)
    return updated, len(new_rows)


def save_csv(df: pd.DataFrame):
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.drop(columns=["_document_number"], errors="ignore").to_csv(CSV_PATH, index=False)


# ── SLACK NOTIFICATION ─────────────────────────────────────────────────────────

def post_slack(new_count: int, total_count: int, by_source: dict, by_agency: dict):
    today = datetime.now().strftime("%B %d, %Y")

    if new_count == 0:
        text = f":mag: *Federal Register Monitor — {today}*\nNo new RFIs or advisory committee items found."
    else:
        source_lines = "\n".join(f"  • {s}: {c}" for s, c in sorted(by_source.items()))
        agency_lines = "\n".join(f"  • {a}: {c}" for a, c in sorted(by_agency.items(), key=lambda x: -x[1])[:10])
        text = (
            f":scroll: *Federal Register Monitor — {today}*\n"
            f"*{new_count} new item{'s' if new_count != 1 else ''}* added "
            f"({total_count} total in tracker)\n\n"
            f"*By source:*\n{source_lines}\n\n"
            f"*By agency (top 10):*\n{agency_lines}\n\n"
            f":arrow_right: <{CSV_URL}|View full tracker on GitHub>"
        )

    resp = requests.post(SLACK_WEBHOOK, json={"text": text}, timeout=10)
    if resp.status_code != 200:
        print(f"WARNING: Slack notification failed ({resp.status_code}): {resp.text}")
    else:
        print("Slack notification sent.")


# ── MAIN ───────────────────────────────────────────────────────────────────────

def main():
    print(f"Starting Federal Register monitor — {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Search terms: {', '.join(SEARCH_TERMS)}")
    print(f"Lookback: {DAYS_LOOKBACK} days\n")

    all_records = []

    # ── Published documents ────────────────────────────────────────────────────
    print("Fetching published documents...")
    for term in SEARCH_TERMS:
        results = fetch_published(term)
        extracted = [extract_published(d) for d in results]
        all_records.extend(extracted)
        print(f"  '{term}' → {len(results)} published documents")

    # ── Public inspection (pre-publication) ───────────────────────────────────
    print("\nFetching public inspection (pre-publication) documents...")
    for term in SEARCH_TERMS:
        try:
            results = fetch_public_inspection(term)
            extracted = [extract_public_inspection(d) for d in results]
            all_records.extend(extracted)
            print(f"  '{term}' → {len(results)} public inspection documents")
        except Exception as e:
            print(f"  WARNING: Public inspection fetch failed for '{term}': {e}")

    print(f"\nTotal records before dedup: {len(all_records)}")
    all_records = dedupe_incoming(all_records)
    print(f"Total records after dedup:  {len(all_records)}")

    if not all_records:
        print("No items found. Notifying Slack.")
        post_slack(0, 0, {}, {})
        return

    incoming_df = pd.DataFrame(all_records)

    existing_df           = load_existing_csv()
    updated_df, new_count = append_new_rows(existing_df, incoming_df)

    save_csv(updated_df)
    print(f"CSV updated — {new_count} new rows added ({len(updated_df)} total).")

    if new_count > 0:
        new_rows   = updated_df.tail(new_count)
        by_source  = new_rows["Source"].value_counts().to_dict()
        # Agency column can be multi-value; count first agency listed
        by_agency  = new_rows["Agency"].apply(
            lambda x: x.split(" | ")[0] if isinstance(x, str) and x else "Unknown"
        ).value_counts().to_dict()
    else:
        by_source = by_agency = {}

    post_slack(new_count, len(updated_df), by_source, by_agency)
    print("Done.")


if __name__ == "__main__":
    main()

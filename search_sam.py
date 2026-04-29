"""
SAM.gov Opportunity Monitor — ARPA-H & DARPA
Fetches new contract opportunities (all types) from ARPA-H and DARPA,
appends to a CSV in the repo, and posts a Slack digest summarizing what's new.

Secrets required (set in GitHub → Settings → Secrets and variables → Actions):
  SAM_API_KEY    — SAM.gov public API key (from sam.gov profile → Account Details)
  SLACK_WEBHOOK  — Slack incoming webhook URL (shared with grants monitor)
"""

import os
import sys
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── CONFIGURATION ──────────────────────────────────────────────────────────────

SAM_API_KEY   = os.environ["SAM_API_KEY"]
SLACK_WEBHOOK = os.environ["SLACK_WEBHOOK"]

SEARCH_ENDPOINT = "https://api.sam.gov/opportunities/v2/search"
CSV_PATH        = Path("data/sam_opportunities.csv")

DAYS_LOOKBACK = 14   # how far back to search; deduplication handles overlap
PAGE_SIZE     = 1000  # SAM.gov max per page
MAX_PAGES     = 20

REPO_URL = "https://github.com/" + os.environ.get("GITHUB_REPOSITORY", "your-org/your-repo")
CSV_URL  = f"{REPO_URL}/blob/main/data/sam_opportunities.csv"

# SAM.gov uses organizationName for filtering — these are partial matches.
# Both ARPA-H and DARPA will match their full official names.
TARGET_ORGS = ["ARPA-H", "DARPA"]

# Procurement type codes — all types included per requirements.
# Leave empty to return all types.
# Available types: p=Pre-Solicitation, o=Solicitation, k=Combined Synopsis/Solicitation,
# r=Sources Sought, s=Special Notice, a=Award Notice, u=Justification (J&A)
# i=Intent to Bundle Requirements (DoD-Funded)
PROCUREMENT_TYPES = []  # empty = all types

# ── API FETCH ──────────────────────────────────────────────────────────────────

def date_str(d: datetime) -> str:
    """Format date as MM/dd/yyyy as required by SAM.gov API."""
    return d.strftime("%m/%d/%Y")


def fetch_for_org(org_name: str) -> list:
    """Fetch all opportunities for a single org name within the lookback window."""
    now    = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=DAYS_LOOKBACK)

    base_params = {
        "api_key":          SAM_API_KEY,
        "postedFrom":       date_str(cutoff),
        "postedTo":         date_str(now),
        "organizationName": org_name,
        "limit":            PAGE_SIZE,
        "offset":           0,
    }

    all_records, page = [], 0

    while page <= MAX_PAGES:
        params = {**base_params, "offset": page * PAGE_SIZE}
        resp   = requests.get(SEARCH_ENDPOINT, params=params, timeout=30)

        if resp.status_code == 401:
            print(f"ERROR: Invalid SAM.gov API key.")
            sys.exit(1)
        if resp.status_code == 403:
            print(f"ERROR: API key lacks permission or rate limit exceeded.\n{resp.text}")
            sys.exit(1)
        resp.raise_for_status()

        data    = resp.json()
        records = data.get("opportunitiesData") or []
        total   = data.get("totalRecords", 0)

        all_records.extend(records)
        fetched = (page + 1) * PAGE_SIZE

        print(f"  {org_name} — page {page + 1}: {len(records)} records "
              f"(total: {min(fetched, total)}/{total})")

        if fetched >= total or not records:
            break
        page += 1

    return all_records


def fetch_all_opportunities() -> list:
    """Fetch opportunities for all target orgs and combine."""
    all_opps = []
    for org in TARGET_ORGS:
        print(f"\nFetching: {org}")
        results = fetch_for_org(org)
        all_opps.extend(results)
        print(f"  → {len(results)} records for {org}")
    return all_opps


# ── FIELD EXTRACTION ───────────────────────────────────────────────────────────

def get_contact(opp: dict) -> str:
    """Extract primary contact email from pointOfContact array."""
    contacts = opp.get("pointOfContact") or []
    for c in contacts:
        if c.get("type", "").lower() == "primary" and c.get("email"):
            return c["email"]
    # Fall back to first contact with an email
    for c in contacts:
        if c.get("email"):
            return c["email"]
    return ""


def get_agency(opp: dict) -> str:
    """Extract the most specific org name from fullParentPathName."""
    path = opp.get("fullParentPathName", "")
    if path:
        parts = [p.strip() for p in path.split(".")]
        return parts[-1] if parts else path
    return opp.get("subtier", "") or opp.get("department", "")


def extract_fields(opp: dict) -> dict:
    notice_id = opp.get("noticeId", "")
    return {
        "Notice ID":              notice_id,
        "Title":                  opp.get("title", ""),
        "Solicitation Number":    opp.get("solicitationNumber", ""),
        "Agency":                 get_agency(opp),
        "Department Path":        opp.get("fullParentPathName", ""),
        "Type":                   opp.get("type", ""),
        "Base Type":              opp.get("baseType", ""),
        "Posted Date":            (opp.get("postedDate") or "")[:10],
        "Response Deadline":      opp.get("responseDeadLine") or opp.get("reponseDeadLine", ""),
        "Archive Date":           opp.get("archiveDate", ""),
        "Active":                 opp.get("active", ""),
        "Set Aside":              opp.get("setAside", ""),
        "NAICS Code":             opp.get("naicsCode", ""),
        "Classification Code":    opp.get("classificationCode", ""),
        "Contact":                get_contact(opp),
        "Description URL":        f"https://api.sam.gov/opportunities/v2/search?api_key={SAM_API_KEY}&noticeid={notice_id}" if notice_id else "",
        "UI Link":                opp.get("uiLink", ""),
        "Resource Links":         " | ".join(opp.get("resourceLinks") or []),
        "_notice_id":             notice_id,  # internal dedup key
    }


# ── CSV UPDATE ─────────────────────────────────────────────────────────────────

def load_existing_csv() -> pd.DataFrame:
    if CSV_PATH.exists():
        return pd.read_csv(CSV_PATH, dtype=str)
    return pd.DataFrame()


def append_new_rows(existing: pd.DataFrame, incoming: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    if existing.empty:
        return incoming, len(incoming)
    known_ids = set(existing["_notice_id"].dropna())
    new_rows  = incoming[~incoming["_notice_id"].isin(known_ids)]
    updated   = pd.concat([existing, new_rows], ignore_index=True)
    return updated, len(new_rows)


def save_csv(df: pd.DataFrame):
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.drop(columns=["_notice_id"], errors="ignore").to_csv(CSV_PATH, index=False)


# ── SLACK NOTIFICATION ─────────────────────────────────────────────────────────

def post_slack(new_count: int, total_count: int, by_org: dict, by_type: dict):
    today = datetime.now().strftime("%B %d, %Y")

    if new_count == 0:
        text = f":mag: *SAM.gov Monitor (ARPA-H & DARPA) — {today}*\nNo new opportunities found."
    else:
        org_lines  = "\n".join(f"  • {org}: {count}"  for org, count in sorted(by_org.items()))
        type_lines = "\n".join(f"  • {t}: {count}" for t, count in sorted(by_type.items()))
        text = (
            f":page_facing_up: *SAM.gov Monitor (ARPA-H & DARPA) — {today}*\n"
            f"*{new_count} new opportunit{'y' if new_count == 1 else 'ies'}* added "
            f"({total_count} total in tracker)\n\n"
            f"*By organization:*\n{org_lines}\n\n"
            f"*By notice type:*\n{type_lines}\n\n"
            f":arrow_right: <{CSV_URL}|View full tracker on GitHub>"
        )

    resp = requests.post(SLACK_WEBHOOK, json={"text": text}, timeout=10)
    if resp.status_code != 200:
        print(f"WARNING: Slack notification failed ({resp.status_code}): {resp.text}")
    else:
        print("Slack notification sent.")


# ── MAIN ───────────────────────────────────────────────────────────────────────

def main():
    print(f"Starting SAM.gov monitor — {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Target organizations: {', '.join(TARGET_ORGS)}")
    print(f"Lookback window: {DAYS_LOOKBACK} days")

    raw = fetch_all_opportunities()
    print(f"\nTotal records fetched: {len(raw)}")

    if not raw:
        print("No opportunities found. Notifying Slack.")
        post_slack(0, 0, {}, {})
        return

    incoming_df = pd.DataFrame([extract_fields(o) for o in raw])

    existing_df           = load_existing_csv()
    updated_df, new_count = append_new_rows(existing_df, incoming_df)

    save_csv(updated_df)
    print(f"CSV updated — {new_count} new rows added ({len(updated_df)} total).")

    if new_count > 0:
        new_rows = updated_df.tail(new_count)
        by_org   = new_rows["Agency"].value_counts().to_dict()
        by_type  = new_rows["Type"].value_counts().to_dict()
    else:
        by_org = by_type = {}

    post_slack(new_count, len(updated_df), by_org, by_type)
    print("Done.")


if __name__ == "__main__":
    main()

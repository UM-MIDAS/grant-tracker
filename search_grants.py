"""
Grants.gov Opportunity Monitor
Fetches new federal grant opportunities, appends to a CSV in the repo,
and posts a Slack digest summarizing what's new.

Secrets required (set in GitHub → Settings → Secrets and variables → Actions):
  GRANTS_API_KEY   — Simpler Grants.gov API key
  SLACK_WEBHOOK    — Slack incoming webhook URL
"""

import os
import re
import sys
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── CONFIGURATION ──────────────────────────────────────────────────────────────

API_KEY       = os.environ["GRANTS_API_KEY"]
SLACK_WEBHOOK = os.environ["SLACK_WEBHOOK"]

BASE_URL        = "https://api.simpler.grants.gov"
SEARCH_ENDPOINT = f"{BASE_URL}/v1/opportunities/search"
CSV_PATH        = Path("data/opportunities.csv")

DAYS_LOOKBACK = 14   # API lookback window; deduplication handles overlap
PAGE_SIZE     = 100
MAX_PAGES     = 20

REPO_URL = "https://github.com/" + os.environ.get("GITHUB_REPOSITORY", "your-org/your-repo")
CSV_URL  = f"{REPO_URL}/blob/main/data/opportunities.csv"

AGENCY_CODES = [
    # National Science Foundation
    "NSF",
    # National Institutes of Health
    "NIH", "HHS", "HHS-NIH",
    # Department of Energy
    "DOE", "USDOE",
    # Department of Commerce
    "DOC", "USDOC", "NOAA", "NIST",
    # Department of Transportation
    "DOT", "USDOT", "FHWA", "FRA", "FTA", "FAA", "NHTSA", "MARAD",
    # Department of Defense
    "DOD", "USDOD", "DARPA", "ARMY", "NAVY", "AF", "OSD",
]

# Post-search eligibility filter
# Keeps opportunities open to:
#   06 → public/state institutions of higher education
#   25 → private institutions of higher education
#   99 → unrestricted (no applicant type listed)
ELIGIBLE_APPLICANT_TYPES = [
    "public_and_state_institutions_of_higher_education",
    "private_institutions_of_higher_education",
]

# ── API FETCH ──────────────────────────────────────────────────────────────────

def build_payload(page_offset: int) -> dict:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=DAYS_LOOKBACK)).strftime("%Y-%m-%d")
    return {
        "filters": {
            "opportunity_status": {"one_of": ["posted", "forecasted"]},
            "agency":             {"one_of": AGENCY_CODES},
            "updated_at":         {"start_date": cutoff},
        },
        "pagination": {
            "page_offset": page_offset,
            "page_size":   PAGE_SIZE,
            "sort_order":  [{"order_by": "post_date", "sort_direction": "descending"}],
        },
    }


def fetch_all_opportunities() -> list:
    headers = {"X-API-Key": API_KEY, "Content-Type": "application/json"}
    all_opps, page = [], 1

    while page <= MAX_PAGES:
        resp = requests.post(SEARCH_ENDPOINT, json=build_payload(page), headers=headers, timeout=30)

        if resp.status_code == 401:
            print("ERROR: Invalid API key.")
            sys.exit(1)
        if resp.status_code == 422:
            print(f"ERROR: Bad request (422).\n{resp.text}")
            sys.exit(1)
        resp.raise_for_status()

        data  = resp.json()
        batch = data.get("data", [])
        all_opps.extend(batch)

        total_pages = data.get("pagination_info", {}).get("total_pages", 1)
        print(f"  Page {page}/{total_pages} — {len(batch)} results fetched")

        if page >= total_pages:
            break
        page += 1

    return all_opps


# ── ELIGIBILITY FILTER ─────────────────────────────────────────────────────────

def is_eligible(opp: dict) -> bool:
    types = opp.get("applicant_types") or []
    if not types:
        return True  # unrestricted (99)
    return any(t in ELIGIBLE_APPLICANT_TYPES for t in types)


# ── FIELD EXTRACTION ───────────────────────────────────────────────────────────

def strip_html(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"<[^>]+>", "", text).strip()


def extract_fields(opp: dict) -> dict:
    summary     = opp.get("summary") or {}
    forecasts   = opp.get("forecasts") or {}
    is_forecast = opp.get("opportunity_status", "") == "forecasted"

    al_raw = opp.get("opportunity_assistance_listings") or []
    al_str = " | ".join(
        f"{a.get('assistance_listing_number','')}|{a.get('program_title','')}"
        for a in al_raw
    ) if isinstance(al_raw, list) else str(al_raw)

    fi_raw = summary.get("funding_instruments") or opp.get("funding_instruments") or []
    fi_str = ", ".join(fi_raw) if isinstance(fi_raw, list) else str(fi_raw)

    opp_id = opp.get("opportunity_id", "")

    addl_elig = (summary.get("applicant_eligibility") or {}).get("additional_info_on_eligibility", "")

    return {
        "Opportunity ID":                       opp.get("opportunity_number", ""),
        "Title":                                opp.get("opportunity_title", ""),
        "Post Date":                            summary.get("post_date") or opp.get("post_date", ""),
        "Est. # of Awards":                     summary.get("expected_number_of_awards"),
        "Est. Total Funding":                   summary.get("estimated_total_program_funding"),
        "Award Ceiling":                        summary.get("award_ceiling"),
        "Assistance Listings":                  al_str,
        "Funding Instrument Type":              fi_str,
        "Contact":                              summary.get("agency_email_address", ""),
        "Deadline":                             summary.get("close_date") or opp.get("close_date", ""),
        "Est. NOFO Date":                       (forecasts or {}).get("post_date", ""),
        "Est. Application Deadline":            (forecasts or {}).get("close_date", ""),
        "Last Updated":                         opp.get("updated_at", ""),
        "URL":                                  f"https://simpler.grants.gov/opportunity/{opp_id}" if opp_id else "",
        "Description":                          strip_html(summary.get("summary_description", "")),
        "Agency":                               opp.get("agency_code", ""),
        "Status":                               "Forecast" if is_forecast else "Posted",
        "Additional Information on Eligibility": addl_elig,
        "_opportunity_id":                      opp_id,  # internal dedup key, not shown to users
    }


# ── CSV UPDATE ─────────────────────────────────────────────────────────────────

def load_existing_csv() -> pd.DataFrame:
    if CSV_PATH.exists():
        return pd.read_csv(CSV_PATH, dtype=str)
    return pd.DataFrame()


def append_new_rows(existing: pd.DataFrame, incoming: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Return (updated_df, count_of_new_rows)."""
    if existing.empty:
        return incoming, len(incoming)

    known_ids = set(existing["_opportunity_id"].dropna())
    new_rows  = incoming[~incoming["_opportunity_id"].isin(known_ids)]
    updated   = pd.concat([existing, new_rows], ignore_index=True)
    return updated, len(new_rows)


def save_csv(df: pd.DataFrame):
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Drop internal dedup column before saving
    df.drop(columns=["_opportunity_id"], errors="ignore").to_csv(CSV_PATH, index=False)


# ── SLACK NOTIFICATION ─────────────────────────────────────────────────────────

def post_slack(new_count: int, total_count: int, by_agency: dict):
    today = datetime.now().strftime("%B %d, %Y")

    if new_count == 0:
        text = f":mag: *Grants.gov Monitor — {today}*\nNo new opportunities found matching your filters."
    else:
        agency_lines = "\n".join(
            f"  • {agency}: {count}" for agency, count in sorted(by_agency.items())
        )
        text = (
            f":memo: *Grants.gov Monitor — {today}*\n"
            f"*{new_count} new opportunit{'y' if new_count == 1 else 'ies'}* added "
            f"({total_count} total in tracker)\n\n"
            f"*New opportunities by agency:*\n{agency_lines}\n\n"
            f":arrow_right: <{CSV_URL}|View full tracker on GitHub>"
        )

    resp = requests.post(SLACK_WEBHOOK, json={"text": text}, timeout=10)
    if resp.status_code != 200:
        print(f"WARNING: Slack notification failed ({resp.status_code}): {resp.text}")
    else:
        print("Slack notification sent.")


# ── MAIN ───────────────────────────────────────────────────────────────────────

def main():
    print(f"Starting Grants.gov monitor — {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Fetching opportunities from {len(AGENCY_CODES)} agency codes...")

    raw       = fetch_all_opportunities()
    filtered  = [o for o in raw if is_eligible(o)]
    dropped   = len(raw) - len(filtered)

    print(f"\nFetched: {len(raw)} | After eligibility filter: {len(filtered)} | Dropped: {dropped}")

    if not filtered:
        print("No eligible opportunities found. Notifying Slack.")
        post_slack(0, 0, {})
        return

    incoming_df = pd.DataFrame([extract_fields(o) for o in filtered])

    # Normalise date columns
    for col in ["Post Date", "Deadline", "Est. NOFO Date", "Est. Application Deadline"]:
        incoming_df[col] = pd.to_datetime(incoming_df[col], errors="coerce").dt.strftime("%Y-%m-%d")
    incoming_df["Last Updated"] = pd.to_datetime(
        incoming_df["Last Updated"], errors="coerce", utc=True
    ).dt.strftime("%Y-%m-%d")

    existing_df            = load_existing_csv()
    updated_df, new_count  = append_new_rows(existing_df, incoming_df)

    save_csv(updated_df)
    print(f"CSV updated — {new_count} new rows added ({len(updated_df)} total).")

    # Agency breakdown of new rows only
    if new_count > 0:
        new_rows   = updated_df.tail(new_count)
        by_agency  = new_rows["Agency"].value_counts().to_dict()
    else:
        by_agency = {}

    post_slack(new_count, len(updated_df), by_agency)
    print("Done.")


if __name__ == "__main__":
    main()

"""
USA.gov Active Challenges Monitor
Scrapes the USA.gov active federal challenges page and replaces the CSV
with only the currently listed challenges. Posts a Slack digest on changes.

No API key required.

Secrets required:
  SLACK_WEBHOOK — Slack incoming webhook URL (shared with other monitors)
"""

import os
import sys
import requests
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path
from bs4 import BeautifulSoup

# ── CONFIGURATION ──────────────────────────────────────────────────────────────

SLACK_WEBHOOK = os.environ["SLACK_WEBHOOK"]

SOURCE_URL = "https://www.usa.gov/find-active-challenge"
BASE_URL   = "https://www.usa.gov"
CSV_PATH   = Path("data/usagov_challenges.csv")

REPO_URL = "https://github.com/" + os.environ.get("GITHUB_REPOSITORY", "your-org/your-repo")
CSV_URL  = f"{REPO_URL}/blob/main/data/usagov_challenges.csv"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; FundingMonitor/1.0)"}

# ── SCRAPE ─────────────────────────────────────────────────────────────────────

def scrape_usagov() -> list[dict]:
    resp = requests.get(SOURCE_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    challenges = []

    # Each challenge is an <li> containing an <h2> (title), <p> (description),
    # and an <a> linking to the detail page
    for item in soup.select("main li"):
        title_tag = item.find(["h2", "h3"])
        if not title_tag:
            continue

        title = title_tag.get_text(strip=True)
        if not title:
            continue

        # Description is the <p> text
        desc_tag = item.find("p")
        description = desc_tag.get_text(strip=True) if desc_tag else ""

        # Link — resolve relative paths
        link_tag = item.find("a", href=True)
        if link_tag:
            href = link_tag["href"]
            url = href if href.startswith("http") else f"{BASE_URL}{href}"
        else:
            url = SOURCE_URL

        challenges.append({
            "Title":       title,
            "Description": description,
            "URL":         url,
            "Source":      "USA.gov",
            "Scraped Date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        })

    return challenges


# ── CSV — REPLACE (not append) ─────────────────────────────────────────────────

def load_existing_csv() -> pd.DataFrame:
    if CSV_PATH.exists():
        return pd.read_csv(CSV_PATH, dtype=str)
    return pd.DataFrame()


def compute_changes(existing: pd.DataFrame, incoming: pd.DataFrame) -> tuple[list, list]:
    """Return (new_titles, removed_titles) compared to previous run."""
    if existing.empty:
        return list(incoming["Title"]), []

    old_titles = set(existing["Title"].dropna())
    new_titles = set(incoming["Title"].dropna())

    added   = sorted(new_titles - old_titles)
    removed = sorted(old_titles - new_titles)
    return added, removed


def save_csv(df: pd.DataFrame):
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(CSV_PATH, index=False)


# ── SLACK ──────────────────────────────────────────────────────────────────────

def post_slack(total: int, added: list, removed: list):
    today = datetime.now().strftime("%B %d, %Y")

    if not added and not removed:
        text = (
            f":white_check_mark: *USA.gov Challenges Monitor — {today}*\n"
            f"No changes. {total} active challenge{'s' if total != 1 else ''} currently listed.\n"
            f":arrow_right: <{CSV_URL}|View tracker on GitHub>"
        )
    else:
        lines = [f":trophy: *USA.gov Challenges Monitor — {today}*\n"
                 f"{total} active challenge{'s' if total != 1 else ''} currently listed.\n"]
        if added:
            lines.append(f"*{len(added)} new:*")
            lines += [f"  + {t}" for t in added]
        if removed:
            lines.append(f"\n*{len(removed)} removed/closed:*")
            lines += [f"  - {t}" for t in removed]
        lines.append(f"\n:arrow_right: <{CSV_URL}|View tracker on GitHub>")
        text = "\n".join(lines)

    resp = requests.post(SLACK_WEBHOOK, json={"text": text}, timeout=10)
    if resp.status_code != 200:
        print(f"WARNING: Slack notification failed ({resp.status_code}): {resp.text}")
    else:
        print("Slack notification sent.")


# ── MAIN ───────────────────────────────────────────────────────────────────────

def main():
    print(f"Starting USA.gov challenges monitor — {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Source: {SOURCE_URL}")

    challenges = scrape_usagov()
    print(f"Found {len(challenges)} active challenges on USA.gov")

    if not challenges:
        print("No challenges found — page structure may have changed. Check the source URL.")
        sys.exit(1)

    incoming_df = pd.DataFrame(challenges)
    existing_df = load_existing_csv()

    added, removed = compute_changes(existing_df, incoming_df)

    # Replace CSV with current open challenges only
    save_csv(incoming_df)
    print(f"CSV replaced with {len(incoming_df)} current challenges.")
    if added:
        print(f"  New:     {added}")
    if removed:
        print(f"  Removed: {removed}")

    post_slack(len(incoming_df), added, removed)
    print("Done.")


if __name__ == "__main__":
    main()

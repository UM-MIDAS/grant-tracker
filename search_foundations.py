"""
Foundations Monitor — Simons Foundation, Alfred P. Sloan Foundation, Schmidt Sciences
Scrapes open funding opportunities from each foundation's public listings page
and replaces the CSV with currently open items. Posts Slack alerts on changes.

No API key required.

Secrets required:
  SLACK_WEBHOOK — Slack incoming webhook URL (shared with other monitors)
"""

import os
import re
import requests
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path
from bs4 import BeautifulSoup

# ── CONFIGURATION ──────────────────────────────────────────────────────────────

SLACK_WEBHOOK = os.environ["SLACK_WEBHOOK"]
CSV_PATH      = Path("data/foundations.csv")

REPO_URL = "https://github.com/" + os.environ.get("GITHUB_REPOSITORY", "your-org/your-repo")
CSV_URL  = f"{REPO_URL}/blob/main/data/foundations.csv"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; FundingMonitor/1.0)"}

SIMONS_URL = "https://www.simonsfoundation.org/funding-opportunities/"
SLOAN_URL  = "https://sloan.org/grants/open-calls"
SCHMIDT_URL = "https://www.schmidtsciences.org/opportunities/"

# ── SIMONS FOUNDATION ──────────────────────────────────────────────────────────

def scrape_simons() -> list[dict]:
    records = []
    today   = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    try:
        resp = requests.get(SIMONS_URL, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Each opportunity is an <h4> or <h3> anchor followed by description
        # and a Status line. We only keep items where Status = Open.
        for item in soup.find_all(["h3", "h4"]):
            # Get the link and title
            link_tag = item.find("a", href=True)
            if not link_tag:
                continue
            title = item.get_text(strip=True)
            if not title or len(title) < 5:
                continue

            href = link_tag["href"]
            url  = href if href.startswith("http") else f"https://www.simonsfoundation.org{href}"

            # Look for status in surrounding text
            parent_text = ""
            for sib in item.find_next_siblings():
                parent_text += " " + sib.get_text(" ", strip=True)
                if len(parent_text) > 400:
                    break

            # Only keep open opportunities
            if "Status - Open" not in parent_text and "Status -  Open" not in parent_text:
                continue

            # Extract deadline
            deadline = ""
            m = re.search(r"(?:Application [Dd]eadline|deadline)[:\s]*([A-Z][a-z]+ \d{1,2},?\s*\d{4})", parent_text)
            if m:
                deadline = m.group(1).strip()

            # Extract program area
            program = ""
            m2 = re.search(r"Program Area[:\s-]*([\w\s&|,]+?)(?:Career Stage|Status)", parent_text)
            if m2:
                program = m2.group(1).strip(" |·-")

            # Extract career stage
            career = ""
            m3 = re.search(r"Career Stage[:\s-]*([\w\s/,]+?)(?:Status|$)", parent_text)
            if m3:
                career = m3.group(1).strip()

            records.append({
                "Title":        title,
                "Funder":       "Simons Foundation",
                "Program Area": program,
                "Career Stage": career,
                "Description":  "",
                "Deadline":     deadline,
                "URL":          url,
                "Scraped Date": today,
            })

    except Exception as e:
        print(f"  WARNING: Simons scrape failed: {e}")

    return records


# ── ALFRED P. SLOAN FOUNDATION ─────────────────────────────────────────────────

def scrape_sloan() -> list[dict]:
    records = []
    today   = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    try:
        resp = requests.get(SLOAN_URL, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Each open call is a block with a title link and a Summary paragraph
        for item in soup.find_all(["h2", "h3", "h4"]):
            link_tag = item.find("a", href=True)
            if not link_tag:
                continue
            title = item.get_text(strip=True)
            if not title or len(title) < 5:
                continue

            href = link_tag["href"]
            url  = href if href.startswith("http") else f"https://sloan.org{href}"

            # Get the summary from next sibling paragraph
            desc = ""
            for sib in item.find_next_siblings():
                t = sib.get_text(strip=True)
                if t and len(t) > 20:
                    desc = t[:300]
                    break

            # Extract deadline
            deadline = ""
            m = re.search(r"(?:[Dd]eadline|[Dd]ue)[:\s]*([A-Z][a-z]+ \d{1,2},?\s*\d{4})", desc)
            if m:
                deadline = m.group(1).strip()

            records.append({
                "Title":        title,
                "Funder":       "Sloan Foundation",
                "Program Area": "",
                "Career Stage": "",
                "Description":  desc,
                "Deadline":     deadline,
                "URL":          url,
                "Scraped Date": today,
            })

    except Exception as e:
        print(f"  WARNING: Sloan scrape failed: {e}")

    return records


# ── SCHMIDT SCIENCES ───────────────────────────────────────────────────────────

def scrape_schmidt() -> list[dict]:
    records = []
    today   = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    try:
        resp = requests.get(SCHMIDT_URL, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Each opportunity <li> contains an <a> with text "Apply" — unique marker
        for li in soup.select("li"):
            apply_tag = li.find("a", string=lambda t: t and t.strip().lower() == "apply")
            if not apply_tag:
                continue

            title_tag = li.find(["h3", "h2"])
            if not title_tag:
                continue
            title = title_tag.get_text(strip=True)
            if not title:
                continue

            # Program area — text node directly after the title
            program = ""
            for sib in title_tag.find_next_siblings():
                t = sib.get_text(strip=True)
                if t and t.lower() != "apply" and len(t) < 120:
                    program = t
                    break

            apply_url = apply_tag.get("href", SCHMIDT_URL)

            records.append({
                "Title":        title,
                "Funder":       "Schmidt Sciences",
                "Program Area": program,
                "Career Stage": "",
                "Description":  program or "See apply link for full details.",
                "Deadline":     "",
                "URL":          SCHMIDT_URL,
                "Scraped Date": today,
            })

    except Exception as e:
        print(f"  WARNING: Schmidt Sciences scrape failed: {e}")

    return records


# ── CSV — REPLACE (not append) ─────────────────────────────────────────────────

def load_existing_csv() -> pd.DataFrame:
    if CSV_PATH.exists():
        return pd.read_csv(CSV_PATH, dtype=str)
    return pd.DataFrame()


def compute_changes(existing: pd.DataFrame, incoming: pd.DataFrame) -> tuple[list, list]:
    if existing.empty:
        return list(incoming["Title"].unique()), []
    old = set(existing["Title"].dropna())
    new = set(incoming["Title"].dropna())
    return sorted(new - old), sorted(old - new)


def save_csv(df: pd.DataFrame):
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(CSV_PATH, index=False)


# ── SLACK ──────────────────────────────────────────────────────────────────────

def post_slack(total: int, added: list, removed: list, by_funder: dict):
    today = datetime.now().strftime("%B %d, %Y")

    if not added and not removed:
        text = (
            f":white_check_mark: *Foundations Monitor — {today}*\n"
            f"No changes. {total} open opportunit{'y' if total == 1 else 'ies'} currently tracked.\n"
            f":arrow_right: <{CSV_URL}|View tracker on GitHub>"
        )
    else:
        funder_lines = "\n".join(f"  • {f}: {c}" for f, c in sorted(by_funder.items()))
        lines = [
            f":classical_building: *Foundations Monitor — {today}*\n"
            f"{total} open opportunit{'y' if total == 1 else 'ies'} currently tracked.\n",
            f"*By funder:*\n{funder_lines}\n",
        ]
        if added:
            lines.append(f"*{len(added)} new:*")
            lines += [f"  + {t}" for t in added[:10]]
        if removed:
            lines.append(f"\n*{len(removed)} closed/removed:*")
            lines += [f"  - {t}" for t in removed[:10]]
        lines.append(f"\n:arrow_right: <{CSV_URL}|View tracker on GitHub>")
        text = "\n".join(lines)

    resp = requests.post(SLACK_WEBHOOK, json={"text": text}, timeout=10)
    if resp.status_code != 200:
        print(f"WARNING: Slack failed ({resp.status_code}): {resp.text}")
    else:
        print("Slack notification sent.")


# ── MAIN ───────────────────────────────────────────────────────────────────────

def main():
    print(f"Starting foundations monitor — {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")

    all_records = []

    print("\nScraping Simons Foundation...")
    simons = scrape_simons()
    all_records.extend(simons)
    print(f"  → {len(simons)} open opportunities")

    print("\nScraping Alfred P. Sloan Foundation...")
    sloan = scrape_sloan()
    all_records.extend(sloan)
    print(f"  → {len(sloan)} open calls")

    print("\nScraping Schmidt Sciences...")
    schmidt = scrape_schmidt()
    all_records.extend(schmidt)
    print(f"  → {len(schmidt)} open opportunities")

    print(f"\nTotal: {len(all_records)} opportunities across all foundations")

    incoming_df = pd.DataFrame(all_records) if all_records else pd.DataFrame(
        columns=["Title", "Funder", "Program Area", "Career Stage",
                 "Description", "Deadline", "URL", "Scraped Date"]
    )

    existing_df          = load_existing_csv()
    added, removed       = compute_changes(existing_df, incoming_df)
    by_funder            = incoming_df["Funder"].value_counts().to_dict() if not incoming_df.empty else {}

    save_csv(incoming_df)
    print(f"CSV replaced with {len(incoming_df)} current opportunities.")

    post_slack(len(incoming_df), added, removed, by_funder)
    print("Done.")


if __name__ == "__main__":
    main()

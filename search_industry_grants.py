"""
Amazon Research Awards & NVIDIA Academic Grants Monitor
Scrapes open call-for-proposal pages for Amazon and NVIDIA and replaces the CSV
with currently open opportunities. Posts Slack alerts on changes.

Note: Schmidt Sciences has moved to search_foundations.py

No API key required.

Secrets required:
  SLACK_WEBHOOK — Slack incoming webhook URL (shared with other monitors)

Strategy:
  Amazon: Fetches the latest-news announcement page (static HTML) to detect
          the current active cycle and its deadline, then lists open tracks.
  NVIDIA:  Fetches the Academic Grant Program and Graduate Fellowship pages
          (static HTML) to confirm open status and extract deadlines.
"""

import os
import re
import sys
import requests
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path
from bs4 import BeautifulSoup

# ── CONFIGURATION ──────────────────────────────────────────────────────────────

SLACK_WEBHOOK = os.environ["SLACK_WEBHOOK"]
CSV_PATH      = Path("data/industry_grants.csv")

REPO_URL = "https://github.com/" + os.environ.get("GITHUB_REPOSITORY", "your-org/your-repo")
CSV_URL  = f"{REPO_URL}/blob/main/data/industry_grants.csv"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; FundingMonitor/1.0)"}

# Amazon: the program-updates news page lists CFP announcements as static HTML
AMAZON_NEWS_URL = "https://www.amazon.science/research-awards/program-updates"
AMAZON_BASE     = "https://www.amazon.science"
AMAZON_CFP_URL  = "https://www.amazon.science/research-awards/call-for-proposals"

# NVIDIA program pages
NVIDIA_GRANT_URL    = "https://www.nvidia.com/en-us/industries/higher-education-research/academic-grant-program/"
NVIDIA_FELLOW_URL   = "https://research.nvidia.com/graduate-fellowships"


# ── AMAZON SCRAPE ──────────────────────────────────────────────────────────────

def scrape_amazon() -> list[dict]:
    """
    Fetches the Amazon Research Awards news page to find the most recent
    call-for-proposals announcement, then visits that page to extract
    the deadline and research areas.
    """
    records = []

    try:
        resp = requests.get(AMAZON_NEWS_URL, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Find links to CFP announcement articles
        cfp_links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True).lower()
            if ("call-for-proposals" in href or "call for proposals" in text) and "program-updates" in href:
                full_url = href if href.startswith("http") else f"{AMAZON_BASE}{href}"
                title = a.get_text(strip=True)
                if title and full_url not in [r.get("URL") for r in cfp_links]:
                    cfp_links.append({"url": full_url, "title": title})

        # Visit the most recent one (first in list)
        if cfp_links:
            latest = cfp_links[0]
            detail = requests.get(latest["url"], headers=HEADERS, timeout=30)
            detail.raise_for_status()
            dsoup = BeautifulSoup(detail.text, "html.parser")
            body  = dsoup.get_text(" ", strip=True)

            # Extract deadline
            deadline = ""
            for pattern in [
                r"deadline[^\d]*(\w+ \d{1,2},? \d{4})",
                r"submissions? (?:close|due|by)[^\d]*(\w+ \d{1,2},? \d{4})",
                r"(\w+ \d{1,2},? \d{4})\s*at\s*11:59",
            ]:
                m = re.search(pattern, body, re.IGNORECASE)
                if m:
                    deadline = m.group(1).strip()
                    break

            # Extract research areas (bullet-pointed list items that look like track names)
            areas = []
            for li in dsoup.find_all("li"):
                t = li.get_text(strip=True)
                if 10 < len(t) < 120 and not any(skip in t.lower() for skip in ["amazon", "submit", "review", "deadline", "award", "recipient"]):
                    areas.append(t)

            if areas:
                for area in areas[:15]:  # cap at 15 tracks
                    records.append({
                        "Title":        f"Amazon Research Awards — {area}",
                        "Program":      "Amazon Research Awards",
                        "Funder":       "Amazon",
                        "Description":  area,
                        "Deadline":     deadline,
                        "URL":          latest["url"],
                        "Apply URL":    AMAZON_CFP_URL,
                        "Scraped Date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    })
            else:
                # Fallback: one record for the whole announcement
                records.append({
                    "Title":        latest["title"] or "Amazon Research Awards — Open Call",
                    "Program":      "Amazon Research Awards",
                    "Funder":       "Amazon",
                    "Description":  "See link for open research tracks and submission details.",
                    "Deadline":     deadline,
                    "URL":          latest["url"],
                    "Apply URL":    AMAZON_CFP_URL,
                    "Scraped Date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                })

        else:
            # Fallback if news page structure has changed
            print("  WARNING: No Amazon CFP links found on news page — using static entry.")
            records.append({
                "Title":        "Amazon Research Awards — Check for Open Calls",
                "Program":      "Amazon Research Awards",
                "Funder":       "Amazon",
                "Description":  "Visit the call-for-proposals page to check for open research tracks.",
                "Deadline":     "",
                "URL":          AMAZON_CFP_URL,
                "Apply URL":    AMAZON_CFP_URL,
                "Scraped Date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            })

    except Exception as e:
        print(f"  WARNING: Amazon scrape failed: {e}")

    return records




# ── NVIDIA SCRAPE ──────────────────────────────────────────────────────────────

def scrape_nvidia() -> list[dict]:
    records = []
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Academic Grant Program — rolling open submissions
    try:
        resp = requests.get(NVIDIA_GRANT_URL, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        body = soup.get_text(" ", strip=True)

        # Check if page signals open status
        is_open = any(kw in body.lower() for kw in [
            "now accepting", "submit your", "open for", "accepting proposals",
            "apply now", "call for proposals"
        ])

        deadline = ""
        for pattern in [r"deadline[^\d]*(\w+ \d{1,2},? \d{4})", r"due[^\d]*(\w+ \d{1,2},? \d{4})"]:
            m = re.search(pattern, body, re.IGNORECASE)
            if m:
                deadline = m.group(1).strip()
                break

        if is_open:
            records.append({
                "Title":        "NVIDIA Academic Grant Program",
                "Program":      "NVIDIA Academic Grant Program",
                "Funder":       "NVIDIA",
                "Description":  "Hardware grants (GPUs) for faculty at accredited institutions. Focus areas include generative AI, simulation and modeling, data science, and robotics.",
                "Deadline":     deadline or "Rolling",
                "URL":          NVIDIA_GRANT_URL,
                "Apply URL":    "https://academicgrants.nvidia.com/academicgrantprogram/s/Application",
                "Scraped Date": today,
            })
            print(f"  NVIDIA Academic Grant Program: open")
        else:
            print(f"  NVIDIA Academic Grant Program: not currently open (or page changed)")

    except Exception as e:
        print(f"  WARNING: NVIDIA Academic Grant scrape failed: {e}")

    # Graduate Fellowship — annual cycle, opens ~August
    try:
        resp = requests.get(NVIDIA_FELLOW_URL, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        body = soup.get_text(" ", strip=True)

        is_open = any(kw in body.lower() for kw in [
            "now open", "now accepting", "applications open", "submit your application",
            "application deadline", "apply now"
        ])
        is_closed = "submissions are now closed" in body.lower() or "closed" in body.lower()

        deadline = ""
        for pattern in [
            r"(?:deadline|applications? due)[^\d]*(\w+ \d{1,2},? \d{4})",
            r"(\w+ \d{1,2},? \d{4})\s*at\s*(?:3pm|noon|12)",
        ]:
            m = re.search(pattern, body, re.IGNORECASE)
            if m:
                deadline = m.group(1).strip()
                break

        # Extract academic year reference
        year_match = re.search(r"(\d{4}[-–]\d{4})\s*academic year", body, re.IGNORECASE)
        year_label = f" ({year_match.group(1)})" if year_match else ""

        if is_open and not is_closed:
            records.append({
                "Title":        f"NVIDIA Graduate Fellowship Program{year_label}",
                "Program":      "NVIDIA Graduate Fellowship",
                "Funder":       "NVIDIA",
                "Description":  "Up to $60,000 for PhD students researching accelerated computing, AI, robotics, or autonomous vehicles. Includes summer internship.",
                "Deadline":     deadline or "See program page",
                "URL":          NVIDIA_FELLOW_URL,
                "Apply URL":    NVIDIA_FELLOW_URL,
                "Scraped Date": today,
            })
            print(f"  NVIDIA Graduate Fellowship: open{year_label}")
        else:
            print(f"  NVIDIA Graduate Fellowship: not currently open")

    except Exception as e:
        print(f"  WARNING: NVIDIA Fellowship scrape failed: {e}")

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
            f":white_check_mark: *Industry Grants Monitor — {today}*\n"
            f"No changes. {total} open opportunit{'y' if total == 1 else 'ies'} currently tracked.\n"
            f":arrow_right: <{CSV_URL}|View tracker on GitHub>"
        )
    else:
        lines = [
            f":briefcase: *Industry Grants Monitor (Amazon & NVIDIA) — {today}*\n"
            f"{total} open opportunit{'y' if total == 1 else 'ies'} currently tracked.\n"
        ]
        funder_lines = "\n".join(f"  • {f}: {c}" for f, c in sorted(by_funder.items()))
        if funder_lines:
            lines.append(f"*By funder:*\n{funder_lines}\n")
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
    print(f"Starting industry grants monitor — {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")

    all_records = []


    print("\nScraping Amazon Research Awards...")
    amazon = scrape_amazon()
    all_records.extend(amazon)
    print(f"  → {len(amazon)} Amazon records")

    print("\nScraping NVIDIA programs...")
    nvidia = scrape_nvidia()
    all_records.extend(nvidia)
    print(f"  → {len(nvidia)} NVIDIA records")

    print(f"\nTotal open opportunities: {len(all_records)}")

    if not all_records:
        print("No open opportunities found. Notifying Slack.")
        post_slack(0, [], [], {})
        return

    incoming_df = pd.DataFrame(all_records)
    existing_df = load_existing_csv()

    added, removed = compute_changes(existing_df, incoming_df)
    by_funder = incoming_df["Funder"].value_counts().to_dict()

    save_csv(incoming_df)
    print(f"CSV replaced with {len(incoming_df)} current opportunities.")

    post_slack(len(incoming_df), added, removed, by_funder)
    print("Done.")


if __name__ == "__main__":
    main()

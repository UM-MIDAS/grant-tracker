"""
NIH Challenges and Prize Competitions Monitor
Scrapes the NIH challenges page and replaces the CSV with only currently
open challenges. Posts a Slack digest showing what's new or closed.

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

SOURCE_URL = "https://www.nih.gov/challenges"
BASE_URL   = "https://www.nih.gov"
CSV_PATH   = Path("data/nih_challenges.csv")

REPO_URL = "https://github.com/" + os.environ.get("GITHUB_REPOSITORY", "your-org/your-repo")
CSV_URL  = f"{REPO_URL}/blob/main/data/nih_challenges.csv"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; FundingMonitor/1.0)"}

# ── SCRAPE ─────────────────────────────────────────────────────────────────────

def scrape_nih_challenges() -> list[dict]:
    resp = requests.get(SOURCE_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    challenges = []

    # The NIH page has an "Open Challenges" heading followed by challenge cards.
    # We stop when we hit "Closed Challenges".
    in_open_section = False

    for element in soup.find_all(["h2", "h3", "li", "article", "div"]):
        text = element.get_text(strip=True)

        # Detect section boundaries
        if element.name in ("h2", "h3"):
            if "Open Challenges" in text:
                in_open_section = True
                continue
            elif "Closed Challenges" in text:
                break  # stop — everything after here is closed

        if not in_open_section:
            continue

        # Each challenge card has a title link and descriptive text.
        # Look for <li> elements containing an <a> with a challenge link.
        if element.name == "li":
            title_tag = element.find(["h3", "h2", "strong", "a"])
            if not title_tag:
                continue

            title = title_tag.get_text(strip=True)
            if not title or len(title) < 5:
                continue

            # Get the link
            link_tag = element.find("a", href=True)
            if link_tag:
                href = link_tag["href"]
                url = href if href.startswith("http") else f"{BASE_URL}{href}"
            else:
                url = SOURCE_URL

            # Description — all text paragraphs in the card
            paragraphs = element.find_all("p")
            description = " ".join(p.get_text(strip=True) for p in paragraphs)

            # Deadline — look for text containing "open until" or date patterns
            deadline = ""
            full_text = element.get_text(" ", strip=True)
            lower = full_text.lower()
            for keyword in ["open until", "closes", "deadline", "phase", "coming soon"]:
                idx = lower.find(keyword)
                if idx != -1:
                    deadline = full_text[idx:idx + 60].strip()
                    break

            challenges.append({
                "Title":        title,
                "Description":  description,
                "Deadline":     deadline,
                "URL":          url,
                "Source":       "NIH",
                "Scraped Date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            })

    # Fallback: if section detection failed, try finding challenge cards directly
    if not challenges:
        print("  Section detection fallback: scanning all challenge links...")
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "/challenges/" in href and href != "/challenges":
                title = link.get_text(strip=True)
                if title and len(title) > 5:
                    url = href if href.startswith("http") else f"{BASE_URL}{href}"
                    challenges.append({
                        "Title":        title,
                        "Description":  "",
                        "Deadline":     "",
                        "URL":          url,
                        "Source":       "NIH",
                        "Scraped Date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    })

    # Deduplicate by URL
    seen, unique = set(), []
    for c in challenges:
        if c["URL"] not in seen:
            seen.add(c["URL"])
            unique.append(c)

    return unique


# ── CSV — REPLACE (not append) ─────────────────────────────────────────────────

def load_existing_csv() -> pd.DataFrame:
    if CSV_PATH.exists():
        return pd.read_csv(CSV_PATH, dtype=str)
    return pd.DataFrame()


def compute_changes(existing: pd.DataFrame, incoming: pd.DataFrame) -> tuple[list, list]:
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
            f":white_check_mark: *NIH Challenges Monitor — {today}*\n"
            f"No changes. {total} open challenge{'s' if total != 1 else ''} currently listed.\n"
            f":arrow_right: <{CSV_URL}|View tracker on GitHub>"
        )
    else:
        lines = [f":microscope: *NIH Challenges Monitor — {today}*\n"
                 f"{total} open challenge{'s' if total != 1 else ''} currently listed.\n"]
        if added:
            lines.append(f"*{len(added)} new:*")
            lines += [f"  + {t}" for t in added]
        if removed:
            lines.append(f"\n*{len(removed)} closed/removed:*")
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
    print(f"Starting NIH challenges monitor — {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Source: {SOURCE_URL}")

    challenges = scrape_nih_challenges()
    print(f"Found {len(challenges)} open challenges on NIH")

    if not challenges:
        print("No challenges found — page structure may have changed. Check the source URL.")
        sys.exit(1)

    incoming_df = pd.DataFrame(challenges)
    existing_df = load_existing_csv()

    added, removed = compute_changes(existing_df, incoming_df)

    # Replace CSV with current open challenges only
    save_csv(incoming_df)
    print(f"CSV replaced with {len(incoming_df)} currently open challenges.")
    if added:
        print(f"  New:    {added}")
    if removed:
        print(f"  Closed: {removed}")

    post_slack(len(incoming_df), added, removed)
    print("Done.")


if __name__ == "__main__":
    main()

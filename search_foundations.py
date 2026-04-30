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

SIMONS_URL  = "https://www.simonsfoundation.org/funding-opportunities/"
SLOAN_URL   = "https://sloan.org/grants/open-calls"
SCHMIDT_URL = "https://www.schmidtsciences.org/opportunities/"

# ── SIMONS FOUNDATION ──────────────────────────────────────────────────────────

def scrape_simons() -> list[dict]:
    """
    Page structure:
      <h4><a href="/grant/pivot-fellowship/">Pivot Fellowship</a></h4>
      <p>Program Area: ...</p>
      <p>Career Stage - ...</p>
      <p>Status - Open Application deadline: 12 p.m. ET May 14, 2026</p>

    Status and deadline may be inside a sibling <div>, so we use the
    parent container's full text rather than direct sibling traversal.
    """
    records = []
    today   = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    try:
        resp = requests.get(SIMONS_URL, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        print(f"  Simons HTTP {resp.status_code}, content length {len(resp.text)}")
        print(f"  'Status - Open' found: {'Status - Open' in resp.text}")
        h4_count = resp.text.count('<h4')
        print(f"  h4 tags in raw HTML: {h4_count}")
        soup = BeautifulSoup(resp.text, "html.parser")
        all_h4 = soup.find_all(["h3", "h4"])
        print(f"  h3/h4 tags parsed: {len(all_h4)}")

        for item in soup.find_all(["h3", "h4"]):
            link_tag = item.find("a", href=True)
            if not link_tag:
                continue
            title = item.get_text(strip=True)
            if not title or len(title) < 5:
                continue

            href = link_tag["href"]
            url  = href if href.startswith("http") else f"https://www.simonsfoundation.org{href}"

            # Walk up to a parent container that holds the full opportunity block
            parent = item.find_parent()
            parent_text = parent.get_text(" ", strip=True) if parent else ""
            if len(parent_text) < 30:
                grandparent = parent.find_parent() if parent else None
                if grandparent:
                    parent_text = grandparent.get_text(" ", strip=True)

            # Only keep open opportunities
            if "Status - Open" not in parent_text:
                continue

            # Deadline — handle "12 p.m. ET May 14, 2026" format
            deadline = ""
            m = re.search(
                r"(?:Application [Dd]eadline|[Dd]eadline)[:\s]*"
                r"(?:\d{1,2}\s*[ap]\.m\.\s*ET\s*)?"
                r"([A-Z][a-z]+ \d{1,2},?\s*\d{4})",
                parent_text
            )
            if m:
                deadline = m.group(1).strip()

            # Program area
            program = ""
            m2 = re.search(r"Program Area[:\s-]*([\w\s&|,]+?)(?:Career Stage|Status)", parent_text)
            if m2:
                program = m2.group(1).strip(" |·-")

            # Career stage
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
    """
    Page structure (open-calls page lists ONLY open calls, no filtering needed):

      <h2>Economic Research on the Returns to R&D Investment</h2>
      <p><strong>Call for:</strong>Letters of Inquiry</p>
      <p><strong>Deadline:</strong>April 30, 2026</p>
      <p><strong>Summary</strong>: Grants available for...</p>
      <p><strong>Link:</strong><a href="https://sloan.org/...">...</a></p>

    Each open call is an <h2> with <strong>-labelled <p> siblings.
    Nav headings like "Open Calls" and "Grants" are skipped.
    """
    records = []
    today   = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    try:
        resp = requests.get(SLOAN_URL, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        print(f"  Sloan HTTP {resp.status_code}, content length {len(resp.text)}")
        print(f"  'Deadline' found: {'Deadline' in resp.text}")
        h2_count = resp.text.count('<h2')
        print(f"  h2 tags in raw HTML: {h2_count}")
        soup = BeautifulSoup(resp.text, "html.parser")
        all_h2 = soup.find_all("h2")
        print(f"  h2 tags parsed: {len(all_h2)}")
        for h in all_h2[:5]:
            print(f"    h2: {repr(h.get_text(strip=True)[:60])}")

        NAV_HEADINGS = {"Open Calls", "Grants", "Programs", "About", "Impact",
                        "Sloan Research Fellowships", "Apply", "For Grantees",
                        "Contact", "Grants Database"}

        for h2 in soup.find_all("h2"):
            title = h2.get_text(strip=True)
            if not title or len(title) < 5 or title in NAV_HEADINGS:
                continue

            # Parse <strong>-labelled fields from following siblings
            fields = {}
            for sib in h2.find_next_siblings():
                if sib.name == "h2":
                    break
                for strong in sib.find_all("strong"):
                    label = strong.get_text(strip=True).rstrip(":")
                    # Value is the text/element immediately after the <strong>
                    val_node = strong.next_sibling
                    if val_node:
                        if hasattr(val_node, "get_text"):
                            val = val_node.get_text(strip=True).lstrip(": ")
                        else:
                            val = str(val_node).strip().lstrip(": ")
                        if val:
                            fields[label] = val
                # Grab the href from any link sibling
                link_tag = sib.find("a", href=True)
                if link_tag:
                    href = link_tag["href"]
                    fields["Link_url"] = href if href.startswith("http") else f"https://sloan.org{href}"

            # Must have Deadline or Summary to be a real open call entry
            if not fields.get("Deadline") and not fields.get("Summary"):
                continue

            url = fields.get("Link_url", fields.get("Link", SLOAN_URL))

            records.append({
                "Title":        title,
                "Funder":       "Sloan Foundation",
                "Program Area": fields.get("Call for", ""),
                "Career Stage": "",
                "Description":  fields.get("Summary", "")[:300],
                "Deadline":     fields.get("Deadline", ""),
                "URL":          url,
                "Scraped Date": today,
            })

    except Exception as e:
        print(f"  WARNING: Sloan scrape failed: {e}")

    return records


# ── SCHMIDT SCIENCES ───────────────────────────────────────────────────────────

def scrape_schmidt() -> list[dict]:
    """
    Page structure:
      <li>
        <h3>VIEW-2 Call for EOIs</h3>
        Virtual Institute for Earth's Water (VIEW)
        <a href="https://airtable.com/...">Apply</a>
      </li>

    Each opportunity is an <li> with an <h3> title, a plain-text subtitle,
    and an Apply link. The Apply link text may be inside an <a> tag.
    """
    records = []
    today   = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    try:
        resp = requests.get(SCHMIDT_URL, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for li in soup.select("li"):
            h3 = li.find("h3")
            if not h3:
                continue
            title = h3.get_text(strip=True)
            if not title or len(title) < 5:
                continue

            # Program area is the text node directly after the h3
            program = ""
            for content in h3.next_siblings:
                if hasattr(content, "get_text"):
                    t = content.get_text(strip=True)
                else:
                    t = str(content).strip()
                if t and t.lower() != "apply" and len(t) < 120:
                    program = t
                    break

            # Apply link
            apply_tag = li.find("a", href=True)
            apply_url = apply_tag["href"] if apply_tag else SCHMIDT_URL

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

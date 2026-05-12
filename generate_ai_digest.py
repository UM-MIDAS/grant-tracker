"""
AI & Data Science Funding Digest Generator
Reads all CSV files in the data/ folder, filters for opportunities mentioning
AI, artificial intelligence, or data science, and generates a self-contained
HTML page committed to the repo and served via GitHub Pages.

No API key required.

Secrets required:
  SLACK_WEBHOOK — Slack incoming webhook URL (optional notification on publish)
"""

import os
import re
import pandas as pd
from datetime import datetime
from pathlib import Path

SLACK_WEBHOOK = os.environ.get("SLACK_WEBHOOK", "")
REPO_URL      = "https://github.com/" + os.environ.get("GITHUB_REPOSITORY", "your-org/your-repo")
PAGES_URL     = "https://" + os.environ.get("GITHUB_REPOSITORY", "your-org/your-repo").replace("/", ".github.io/", 1)
OUTPUT_PATH   = Path("docs/ai-digest.html")

# ── SEARCH TERMS ───────────────────────────────────────────────────────────────

SEARCH_TERMS = [
    r"\bai\b",
    r"artificial intelligence",
    r"data science",
    r"machine learning",
    r"deep learning",
    r"large language model",
    r"\bllm\b",
    r"natural language processing",
    r"\bnlp\b",
    r"computer vision",
    r"neural network",
]

SEARCH_PATTERN = re.compile(
    "|".join(SEARCH_TERMS),
    re.IGNORECASE
)

# ── CSV SOURCES ────────────────────────────────────────────────────────────────

# Each entry: (csv_path, source_label, title_col, desc_col, url_col, deadline_col, agency_col)
SOURCES = [
    (
        "data/opportunities.csv",
        "Grants.gov",
        "Title", "Description", "URL", "Deadline", "Agency"
    ),
    (
        "data/sam_opportunities.csv",
        "SAM.gov",
        "Title", None, "UI Link", "Response Deadline", "Agency"
    ),
    (
        "data/federal_register.csv",
        "Federal Register",
        "Title", "Abstract", "HTML URL", "Response Deadline", "Agency"
    ),
    (
        "data/nih_challenges.csv",
        "NIH Challenges",
        "Title", "Description", "URL", "Deadline", None
    ),
    (
        "data/usagov_challenges.csv",
        "USA.gov Challenges",
        "Title", "Description", "URL", None, None
    ),
    (
        "data/industry_grants.csv",
        "Industry",
        "Title", "Description", "URL", "Deadline", "Funder"
    ),
    (
        "data/foundations.csv",
        "Foundations",
        "Title", "Description", "URL", "Deadline", "Funder"
    ),
]

# ── LOAD AND FILTER ────────────────────────────────────────────────────────────

def load_and_filter() -> list[dict]:
    results = []

    for csv_path, source, title_col, desc_col, url_col, deadline_col, agency_col in SOURCES:
        path = Path(csv_path)
        if not path.exists():
            print(f"  Skipping {csv_path} — file not found")
            continue

        df = pd.read_csv(path, dtype=str).fillna("")
        print(f"  {source}: {len(df)} rows loaded")

        for _, row in df.iterrows():
            title = row.get(title_col, "") if title_col else ""
            desc  = row.get(desc_col, "")  if desc_col  else ""
            search_text = f"{title} {desc}"

            if not SEARCH_PATTERN.search(search_text):
                continue

            results.append({
                "source":   source,
                "title":    title,
                "desc":     desc[:400] + ("…" if len(desc) > 400 else ""),
                "url":      row.get(url_col, "")      if url_col      else "",
                "deadline": row.get(deadline_col, "") if deadline_col else "",
                "agency":   row.get(agency_col, "")   if agency_col   else "",
            })

    print(f"\nTotal matching opportunities: {len(results)}")
    return results


# ── HTML GENERATION ───────────────────────────────────────────────────────────

def highlight(text: str) -> str:
    """Wrap matched terms in a highlight span."""
    return SEARCH_PATTERN.sub(
        lambda m: f'<mark>{m.group(0)}</mark>',
        text
    )


def source_color(source: str) -> str:
    colors = {
        "Grants.gov":         "#2563eb",
        "SAM.gov":            "#7c3aed",
        "Federal Register":   "#0891b2",
        "NIH Challenges":     "#059669",
        "USA.gov Challenges": "#d97706",
        "Industry":           "#dc2626",
        "Foundations":        "#9333ea",
    }
    return colors.get(source, "#6b7280")


def generate_html(results: list[dict]) -> str:
    updated = datetime.now().strftime("%B %d, %Y at %I:%M %p UTC")
    count   = len(results)

    # Group by source for the filter buttons
    sources = sorted(set(r["source"] for r in results))

    # Build cards HTML
    cards_html = ""
    for r in results:
        color    = source_color(r["source"])
        deadline = f'<span class="deadline">⏱ {r["deadline"]}</span>' if r["deadline"] else ""
        agency   = f'<span class="agency">{r["agency"]}</span>'        if r["agency"]   else ""
        desc     = f'<p class="desc">{highlight(r["desc"])}</p>'        if r["desc"]     else ""
        link     = f'<a class="cta" href="{r["url"]}" target="_blank" rel="noopener">View opportunity →</a>' if r["url"] else ""
        source_slug = r["source"].replace(".", "").replace(" ", "-").replace("/", "")

        cards_html += f"""
        <article class="card" data-source="{source_slug}">
          <div class="card-header" style="border-left: 4px solid {color}">
            <span class="badge" style="background:{color}">{r["source"]}</span>
            {agency}
            {deadline}
          </div>
          <h3 class="card-title">{highlight(r["title"])}</h3>
          {desc}
          {link}
        </article>"""

    # Build filter buttons
    filters_html = '<button class="filter-btn active" data-filter="all">All <span class="count">{count}</span></button>'.format(count=count)
    for src in sources:
        src_count = sum(1 for r in results if r["source"] == src)
        slug = src.replace(".", "").replace(" ", "-").replace("/", "")
        color = source_color(src)
        filters_html += f'<button class="filter-btn" data-filter="{slug}" style="--src-color:{color}">{src} <span class="count">{src_count}</span></button>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AI & Data Science Funding Digest</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    :root {{
      --bg:        #f8f7f4;
      --surface:   #ffffff;
      --border:    #e8e4dd;
      --text:      #1a1816;
      --muted:     #6b6560;
      --accent:    #1a3a5c;
      --highlight: #fff3b0;
      --radius:    12px;
      --shadow:    0 2px 12px rgba(0,0,0,0.06), 0 1px 3px rgba(0,0,0,0.04);
      --shadow-hover: 0 8px 32px rgba(0,0,0,0.12), 0 2px 8px rgba(0,0,0,0.06);
    }}

    body {{
      font-family: 'DM Sans', sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
      padding: 0;
    }}

    /* ── HEADER ── */
    .header {{
      background: var(--accent);
      color: white;
      padding: 2.5rem 2rem 2rem;
      position: relative;
      overflow: hidden;
    }}
    .header::before {{
      content: '';
      position: absolute;
      inset: 0;
      background: radial-gradient(ellipse at 70% 50%, rgba(255,255,255,0.07) 0%, transparent 60%);
      pointer-events: none;
    }}
    .header-inner {{
      max-width: 1100px;
      margin: 0 auto;
      position: relative;
    }}
    .header-eyebrow {{
      font-size: 0.7rem;
      font-weight: 600;
      letter-spacing: 0.15em;
      text-transform: uppercase;
      opacity: 0.6;
      margin-bottom: 0.5rem;
    }}
    .header h1 {{
      font-family: 'DM Serif Display', serif;
      font-size: clamp(1.8rem, 4vw, 2.8rem);
      line-height: 1.1;
      margin-bottom: 0.75rem;
    }}
    .header h1 em {{
      font-style: italic;
      opacity: 0.8;
    }}
    .header-meta {{
      font-size: 0.82rem;
      opacity: 0.65;
      display: flex;
      gap: 1.5rem;
      flex-wrap: wrap;
      align-items: center;
    }}
    .header-meta strong {{
      opacity: 1;
      font-weight: 600;
      font-size: 1rem;
    }}

    /* ── SEARCH ── */
    .search-bar {{
      background: var(--surface);
      border-bottom: 1px solid var(--border);
      padding: 1rem 2rem;
      position: sticky;
      top: 0;
      z-index: 10;
      box-shadow: 0 2px 8px rgba(0,0,0,0.05);
    }}
    .search-inner {{
      max-width: 1100px;
      margin: 0 auto;
      display: flex;
      gap: 0.75rem;
      align-items: center;
      flex-wrap: wrap;
    }}
    .search-input-wrap {{
      position: relative;
      flex: 1;
      min-width: 200px;
    }}
    .search-icon {{
      position: absolute;
      left: 0.85rem;
      top: 50%;
      transform: translateY(-50%);
      opacity: 0.35;
      font-size: 0.9rem;
    }}
    input[type="search"] {{
      width: 100%;
      padding: 0.6rem 1rem 0.6rem 2.25rem;
      border: 1.5px solid var(--border);
      border-radius: 8px;
      font-family: inherit;
      font-size: 0.875rem;
      background: var(--bg);
      color: var(--text);
      outline: none;
      transition: border-color 0.15s;
    }}
    input[type="search"]:focus {{
      border-color: var(--accent);
    }}

    /* ── FILTERS ── */
    .filters {{
      display: flex;
      gap: 0.4rem;
      flex-wrap: wrap;
    }}
    .filter-btn {{
      padding: 0.35rem 0.8rem;
      border-radius: 999px;
      border: 1.5px solid var(--border);
      background: transparent;
      font-family: inherit;
      font-size: 0.75rem;
      font-weight: 500;
      color: var(--muted);
      cursor: pointer;
      transition: all 0.15s;
      white-space: nowrap;
    }}
    .filter-btn:hover {{
      border-color: var(--src-color, var(--accent));
      color: var(--src-color, var(--accent));
    }}
    .filter-btn.active {{
      background: var(--accent);
      border-color: var(--accent);
      color: white;
    }}
    .filter-btn.active[data-filter="all"] {{ background: var(--accent); }}
    .filter-btn .count {{
      opacity: 0.65;
      font-size: 0.7rem;
      margin-left: 0.2rem;
    }}

    /* ── GRID ── */
    .grid-wrap {{
      max-width: 1100px;
      margin: 0 auto;
      padding: 1.5rem 2rem 4rem;
    }}
    .results-count {{
      font-size: 0.8rem;
      color: var(--muted);
      margin-bottom: 1.25rem;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
      gap: 1.25rem;
    }}

    /* ── CARD ── */
    .card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 1.25rem 1.4rem 1.4rem;
      box-shadow: var(--shadow);
      display: flex;
      flex-direction: column;
      gap: 0.6rem;
      transition: box-shadow 0.2s, transform 0.2s;
      animation: fadeUp 0.4s ease both;
    }}
    .card:hover {{
      box-shadow: var(--shadow-hover);
      transform: translateY(-2px);
    }}
    @keyframes fadeUp {{
      from {{ opacity: 0; transform: translateY(12px); }}
      to   {{ opacity: 1; transform: translateY(0); }}
    }}
    .card.hidden {{ display: none; }}

    .card-header {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.4rem;
      align-items: center;
      padding-left: 0.75rem;
      margin-left: -1.4rem;
      padding-right: 0;
    }}
    .badge {{
      font-size: 0.65rem;
      font-weight: 600;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: white;
      padding: 0.2rem 0.55rem;
      border-radius: 999px;
    }}
    .agency {{
      font-size: 0.72rem;
      font-weight: 500;
      color: var(--muted);
      background: var(--bg);
      padding: 0.2rem 0.5rem;
      border-radius: 999px;
      border: 1px solid var(--border);
    }}
    .deadline {{
      font-size: 0.72rem;
      color: var(--muted);
      margin-left: auto;
    }}

    .card-title {{
      font-family: 'DM Serif Display', serif;
      font-size: 1rem;
      line-height: 1.35;
      color: var(--text);
    }}
    .desc {{
      font-size: 0.8rem;
      line-height: 1.6;
      color: var(--muted);
      flex: 1;
    }}
    mark {{
      background: var(--highlight);
      color: inherit;
      border-radius: 2px;
      padding: 0 1px;
    }}
    .cta {{
      display: inline-block;
      margin-top: 0.25rem;
      font-size: 0.78rem;
      font-weight: 600;
      color: var(--accent);
      text-decoration: none;
      border-top: 1px solid var(--border);
      padding-top: 0.65rem;
    }}
    .cta:hover {{ text-decoration: underline; }}

    /* ── EMPTY STATE ── */
    .empty {{
      grid-column: 1/-1;
      text-align: center;
      padding: 4rem 1rem;
      color: var(--muted);
      font-size: 0.9rem;
    }}

    /* ── FOOTER ── */
    .footer {{
      text-align: center;
      padding: 1.5rem;
      font-size: 0.72rem;
      color: var(--muted);
      border-top: 1px solid var(--border);
    }}

    @media (max-width: 600px) {{
      .header, .search-bar, .grid-wrap {{ padding-left: 1rem; padding-right: 1rem; }}
      .grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>

<header class="header">
  <div class="header-inner">
    <p class="header-eyebrow">The Michigan Institute for Data and AI in Society</p>
    <h1>AI & <em>Data Science</em><br>Funding Digest</h1>
    <div class="header-meta">
      <span><strong>{count}</strong> opportunities matched</span>
      <span>Updated {updated}</span>
      <span>Sources: Grants.gov · SAM.gov · Federal Register · NIH · Foundations · Industry</span>
    </div>
  </div>
</header>

<div class="search-bar">
  <div class="search-inner">
    <div class="search-input-wrap">
      <span class="search-icon">🔍</span>
      <input type="search" id="searchInput" placeholder="Filter by keyword…" autocomplete="off">
    </div>
    <div class="filters" id="filters">
      {filters_html}
    </div>
  </div>
</div>

<div class="grid-wrap">
  <p class="results-count" id="resultsCount">{count} opportunities</p>
  <div class="grid" id="grid">
    {cards_html}
    <div class="empty hidden" id="emptyState">No matching opportunities found.</div>
  </div>
</div>

<footer class="footer">
  Auto-generated by Federal Funding Monitor · <a href="{REPO_URL}" target="_blank">GitHub</a> · Updated {updated}
</footer>

<script>
  const cards      = Array.from(document.querySelectorAll('.card'));
  const searchInput = document.getElementById('searchInput');
  const filterBtns  = document.querySelectorAll('.filter-btn');
  const countEl     = document.getElementById('resultsCount');
  const emptyEl     = document.getElementById('emptyState');

  let activeFilter = 'all';

  function applyFilters() {{
    const q = searchInput.value.toLowerCase().trim();
    let visible = 0;

    cards.forEach(card => {{
      const matchFilter = activeFilter === 'all' || card.dataset.source === activeFilter;
      const matchSearch = !q || card.textContent.toLowerCase().includes(q);
      const show = matchFilter && matchSearch;
      card.classList.toggle('hidden', !show);
      if (show) visible++;
    }});

    countEl.textContent = visible + ' opportunit' + (visible === 1 ? 'y' : 'ies');
    emptyEl.classList.toggle('hidden', visible > 0);
  }}

  filterBtns.forEach(btn => {{
    btn.addEventListener('click', () => {{
      filterBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      activeFilter = btn.dataset.filter;
      applyFilters();
    }});
  }});

  searchInput.addEventListener('input', applyFilters);

  // Stagger card animations
  cards.forEach((card, i) => {{
    card.style.animationDelay = (i * 0.03) + 's';
  }});
</script>
</body>
</html>"""


# ── SLACK NOTIFICATION ─────────────────────────────────────────────────────────

def post_slack(count: int):
    if not SLACK_WEBHOOK:
        return
    import requests as req
    today = datetime.now().strftime("%B %d, %Y")
    text = (
        f":sparkles: *AI & Data Science Funding Digest — {today}*\n"
        f"Weekly digest updated with *{count} opportunities* matching AI, artificial intelligence, or data science.\n"
        f":arrow_right: <{PAGES_URL}/ai-digest.html|View the digest>"
    )
    resp = req.post(SLACK_WEBHOOK, json={"text": text}, timeout=10)
    if resp.status_code != 200:
        print(f"WARNING: Slack failed ({resp.status_code})")
    else:
        print("Slack notification sent.")


# ── MAIN ───────────────────────────────────────────────────────────────────────

def main():
    print(f"Starting AI digest generator — {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Loading and filtering CSVs...")

    results = load_and_filter()

    print(f"\nGenerating HTML ({len(results)} cards)...")
    html = generate_html(results)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    print(f"Saved to {OUTPUT_PATH}")

    post_slack(len(results))
    print("Done.")


if __name__ == "__main__":
    main()

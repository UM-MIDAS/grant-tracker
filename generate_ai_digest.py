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
from html import escape
import re
import pandas as pd
from datetime import datetime
from pathlib import Path
from search_terms import SEARCH_TERMS

# SLACK_WEBHOOK = os.environ.get("SLACK_WEBHOOK", "")
REPO_URL      = "https://github.com/" + os.environ.get("GITHUB_REPOSITORY", "your-org/your-repo")
PAGES_URL     = "https://" + os.environ.get("GITHUB_REPOSITORY", "your-org/your-repo").replace("/", ".github.io/", 1)
OUTPUT_PATH   = Path("docs/ai-digest.html")

# ── SEARCH TERMS ───────────────────────────────────────────────────────────────

# SEARCH_TERMS = [
#     r"\bai\b",
#     r"artificial intelligence",
#     r"data science",
#     r"machine learning",
#     r"deep learning",
#     r"large language model",
#     r"\bllm\b",
#     r"natural language processing",
#     r"\bnlp\b",
#     r"computer vision",
#     r"neural network",
# ]

SEARCH_PATTERN = re.compile(
    "|".join(SEARCH_TERMS),
    re.IGNORECASE
)

# ── CSV SOURCES ────────────────────────────────────────────────────────────────

# Each entry: (csv_path, source_label, title_col, desc_col, url_col, postdate_col, deadline_col, agency_col)
SOURCES = [
    (
        "data/opportunities.csv",
        "Grants.gov",
        "Title", "Description", "URL", "Post Date", "Deadline", "Agency"
    ),
    (
        "data/sam_opportunities.csv",
        "SAM.gov",
        "Title", "Description", "UI Link", "Posted Date", "Response Deadline", "Agency"
    ),
    (
        "data/federal_register.csv",
        "Federal Register",
        "Title", "Abstract", "HTML URL", "Publication Date", "Response Deadline", "Agency"
    ),
    (
        "data/nih_challenges.csv",
        "NIH Challenges",
        "Title", "Description", "URL", None, "Deadline", None
    ),
    (
        "data/usagov_challenges.csv",
        "USA.gov Challenges",
        "Title", "Description", "URL", None, None, None
    ),
    (
        "data/industry_grants.csv",
        "Industry",
        "Title", "Description", "URL", None, "Deadline", "Funder"
    ),
    (
        "data/foundations.csv",
        "Foundations",
        "Title", "Description", "URL", None, "Deadline", "Funder"
    ),
]

# ── LOAD AND FILTER ────────────────────────────────────────────────────────────

def load_and_filter() -> list[dict]:
    results = []

    for csv_path, source, title_col, desc_col, url_col, postdate_col, deadline_col, agency_col in SOURCES:
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

            # Create a description snippet centered on the first search match when possible
            full_desc = desc
            concatenated = f"{title} {full_desc}"
            m = SEARCH_PATTERN.search(concatenated)

            if full_desc:
                # default snippet (fallback)
                snippet = full_desc[:400] + ("…" if len(full_desc) > 400 else "")

                if m:
                    # If the match occurs in the description portion, center the snippet on it
                    desc_offset = len(title) + 1
                    if m.start() >= desc_offset:
                        match_pos = m.start() - desc_offset
                        SNIPPET_LEN = 400
                        half = SNIPPET_LEN // 2
                        start_idx = max(0, match_pos - half)
                        end_idx = start_idx + SNIPPET_LEN
                        if end_idx > len(full_desc):
                            end_idx = len(full_desc)
                            start_idx = max(0, end_idx - SNIPPET_LEN)
                        prefix = "…" if start_idx > 0 else ""
                        suffix = "…" if end_idx < len(full_desc) else ""
                        snippet = prefix + full_desc[start_idx:end_idx] + suffix
                    else:
                        # match in title — keep default snippet starting at beginning
                        snippet = full_desc[:400] + ("…" if len(full_desc) > 400 else "")
            else:
                snippet = ""

            results.append({
                "source":   source,
                "title":    title,
                "desc":     snippet,
                "full_desc": full_desc,
                "url":      row.get(url_col, "")      if url_col      else "",
                "deadline": row.get(deadline_col, "") if deadline_col else "",
                "agency":   row.get(agency_col, "")   if agency_col   else "",
                "posted":   row.get(postdate_col, "") if postdate_col else "",
                "update_type": row.get("Update Type", "")
            })

    print(f"\nTotal matching opportunities: {len(results)}")
    return results


# ── HTML GENERATION ───────────────────────────────────────────────────────────

def highlight(text: str) -> str:
    """Escape source text and wrap matched terms in a highlight span."""
    parts = []
    cursor = 0
    for match in SEARCH_PATTERN.finditer(text):
        parts.extend((escape(text[cursor:match.start()]), f"<mark>{escape(match.group(0))}</mark>"))
        cursor = match.end()
    parts.append(escape(text[cursor:]))
    return "".join(parts)


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


def _parse_date(raw: str):
    """Try to parse a variety of date strings.

    Returns (datetime_obj, has_time) or (None, False) when parsing fails.
    """
    if not raw:
        return None, False

    s = raw.strip()
    # Treat explicit 'Z' as +00:00 for fromisoformat
    if s.endswith('Z'):
        s = s[:-1] + '+00:00'

    # Heuristic: if there's a time component in the string
    has_time = ('T' in s) or (':' in s)

    # Try ISO first
    try:
        dt = datetime.fromisoformat(s)
        return dt, has_time
    except Exception:
        pass

    # Try several common patterns
    patterns = [
        '%Y-%m-%d %H:%M:%S%z',
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d %H:%M%z',
        '%Y-%m-%d %H:%M',
        '%Y-%m-%d',
        '%m/%d/%Y %H:%M:%S',
        '%m/%d/%Y %H:%M',
        '%m/%d/%Y',
        '%B %d, %Y',
        '%b %d, %Y',
    ]

    for p in patterns:
        try:
            dt = datetime.strptime(s, p)
            return dt, has_time
        except Exception:
            continue

    return None, False


def _format_display(dt: datetime, show_time: bool) -> str:
    """Format a datetime for display as 'Month day, Year' and optional 12-hour time."""
    if not dt:
        return ''
    date_part = f"{dt.strftime('%B')} {dt.day}, {dt.year}"
    if show_time:
        time_str = dt.strftime('%I:%M %p').lstrip('0')
        return f"{date_part} at {time_str}"
    return date_part


def generate_html(results: list[dict]) -> str:
    updated = datetime.now().strftime("%B %d, %Y at %I:%M %p UTC")
    count   = len(results)

    # Group by source for the filter buttons
    sources = sorted(set(r["source"] for r in results))

    # Build cards HTML
    cards_html = ""
    for r in results:
        color    = source_color(r["source"])
        # For certain sources, show both posted and deadline dates
        posted_val = r.get("posted", "")
        deadline_val = r.get("deadline", "")
        agency_list = r["agency"].split("|") if r["agency"]   else []
        agency = "".join(
            f'<span class="agency">{a}</span>'
            for a in agency_list
        )
        # agency   = f'<span class="agency">{r["agency"]}</span>'        if r["agency"]   else ""
        full_desc = r.get("full_desc", r["desc"])
        desc = (
            f'<p class="desc" data-full-description="{escape(full_desc, quote=True)}">{highlight(r["desc"])}</p>'
        ) if full_desc else ""
        link     = f'<a class="cta" href="{r["url"]}" target="_blank" rel="noopener">View opportunity →</a>' if r["url"] else ""
        source_slug = r["source"].replace(".", "").replace(" ", "-").replace("/", "")

        # Parse and format posted/deadline for display; supply ISO for sorting
        posted_dt, posted_has_time = _parse_date(posted_val)
        deadline_dt, deadline_has_time = _parse_date(deadline_val)

        posted_iso = posted_dt.isoformat() if posted_dt else ''
        deadline_iso = (deadline_dt.isoformat() if deadline_has_time else deadline_dt.date().isoformat()) if deadline_dt else ''

        posted_display = _format_display(posted_dt, posted_has_time) if posted_dt else 'Not listed'
        deadline_display = _format_display(deadline_dt, deadline_has_time) if deadline_dt else 'Not listed'

        # Keep the deadline in the header and the posted date in the footer.
        deadline_html = f'<span class="deadline"><strong>Deadline:</strong> {deadline_display}</span>'

        dates_html = f'<span class="dates">{deadline_html}</span>'

        # Determine update type (if provided) and render a small badge
        update_raw = r.get("update_type", "") or r.get("Update Type", "")
        update_type = update_raw.strip().lower()
        update_badge = ""
        if update_type in ("updated", "new"):
            update_badge = f'<span class="update-pill {update_type}">{update_type.capitalize()}</span>'

        # Ensure link placeholder exists so footer layout stays consistent when missing
        link_html = link if link else '<span></span>'

        cards_html += f"""
        <article class="card" data-source="{source_slug}" data-posted-date="{posted_iso}" data-deadline-date="{deadline_iso}">
          <div class="card-header">
            <div class="card-header-top">
              <div class="card-labels">
                <span class="badge" style="--src-color:{color}">{r["source"]}</span>
                {update_badge}
                <span class="closed-pill hidden">Closed</span>
              </div>
              {dates_html}
            </div>
            <div class="card-agencies">{agency}</div>
          </div>
          <h3 class="card-title">{highlight(r["title"])}</h3>
          {desc}
          <div class="card-footer">
            {link_html}
            <span class="posted">Posted: {posted_display}</span>
          </div>
        </article>"""

    # Build filter buttons
    filters_html = '<button class="filter-btn active" data-filter="all" aria-pressed="true">All <span class="count">{count}</span></button>'.format(count=count)
    for src in sources:
        src_count = sum(1 for r in results if r["source"] == src)
        slug = src.replace(".", "").replace(" ", "-").replace("/", "")
        color = source_color(src)
        filters_html += f'<button class="filter-btn" data-filter="{slug}" aria-pressed="false" style="--src-color:{color}">{src} <span class="count">{src_count}</span></button>'

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
      --bg: #f4f6f8; --surface: #fff; --border: #dce2e8;
      --text: #172b40; --muted: #303A45; --accent: #00274c;
      --highlight: #fff0ad; --radius: 16px;
    }}
    body {{ font-family: 'DM Sans', sans-serif; background: var(--bg); color: var(--text); line-height: 1.5; }}
    button, input, select {{ font: inherit; }}
    button, a, input, select {{ -webkit-tap-highlight-color: transparent; }}
    :focus-visible {{ outline: 3px solid #287bb5; outline-offset: 4px; }}
    .skip-link {{ position: absolute; left: 1rem; top: -5rem; z-index: 20; padding: .75rem 1rem; background: white; color: var(--accent); }}
    .skip-link:focus {{ top: 1rem; }}
    .header {{ background: var(--accent); color: white; border-top: 6px solid #ffcb05; padding: 3rem 2rem; }}
    .header-inner, .search-inner, .grid-wrap {{ max-width: 1200px; margin: 0 auto; }}
    .header-eyebrow {{ font-size: .75rem; font-weight: 600; letter-spacing: .12em; text-transform: uppercase; color: #ffdb50; margin-bottom: 1.25rem; }}
    .header h1 {{ font-family: 'DM Serif Display', Georgia, serif; font-weight: 400; font-size: clamp(2.25rem, 5vw, 3.75rem); line-height: 1.12; letter-spacing: -.025em; }}
    .header h1 em {{ color: #ffdb50; }}
    .header-description {{ color: #d6e2ed; max-width: 620px; margin: 1rem 0 1.75rem; }}
    .header-meta {{ display: flex; align-items: baseline; flex-wrap: wrap; gap: .75rem 2rem; font-size: .82rem; color: #d6e2ed; }}
    .header-meta strong {{ color: white; font-size: 1.1rem; }}
    .search-bar {{ background: var(--surface); border-bottom: 1px solid var(--border); padding: 1.25rem 2rem; }}
    .search-inner {{ display: flex; flex-wrap: wrap; gap: 1rem; align-items: start; }}
    .search-submit-row {{ display: flex; gap: .5rem; }}
    .search-submit-row input {{ min-width: 0; }}
    .search-submit {{ border: 0; border-radius: 8px; background: var(--accent); color: white; padding: .65rem 1rem; cursor: pointer; }}
    .search-help {{ margin-top: .4rem; color: var(--muted); font-size: .75rem; }}
    .search-input-wrap {{ position: relative; flex: 1 1 360px; }}
    .control-label {{ display: block; font-size: .75rem; font-weight: 600; color: var(--muted); margin-bottom: .4rem; }}
    input[type="search"], .sort-select {{ width: 100%; min-height: 46px; border: 1px solid #b9c5d1; border-radius: 8px; background: white; color: var(--text); padding: .65rem .85rem; font-size: .875rem; }}
    input[type="search"]::placeholder {{ color: #637387; }}
    .sort-controls {{ display: flex; gap: .75rem; }}
    .sort-select {{ width: auto; min-width: 0; max-width: 100%; padding-inline: .6rem; }}
    .filters {{ display: flex; flex-wrap: wrap; gap: .5rem; flex-basis: 100%; }}
    .filter-btn {{ min-height: 40px; padding: .4rem .85rem; border-radius: 7px; border: 1px solid var(--border); background: white; font-size: .8rem; font-weight: 500; color: var(--muted); cursor: pointer; }}
    .filter-btn:hover {{ border-color: var(--accent); color: var(--accent); }}
    .filter-btn.active {{ background: var(--accent); border-color: var(--accent); color: white; }}
    .count {{ display: inline-block; margin-left: .35rem; padding: 0 .35rem; border-radius: 4px; background: #edf1f5; color: var(--accent); font-size: .72rem; }}
    .filter-btn.active .count {{ background: #284d70; color: white; }}
    .grid-wrap {{ padding: 2rem 2rem 4rem; }}
    .results-toolbar {{ display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 1rem; margin-bottom: 1.25rem; }}
    .results-toolbar h2 {{ font-family: 'DM Serif Display', Georgia, serif; font-weight: 400; font-size: 1.6rem; }}
    .results-count {{ font-size: .85rem; color: var(--muted); margin-top: .25rem; }}
    .reset-btn {{ border: 1px solid var(--border); border-radius: 8px; padding: .65rem .85rem; margin-top: calc(.75rem * 1.5 + .4rem); min-height: 46px; color: var(--accent); background: white; cursor: pointer; font-size: .8rem; }}
    .reset-btn:hover {{ background: #eaf0f5; }}
    .grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1.25rem; }}
    .card {{ min-width: 0; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 1.5rem; display: flex; flex-direction: column; gap: 1rem; box-shadow: 0 2px 5px #00274c05; overflow-wrap: anywhere; }}
    .card:hover {{ border-color: #aabccd; box-shadow: 0 4px 16px #00274c0a; }}
    .hidden {{ display: none !important; }}
    .card-header {{ display: flex; flex-direction: column; gap: .75rem; }}
    .card-header-top {{ display: flex; flex-wrap: wrap; gap: .5rem; align-items: center; }}
    .card-labels {{ display: flex; flex: 1 1 auto; flex-wrap: wrap; gap: .5rem; align-items: center; }}
    .badge {{ font-size: .72rem; font-weight: 600; color: var(--accent); background: #eaf0f6; padding: .3rem .6rem; border-radius: 5px; border-left: 3px solid var(--src-color); }}
    .card-agencies {{ display: flex; flex-wrap: wrap; gap: .3rem .6rem; }}
    .agency {{ font-size: .72rem; font-weight: 500; color: var(--muted); background: #f5f7f9; border-radius: 4px; padding: .15rem .4rem; }}
    .update-pill {{ font-size: .7rem; font-weight: 600; padding: .25rem .5rem; border-radius: 5px; }}
    .update-pill.updated {{ color: var(--text); background: #eae9ff; }}
    .update-pill.new {{ color: #176040; background: #e0f3e9; }}
    .closed-pill {{ font-size: .7rem; font-weight: 600; padding: .25rem .5rem; border-radius: 5px; color: #8b3030; background: #fbe9e9; }}
    .dates {{ font-variant-numeric: tabular-nums; }}
    .deadline {{ display: inline-block; font-size: .8rem; color: var(--text); background: #fff5ea; border-radius: 4px; border-right: 2px solid #ff9a29; padding: .35rem .6rem; }}
    .dates.wrapped .deadline {{ border-right: 0; border-left: 2px solid #ff9a29; }}
    .card-title {{ font-size: 1.15rem; font-weight: 600; line-height: 1.45; letter-spacing: -.015em; }}
    .desc {{ font-size: .875rem; line-height: 1.75; color: var(--muted); flex: 1; }}
    mark {{ background: var(--highlight); color: inherit; border-radius: 2px; }}
    mark.search-match {{ background: #ffcb05; color: #00274c; box-shadow: 0 1px 0 #9d7100; }}
    .card-footer {{ display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: .75rem; border-top: 1px solid var(--border); padding-top: 1rem; margin-top: auto; }}
    .posted {{ font-size: .75rem; color: var(--muted); }}
    .cta {{ font-size: .82rem; font-weight: 600; color: var(--accent); text-decoration: none; padding: .25rem 0; }}
    .cta:hover {{ text-decoration: underline; text-underline-offset: 4px; }}
    .empty {{ grid-column: 1 / -1; text-align: center; padding: 4rem 1.5rem; background: white; border: 1px dashed #b9c5d1; border-radius: var(--radius); color: var(--muted); }}
    .empty h3 {{ color: var(--text); margin-bottom: .5rem; }}
    .footer {{ text-align: center; padding: 1.5rem; font-size: .75rem; color: var(--muted); border-top: 1px solid var(--border); }}
    .footer a {{ color: var(--accent); }}
    @media (max-width: 700px) {{
      .header {{ padding: 2rem 1rem; }}
      .search-bar {{ padding: 1rem; }}
      .grid-wrap {{ padding: 1.5rem 1rem 3rem; }}
      .grid {{ grid-template-columns: minmax(0, 1fr); }}
      .card {{ padding: 1.25rem; }}
      .sort-controls {{ width: 100%; flex-wrap: wrap; }}
      .sort-controls label {{ flex: 0 1 auto; min-width: 0; }}
      .sort-select {{ min-width: 0; }}
      .reset-btn {{ width: 100%; margin-top: 0; }}
    }}
  </style>
</head>
<body>
<a class="skip-link" href="#opportunities">Skip to opportunities</a>

<header class="header">
  <div class="header-inner">
    <p class="header-eyebrow">The Michigan Institute for Data and AI in Society</p>
    <h1>AI & <em>Data Science</em><br>Funding Digest</h1>
    <p class="header-description">Explore research funding, challenges, and calls for participation across government, industry, and foundations.</p>
    <div class="header-meta">
      <span><strong>{count}</strong> opportunities matched</span>
      <span>Updated {updated}</span>
      <span>Sources: {' • '.join(sources)}</span>
    </div>
  </div>
</header>

<div class="search-bar">
  <div class="search-inner">
    <form class="search-input-wrap" id="searchForm" role="search">
      <label class="control-label" for="searchInput">Search opportunities</label>
      <div class="search-submit-row">
        <input type="search" id="searchInput" placeholder="Enter a word or exact phrase…" autocomplete="off" aria-describedby="searchHelp">
        <button class="search-submit" type="submit">Search</button>
      </div>
    </form>
    <div class="sort-controls">
      <label><span class="control-label">Status</span>
      <select id="statusFilter" class="sort-select" title="Open includes opportunities with no known deadline">
        <option value="open" selected>Open</option>
        <option value="closed">Closed</option>
        <option value="all">All</option>
      </select></label>
      <label><span class="control-label">Sort by</span>
      <select id="sortField" class="sort-select" aria-label="Sort opportunities by date">
        <option value="">Sort by date…</option>
        <option value="posted" selected>Posted date</option>
        <option value="deadline">Deadline</option>
      </select>
      </label>
      <label><span class="control-label">Order</span>
      <select id="sortDirection" class="sort-select" aria-label="Sort direction">
        <option value="desc" selected>Newest</option>
        <option value="asc">Oldest</option>
      </select></label>
    </div>
    <button class="reset-btn" id="resetFilters" type="button">Reset filters</button>
    <div class="filters" id="filters" role="group" aria-label="Filter by source">
      {filters_html}
    </div>
  </div>
</div>

<main class="grid-wrap" id="opportunities" tabindex="-1">
  <div class="results-toolbar">
    <div><h2>Explore opportunities</h2><p class="results-count" id="resultsCount" role="status" aria-live="polite">{count} opportunities</p></div>
  </div>
  <div class="grid" id="grid">
    {cards_html}
    <div class="empty hidden" id="emptyState"><h3>No matching opportunities</h3><p>Try a different keyword or reset the filters to explore all opportunities.</p></div>
  </div>
</main>

<footer class="footer">
  Auto-generated by Federal Funding Monitor · <a href="{REPO_URL}" target="_blank">GitHub</a> · Updated {updated}
</footer>

<script>
  const cards      = Array.from(document.querySelectorAll('.card'));
  const searchInput = document.getElementById('searchInput');
  const filterBtns  = document.querySelectorAll('.filter-btn');
  const sortField   = document.getElementById('sortField');
  const sortDirection = document.getElementById('sortDirection');
  const statusFilter = document.getElementById('statusFilter');
  const grid        = document.getElementById('grid');
  const countEl     = document.getElementById('resultsCount');
  const emptyEl     = document.getElementById('emptyState');

  let activeFilter = 'all';
  let activeQuery = '';
  const cardContent = new Map(cards.map(card => {{
    const description = card.querySelector('.desc');
    const fields = Array.from(card.querySelectorAll('.card-title, .badge, .agency, .deadline, .posted'))
      .map(field => field.textContent);
    if (description) fields.push(description.dataset.fullDescription);
    return [card, {{ description, preview: description?.innerHTML, fields }}];
  }}));

  function searchMatches(text, query) {{
    if (!query) return [];
    // Encode every character literally; punctuation never acts as regex syntax.
    const literal = Array.from(query, char => '\\\\u{{' + char.codePointAt(0).toString(16) + '}}').join('');
    const pattern = new RegExp('(?<![\\\\p{{L}}\\\\p{{N}}_])' + literal + '(?![\\\\p{{L}}\\\\p{{N}}_])', 'giu');
    return Array.from(text.matchAll(pattern), match => [match.index, match.index + match[0].length]);
  }}


  function searchSnippet(text, query) {{
    const match = searchMatches(text, query)[0];
    if (!match) return null;
    // Mirror the initial description slicing, keeping long phrases intact.
    const length = Math.max(400, match[1] - match[0]);
    let start = Math.max(0, match[0] - Math.floor(length / 2));
    let end = start + length;
    if (end < match[1]) {{
      end = match[1];
      start = Math.max(0, end - length);
    }}
    if (end > text.length) {{
      end = text.length;
      start = Math.max(0, end - length);
    }}
    return (start > 0 ? '…' : '') + text.slice(start, end) + (end < text.length ? '…' : '');
  }}

  function highlightSearch(card, query) {{
    // Remove only search highlights, keeping the original topic highlights.
    card.querySelectorAll('mark.search-match').forEach(mark => {{
      mark.replaceWith(document.createTextNode(mark.textContent));
    }});
    card.normalize();
    if (!query) return;

    const matches = searchMatches(card.textContent, query);

    // Track offsets across text nodes so phrases spanning existing marks match.
    const walker = document.createTreeWalker(card, NodeFilter.SHOW_TEXT);
    const nodes = [];
    let offset = 0;
    while (walker.nextNode()) {{
      const node = walker.currentNode;
      nodes.push({{ node, start: offset, end: offset + node.length }});
      offset += node.length;
    }}
    nodes.forEach(({{ node, start, end }}) => {{
      const overlaps = matches.filter(([a, b]) => a < end && b > start);
      if (!overlaps.length) return;
      const fragment = document.createDocumentFragment();
      let cursor = 0;
      overlaps.forEach(([a, b]) => {{
        const from = Math.max(a, start) - start;
        const to = Math.min(b, end) - start;
        fragment.append(document.createTextNode(node.data.slice(cursor, from)));
        const mark = document.createElement('mark');
        mark.className = 'search-match';
        mark.textContent = node.data.slice(from, to);
        fragment.append(mark);
        cursor = to;
      }});
      fragment.append(document.createTextNode(node.data.slice(cursor)));
      node.replaceWith(fragment);
    }});
  }}

  function parseDateValue(value) {{
    if (!value) return null;
    const time = Date.parse(value);
    return Number.isNaN(time) ? null : time;
  }}

  function updateSortDirectionLabels() {{
    const descOption = sortDirection.options[0];
    const ascOption = sortDirection.options[1];

    if (sortField.value === 'deadline') {{
      descOption.value = 'asc';
      descOption.textContent = 'Soonest';
      ascOption.value = 'desc';
      ascOption.textContent = 'Latest';
      if (sortDirection.value !== 'asc' && sortDirection.value !== 'desc') {{
        sortDirection.value = 'asc';
      }}
    }} else if (sortField.value === 'posted') {{
      descOption.value = 'desc';
      descOption.textContent = 'Newest';
      ascOption.value = 'asc';
      ascOption.textContent = 'Oldest';
      if (sortDirection.value !== 'desc' && sortDirection.value !== 'asc') {{
        sortDirection.value = 'desc';
      }}
    }} else {{
      descOption.value = 'desc';
      descOption.textContent = 'Descending';
      ascOption.value = 'asc';
      ascOption.textContent = 'Ascending';
    }}
  }}

  function sortCards(cardList) {{
    const field = sortField.value;
    if (!field) return cardList;

    const direction = sortDirection.value === 'asc' ? 1 : -1;

    return [...cardList].sort((a, b) => {{
      const aValue = parseDateValue(a.dataset[field + 'Date']);
      const bValue = parseDateValue(b.dataset[field + 'Date']);

      if (aValue === null && bValue === null) return 0;
      if (aValue === null) return 1;
      if (bValue === null) return -1;

      if (aValue === bValue) return 0;
      return aValue > bValue ? direction : -direction;
    }});
  }}

  function renderDescription(content, query) {{
    if (!content.description) return;
    const description = content.description;
    const fullText = description.dataset.fullDescription;
    description.innerHTML = content.preview;
    if (query) {{
      const snippet = searchSnippet(fullText, query);
      if (snippet !== null) description.textContent = snippet;
    }}

  }}

  function isDeadlineClosed(value, now = new Date()) {{
    if (!value) return false;
    // Date-only deadlines stay open through that day in the viewer's timezone.
    if (value.length === 10) {{
      const end = new Date(value + 'T00:00:00');
      end.setDate(end.getDate() + 1);
      return now.getTime() >= end.getTime();
    }}
    const deadline = Date.parse(value);
    return !Number.isNaN(deadline) && now.getTime() >= deadline;
  }}

  function applyFilters() {{
    const q = activeQuery;
    const now = new Date();
    const sourceCounts = new Map();
    let matchingStatusAndSearch = 0;
    let visible = 0;

    cards.forEach(card => {{
      const matchFilter = activeFilter === 'all' || card.dataset.source === activeFilter;
      const content = cardContent.get(card);
      const closed = isDeadlineClosed(card.dataset.deadlineDate, now);
      card.querySelector('.closed-pill').classList.toggle('hidden', !closed);
      const matchStatus = statusFilter.value === 'all' || (statusFilter.value === 'closed' ? closed : !closed);
      const matchSearch = !q || content.fields.some(text => searchMatches(text, q).length > 0);
      if (matchStatus && matchSearch) {{
        matchingStatusAndSearch++;
        sourceCounts.set(card.dataset.source, (sourceCounts.get(card.dataset.source) || 0) + 1);
      }}
      const show = matchFilter && matchSearch && matchStatus;
      card.classList.toggle('hidden', !show);
      renderDescription(content, show ? q : '');
      highlightSearch(card, show ? q : '');
      if (show) visible++;
    }});

    sortCards(cards).forEach(card => grid.insertBefore(card, emptyEl));

    countEl.textContent = visible + ' opportunit' + (visible === 1 ? 'y' : 'ies');
    filterBtns.forEach(btn => {{
      btn.querySelector('.count').textContent = btn.dataset.filter === 'all'
        ? matchingStatusAndSearch : (sourceCounts.get(btn.dataset.filter) || 0);
    }});
    emptyEl.classList.toggle('hidden', visible > 0);
  }}

  filterBtns.forEach(btn => {{
    btn.addEventListener('click', () => {{
      filterBtns.forEach(b => {{
        b.classList.remove('active');
        b.setAttribute('aria-pressed', 'false');
      }});
      btn.classList.add('active');
      btn.setAttribute('aria-pressed', 'true');
      activeFilter = btn.dataset.filter;
      applyFilters();
    }});
  }});

  document.getElementById('resetFilters').addEventListener('click', () => {{
    searchInput.value = '';
    activeQuery = '';
    statusFilter.value = 'open';
    sortField.value = 'posted';
    updateSortDirectionLabels();
    sortDirection.value = 'desc';
    document.querySelector('[data-filter="all"]').click();
    searchInput.focus();
  }});

  document.getElementById('searchForm').addEventListener('submit', event => {{
    event.preventDefault();
    activeQuery = searchInput.value.trim();
    applyFilters();
  }});
  sortField.addEventListener('change', () => {{
    updateSortDirectionLabels();
    if (sortField.value === 'deadline') {{
      sortDirection.value = 'asc';
    }} else if (sortField.value === 'posted') {{
      sortDirection.value = 'desc';
    }}
    applyFilters();
  }});
  sortDirection.addEventListener('change', applyFilters);
  statusFilter.addEventListener('change', applyFilters);
  // Keep deadline status current even when the digest remains open overnight.
  setInterval(applyFilters, 60000);

  const deadlineLayoutObserver = new ResizeObserver(entries => {{
    entries.forEach(({{ target: header }}) => {{
      if (!header.getClientRects().length) return;
      const labels = header.querySelector('.card-labels');
      const dates = header.querySelector('.dates');
      const wrapped = dates.getBoundingClientRect().top >= labels.getBoundingClientRect().bottom;
      dates.classList.toggle('wrapped', wrapped);
    }});
  }});
  document.querySelectorAll('.card-header-top').forEach(header => deadlineLayoutObserver.observe(header));

  updateSortDirectionLabels();
  applyFilters();

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
    html = "\n".join(line.rstrip() for line in generate_html(results).splitlines()) + "\n"

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    print(f"Saved to {OUTPUT_PATH}")

    # post_slack(len(results))
    print("Done.")


if __name__ == "__main__":
    main()

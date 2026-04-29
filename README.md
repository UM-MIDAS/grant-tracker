# Federal Funding Monitor

Automatically monitors seven sources for new funding opportunities, contract notices, RFIs, advisory committee nominations, prize competitions, and industry grants every weekday morning. Results are saved to CSV files in this repository and summaries are posted to Slack.

---

## What it monitors

| Monitor | Source | What it tracks | Schedule | Output file | CSV behavior |
|---|---|---|---|---|---|
| Grants.gov | Grants.gov API | Grant opportunities & forecasts from NSF, NIH, NEH, DOE, DOC, DOT, DOD | 8:00 AM Eastern | `data/opportunities.csv` | Appends new rows |
| SAM.gov | SAM.gov API | Contract opportunities, RFIs, and pre-solicitations from ARPA-H & DARPA | 8:15 AM Eastern | `data/sam_opportunities.csv` | Appends new rows |
| Federal Register | FederalRegister.gov API | RFIs and advisory committee nomination calls — published and pre-publication | 8:30 AM Eastern | `data/federal_register.csv` | Appends new rows |
| NIH Challenges | nih.gov/challenges | Open prize competitions sponsored by NIH | 8:45 AM Eastern | `data/nih_challenges.csv` | Replaces with current open items |
| USA.gov Challenges | usa.gov/find-active-challenge | Active federal prize competitions listed by USA.gov | 8:45 AM Eastern | `data/usagov_challenges.csv` | Replaces with current open items |
| Industry Grants | Schmidt Sciences, Amazon, NVIDIA | Open calls, research awards, and academic grant programs | 9:00 AM Eastern | `data/industry_grants.csv` | Replaces with current open items |

**Note on CSV behavior:** Grants.gov, SAM.gov, and Federal Register monitors append new rows on each run and skip duplicates, building a cumulative archive. All other monitors replace the CSV entirely each run so the file always reflects only what is currently open.

Each monitor runs independently. If one fails, the others are unaffected. All post to the same Slack channel.

---

## Sources and coverage

### Grants.gov
Searches for posted and forecasted grant opportunities from seven federal departments and agencies. Filtered post-search to include opportunities open to public and private institutions of higher education (eligibility codes 06 and 25) and unrestricted opportunities (code 99).

Agencies covered: NSF, NIH (and sub-agencies), NEH, DOE, DOC (including NOAA and NIST), DOT (including FHWA, FRA, FTA, FAA, NHTSA, MARAD), DOD (including DARPA, Army, Navy, Air Force).

### SAM.gov
Searches for all contract opportunity types — solicitations, pre-solicitations, sources sought, RFIs, special notices, award notices, and justifications — from ARPA-H and DARPA.

### Federal Register
Searches for published notices and pre-publication public inspection documents matching terms related to requests for information, advisory committees, and nominations. Pre-publication items (public inspection PDFs) are captured as soon as they are filed — before the official published version appears.

Search terms: request for information, requests for information, advisory committee, call for nominations, nominations, call for experts.

### NIH Challenges
Scrapes the NIH challenges page daily and tracks only currently open prize competitions. When a challenge closes it is automatically removed from the CSV. Slack alerts show what is newly opened or recently closed.

### USA.gov Challenges
Scrapes the USA.gov active federal challenges listing — a curated federal challenge listing maintained by GSA following the sunset of Challenge.gov in March 2026. Slack alerts show what is newly added or removed.

### Industry Grants
Scrapes three sources for currently open industry-funded research opportunities:
- **Schmidt Sciences** — open calls listed at schmidtsciences.org/opportunities
- **Amazon Research Awards** — active call-for-proposals cycles at amazon.science
- **NVIDIA** — Academic Grant Program (rolling) and Graduate Fellowship (annual, opens ~August)

---

## One-time setup

You only need to do this once. It takes about 20 minutes.

### Step 1 — Get a Grants.gov API key

1. Go to [simpler.grants.gov/developer](https://simpler.grants.gov/developer)
2. Sign in with Login.gov (or create a free account)
3. Click **Manage API Keys** → **Create new key**
4. Copy the key and save it somewhere safe

### Step 2 — Get a SAM.gov API key

1. Go to [sam.gov](https://sam.gov) and sign in (or create a free account)
2. Click your name/profile icon in the top right → **Account Details**
3. Scroll down to the **Public API Key** section
4. Click the **eye icon** and enter your account password when prompted
5. Copy the key and save it somewhere safe

> **Note:** SAM.gov API keys expire every 90 days. You will receive an email reminder before expiry — just repeat these steps and update the `SAM_API_KEY` GitHub Secret.

> **Note:** The Federal Register, NIH, USA.gov, and industry grant monitors require no API keys.

### Step 3 — Get a Slack webhook URL

1. Go to [api.slack.com/apps](https://api.slack.com/apps) and click **Create New App**
2. Choose **From scratch**, give it a name (e.g. "Funding Monitor"), and select your workspace
3. In the left sidebar, click **Incoming Webhooks** and toggle it **On**
4. Click **Add New Webhook to Workspace**, choose the channel for alerts, and click **Allow**
5. Copy the webhook URL — it starts with `https://hooks.slack.com/services/...`

### Step 4 — Add secrets to GitHub

Your API keys and Slack webhook are stored as **secrets** in GitHub — never visible in the code or to anyone browsing the repository.

1. In this repository, click **Settings** (top menu)
2. In the left sidebar, click **Secrets and variables** → **Actions**
3. Click **New repository secret** and add each of the following:

| Secret name | Value |
|---|---|
| `GRANTS_API_KEY` | The Grants.gov API key from Step 1 |
| `SAM_API_KEY` | The SAM.gov API key from Step 2 |
| `SLACK_WEBHOOK` | The webhook URL from Step 3 |

### Step 5 — Enable GitHub Actions

1. In this repository, click the **Actions** tab (top menu)
2. If prompted, click **I understand my workflows, go ahead and enable them**
3. Go to **Settings** → **Actions** → **General** → **Workflow permissions** and confirm **Read and write** is selected

That's it. All monitors will run automatically every weekday morning.

---

## Testing manually

To trigger any monitor immediately without waiting for the schedule:

1. Go to the **Actions** tab in this repository
2. Click the workflow you want to test in the left sidebar:
   - **Grants.gov Daily Monitor**
   - **SAM.gov Daily Monitor**
   - **Federal Register Daily Monitor**
   - **Challenges Daily Monitor** (runs both NIH and USA.gov)
   - **Industry Grants Monitor** (runs Schmidt Sciences, Amazon, and NVIDIA)
3. Click **Run workflow** → **Run workflow**

You will see a Slack message within a minute or two and the relevant CSV will be updated.

---

## Downloading the CSVs

1. In this repository, click the `data` folder
2. Click the CSV you want
3. Click the **Download raw file** button (the download icon in the top right)

---

## Fields in each CSV

### Grants.gov (`data/opportunities.csv`)

| Column | Description |
|---|---|
| Opportunity ID | Grants.gov opportunity number |
| Title | Full opportunity title |
| Post Date | Date the opportunity was posted |
| Est. # of Awards | Estimated number of awards |
| Est. Total Funding | Total program funding available |
| Award Ceiling | Maximum award per applicant |
| Assistance Listings | CFDA number and program name |
| Funding Instrument Type | e.g. grant, cooperative agreement |
| Contact | Agency contact email |
| Deadline | Application close date |
| Est. NOFO Date | Forecasted NOFO publication date |
| Est. Application Deadline | Forecasted application deadline |
| Last Updated | Date the record was last updated |
| URL | Link to the opportunity on Simpler Grants.gov |
| Description | Plain-text summary of the opportunity |
| Agency | Posting agency code (e.g. NSF, NIH) |
| Status | Posted or Forecast |
| Additional Information on Eligibility | Extra eligibility notes |

### SAM.gov (`data/sam_opportunities.csv`)

| Column | Description |
|---|---|
| Notice ID | SAM.gov unique notice identifier |
| Title | Full opportunity title |
| Solicitation Number | Solicitation or contract number |
| Agency | Posting office (e.g. DARPA, ARPA-H) |
| Department Path | Full organizational hierarchy |
| Type | Notice type (e.g. Solicitation, Sources Sought, Pre-Solicitation) |
| Base Type | Original notice type if amended |
| Posted Date | Date the notice was posted |
| Response Deadline | Date responses are due |
| Archive Date | Date the notice will be archived |
| Active | Whether the notice is currently active |
| Set Aside | Small business or other set-aside designation |
| NAICS Code | North American Industry Classification code |
| Classification Code | Product or service classification |
| Contact | Primary contact email |
| Description URL | Link to full notice description |
| UI Link | Direct link to the notice on SAM.gov |
| Resource Links | Links to attached documents |

### Federal Register (`data/federal_register.csv`)

| Column | Description |
|---|---|
| Document Number | Federal Register document number |
| Title | Full document title |
| Type | Document type (e.g. Notice) |
| Source | Published or Public Inspection (Pre-Publication) |
| Agency | Issuing agency or agencies |
| Publication Date | Date published in the Federal Register |
| Filing Date | Date filed for public inspection (pre-publication items only) |
| Response Deadline | Comment or response deadline |
| Effective Date | Date the document takes effect |
| Citation | Federal Register citation (e.g. 90 FR 1234) |
| Docket IDs | Associated regulatory docket numbers |
| Abstract | Brief summary of the document |
| HTML URL | Link to the HTML version on FederalRegister.gov |
| PDF URL | Link to the official PDF |
| Public Inspection PDF | Link to the pre-publication PDF (when available) |

### NIH Challenges (`data/nih_challenges.csv`)

*This file reflects currently open challenges only. It is replaced on each run.*

| Column | Description |
|---|---|
| Title | Full challenge title |
| Description | Challenge summary |
| Deadline | Submission deadline or phase deadline |
| URL | Link to the challenge page on nih.gov |
| Source | NIH |
| Scraped Date | Date this record was last confirmed open |

### USA.gov Challenges (`data/usagov_challenges.csv`)

*This file reflects currently listed challenges only. It is replaced on each run.*

| Column | Description |
|---|---|
| Title | Full challenge title |
| Description | Challenge summary |
| URL | Link to the challenge detail page |
| Source | USA.gov |
| Scraped Date | Date this record was last confirmed listed |

### Industry Grants (`data/industry_grants.csv`)

*This file reflects currently open opportunities only. It is replaced on each run.*

| Column | Description |
|---|---|
| Title | Full opportunity title |
| Program | Program or research area name |
| Funder | Schmidt Sciences, Amazon, or NVIDIA |
| Description | Summary of the opportunity or research area |
| Deadline | Submission deadline (where listed) |
| URL | Link to the announcement or program page |
| Apply URL | Direct link to the application or submission form |
| Scraped Date | Date this record was last confirmed open |

---

## Repo structure

```
your-repo/
├── .github/
│   └── workflows/
│       ├── grants_monitor.yml             ← Grants.gov (8:00 AM ET)
│       ├── sam_monitor.yml                ← SAM.gov (8:15 AM ET)
│       ├── federal_register_monitor.yml   ← Federal Register (8:30 AM ET)
│       ├── challenges_monitor.yml         ← NIH & USA.gov challenges (8:45 AM ET)
│       └── industry_grants_monitor.yml    ← Industry grants (9:00 AM ET)
├── data/
│   ├── opportunities.csv                  ← Grants.gov results (cumulative)
│   ├── sam_opportunities.csv              ← SAM.gov results (cumulative)
│   ├── federal_register.csv              ← Federal Register results (cumulative)
│   ├── nih_challenges.csv                 ← NIH open challenges (current only)
│   ├── usagov_challenges.csv             ← USA.gov active challenges (current only)
│   └── industry_grants.csv               ← Industry grants open calls (current only)
├── search_grants.py                       ← Grants.gov script
├── search_sam.py                          ← SAM.gov script
├── search_federal_register.py             ← Federal Register script
├── search_nih_challenges.py              ← NIH challenges script
├── search_usagov_challenges.py           ← USA.gov challenges script
├── search_industry_grants.py             ← Industry grants script
└── README.md
```

---

## Customization

### Changing the schedule
Edit the `cron` line in the relevant workflow file inside `.github/workflows/`. Use [crontab.guru](https://crontab.guru) to build a custom schedule. Times are in UTC — Eastern Standard Time is UTC-5, Eastern Daylight Time is UTC-4.

### Grants.gov — adding or removing agencies
Edit the `AGENCY_CODES` list near the top of `search_grants.py`.

### SAM.gov — adding organizations
Edit the `TARGET_ORGS` list near the top of `search_sam.py`. Values match against the organization name field so partial matches work (e.g. `"DARPA"` matches `"Defense Advanced Research Projects Agency"`).

### Federal Register — adding search terms
Edit the `SEARCH_TERMS` list near the top of `search_federal_register.py`. Each term is searched independently and results are combined and deduplicated.

### Industry grants — adding sources
Add a new scrape function to `search_industry_grants.py` following the same pattern as the existing Schmidt, Amazon, and NVIDIA functions, then call it from `main()`.

---

## Troubleshooting

**No Slack message arrived**
- Go to the **Actions** tab, click the most recent run, and check the logs for errors
- Confirm all secrets are correctly saved under Settings → Secrets and variables → Actions

**Grants.gov, SAM.gov, or Federal Register show "no new items" every day**
- The CSV already contains recent results and nothing new has been posted — this is expected
- To verify the monitor is working, delete the relevant CSV from the `data` folder and trigger a manual run

**Industry grants or challenge monitors show incorrect or missing data**
- The source page structure may have changed — check the URL directly in a browser
- Review the Actions log for scraping warnings and flag the issue for a script update

**Slack message arrives but CSV is not updating**
- Go to Settings → Actions → General → Workflow permissions and confirm **Read and write** is selected

**SAM.gov returns a 401 or 403 error**
- Your SAM.gov API key has likely expired (keys expire every 90 days)
- Generate a new key from your SAM.gov Account Details page and update the `SAM_API_KEY` secret

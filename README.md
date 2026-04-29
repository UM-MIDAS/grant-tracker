# Grants.gov Opportunity Monitor

Automatically checks for new federal grant opportunities every weekday morning and posts a summary to Slack. New opportunities are saved to a CSV file in this repository that the team can download at any time.

---

## What it does

- Runs automatically every weekday at **8:00 AM Eastern**
- Searches Grants.gov for opportunities from **NSF, NIH, DOE, DOC, DOT, and DOD**
- Filters for opportunities open to universities (public, private, or unrestricted)
- Adds any new opportunities to `data/opportunities.csv` in this repo (duplicates are skipped)
- Posts a Slack message summarizing how many new opportunities were found and which agencies posted them

---

## One-time setup

You only need to do this once. It takes about 15 minutes.

### Step 1 — Get a Grants.gov API key

1. Go to [simpler.grants.gov/developer](https://simpler.grants.gov/developer)
2. Sign in with Login.gov (or create a free account)
3. Click **Manage API Keys** → **Create new key**
4. Copy the key and save it somewhere safe — you'll need it in Step 3

### Step 2 — Get a Slack webhook URL

1. Go to [api.slack.com/apps](https://api.slack.com/apps) and click **Create New App**
2. Choose **From scratch**, give it a name (e.g. "Grants Monitor"), and select your workspace
3. In the left sidebar, click **Incoming Webhooks** and toggle it **On**
4. Click **Add New Webhook to Workspace**, choose the channel you want alerts posted to, and click **Allow**
5. Copy the webhook URL that appears — it starts with `https://hooks.slack.com/services/...`

### Step 3 — Add secrets to GitHub

Your API key and Slack webhook are stored as **secrets** in GitHub — they are never visible in the code.

1. In this GitHub repository, click **Settings** (top menu)
2. In the left sidebar, click **Secrets and variables** → **Actions**
3. Click **New repository secret** and add each of the following:

| Secret name | Value |
|---|---|
| `GRANTS_API_KEY` | The API key from Step 1 |
| `SLACK_WEBHOOK` | The webhook URL from Step 2 |

### Step 4 — Enable GitHub Actions

1. In this repository, click the **Actions** tab (top menu)
2. If prompted, click **I understand my workflows, go ahead and enable them**

That's it. The monitor will run automatically on the next weekday at 8:00 AM Eastern.

---

## Testing it manually

To run the monitor immediately without waiting for the schedule:

1. Go to the **Actions** tab in this repository
2. Click **Grants.gov Daily Monitor** in the left sidebar
3. Click **Run workflow** → **Run workflow**

You'll see a Slack message within a minute or two and the CSV will be updated.

---

## Downloading the CSV

1. In this repository, click the `data` folder
2. Click `opportunities.csv`
3. Click the **Download raw file** button (the download icon in the top right)

---

## Fields in the CSV

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

---

## Adjusting the schedule

The monitor runs weekdays at 8:00 AM Eastern by default. To change this, edit the `cron` line in `.github/workflows/grants_monitor.yml`. Use [crontab.guru](https://crontab.guru) to build a cron expression if needed.

## Adding or removing agencies

Edit the `AGENCY_CODES` list near the top of `search_grants.py`. After saving, commit and push the change — the next run will use the updated list.

---

## Troubleshooting

**No Slack message arrived**
- Check the Actions tab for error logs — click the most recent run to see details
- Confirm `GRANTS_API_KEY` and `SLACK_WEBHOOK` are correctly saved as secrets (Step 3)

**"No new opportunities found" every day**
- The CSV already contains recent results; the monitor is working correctly but found no new items
- Try triggering a manual run after clearing `data/opportunities.csv` to confirm everything works end-to-end

**Slack message arrives but CSV isn't updating**
- Confirm the repository has **Actions write permissions** enabled (Settings → Actions → General → Workflow permissions → Read and write)

# ✨ Internship Tracker

A personal internship alert system for fashion, beauty, creative tech, and more.
Runs every 30 minutes via GitHub Actions. Notifies you by email + text the second a new matching posting appears. Zero cost, no third-party services.

---

## What it does

- Scrapes 140+ career pages every 30 minutes
- Filters for internship/co-op keywords (OR logic — any match triggers)
- Sends an **email** and a **text message** only when something new is found (silent if nothing changed)
- Tracks a live dashboard with color-coded freshness:
  - 🔵 Blue — under 1 hour (pinned to top)
  - 🟢 Green — under 2 hours
  - 🟡 Yellow — under 24 hours
  - ⚫ Gray — older
  - 🔴 Red — removed from the careers page
- Logs every run with timestamp, brands checked, new jobs found, and errors

---

## Setup (one-time, ~15 minutes)

### Step 1 — Fork or create this repo

Create a **private** repo on GitHub and push all these files to it.

```bash
git init
git add .
git commit -m "initial setup"
git remote add origin https://github.com/YOURUSERNAME/internship-tracker.git
git push -u origin main
```

---

### Step 2 — Create a Gmail App Password

Your real Gmail password won't work. You need an App Password:

1. Go to your Google Account → **Security**
2. Make sure **2-Step Verification** is ON
3. Search for **"App Passwords"**
4. Create one — name it "Internship Tracker"
5. Copy the 16-character password (e.g. `abcd efgh ijkl mnop`)

---

### Step 3 — Add GitHub Secrets

In your repo on GitHub: **Settings → Secrets and variables → Actions → New repository secret**

Add these four secrets exactly:

| Secret Name     | Value                              |
|-----------------|------------------------------------|
| `GMAIL_USER`    | `faithled03@gmail.com`             |
| `GMAIL_APP_PASS`| your 16-char app password          |
| `EMAIL_TO`      | `fa667291@ucf.edu`                 |
| `SMS_TO`        | `yournumber@tmomail.net`           |

> 💡 T-Mobile SMS gateway is `number@tmomail.net` — replace `number` with your 10-digit phone number, no dashes (e.g. `4075551234@tmomail.net`)

---

### Step 4 — Enable GitHub Actions

1. Go to the **Actions** tab in your repo
2. If prompted, click **"I understand my workflows, enable them"**
3. Click **"Internship Tracker"** in the left sidebar
4. Click **"Run workflow"** to trigger a manual first run and confirm everything works

---

### Step 5 — Enable GitHub Pages (for the dashboard)

1. Go to **Settings → Pages**
2. Source: **Deploy from a branch**
3. Branch: `main`, folder: `/ (root)`
4. Save — your dashboard will be live at:
   `https://YOURUSERNAME.github.io/internship-tracker/`

---

## Adding or removing brands

Open `brands.csv` and edit directly in GitHub (or locally). Each row has:

```
name, careers_url, ats_platform, category, notes
```

**ATS platform options:** `greenhouse`, `lever`, `workday`, `custom`

For Greenhouse brands, add the company's board slug to `GREENHOUSE_SLUG_MAP` in `scraper.py`. You can find the slug by visiting `https://boards.greenhouse.io/COMPANYNAME`.

---

## Customizing keywords

Edit the `KEYWORDS` list in `scraper.py`:

```python
KEYWORDS = [
    "intern", "internship", "co-op",
    "summer 2026", "fall 2026",
    # add anything here
]
```

---

## Customizing role categories

Edit `ROLE_PATTERNS` in `scraper.py`. Each category has a list of regex patterns matched against the job title.

---

## Running locally (for testing)

```bash
# Install dependencies
pip install -r requirements.txt

# Copy and fill in your .env
cp .env.example .env
# edit .env with your real values

# Load .env and run
export $(cat .env | xargs) && python scraper.py
```

---

## How notifications look

**Email subject:**
```
🆕 Product Management Intern @ Pinterest — New York, NY
```

**Text message:**
```
🆕 Product Management Intern @ Pinterest (New York, NY)
https://boards.greenhouse.io/pinterest/jobs/12345
```

---

## File structure

```
internship-tracker/
├── .github/
│   └── workflows/
│       └── scrape.yml       ← GitHub Actions cron (every 30 min)
├── scraper.py               ← main script
├── brands.csv               ← your brand list — edit this to add/remove
├── seen_jobs.json           ← auto-updated: tracks all known postings
├── run_log.json             ← auto-updated: history of every run
├── index.html               ← live dashboard (GitHub Pages)
├── requirements.txt
├── .env.example             ← template for local testing
├── .gitignore
└── README.md
```

---

## Notes

- GitHub Actions free tier gives you 2,000 minutes/month. At 30-min intervals that's ~1,440 runs/month — well within the free limit.
- The scraper is polite: 0.5s between brands, 1s between notifications.
- `seen_jobs.json` and `run_log.json` are committed back to the repo automatically after each run — that's how the dashboard stays up to date.
- Some brands (Workday, custom pages) are harder to scrape reliably. If a brand consistently errors, check the Run History on the dashboard and consider finding their Greenhouse/Lever slug instead.

---

## Troubleshooting

**I'm not getting emails/texts**
- Double-check your GitHub Secrets spelling (case-sensitive)
- Make sure your Gmail App Password has no spaces when you paste it
- Check the Actions tab → click the latest run → expand logs to see errors

**A brand is always erroring**
- Visit their careers URL manually — it may have changed
- Update `brands.csv` with the new URL

**Dashboard shows nothing**
- The first run needs to complete and commit `seen_jobs.json` before the dashboard has data
- Check Actions → latest run → confirm it committed successfully

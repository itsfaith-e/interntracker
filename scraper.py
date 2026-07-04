#!/usr/bin/env python3
"""
Fashion & Tech Internship Tracker
Scrapes career pages every 30 mins, notifies on new matching postings.
"""

import csv
import json
import os
import re
import smtplib
import time
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ─────────────────────────────────────────────
# CONFIG (all sensitive values come from GitHub Secrets / .env)
# ─────────────────────────────────────────────
GMAIL_USER     = os.environ["GMAIL_USER"]       # e.g. faithled03@gmail.com
GMAIL_APP_PASS = os.environ["GMAIL_APP_PASS"]   # Gmail App Password
EMAIL_TO       = os.environ["EMAIL_TO"]         # your UCF email
SMS_TO         = os.environ["SMS_TO"]           # yournumber@tmomail.net

BRANDS_FILE    = Path("brands.csv")
SEEN_FILE      = Path("seen_jobs.json")
LOG_FILE       = Path("run_log.json")

# ─────────────────────────────────────────────
# KEYWORDS  (OR logic — any match = include)
# ─────────────────────────────────────────────
KEYWORDS = [
    "intern", "internship", "co-op", "coop",
    "summer 2026", "fall 2026", "spring 2026",
    "summer 2027", "new grad", "entry level", "entry-level",
    "student", "university", "associate",
]

# ─────────────────────────────────────────────
# EXCLUSIONS (if any match = skip the posting)
# ─────────────────────────────────────────────
EXCLUDE_TITLE_KEYWORDS = [
    "senior", " sr.", " sr ",
    " vp ", "vice president",
    "sales associate", "sales representative", "sales advisor",
    "retail associate", "retail advisor", "retail lead",
    "store associate", "store lead", "store manager",
    "stock associate", "stockroom",
    "keyholder", "key holder",
    "warehouse", "distribution center",
    "cashier", "stylist", "beauty advisor", "brand ambassador",
]

EXCLUDE_LOCATIONS = [
    "milan", "milano",
    "france", "paris",
    "saudi arabia", "riyadh",
    "belgium", "brussels",
    "dubai", "uae",
]

# ─────────────────────────────────────────────
# ROLE CATEGORIES  (for dashboard tagging)
# ─────────────────────────────────────────────
ROLE_PATTERNS = {
    "Product Management": [
        r"product manager", r"product management", r"\bpm\b", r"associate pm",
        r"product lead",
    ],
    "Project Management": [
        r"project manager", r"project management", r"program manager",
        r"program management", r"tpm", r"technical program",
    ],
    "Software Engineering": [
        r"software engineer", r"software developer", r"swe\b", r"full.?stack",
        r"frontend", r"backend", r"mobile engineer",
    ],
    "Data Analytics": [
        r"data analyst", r"data science", r"data engineer", r"analytics",
        r"business intelligence", r"\bbi\b", r"machine learning", r"\bml\b",
    ],
    "Ecommerce": [
        r"ecommerce", r"e-commerce", r"digital merchandising", r"site merchandis",
        r"marketplace", r"growth",
    ],
    "AI / Machine Learning": [
        r"\bai\b", r"artificial intelligence", r"machine learning", r"\bllm\b",
        r"generative ai", r"nlp\b", r"computer vision",
    ],
    "IT & Technical Operations": [
        r"\bit\b", r"information technology", r"technical operations",
        r"systems analyst", r"infrastructure", r"devops", r"cloud",
    ],
    "Design": [
        r"ux\b", r"ui\b", r"product design", r"visual design",
        r"interaction design", r"brand design",
    ],
    "Marketing": [
        r"marketing", r"brand strategy", r"social media", r"content",
        r"communications", r"pr\b", r"public relations",
    ],
    "Other": [],
}


def keyword_match(text: str, location: str = "") -> bool:
    t = text.lower()
    loc = location.lower()

    # Must match at least one include keyword
    if not any(kw in t for kw in KEYWORDS):
        return False

    # Skip if title contains excluded keywords
    if any(ex in t for ex in EXCLUDE_TITLE_KEYWORDS):
        return False

    # Skip if location is excluded
    if any(ex in loc for ex in EXCLUDE_LOCATIONS):
        return False

    return True


def detect_role(title: str) -> str:
    t = title.lower()
    for role, patterns in ROLE_PATTERNS.items():
        if role == "Other":
            continue
        if any(re.search(p, t) for p in patterns):
            return role
    return "Other"


# ─────────────────────────────────────────────
# ATS SCRAPERS
# ─────────────────────────────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


def fetch(url: str, timeout: int = 15) -> requests.Response | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        return r
    except Exception as e:
        print(f"  ⚠️  fetch error {url}: {e}")
        return None


def scrape_greenhouse(brand: dict) -> list[dict]:
    """Greenhouse boards expose a public JSON API."""
    # Extract board slug from URL
    url = brand["careers_url"]
    # Try to extract board token from URL patterns like boards.greenhouse.io/company
    slug_match = re.search(r"boards\.greenhouse\.io/([^/?]+)", url)
    if not slug_match:
        # Fall back to domain scrape
        return scrape_generic(brand)

    slug = slug_match.group(1)
    api_url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    r = fetch(api_url)
    if not r:
        return []

    try:
        data = r.json()
    except Exception:
        return []

    jobs = []
    for job in data.get("jobs", []):
        title = job.get("title", "")
        location = (job.get("location") or {}).get("name", "Remote")
        link = job.get("absolute_url", url)
        job_id = str(job.get("id", ""))

        if not keyword_match(title + " " + (job.get("content") or ""), location):
            continue

        jobs.append({
            "id": f"{brand['name']}::{job_id}",
            "brand": brand["name"],
            "title": title,
            "location": location,
            "url": link,
            "category": brand["category"],
            "role_type": detect_role(title),
            "first_seen": datetime.now(timezone.utc).isoformat(),
            "status": "open",
        })
    return jobs


def scrape_lever(brand: dict) -> list[dict]:
    """Lever postings have a public JSON endpoint."""
    url = brand["careers_url"]
    slug_match = re.search(r"jobs\.lever\.co/([^/?]+)", url)
    if not slug_match:
        return scrape_generic(brand)

    slug = slug_match.group(1)
    api_url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    r = fetch(api_url)
    if not r:
        return []

    try:
        data = r.json()
    except Exception:
        return []

    jobs = []
    for job in data:
        title = job.get("text", "")
        location = (job.get("categories") or {}).get("location", "Remote")
        link = job.get("hostedUrl", url)
        job_id = job.get("id", "")

        if not keyword_match(title + " " + job.get("descriptionPlain", ""), location):
            continue

        jobs.append({
            "id": f"{brand['name']}::{job_id}",
            "brand": brand["name"],
            "title": title,
            "location": location,
            "url": link,
            "category": brand["category"],
            "role_type": detect_role(title),
            "first_seen": datetime.now(timezone.utc).isoformat(),
            "status": "open",
        })
    return jobs


def scrape_workday(brand: dict) -> list[dict]:
    """Workday doesn't have a public API; scrape the HTML listing."""
    return scrape_generic(brand)


def scrape_generic(brand: dict) -> list[dict]:
    """Generic HTML scraper — grabs all anchor text + hrefs, matches keywords."""
    r = fetch(brand["careers_url"])
    if not r:
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    jobs = []
    seen_ids = set()

    for a in soup.find_all("a", href=True):
        title = a.get_text(strip=True)
        if not title or len(title) < 5:
            continue
        if not keyword_match(title, location):
            continue

        href = a["href"]
        if not href.startswith("http"):
            base = brand["careers_url"].rstrip("/")
            href = base + "/" + href.lstrip("/")

        job_id = re.sub(r"[^a-z0-9]", "", title.lower())[:60]
        uid = f"{brand['name']}::{job_id}"
        if uid in seen_ids:
            continue
        seen_ids.add(uid)

        # Try to extract location from nearby text
        parent = a.parent
        location = "See posting"
        if parent:
            text = parent.get_text(" ", strip=True)
            loc_match = re.search(
                r"(remote|new york|los angeles|san francisco|london|paris|"
                r"orlando|miami|chicago|seattle|austin|boston|toronto|nyc)",
                text, re.I
            )
            if loc_match:
                location = loc_match.group(0).title()

        jobs.append({
            "id": uid,
            "brand": brand["name"],
            "title": title,
            "location": location,
            "url": href,
            "category": brand["category"],
            "role_type": detect_role(title),
            "first_seen": datetime.now(timezone.utc).isoformat(),
            "status": "open",
        })

    return jobs


# ─────────────────────────────────────────────
# GREENHOUSE URL RESOLVER
# Many brands use greenhouse but link to their own branded board.
# We'll resolve the slug from the URL.
# ─────────────────────────────────────────────
GREENHOUSE_SLUG_MAP = {
    "Pinterest": "pinterest",
    "Notion": "notion",
    "Figma": "figma",
    "Canva": "canva",
    "Spotify": "spotify",
    "Discord": "discord",
    "Etsy": "etsy",
    "Miro": "miro",
    "Webflow": "webflow",
    "Squarespace": "squarespace",
    "Airtable": "airtable",
    "Coda": "coda",
    "Asana": "asana",
    "Monday.com": "mondaydotcom",
    "Atlassian": "atlassian",
    "ClickUp": "clickup",
    "Zapier": "zapier",
    "Loom": "loomdotcom",
    "Lucid Software": "lucidsoftware",
    "MURAL": "mural",
    "Netflix": "netflix",
    "Riot Games": "riotgames",
    "Epic Games": "epicgames",
    "Roblox": "roblox",
    "Airbnb": "airbnb",
    "Duolingo": "duolingo",
    "Uber": "uber",
    "DoorDash": "doordash",
    "Stripe": "stripe",
    "Robinhood": "robinhood",
    "Calm": "calm",
    "Flo Health": "flo",
    "Rivian": "rivian",
    "Lucid Motors": "lucidmotors",
    "Polestar": "polestar",
    "OpenAI": "openai",
    "Snap": "snap",
    "Anthropic": "anthropic",
    "Perplexity": "perplexityai",
    "Scale AI": "scaleai",
    "Runway": "runwayml",
    "ElevenLabs": "elevenlabs",
    "Replit": "replit",
    "Vercel": "vercel",
    "Retool": "retool",
    "Mercury": "mercury",
    "Plaid": "plaid",
    "The Trade Desk": "thetradedesk",
    "LTK": "shopltk",
    "Depop": "depop",
    "GOAT": "goatapp",
    "StockX": "stockx",
    "The RealReal": "therealreal",
    "Farfetch": "farfetch",
    "Rent the Runway": "renttherunway",
    "Stitch Fix": "stitchfix",
    "Poshmark": "poshmark",
    "Shopify": "shopify",
    "Klaviyo": "klaviyo",
    "Faire": "faire",
    "Tapestry": "tapestry",
    "Tory Burch": "toryburch",
    "Reformation": "reformation",
    "REVOLVE": "revolve",
    "Glossier": "glossier",
    "e.l.f. Beauty": "elfbeauty",
    "Burberry": "burberry",
    "Warner Music Group": "warnermusic",
}

LEVER_SLUG_MAP = {
    "Everlane": "everlane",
    "SSENSE": "ssense",
}


def get_scraper(brand: dict):
    ats = brand["ats_platform"].strip().lower()
    name = brand["name"]

    if ats == "greenhouse" or name in GREENHOUSE_SLUG_MAP:
        slug = GREENHOUSE_SLUG_MAP.get(name)
        if slug:
            brand = dict(brand)
            brand["careers_url"] = f"https://boards.greenhouse.io/{slug}"
        return scrape_greenhouse

    if ats == "lever" or name in LEVER_SLUG_MAP:
        slug = LEVER_SLUG_MAP.get(name)
        if slug:
            brand = dict(brand)
            brand["careers_url"] = f"https://jobs.lever.co/{slug}"
        return scrape_lever

    return scrape_generic


# ─────────────────────────────────────────────
# STATE MANAGEMENT
# ─────────────────────────────────────────────
def load_seen() -> dict:
    if SEEN_FILE.exists():
        return json.loads(SEEN_FILE.read_text())
    return {}


def save_seen(data: dict):
    SEEN_FILE.write_text(json.dumps(data, indent=2))


def load_log() -> list:
    if LOG_FILE.exists():
        return json.loads(LOG_FILE.read_text())
    return []


def save_log(data: list):
    LOG_FILE.write_text(json.dumps(data, indent=2))


# ─────────────────────────────────────────────
# NOTIFICATIONS
# ─────────────────────────────────────────────
def send_email(subject: str, body_html: str, body_text: str, to: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_USER
    msg["To"]      = to
    msg.attach(MIMEText(body_text, "plain"))
    msg.attach(MIMEText(body_html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASS)
        server.sendmail(GMAIL_USER, to, msg.as_string())


def send_sms(text: str):
    """T-Mobile gateway: number@tmomail.net — plain text only."""
    msg = MIMEText(text)
    msg["Subject"] = ""
    msg["From"]    = GMAIL_USER
    msg["To"]      = SMS_TO

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASS)
        server.sendmail(GMAIL_USER, SMS_TO, msg.as_string())


def notify(job: dict):
    title    = job["title"]
    brand    = job["brand"]
    location = job["location"]
    url      = job["url"]

    subject   = f"🆕 {title} @ {brand} — {location}"
    body_text = f"{title}\n{brand} | {location}\nApply: {url}"
    body_html = f"""
    <div style="font-family:sans-serif;max-width:600px">
      <h2 style="color:#1a1a2e">🆕 New Internship Alert</h2>
      <table style="width:100%;border-collapse:collapse">
        <tr><td style="padding:8px;font-weight:bold">Role</td>
            <td style="padding:8px">{title}</td></tr>
        <tr style="background:#f5f5f5">
            <td style="padding:8px;font-weight:bold">Brand</td>
            <td style="padding:8px">{brand}</td></tr>
        <tr><td style="padding:8px;font-weight:bold">Location</td>
            <td style="padding:8px">{location}</td></tr>
      </table>
      <a href="{url}" style="display:inline-block;margin-top:16px;padding:12px 24px;
         background:#6366f1;color:white;text-decoration:none;border-radius:6px;
         font-weight:bold">Apply Now →</a>
    </div>
    """

    try:
        send_email(subject, body_html, body_text, EMAIL_TO)
        print(f"  📧 Email sent: {subject}")
    except Exception as e:
        print(f"  ❌ Email failed: {e}")

    sms_text = f"🆕 {title} @ {brand} ({location})\n{url}"
    try:
        send_sms(sms_text)
        print(f"  📱 SMS sent")
    except Exception as e:
        print(f"  ❌ SMS failed: {e}")


# ─────────────────────────────────────────────
# MAIN RUN
# ─────────────────────────────────────────────
def main():
    run_start = datetime.now(timezone.utc).isoformat()
    print(f"\n{'='*60}")
    print(f"🔍 Internship Tracker — {run_start}")
    print(f"{'='*60}\n")

    seen      = load_seen()
    log       = load_log()
    new_jobs  = []
    errors    = []
    checked   = 0

    # Load brands
    brands = []
    with open(BRANDS_FILE, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            brands.append(row)

    print(f"📋 Loaded {len(brands)} brands\n")

    for brand in brands:
        name = brand["name"]
        print(f"  Checking {name}...")
        scraper = get_scraper(brand)

        try:
            jobs = scraper(brand)
            checked += 1
        except Exception as e:
            print(f"  ❌ Error: {e}")
            errors.append({"brand": name, "error": str(e)})
            continue

        for job in jobs:
            job_id = job["id"]
            if job_id not in seen:
                # Brand new posting!
                seen[job_id] = job
                new_jobs.append(job)
                print(f"    🆕 NEW: {job['title']} @ {job['location']}")
                notify(job)
                time.sleep(1)  # be polite between notifications
            else:
                # Already seen — keep status as open
                seen[job_id]["status"] = "open"

        # Mark removed postings
        for job_id, job in seen.items():
            if job["brand"] == name:
                found_ids = {j["id"] for j in jobs}
                if job_id not in found_ids and job["status"] == "open":
                    seen[job_id]["status"] = "removed"
                    print(f"    🔴 REMOVED: {job['title']}")

        time.sleep(0.5)  # rate limit

    # Save state
    save_seen(seen)

    # Log this run
    run_entry = {
        "timestamp": run_start,
        "brands_checked": checked,
        "new_jobs_found": len(new_jobs),
        "errors": errors,
        "new_jobs": [
            {"brand": j["brand"], "title": j["title"], "url": j["url"]}
            for j in new_jobs
        ],
    }
    log.insert(0, run_entry)
    log = log[:200]  # keep last 200 runs (~4 days at 30-min intervals)
    save_log(log)

    print(f"\n{'='*60}")
    print(f"✅ Done — {len(new_jobs)} new job(s) found, {len(errors)} error(s)")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()

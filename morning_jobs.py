#!/usr/bin/env python3
"""
Morning jobs: pull recently-opened Software Engineer / SE2-level roles (<= 4 years
experience) from company career boards and push a notification to your phone via
ntfy.sh.

Standard library only (no pip install needed), so it runs in a bare GitHub Actions
runner. Edit the COMPANIES list below; tune the rest via environment variables.
"""

import html
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone, timedelta

# --------------------------------------------------------------------------
# 1) EDIT THIS LIST. ats: "greenhouse" or "lever". token: board slug (see README).
#    Entries left as "REPLACE_ME" are skipped.
# --------------------------------------------------------------------------
COMPANIES = [
    # Well-known, regular H-1B sponsors that use Greenhouse. Token = the slug in
    # their careers URL (boards.greenhouse.io/<token>). The first two are verified
    # live; the rest follow the same lowercase-name convention -- do the 30-second
    # browser check in the README before relying on each (ATS choices change).
    {"name": "Databricks", "ats": "greenhouse", "token": "databricks"},   # verified
    {"name": "Coinbase",   "ats": "greenhouse", "token": "coinbase"},     # verified
    {"name": "Pinterest",  "ats": "greenhouse", "token": "pinterest"},
    {"name": "DoorDash",   "ats": "greenhouse", "token": "doordash"},
    {"name": "Robinhood",  "ats": "greenhouse", "token": "robinhood"},
    {"name": "Plaid",      "ats": "greenhouse", "token": "plaid"},
    {"name": "Affirm",     "ats": "greenhouse", "token": "affirm"},
    {"name": "Reddit",     "ats": "greenhouse", "token": "reddit"},
    {"name": "Dropbox",    "ats": "greenhouse", "token": "dropbox"},
    {"name": "Airbnb",     "ats": "greenhouse", "token": "airbnb"},
    {"name": "Twilio",     "ats": "greenhouse", "token": "twilio"},
    {"name": "Cloudflare", "ats": "greenhouse", "token": "cloudflare"},
    {"name": "Datadog",    "ats": "greenhouse", "token": "datadog"},
    {"name": "Confluent",  "ats": "greenhouse", "token": "confluent"},
    {"name": "HashiCorp",  "ats": "greenhouse", "token": "hashicorp"},
    {"name": "Roblox",     "ats": "greenhouse", "token": "roblox"},
    {"name": "Instacart",  "ats": "greenhouse", "token": "instacart"},
    {"name": "Lyft",       "ats": "greenhouse", "token": "lyft"},
    {"name": "Brex",       "ats": "greenhouse", "token": "brex"},
    {"name": "Figma",      "ats": "greenhouse", "token": "figma"},
    {"name": "Discord",    "ats": "greenhouse", "token": "discord"},
    {"name": "Anthropic",  "ats": "greenhouse", "token": "anthropic"},
    {"name": "Rippling",   "ats": "greenhouse", "token": "rippling"},
    {"name": "GitLab",     "ats": "greenhouse", "token": "gitlab"},
    {"name": "MongoDB",    "ats": "greenhouse", "token": "mongodb"},
    {"name": "Grammarly",  "ats": "greenhouse", "token": "grammarly"},
    {"name": "Samsara",    "ats": "greenhouse", "token": "samsara"},
    {"name": "Flexport",   "ats": "greenhouse", "token": "flexport"},
    # --- Ashby (jobs.ashbyhq.com/<token>) ---
    {"name": "OpenAI",  "ats": "ashby", "token": "openai"},
    {"name": "Ramp",    "ats": "ashby", "token": "ramp"},
    {"name": "Notion",  "ats": "ashby", "token": "notion"},
    {"name": "Mercury", "ats": "ashby", "token": "mercury"},
    {"name": "Linear",  "ats": "ashby", "token": "linear"},
    # Note: FAANG, Stripe, Netflix, etc. run custom ATSes and CANNOT be pulled here
    # -- use native LinkedIn / company-careers alerts for those (see README).
]

# --------------------------------------------------------------------------
# 2) Filters (override via env vars).
# --------------------------------------------------------------------------
# Title must contain at least one INCLUDE term...
INCLUDE_TITLES = [t.strip().lower() for t in os.getenv(
    "INCLUDE_TITLES",
    "software engineer,software developer,swe,sde,backend engineer,engineer ii,engineer 2,se2,se ii"
).split(",") if t.strip()]

# ...and must contain NONE of these EXCLUDE terms (these imply > 4 yrs / wrong role).
EXCLUDE_TITLES = [t.strip().lower() for t in os.getenv(
    "EXCLUDE_TITLES",
    "senior,sr.,sr ,staff,principal,lead,manager,director,architect,head of,intern,iii,iv, v ,level 3,l3,l4,l5"
).split(",") if t.strip()]

# Keep a role only if its stated experience minimum is <= MAX_YEARS
# (roles that state no number are kept and labelled "exp: not stated").
MAX_YEARS = int(os.getenv("MAX_YEARS", "4"))

# Novelty is tracked via a "seen jobs" file persisted across runs (see workflow
# cache step), so you get each role once. WINDOW_HOURS is just a sanity bound to
# ignore very stale postings (default 60 days).
WINDOW_HOURS = int(os.getenv("JOB_WINDOW_HOURS", "1440"))
SEEN_FILE = os.getenv("SEEN_FILE", "seen.json")
MAX_NOTIFY = int(os.getenv("MAX_NOTIFY", "25"))

# Keep only US-based (or US-remote / unspecified) roles. Set US_ONLY=false to allow all.
US_ONLY = os.getenv("US_ONLY", "true").lower() == "true"

_US_STATES = ("al ak az ar ca co ct de fl ga hi id il in ia ks ky la me md ma mi mn ms mo "
              "mt ne nv nh nj nm ny nc nd oh ok or pa ri sc sd tn tx ut vt va wa wv wi wy dc").split()
_US_STATE_RE = re.compile(r',\s*(' + '|'.join(_US_STATES) + r')\b', re.I)
_US_HINTS = [
    "united states", "usa", "u.s.", "u.s.a", "remote - us", "remote, us", "remote (us",
    "us remote", "new york", "san francisco", "seattle", "austin", "boston", "chicago",
    "los angeles", "denver", "atlanta", "mountain view", "palo alto", "sunnyvale", "san jose",
    "bellevue", "san mateo", "redwood city", "menlo park", "cambridge", "brooklyn", "bay area",
]
_NON_US = [
    "india", "bengaluru", "bangalore", "hyderabad", "gurgaon", "gurugram", "pune", "mumbai",
    "chennai", "noida", "delhi", "canada", "toronto", "vancouver", "montreal", "united kingdom",
    "london", "manchester", "ireland", "dublin", "germany", "berlin", "munich", "france", "paris",
    "netherlands", "amsterdam", "spain", "madrid", "barcelona", "portugal", "lisbon", "poland",
    "krakow", "warsaw", "romania", "bucharest", "singapore", "australia", "sydney", "melbourne",
    "new zealand", "japan", "tokyo", "china", "shanghai", "hong kong", "korea", "seoul", "taiwan",
    "israel", "tel aviv", "brazil", "mexico", "colombia", "argentina", "sweden", "switzerland",
    "zurich", "united arab emirates", "dubai", "uae", "philippines", "vietnam", "indonesia",
    "malaysia", "thailand", "italy", "milan", "austria", "vienna", "belgium", "denmark", "norway",
    "finland", "greece", "czech", "prague", "emea", "apac", "latam",
]

NTFY_SERVER = os.getenv("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
NTFY_TOPIC = os.getenv("NTFY_TOPIC", "")
NOTIFY_WHEN_EMPTY = os.getenv("NOTIFY_WHEN_EMPTY", "false").lower() == "true"

_UA = {"User-Agent": "morning-jobs/1.1 (+github actions)"}

# Experience patterns. Ranges first ("2-12+ years" -> 2), then "<n> years ... experience".
_EXP_RANGE = re.compile(r'(\d{1,2})\s*[-\u2013]\s*\d{1,2}\s*\+?\s*years?', re.I)
_EXP_NEAR = re.compile(r'(\d{1,2})\s*\+?\s*years?(?:\s+[\w-]+){0,6}?\s+experience', re.I)
_EXP_ANY = re.compile(r'(\d{1,2})\s*\+?\s*years?', re.I)
_TAGS = re.compile(r'<[^>]+>')


def _get_json(url):
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read().decode("utf-8"))


def _parse_iso(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _plain(text):
    return html.unescape(_TAGS.sub(" ", text or ""))


def min_years(text):
    """Best-effort: smallest plausible years-of-experience minimum in the text."""
    text = _plain(text)
    nums = [int(n) for n in _EXP_RANGE.findall(text)]   # lower bound of any range
    nums += [int(n) for n in _EXP_NEAR.findall(text)]
    if not nums:
        nums = [int(n) for n in _EXP_ANY.findall(text)]
    nums = [n for n in nums if 0 < n <= 30]
    return min(nums) if nums else None


def title_ok(title):
    t = f" {title.lower()} "
    if INCLUDE_TITLES and not any(k in t for k in INCLUDE_TITLES):
        return False
    if any(k in t for k in EXCLUDE_TITLES):
        return False
    return True


def location_ok(loc):
    """Keep US, US-remote, and unspecified roles; drop clearly non-US ones."""
    if not US_ONLY:
        return True
    l = (loc or "").lower()
    has_us = any(h in l for h in _US_HINTS) or bool(_US_STATE_RE.search(loc or ""))
    has_non_us = any(c in l for c in _NON_US)
    return has_us or not has_non_us


def fetch_greenhouse(token):
    data = _get_json(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true")
    out = []
    for j in data.get("jobs", []):
        out.append({
            "title": j.get("title", ""),
            "url": j.get("absolute_url", ""),
            "location": (j.get("location") or {}).get("name", ""),
            "posted": _parse_iso(j.get("updated_at", "")),
            "desc": j.get("content", ""),
        })
    return out


def fetch_lever(token):
    data = _get_json(f"https://api.lever.co/v0/postings/{token}?mode=json")
    out = []
    for j in data:
        ts = j.get("createdAt")
        posted = datetime.fromtimestamp(ts / 1000, tz=timezone.utc) if ts else None
        cats = j.get("categories") or {}
        lists = " ".join(f"{x.get('text','')} {x.get('content','')}" for x in (j.get("lists") or []))
        desc = " ".join([j.get("descriptionPlain", ""), lists, j.get("additionalPlain", "")])
        out.append({
            "title": j.get("text", ""),
            "url": j.get("hostedUrl", ""),
            "location": cats.get("location", ""),
            "posted": posted,
            "desc": desc,
        })
    return out


def fetch_ashby(token):
    data = _get_json(f"https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=false")
    out = []
    for j in data.get("jobs", []):
        if j.get("isListed") is False:
            continue
        out.append({
            "title": j.get("title", ""),
            "url": j.get("jobUrl") or j.get("applyUrl") or "",
            "location": j.get("location", ""),
            "posted": _parse_iso(j.get("publishedAt", "")),
            "desc": j.get("descriptionPlain", "") or j.get("descriptionHtml", ""),
        })
    return out


FETCHERS = {"greenhouse": fetch_greenhouse, "lever": fetch_lever, "ashby": fetch_ashby}


def select(jobs):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=WINDOW_HOURS)
    keep = []
    for j in jobs:
        dt = j["posted"]
        if dt is not None and dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if dt is None or dt < cutoff:
            continue
        if not title_ok(j["title"]):
            continue
        if not location_ok(j["location"]):
            continue
        yrs = min_years(j["desc"])
        if yrs is not None and yrs > MAX_YEARS:
            continue
        j["years"] = yrs
        keep.append(j)
    return keep


def notify(title, body):
    if not NTFY_TOPIC:
        print("[notify] NTFY_TOPIC not set; skipping phone push.", file=sys.stderr)
        return
    req = urllib.request.Request(
        f"{NTFY_SERVER}/{NTFY_TOPIC}",
        data=body.encode("utf-8"),
        method="POST",
        headers={"Title": title, "Tags": "briefcase", **_UA},
    )
    try:
        urllib.request.urlopen(req, timeout=30)
        print(f"[notify] pushed to {NTFY_SERVER}/{NTFY_TOPIC}")
    except Exception as e:  # noqa: BLE001
        print(f"[notify] push failed: {e}", file=sys.stderr)


def load_seen():
    try:
        with open(SEEN_FILE) as f:
            return set(json.load(f)), True
    except (OSError, ValueError):
        return set(), False  # first run (no usable seen file yet)


def save_seen(ids):
    try:
        with open(SEEN_FILE, "w") as f:
            json.dump(sorted(ids), f)
    except OSError as e:  # noqa: BLE001
        print(f"[seen] could not write {SEEN_FILE}: {e}", file=sys.stderr)


def _format(jobs):
    lines = []
    for j in jobs[:MAX_NOTIFY]:
        loc = f" \u2014 {j['location']}" if j["location"] else ""
        exp = f"{j['years']}+ yrs" if j.get("years") is not None else "exp: not stated"
        lines.append(f"\u2022 {j['company']}: {j['title']}{loc}  [{exp}]\n  {j['url']}")
    if len(jobs) > MAX_NOTIFY:
        lines.append(f"...and {len(jobs) - MAX_NOTIFY} more.")
    return "\n".join(lines)


def main():
    matching, errors, ok = [], [], 0
    for c in COMPANIES:
        fetch = FETCHERS.get(c.get("ats"))
        token = c.get("token", "")
        if fetch is None or token in ("", "REPLACE_ME"):
            continue
        try:
            jobs = select(fetch(token))
            ok += 1
            for j in jobs:
                j["company"] = c["name"]
            matching.extend(jobs)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{c['name']} ({c['ats']}/{token}): {e}")

    matching.sort(key=lambda j: j["posted"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

    seen, had_seen = load_seen()
    current_ids = {j["url"] for j in matching if j["url"]}
    new_jobs = matching if not had_seen else [j for j in matching if j["url"] not in seen]
    save_seen(current_ids)

    print(f"[summary] {ok}/{len(COMPANIES)} boards reachable, {len(errors)} skipped, "
          f"{len(matching)} matching role(s), {len(new_jobs)} new"
          f"{' (first run = baseline)' if not had_seen else ''}.")
    if errors:
        print("[warnings] skipped boards -- fix or remove these tokens:\n  " + "\n  ".join(errors),
              file=sys.stderr)

    if not new_jobs:
        if NOTIFY_WHEN_EMPTY:
            notify("Morning jobs", "No new SE2/SWE roles today.")
        return

    body = _format(new_jobs)
    print(body)
    label = "current SE2/SWE role(s) (baseline)" if not had_seen else "NEW SE2/SWE role(s)"
    notify(f"{len(new_jobs)} {label}", body)


if __name__ == "__main__":
    main()

# Morning jobs → phone notification

Pulls newly-opened roles from company career boards every morning at 5:30 AM and
pushes a notification to your phone. Runs on GitHub Actions (free) — no server,
no always-on machine, no paid services.

## How it works

1. A scheduled GitHub Action runs `morning_jobs.py` once a day.
2. The script queries each company's public job-board API (Greenhouse / Lever),
   keeps only roles posted in the last ~26 hours whose title matches your
   keywords, and formats a short digest.
3. It POSTs the digest to an [ntfy.sh](https://ntfy.sh) topic, which the free
   ntfy app on your phone receives as a push notification.

## One-time setup (~10 minutes)

1. **Create a repo.** Make a new GitHub repo (private is fine) and add these two
   files, keeping the paths:
   - `morning_jobs.py`
   - `.github/workflows/morning-jobs.yml`

2. **Install ntfy + pick a topic.** Install the **ntfy** app (iOS / Android).
   Choose a hard-to-guess topic name — anyone who knows it can send to it —
   e.g. `pavan-jobs-9f3a2c`. In the app, tap **+** and subscribe to that topic.

3. **Add the topic as a repo secret.** In the repo: **Settings → Secrets and
   variables → Actions → New repository secret**. Name it `NTFY_TOPIC`, value =
   your topic name (just `pavan-jobs-9f3a2c`, not a URL).

4. **List your companies.** Open `morning_jobs.py` and edit the `COMPANIES` list.
   For each company you want to track, you need its **ATS** (`greenhouse` or
   `lever`) and its **board token** — see "Finding a board token" below.

5. **Test it now.** Go to the repo's **Actions** tab → **morning-jobs** → **Run
   workflow**. Within a few seconds you should get a push on your phone (or, if
   nothing matched the last 26h, the run log will say so). The run log also
   prints the full digest.

That's it. It now runs automatically around 5:30 AM Pacific each day.

## Finding a board token

The token is the company slug in their public careers URL:

- **Greenhouse** — careers page looks like
  `https://job-boards.greenhouse.io/<token>` or `https://boards.greenhouse.io/<token>`.
  The API the script calls is `https://boards-api.greenhouse.io/v1/boards/<token>/jobs`.
- **Lever** — careers page looks like `https://jobs.lever.co/<token>`.
  The API is `https://api.lever.co/v0/postings/<token>?mode=json`.

Quick check: paste the API URL into a browser. If you see JSON with job
listings, the token is right.

## Tuning

Set these as repo secrets/variables or edit the workflow `env:` block:

| Variable | Default | Meaning |
|---|---|---|
| `NTFY_TOPIC` | (required) | Your ntfy topic name |
| `MAX_YEARS` | `4` | Keep a role only if its stated experience minimum is at or below this. Roles that state no number are kept and labelled "exp: not stated" |
| `US_ONLY` | `true` | Keep only US, US-remote, and unspecified-location roles; drop clearly non-US ones |
| `INCLUDE_TITLES` | software engineer, software developer, swe, sde, backend engineer, engineer ii, engineer 2, se2, se ii | Title must contain one of these |
| `EXCLUDE_TITLES` | senior, sr., staff, principal, lead, manager, director, architect, head of, intern, iii, iv, l3, l4, l5 | Title is dropped if it contains any of these (filters out > 4-yr / wrong-level roles) |
| `JOB_WINDOW_HOURS` | `48` | How recent a posting must be to count (48h gives more coverage; a role may notify on two consecutive mornings) |
| `NOTIFY_WHEN_EMPTY` | `false` | Set `true` to also get a "nothing new" ping |

The experience cap reads each job description and pulls the smallest plausible
"N years" figure (handling ranges like "2-12+ years" as a 2-year floor). It's a
best-effort text parse, so an oddly-worded posting can occasionally slip through
or be missed — treat it as a strong filter, not a guarantee.

Schedule: edit the `cron` line in the workflow. It's UTC. `30 12 * * *` is
5:30 AM Pacific in summer (PDT); switch to `30 13 * * *` in winter (PST), or
leave it and accept a one-hour seasonal drift. GitHub may also delay scheduled
runs by a few minutes at peak times.

## What this can and can't cover

**Can:** the large tier of companies on Greenhouse, Lever, or Ashby public
boards. The script ships seeded with ~33 well-known, regular H-1B sponsors
across these ATSes (Databricks, Coinbase, Pinterest, DoorDash, Robinhood, Plaid,
Affirm, Reddit, Dropbox, Airbnb, Twilio, Cloudflare, Datadog, Confluent,
HashiCorp, Roblox, Instacart, Lyft, Brex, Figma, Discord, Anthropic, Rippling,
GitLab, MongoDB, Grammarly, Samsara, Flexport, and via Ashby: OpenAI, Ramp,
Notion, Mercury, Linear). A stale or wrong token just logs a warning and is
skipped, so the run never breaks — verify any you depend on with the browser
check above.

**Can't:** the mega-caps. Google, Meta, Amazon, Apple, Microsoft, Stripe,
Netflix, Nvidia, and similar run **custom career systems** with no public
Greenhouse/Lever API, so they can't be pulled here. Cover those with native
alerts, which already deliver on a schedule:

- A **LinkedIn job alert** (e.g. "Software Engineer" + each company, set to daily).
- A job alert on each company's own careers page.
- The **Indeed connector** in this chat, on demand.

## Targeting H-1B sponsors specifically

To decide which companies to add, use authoritative public petition data rather
than guessing:

- **USCIS H-1B Employer Data Hub** (`uscis.gov/tools/reports-and-studies/h-1b-employer-data-hub`)
  — search any employer's approved/denied petition counts by year.
- **MyVisaJobs** (`myvisajobs.com`) — ranked lists of the top H-1B sponsors,
  filterable by occupation and year.

Pick the sponsors you care about, then add the ones that use Greenhouse/Lever to
`COMPANIES`. Send me a batch and I'll look up each one's ATS and board token.

## Adding more sources

The script supports `greenhouse` and `lever` out of the box. To add another ATS
(e.g. Ashby, Workday) or a job-board RSS feed, add a `fetch_<name>(token)`
function that returns a list of `{"title","url","location","posted"}` dicts and
register it in the `FETCHERS` map. Ask me and I'll write it.

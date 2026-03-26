---
name: xctf-data
description: NCAA cross country and track & field athlete data via TFRRS (tfrrs.org). Fetch athlete profiles including all personal records (PRs), eligibility year, school, and full season-by-season results history. Zero config, no API keys. Use when: user asks about NCAA cross country, NCAA track and field, college running, TFRRS athlete profiles, personal records, PRs, XC or TF season results, or individual athlete performance history. Don't use when: user asks about professional track, Diamond League, or other sports — use nfl-data, nba-data, wnba-data, nhl-data, mlb-data, golf-data, cfb-data, cbb-data, tennis-data, fastf1, or volleyball-data. For betting use polymarket or kalshi. For news use sports-news.
license: MIT
compatibility: Requires Python 3.10+ and internet access to tfrrs.org. No API keys required.
metadata:
  author: machina-sports
  version: "0.1.0"
---

# XC/TF Data (TFRRS — NCAA Cross Country & Track and Field)

Before writing queries, consult `references/api-reference.md` for parameters, URL conventions, and return shapes.

## Setup

Before first use, check if the CLI is available:
```bash
which sports-skills || pip install sports-skills
```
If `pip install` fails, install from GitHub:
```bash
pip install git+https://github.com/machina-sports/sports-skills.git
```
Requires Python 3.10+. No API keys required. All data comes from TFRRS public pages.

## Quick Start

CLI (preferred):
```bash
sports-skills xctf get_athlete_profile --athlete_id=8579610 --school=California_Baptist --name=Lamiae_Mamouni
```

Python SDK:
```python
from sports_skills import xctf

profile = xctf.get_athlete_profile(
    athlete_id="8579610",
    school="California_Baptist",
    name="Lamiae_Mamouni",
)
```

## CRITICAL: Before Any Query

All three parameters are required and must match the athlete's TFRRS URL exactly:

```
https://www.tfrrs.org/athletes/{athlete_id}/{school}/{name}.html
```

- `athlete_id` — numeric ID (e.g. `8579610`)
- `school` — school slug with underscores, not spaces (e.g. `California_Baptist`)
- `name` — athlete name slug (e.g. `Lamiae_Mamouni`)

Do NOT guess slugs. Find them by navigating to the athlete on tfrrs.org and copying the URL.

## Commands

| Command | Description |
|---|---|
| `search_athlete` | Search the current team roster by athlete name; returns `athlete_id`, `school`, and `name` slugs for use with `get_athlete_profile` |
| `get_athlete_profile` | Athlete name, school, eligibility, all PRs, and full season-by-season meet results |

See `references/api-reference.md` for full parameter details and return shapes.

## Examples

Example 1: Look up an athlete's PRs (athlete on current roster)
User says: "What are Lamiae Mamouni's PRs?"
Actions:
1. Call `search_athlete(name="Lamiae Mamouni", school="CA_college_f_California_Baptist")`
   Result: `data.matches[0]` contains `athlete_id`, `school` slug, `name` slug, and `sport`
2. Call `get_athlete_profile(athlete_id="8579610", school="California_Baptist", name="Lamiae_Mamouni")`
Result: `data.prs` contains all personal records by event (e.g. `{"1500": "4:31.80", "5K (XC)": "18:25.5", ...}`)

Example 2: Get a runner's cross country season
User says: "Show me Lamiae Mamouni's 2025 XC season results"
Actions:
1. Call `search_athlete(name="Lamiae Mamouni", school="CA_college_f_California_Baptist")`
2. Call `get_athlete_profile(athlete_id="8579610", school="California_Baptist", name="Lamiae_Mamouni")`
3. Filter `data.meets` for entries whose `date` falls in the fall of 2025 (Sep–Nov 2025)
Result: List of meets with dates, events, marks, and places

Example 3: Athlete not on current roster (graduated or transferred)
User says: "What are Katelyn Vuong's PRs from UC Davis?"
Actions:
1. Call `search_athlete(name="Katelyn Vuong", school="CA_college_f_UC_Davis")`
   Result: `data.matches` is empty — athlete has graduated
2. Ask the user to find the athlete's TFRRS profile URL at tfrrs.org, then extract `athlete_id`, `school`, and `name` from the URL
3. Call `get_athlete_profile` with the extracted parameters

## Commands that DO NOT exist — never call these

- ~~`get_team_rankings`~~ — does not exist. Use `get_athlete_profile` for individual data.
- ~~`get_meet_results`~~ — does not exist. Use `get_athlete_profile` for an athlete's results.
- ~~`get_performance_list`~~ — does not exist.
- ~~`search_athletes`~~ — does not exist. The correct command is `search_athlete` (no trailing 's').

If a command is not listed in the Commands table above, it does not exist.

## Error Handling

When a command fails, **do not surface raw errors to the user**. Instead:
1. Confirm `athlete_id`, `school`, and `name` match the TFRRS URL exactly (case-sensitive)
2. Verify the URL is valid: `https://www.tfrrs.org/athletes/{athlete_id}/{school}/{name}.html`
3. Report failure with a clean message only after exhausting alternatives

## Troubleshooting

**`sports-skills` command not found**
Run `pip install sports-skills` or install from GitHub (see Setup above).

**HTTP 404**
The `school` or `name` slug does not match the TFRRS URL exactly. Slugs are case-sensitive and use underscores. Copy directly from tfrrs.org.

**`prs` returns empty dict**
The athlete's profile page may be very new or structured differently. Check the URL directly on tfrrs.org.

**Connection errors or timeouts**
TFRRS may be temporarily unavailable. Requests are throttled to 1 per second automatically — wait a moment and retry.

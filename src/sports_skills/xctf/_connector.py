"""TFRRS (Track & Field Results Reporting System) connector.

Fetches NCAA cross country and track & field athlete profiles from tfrrs.org
by parsing public HTML pages. No API keys required.

URL format: https://www.tfrrs.org/athletes/{id}/{School_Slug}/{First_Last}.html
"""

from __future__ import annotations

import re
import time
import urllib.error
import urllib.parse
import urllib.request

_BASE = "https://www.tfrrs.org"
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

_MIN_INTERVAL = 1.0
_last_request_time = 0.0

_cache: dict[str, tuple[float, str]] = {}
_CACHE_TTL = 300


def _throttle() -> None:
    global _last_request_time
    now = time.monotonic()
    elapsed = now - _last_request_time
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    _last_request_time = time.monotonic()


def _fetch(url: str) -> str | dict:
    """Fetch a URL and return the response body as a string."""
    now = time.monotonic()
    cached = _cache.get(url)
    if cached and (now - cached[0]) < _CACHE_TTL:
        return cached[1]

    _throttle()
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": _UA,
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        _cache[url] = (time.monotonic(), html)
        return html
    except urllib.error.HTTPError as e:
        return {"error": True, "message": f"HTTP {e.code}: {e.reason}", "url": url}
    except urllib.error.URLError as e:
        return {"error": True, "message": f"Connection error: {e.reason}"}
    except Exception as e:
        return {"error": True, "message": str(e)}


def _strip_tags(html: str) -> str:
    """Strip HTML tags and normalize whitespace."""
    text = re.sub(r"<[^>]+>", " ", html)
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&uarr;", "")
        .replace("&gt;", ">")
        .replace("&lt;", "<")
    )
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------


def _parse_prs(table_html: str) -> dict[str, str]:
    """Parse the top PR summary table — cells alternate event name / mark."""
    tds = re.findall(r"<td[^>]*>(.*?)</td>", table_html, re.DOTALL | re.IGNORECASE)
    cells = [_strip_tags(td) for td in tds]
    cells = [c for c in cells if c]

    prs: dict[str, str] = {}
    i = 0
    while i < len(cells) - 1:
        event = cells[i]
        mark = cells[i + 1]
        # Mark should start with a digit (time or distance), not a letter
        if event and mark and mark[:1].isdigit():
            prs[event] = mark
            i += 2
        else:
            i += 1
    return prs


def _parse_meet_table(table_html: str) -> dict | None:
    """Parse a single meet result table into meet name, date, and results.

    Returns None if the first row does not contain a date — this filters out
    per-event cumulative tables (season bests, year bests) that share the same
    section HTML but are not meet result tables.
    """
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, re.DOTALL | re.IGNORECASE)
    if not rows:
        return None

    meet_name = ""
    meet_date = ""
    results: list[dict] = []
    header_found = False

    for row_html in rows:
        cells = re.findall(
            r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, re.DOTALL | re.IGNORECASE
        )
        texts = [_strip_tags(c) for c in cells]
        texts = [t for t in texts if t]
        if not texts:
            continue

        row_text = " ".join(texts)

        if not header_found:
            # First data row must contain a date to be a meet result table.
            # Per-event summary tables have no date in their header row.
            date_m = re.search(
                r"([A-Z][a-z]{2,8}\.?\s+\d{1,2}(?:[–\-]\d{1,2})?,\s*\d{4})",
                row_text,
            )
            if not date_m:
                return None
            meet_date = date_m.group(1)
            meet_name = row_text[: date_m.start()].strip().lstrip('>"').strip()
            # Per-event all-time tables start with a time/distance mark before the meet
            # name (e.g. "2:13.37 (-0.3) 2024 WAC..." or "18:25.5 Mark Covert...").
            # Real meet names may start with digits (years, ordinals) but never with
            # a time mark pattern (digits immediately followed by ':' or '.').
            if meet_name and re.match(r"^\d+[:.]\d", meet_name):
                return None
            header_found = True
            continue

        # Subsequent rows: event, mark[, place]
        if len(texts) >= 2:
            result: dict = {"event": texts[0], "mark": texts[1]}
            if len(texts) >= 3:
                result["place"] = texts[2]
            results.append(result)

    if not header_found:
        return None

    return {"meet": meet_name, "date": meet_date, "results": results}


def _parse_athlete_profile(html: str) -> dict:
    """Parse a full TFRRS athlete profile HTML page."""
    # Remove scripts and styles to avoid false matches
    html = re.sub(
        r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE
    )
    html = re.sub(
        r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE
    )

    # --- All h3 tags in document order ---
    # TFRRS uses h3 for: athlete name (first), school (second), season labels (rest)
    h3_matches = list(
        re.finditer(r"<h3[^>]*>(.*?)</h3>", html, re.DOTALL | re.IGNORECASE)
    )

    # --- Name and eligibility from first h3 ---
    name = ""
    eligibility = ""
    if h3_matches:
        h3_text = _strip_tags(h3_matches[0].group(1))
        elig_m = re.search(r"\(([^)]+)\)", h3_text)
        if elig_m:
            eligibility = elig_m.group(1)
            name = h3_text[: elig_m.start()].strip().title()
        else:
            name = h3_text.strip().title()

    # --- School abbreviation from second h3 ---
    school = ""
    if len(h3_matches) >= 2:
        school = _strip_tags(h3_matches[1].group(1))

    # --- PRs from the first table on the page ---
    all_tables = re.findall(
        r"<table[^>]*>(.*?)</table>", html, re.DOTALL | re.IGNORECASE
    )
    prs = _parse_prs(all_tables[0]) if all_tables else {}

    # --- Meet results ---
    # All individual meet result tables are in the section between the school h3
    # (h3_matches[1]) and the first season-label h3 (e.g. "2026 Outdoors").
    # The season-label h3 sections only contain per-event summary tables, not meets.
    season_pattern = re.compile(r"^\d{4}\s+(XC|Outdoors|Indoors)", re.IGNORECASE)
    season_h3s = [
        m for m in h3_matches if season_pattern.match(_strip_tags(m.group(1)))
    ]

    meets_section_start = h3_matches[1].end() if len(h3_matches) >= 2 else 0
    meets_section_end = season_h3s[0].start() if season_h3s else len(html)
    meets_section = html[meets_section_start:meets_section_end]

    meets: list[dict] = []
    for table_html in re.findall(
        r"<table[^>]*>(.*?)</table>", meets_section, re.DOTALL | re.IGNORECASE
    ):
        meet = _parse_meet_table(table_html)
        if meet:
            meets.append(meet)

    return {
        "name": name,
        "school": school,
        "eligibility": eligibility,
        "prs": prs,
        "meets": meets,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


_DDG_LITE = "https://lite.duckduckgo.com/lite/"


def _search_duckduckgo_lite(name: str, school: str = "") -> list[dict]:
    """Search DuckDuckGo Lite for TFRRS athlete profile URLs.

    Returns a deduplicated list of dicts with athlete_id, school, name slugs.
    sport is None because it cannot be determined from search results alone.
    """
    query = f"site:tfrrs.org/athletes {name}"
    if school:
        query += f" {school}"

    url = f"{_DDG_LITE}?q={urllib.parse.quote(query)}"
    result = _fetch(url)
    if isinstance(result, dict):
        return []  # fetch error — graceful fallback

    raw = re.findall(
        r"tfrrs\.org/athletes/(\d+)/([^/\"<>&\s]+)/([^\"<>&\s]+?)(?:\.html)?(?=[\"<>&\s])",
        result,
    )
    seen: set[tuple] = set()
    matches: list[dict] = []
    for athlete_id, school_slug, name_slug in raw:
        key = (athlete_id, school_slug, name_slug)
        if key in seen:
            continue
        seen.add(key)
        matches.append(
            {
                "athlete_id": athlete_id,
                "school": school_slug,
                "name": name_slug,
                "sport": None,
                "url": f"{_BASE}/athletes/{athlete_id}/{school_slug}/{name_slug}.html",
            }
        )
    return matches


def _parse_team_roster(html: str) -> list[dict]:
    """Extract athlete links from a TFRRS team page.

    Returns a deduplicated list of dicts with athlete_id, school, and name slugs.
    """
    # Athlete links on team pages: /athletes/{id}/{school_slug}/{name_slug}.html
    # Some entries in the top-marks section omit the .html extension.
    raw = re.findall(
        r'href="/athletes/(\d+)/([^/"]+)/([^".]+?)(?:\.html)?"',
        html,
    )
    seen: set[tuple] = set()
    athletes: list[dict] = []
    for athlete_id, school_slug, name_slug in raw:
        key = (athlete_id, school_slug, name_slug)
        if key in seen:
            continue
        seen.add(key)
        athletes.append(
            {"athlete_id": athlete_id, "school": school_slug, "name": name_slug}
        )
    return athletes


def search_athlete(*, name: str, school: str = "") -> dict:
    """Search for a TFRRS athlete by name, with optional school filter.

    First checks the current team roster (fast, exact). If no match is found
    — e.g. the athlete has graduated or transferred — falls back to a
    DuckDuckGo Lite search scoped to tfrrs.org. Works for current and
    historical athletes. No API keys required.

    Args:
        name: Athlete name to search for (e.g. "Katelyn Vuong").
        school: School name or TFRRS team slug (e.g. "UC Davis" or
            "CA_college_f_UC_Davis"). Optional but recommended to narrow
            results when the name is common.
    """
    name_parts = name.lower().split()
    matches: list[dict] = []
    seen_keys: set[tuple] = set()

    # Step 1: Try the current team roster pages if school looks like a
    # TFRRS team slug (underscores, no spaces).
    if school and "_" in school and " " not in school:
        for sport in ("xc", "tf"):
            url = f"{_BASE}/teams/{sport}/{school}.html"
            result = _fetch(url)
            if isinstance(result, dict):
                continue

            for athlete in _parse_team_roster(result):
                key = (athlete["athlete_id"], sport)
                if key in seen_keys:
                    continue
                display = athlete["name"].replace("_", " ").lower()
                if all(part in display for part in name_parts):
                    seen_keys.add(key)
                    matches.append(
                        {
                            **athlete,
                            "sport": sport,
                            "url": (
                                f"{_BASE}/athletes/{athlete['athlete_id']}"
                                f"/{athlete['school']}/{athlete['name']}.html"
                            ),
                        }
                    )

    # Step 2: Fall back to DuckDuckGo Lite search (covers all athletes,
    # including graduated and transferred).
    if not matches:
        for m in _search_duckduckgo_lite(name, school):
            # Filter by name — all parts of the search name must appear in
            # the returned name slug to exclude partial DDG matches.
            display = m["name"].replace("_", " ").lower()
            if not all(part in display for part in name_parts):
                continue
            key = (m["athlete_id"], m["school"], m["name"])
            if key not in seen_keys:
                seen_keys.add(key)
                matches.append(m)

    return {"matches": matches}


def get_athlete_profile(
    *, athlete_id: str, school: str, name: str
) -> dict:
    """Fetch a TFRRS athlete profile: PRs and full results history.

    Args:
        athlete_id: TFRRS numeric athlete ID (e.g. "8579610").
        school: School slug as it appears in the TFRRS URL (e.g. "California_Baptist").
        name: Athlete name slug as it appears in the TFRRS URL (e.g. "Lamiae_Mamouni").
    """
    url = f"{_BASE}/athletes/{athlete_id}/{school}/{name}.html"
    result = _fetch(url)
    if isinstance(result, dict):
        return result  # error dict — caller wraps

    profile = _parse_athlete_profile(result)
    profile["athlete_id"] = athlete_id
    profile["url"] = url
    return profile

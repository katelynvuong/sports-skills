"""NCAA cross country and track & field data via TFRRS (tfrrs.org).

Fetches athlete profiles, personal records, and full results history
by parsing the Track & Field Results Reporting System public pages.
No API keys required.
"""

from __future__ import annotations

from sports_skills._response import wrap
from sports_skills.xctf import _connector


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
    result = _connector.search_athlete(name=name, school=school)
    return wrap(result)


def get_athlete_profile(*, athlete_id: str, school: str, name: str) -> dict:
    """Fetch a TFRRS athlete profile including PRs and full results history.

    Args:
        athlete_id: TFRRS numeric athlete ID (e.g. "8579610").
        school: School slug as it appears in the TFRRS URL (e.g. "California_Baptist").
        name: Athlete name slug as it appears in the TFRRS URL (e.g. "Lamiae_Mamouni").
    """
    result = _connector.get_athlete_profile(
        athlete_id=athlete_id, school=school, name=name
    )
    return wrap(result)

"""NCAA cross country and track & field data via TFRRS (tfrrs.org).

Fetches athlete profiles, personal records, and full results history
by parsing the Track & Field Results Reporting System public pages.
No API keys required.
"""

from __future__ import annotations

from sports_skills._response import wrap
from sports_skills.xctf import _connector


def search_athlete(*, name: str, school: str) -> dict:
    """Search XC and TF team roster pages for athletes matching a name.

    Searches the current-season roster only. Athletes who have graduated or
    transferred may not appear — use get_athlete_profile directly if you
    have their athlete_id from their TFRRS profile URL.

    Args:
        name: Athlete name to search for (e.g. "Lamiae Mamouni").
        school: TFRRS team slug as it appears in the team page URL
            (e.g. "CA_college_f_UC_Davis"). Find it at:
            https://www.tfrrs.org/teams/{xc|tf}/{school}.html
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

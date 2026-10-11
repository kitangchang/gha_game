"""New Zealand time and UTC, including daylight saving, without needing a time
zone database (Windows Pythons often lack one).

NZ daylight saving rules since 1974 (both changes happen at 02:00 NZST, which is
14:00 UTC on the Saturday before):
  1974          starts first Sunday in November
  1975          ends last Sunday in February
  1975-1988     starts last Sunday in October
  1976-1989     ends first Sunday in March
  1989          starts second Sunday in October
  1990-2006     starts first Sunday in October
  1990-2007     ends third Sunday in March
  2007-         starts last Sunday in September
  2008-         ends first Sunday in April
"""
from __future__ import annotations

from bisect import bisect_right
from datetime import date, datetime, timedelta

NZST, NZDT = 12, 13
FIRST_YEAR, LAST_YEAR = 1974, 2100
_EPOCH = datetime(1970, 1, 1)
_TRANSITIONS: list = []       # UTC epoch seconds, alternately DST on / DST off


def _sunday_on_or_after(year: int, month: int, day: int) -> date:
    d = date(year, month, day)
    return d + timedelta(days=(6 - d.weekday()) % 7)


def _last_sunday(year: int, month: int) -> date:
    nxt = date(year + month // 12, month % 12 + 1, 1)
    d = nxt - timedelta(days=1)
    return d - timedelta(days=(d.weekday() + 1) % 7)


def dst_start(year: int) -> date | None:
    """The Sunday daylight saving begins in `year` (spring), or None."""
    if year < 1974:
        return None
    if year == 1974:
        return _sunday_on_or_after(1974, 11, 1)
    if year <= 1988:
        return _last_sunday(year, 10)
    if year == 1989:
        return _sunday_on_or_after(1989, 10, 8)
    if year <= 2006:
        return _sunday_on_or_after(year, 10, 1)
    return _last_sunday(year, 9)


def dst_end(year: int) -> date | None:
    """The Sunday daylight saving ends in `year` (autumn), or None."""
    if year < 1975:
        return None
    if year == 1975:
        return _last_sunday(1975, 2)
    if year <= 1989:
        return _sunday_on_or_after(year, 3, 1)
    if year <= 2007:
        return _sunday_on_or_after(year, 3, 15)
    return _sunday_on_or_after(year, 4, 1)


def _change_seconds(d: date) -> float:
    """02:00 NZST on local date d, as UTC epoch seconds (14:00 UTC the day before)."""
    return (datetime(d.year, d.month, d.day) - timedelta(hours=NZST - 2) - _EPOCH).total_seconds()


def _transitions() -> list:
    if not _TRANSITIONS:
        out = []
        for year in range(FIRST_YEAR, LAST_YEAR + 1):
            for d in (dst_end(year), dst_start(year)):
                if d is not None:
                    out.append(_change_seconds(d))
        _TRANSITIONS.extend(sorted(out))
    return _TRANSITIONS


def nz_offset_hours(utc_seconds: float) -> int:
    """Hours NZ is ahead of UTC at this moment (12 or 13)."""
    return NZDT if bisect_right(_transitions(), utc_seconds) % 2 else NZST


def nz_offset_for_local(local_minutes: float) -> int:
    """Hours ahead of UTC for an NZ wall-clock time, given as minutes since
    1970-01-01 00:00 local. (The skipped and repeated hours resolve to NZDT.)"""
    return NZDT if nz_offset_hours((local_minutes - NZDT * 60) * 60) == NZDT else NZST


def local_minutes(utc_seconds: float, daylight_saving: bool = True, fixed_offset: float = NZST) -> float:
    """UTC epoch seconds -> NZ local minutes since 1970-01-01 00:00 local."""
    offset = nz_offset_hours(utc_seconds) if daylight_saving else fixed_offset
    return utc_seconds / 60.0 + offset * 60.0


def day_utc_offset(source: str, day_start_hour: int, minute: float, daylight_saving: bool = True,
                   fixed_offset: float = NZST) -> float:
    """UTC offset during a replayed catalogue day.

    source: the day's label ('2016-11-14' for a real day; anything else is synthetic)
    minute: minutes since the game day started (at day_start_hour)."""
    if not daylight_saving:
        return fixed_offset
    try:
        d = datetime.strptime(source, "%Y-%m-%d")
    except (TypeError, ValueError):
        return fixed_offset
    local = (d - _EPOCH).total_seconds() / 60.0 + day_start_hour * 60 + minute
    return nz_offset_for_local(local)

"""NYSE session calendar (2026-2027) and session arithmetic. Alert-only bot: a wrong date here changes an exit date, never an order."""
import datetime as dt

D = dt.date
HOLIDAYS = {
    # 2026
    D(2026, 1, 1), D(2026, 1, 19), D(2026, 2, 16), D(2026, 4, 3), D(2026, 5, 25), D(2026, 6, 19),
    D(2026, 7, 3), D(2026, 9, 7), D(2026, 11, 26), D(2026, 12, 25),
    # 2027 (Jun 19 is a Saturday -> Fri Jun 18; Jul 4 is a Sunday -> Mon Jul 5; Dec 25 is a Saturday -> Fri Dec 24)
    D(2027, 1, 1), D(2027, 1, 18), D(2027, 2, 15), D(2027, 3, 26), D(2027, 5, 31), D(2027, 6, 18),
    D(2027, 7, 5), D(2027, 9, 6), D(2027, 11, 25), D(2027, 12, 24),
}
EARLY_CLOSE = {D(2026, 11, 27), D(2026, 12, 24), D(2027, 11, 26)}   # 13:00 ET; 2027 list is a best estimate, verify before relying on it
CALENDAR_END = D(2027, 12, 31)


class CalendarExpired(RuntimeError):
    pass


def _check(d: dt.date):
    if d > CALENDAR_END:
        raise CalendarExpired(f"NYSE calendar in bot/nyse.py ends {CALENDAR_END}; extend HOLIDAYS before {d}")


def is_session(d: dt.date) -> bool:
    _check(d)
    return d.weekday() < 5 and d not in HOLIDAYS


def add_sessions(d: dt.date, n: int) -> dt.date:
    """The date n sessions after d (n >= 0). d need not itself be a session."""
    cur = d
    while n > 0:
        cur += dt.timedelta(days=1)
        if is_session(cur):
            n -= 1
    return cur


def sessions_between(a: dt.date, b: dt.date) -> int:
    """Number of sessions in (a, b]."""
    n, cur = 0, a
    while cur < b:
        cur += dt.timedelta(days=1)
        if is_session(cur):
            n += 1
    return n


def close_time(d: dt.date) -> dt.time:
    return dt.time(13, 0) if d in EARLY_CLOSE else dt.time(16, 0)

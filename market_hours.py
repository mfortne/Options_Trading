"""
Market hours checker
Determines if US stock market is currently open.
Handles weekends, federal holidays, and 9:30am-4pm ET window.
"""

from datetime import datetime, date, timedelta
import zoneinfo


# ---------------------------------------------------------------------------
# US Federal Market Holidays (add new years as needed)
# ---------------------------------------------------------------------------

def _get_market_holidays(year: int) -> set:
    """
    Return set of market holidays for a given year.
    Uses fixed and floating rules for each holiday.
    """
    holidays = set()

    # New Year's Day (Jan 1, observed Mon if Sun)
    nyd = date(year, 1, 1)
    if nyd.weekday() == 6:
        nyd = date(year, 1, 2)
    holidays.add(nyd)

    # Martin Luther King Jr. Day (3rd Monday of January)
    holidays.add(_nth_weekday(year, 1, 0, 3))

    # Presidents Day (3rd Monday of February)
    holidays.add(_nth_weekday(year, 2, 0, 3))

    # Good Friday (Friday before Easter)
    holidays.add(_good_friday(year))

    # Memorial Day (last Monday of May)
    holidays.add(_last_weekday(year, 5, 0))

    # Juneteenth (June 19, observed Mon if Sun, Fri if Sat)
    jt = date(year, 6, 19)
    if jt.weekday() == 6:
        jt = date(year, 6, 20)
    elif jt.weekday() == 5:
        jt = date(year, 6, 18)
    holidays.add(jt)

    # Independence Day (July 4, observed Mon if Sun, Fri if Sat)
    id4 = date(year, 7, 4)
    if id4.weekday() == 6:
        id4 = date(year, 7, 5)
    elif id4.weekday() == 5:
        id4 = date(year, 7, 3)
    holidays.add(id4)

    # Labor Day (1st Monday of September)
    holidays.add(_nth_weekday(year, 9, 0, 1))

    # Thanksgiving (4th Thursday of November)
    holidays.add(_nth_weekday(year, 11, 3, 4))

    # Christmas (Dec 25, observed Mon if Sun, Fri if Sat)
    xmas = date(year, 12, 25)
    if xmas.weekday() == 6:
        xmas = date(year, 12, 26)
    elif xmas.weekday() == 5:
        xmas = date(year, 12, 24)
    holidays.add(xmas)

    return holidays


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """Return the nth occurrence of weekday (0=Mon) in given month/year."""
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + (n - 1) * 7)


def _last_weekday(year: int, month: int, weekday: int) -> date:
    """Return the last occurrence of weekday (0=Mon) in given month/year."""
    if month == 12:
        last = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last = date(year, month + 1, 1) - timedelta(days=1)
    offset = (last.weekday() - weekday) % 7
    return last - timedelta(days=offset)


def _good_friday(year: int) -> date:
    """Calculate Good Friday using the Anonymous Gregorian algorithm."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    easter = date(year, month, day)
    return easter - timedelta(days=2)  # Good Friday = 2 days before Easter


# ---------------------------------------------------------------------------
# Main check
# ---------------------------------------------------------------------------

def is_market_open() -> tuple:
    """
    Check if the US stock market is currently open.

    Returns:
        (is_open: bool, reason: str)
    """
    et = zoneinfo.ZoneInfo("America/New_York")
    now_et = datetime.now(et)
    today = now_et.date()

    # Weekend check
    if today.weekday() >= 5:
        day_name = "Saturday" if today.weekday() == 5 else "Sunday"
        return False, f"Weekend ({day_name})"

    # Holiday check
    holidays = _get_market_holidays(today.year)
    if today in holidays:
        return False, f"Market Holiday"

    # Market hours check (9:30am - 4:00pm ET)
    market_open  = now_et.replace(hour=9,  minute=30, second=0, microsecond=0)
    market_close = now_et.replace(hour=16, minute=0,  second=0, microsecond=0)

    if now_et < market_open:
        return False, f"Before market open (opens 9:30am ET, now {now_et.strftime('%I:%M%p')} ET)"

    if now_et >= market_close:
        return False, f"After market close (closed 4:00pm ET, now {now_et.strftime('%I:%M%p')} ET)"

    return True, f"Market open ({now_et.strftime('%I:%M%p')} ET)"


def market_status_message(is_open: bool, reason: str) -> str:
    """Build a Telegram message for market status."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    if is_open:
        return f"✅ *Market Open* — starting scan\n🕐 {now}"
    else:
        return f"🔴 *Market Closed*\n🕐 {now}\nReason: {reason}"


if __name__ == "__main__":
    # Quick test
    open_, reason = is_market_open()
    print(f"Market open: {open_}")
    print(f"Reason: {reason}")

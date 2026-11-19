"""Years a type beat title may advertise on a given publication day.

In November and December viewers already search next year's term, so both the
current and the next year are valid; from 1 January only the current year is.
"""
from datetime import date

FIRST_NEXT_YEAR_MONTH = 11


def years_for(day: date) -> list[int]:
    if day.month >= FIRST_NEXT_YEAR_MONTH:
        return [day.year, day.year + 1]
    return [day.year]

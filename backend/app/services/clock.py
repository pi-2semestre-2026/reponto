"""Local-time helpers: the product speaks "dia do mercado" (America/Sao_Paulo by
default), while the DB stores UTC timestamps. All date windows and daily
buckets are computed in the app timezone."""

import datetime as dt
import os
from zoneinfo import ZoneInfo

_TZ_NAME = os.environ.get("APP_TZ", "America/Sao_Paulo")

try:
    LOCAL_TZ = ZoneInfo(_TZ_NAME)
except Exception:
    LOCAL_TZ = dt.timezone(dt.timedelta(hours=-3))

LOCAL_TZ_NAME = _TZ_NAME


def now_local() -> dt.datetime:
    return dt.datetime.now(LOCAL_TZ)


def today_local() -> dt.date:
    return now_local().date()


def local_date(d: dt.datetime) -> dt.date:
    """Local calendar date of a (possibly UTC) datetime."""
    if d.tzinfo is None:
        return d.date()
    return d.astimezone(LOCAL_TZ).date()


def day_bounds(date_from: dt.date, date_to: dt.date) -> tuple[dt.datetime, dt.datetime]:
    """[from 00:00, to+1 00:00) in local time, as aware datetimes for SQL."""
    start = dt.datetime.combine(date_from, dt.time.min, tzinfo=LOCAL_TZ)
    end = dt.datetime.combine(date_to + dt.timedelta(days=1), dt.time.min, tzinfo=LOCAL_TZ)
    return start, end
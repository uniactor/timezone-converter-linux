"""Time-zone display helpers with no GUI dependencies."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

WEEKDAYS = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")


def fmt_gmt(delta: timedelta | None) -> str:
    if delta is None:
        return "GMT"
    minutes = int(delta.total_seconds() // 60)
    sign = "+" if minutes >= 0 else "−"
    minutes = abs(minutes)
    hours, mins = divmod(minutes, 60)
    if mins:
        return f"GMT{sign}{hours}:{mins:02d}"
    return f"GMT{sign}{hours}"


def fmt_rel(delta: timedelta) -> str:
    minutes = int(round(delta.total_seconds() / 60))
    sign = "+" if minutes >= 0 else "−"
    minutes = abs(minutes)
    hours, mins = divmod(minutes, 60)
    return f"{sign}{hours}:{mins:02d}"


def fmt_date(moment: datetime) -> str:
    return f"{moment.month}月{moment.day}日 {WEEKDAYS[moment.weekday()]}"


def is_dst(moment: datetime) -> bool:
    offset = moment.dst()
    return offset is not None and offset != timedelta(0)


_DST_CACHE: dict[tuple[str, int], bool] = {}


def observes_dst(tz_name: str, year: int) -> bool:
    key = (tz_name, year)
    cached = _DST_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        zone = ZoneInfo(tz_name)
        january = datetime(year, 1, 15, 12, tzinfo=zone)
        july = datetime(year, 7, 15, 12, tzinfo=zone)
        result = january.utcoffset() != july.utcoffset()
    except Exception:
        result = False
    _DST_CACHE[key] = result
    return result


def season_label(local: datetime) -> str:
    key = getattr(local.tzinfo, "key", None)
    if not key or not observes_dst(key, local.year):
        return ""
    return "夏令时" if is_dst(local) else "冬令时"


def _season_anchor(tz_a: str, tz_b: str, year: int) -> str | None:
    observing = [name for name in (tz_a, tz_b) if observes_dst(name, year)]
    if not observing:
        return None
    for name in observing:
        if name.startswith("Europe/"):
            return name
    return observing[0]


def mechanism_name(tz_a: str, tz_b: str, moment: datetime) -> str:
    """Name of the season currently in effect, preferring a European zone."""
    year = moment.astimezone(ZoneInfo(tz_a)).year
    anchor = _season_anchor(tz_a, tz_b, year)
    if anchor is None:
        return ""
    return season_label(moment.astimezone(ZoneInfo(anchor)))


def ahead_text(first_label: str, first_offset: timedelta, second_label: str, second_offset: timedelta) -> str:
    minutes = int(round((second_offset - first_offset).total_seconds() / 60))
    if minutes == 0:
        return "时间相同"
    label = second_label if minutes > 0 else first_label
    minutes = abs(minutes)
    hours, mins = divmod(minutes, 60)
    if hours and mins:
        body = f"{hours} 小时 {mins} 分"
    elif hours:
        body = f"{hours} 小时"
    else:
        body = f"{mins} 分"
    return f"{label}快 {body}"


def day_note(local: datetime, primary: datetime) -> str:
    delta = (local.date() - primary.date()).days
    if delta == 1:
        return "次日"
    if delta == -1:
        return "前一天"
    if delta > 1:
        return f"+{delta}天"
    if delta < -1:
        return f"{delta}天"
    return ""


def local_at(tz_name: str, moment: datetime) -> datetime:
    return moment.astimezone(ZoneInfo(tz_name))

"""Purpose-city date and time helpers for Shanghai product behavior."""

from datetime import datetime
from zoneinfo import ZoneInfo

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def shanghai_now():
    return datetime.now(SHANGHAI_TZ)


def shanghai_today():
    return shanghai_now().date()

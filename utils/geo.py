from __future__ import annotations

import math
from decimal import Decimal

EARTH_RADIUS_M = 6371000.0


def haversine_meters(
    lat1: Decimal | float,
    lng1: Decimal | float,
    lat2: Decimal | float,
    lng2: Decimal | float,
) -> float:
    la1 = math.radians(float(lat1))
    lo1 = math.radians(float(lng1))
    la2 = math.radians(float(lat2))
    lo2 = math.radians(float(lng2))
    dla = la2 - la1
    dlo = lo2 - lo1
    h = math.sin(dla / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin(dlo / 2) ** 2
    c = 2 * math.asin(min(1.0, math.sqrt(h)))
    return EARTH_RADIUS_M * c

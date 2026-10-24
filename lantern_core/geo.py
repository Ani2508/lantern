from __future__ import annotations

import math

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def site_distance_km(sites_by_id: dict[str, dict], a: str, b: str) -> float:
    if a not in sites_by_id or b not in sites_by_id:
        return 0.0
    sa, sb = sites_by_id[a], sites_by_id[b]
    return round(haversine_km(sa["lat"], sa["lon"], sb["lat"], sb["lon"]), 2)

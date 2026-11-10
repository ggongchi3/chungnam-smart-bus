"""WGS84 representative-point distances, never advertised as road distances."""
from math import asin, cos, radians, sin, sqrt


def haversine_meters(a, b):
    lat1, lat2 = radians(a['latitude']), radians(b['latitude'])
    dlat = lat2 - lat1
    dlon = radians(b['longitude'] - a['longitude'])
    value = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6371008.8 * 2 * asin(min(1, sqrt(value)))


def destination_key(item):
    return (item.distanceMeters is None, item.distanceMeters or 0, item.name, item.destinationId)

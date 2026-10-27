from datetime import datetime, timezone

from backend.models.schemas import Quality


def aware_time(value):
    return value if isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None else None


def freshness(source, now):
    if aware_time(source) is None:
        return 'unknown'
    age = (now.astimezone(timezone.utc) - source.astimezone(timezone.utc)).total_seconds()
    return 'unknown' if age < 0 else ('fresh' if age <= 90 else 'stale')


def quality(source, fetched, now, source_id='demo-fixture'):
    return Quality(sourceId=source_id, sourceUpdatedAt=aware_time(source), fetchedAt=aware_time(fetched),
                   freshness=freshness(source, now))


def refresh_quality(value, now):
    return quality(value.sourceUpdatedAt, value.fetchedAt, now, value.sourceId)

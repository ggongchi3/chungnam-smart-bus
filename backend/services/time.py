from datetime import timezone

from backend.models.schemas import Quality


def freshness(source, now):
    if source is None:
        return 'unknown'
    age = (now.astimezone(timezone.utc) - source.astimezone(timezone.utc)).total_seconds()
    return 'unknown' if age < 0 else ('fresh' if age <= 90 else 'stale')


def quality(source, fetched, now, source_id='demo-fixture'):
    return Quality(sourceId=source_id, sourceUpdatedAt=source, fetchedAt=fetched,
                   freshness=freshness(source, now))

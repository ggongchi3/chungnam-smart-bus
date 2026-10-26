from pydantic import ValidationError
from time import monotonic

from backend.models import schemas as s


async def interpret(boundary, text, destinations, data_mode):
    started = monotonic()
    payload = {'text': text, 'dataMode': data_mode,
               'allowedDestinations': [d.model_dump(include={'destinationId', 'name', 'aliases'}) for d in destinations]}
    raw = await boundary.call('interpret_destination', payload)
    fallback = s.InterpretationData(status='unavailable', candidates=[], reasonCode='AI_UNAVAILABLE')
    try:
        value = s.AIInterpretation.model_validate(raw)
        allowed = {d.destinationId: d for d in destinations}
        ids = value.candidateDestinationIds
        if len(ids) != len(set(ids)) or not set(ids).issubset(allowed):
            return fallback
        if (value.status in ('matched', 'needs_confirmation')) != bool(ids):
            return fallback
        if value.status == 'matched' and len(ids) != 1:
            return fallback
        if monotonic() - started > boundary.budget:
            return fallback
        # Never expose model-generated explanations; backend owns reason codes.
        reasons = {'matched': 'USER_CONFIRMATION_REQUIRED', 'needs_confirmation': 'USER_CONFIRMATION_REQUIRED',
                   'no_match': 'NO_MATCH', 'unavailable': 'AI_UNAVAILABLE'}
        return s.InterpretationData(status=value.status, candidates=[allowed[k] for k in ids],
                                     reasonCode=reasons[value.status])
    except (ValidationError, TypeError, ValueError):
        return fallback


def template_text(segment):
    if segment.type == 'bus':
        return (f'{segment.boardStation.name}에서 {segment.routeName} 버스를 타세요. '
                f'{segment.stopCount}개 정류장을 지나 {segment.alightStation.name}에서 내리세요.')
    if segment.type == 'transfer':
        return f'{segment.atStation.name}에서 다음 안내의 버스로 갈아타세요.'
    distance = f' 거리는 {segment.distanceMeters}미터입니다.' if segment.distanceMeters is not None else ' 거리와 이동 시간은 확인되지 않았습니다.'
    return f'{segment.fromLabel}에서 {segment.toLabel}까지 걸어가세요.' + distance


def fixed_guidance(detail, data_mode='demo'):
    steps = [s.Step(segmentId=p.segmentId, text=template_text(p)) for p in detail.segments]
    if data_mode == 'demo' and steps:
        steps[0].text = s.NOTICE + '. ' + steps[0].text
    return s.GuidanceData(routeSnapshotVersion=detail.routeSnapshotVersion, mode='template_fallback', steps=steps)


async def guidance(boundary, detail, data_mode):
    started = monotonic()
    fallback = fixed_guidance(detail, data_mode)
    payload = {'routeSnapshotVersion': detail.routeSnapshotVersion, 'dataMode': data_mode,
        'verifiedSegments': [{'segmentId': p.segmentId, 'type': p.type, 'allowedTemplateIds': [p.type + '.basic']}
                             for p in detail.segments]}
    raw = await boundary.call('choose_guidance', payload)
    try:
        value = s.AIGuidance.model_validate(raw)
        expected = [(p.segmentId, p.type + '.basic') for p in detail.segments]
        actual = [(p.segmentId, p.templateId) for p in value.steps]
        if (value.status == 'ok' and value.routeSnapshotVersion == detail.routeSnapshotVersion and
                actual == expected and monotonic() - started <= boundary.budget):
            return fallback.model_copy(update={'mode': 'ai_assisted'})
    except (ValidationError, TypeError, ValueError):
        pass
    return fallback

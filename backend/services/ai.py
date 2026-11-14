from pydantic import ValidationError
from time import monotonic

from ai.conversation import dialogue, explain
from ai.conversation.understand import SORTS
from backend.models import schemas as s


def interpretation_payload(text, destinations, data_mode):
    return {'text': text, 'dataMode': data_mode,
            'allowedDestinations': [d.model_dump(include={'destinationId', 'name', 'aliases'}) for d in destinations]}


def checked_interpretation(raw, destinations, reload_destinations, deadline):
    fallback = s.InterpretationData(status='unavailable', candidates=[], reasonCode='AI_UNAVAILABLE')
    try:
        if (type(raw) is not dict or type(raw.get('candidateDestinationIds')) is not list or
                len(raw['candidateDestinationIds']) > len(destinations)):
            return fallback
        value = s.AIInterpretation.model_validate(raw)
        allowed = {d.destinationId: d for d in destinations}
        ids = value.candidateDestinationIds
        if len(ids) != len(set(ids)) or not set(ids).issubset(allowed):
            return fallback
        # Candidate order is part of the internal AI contract: choose a
        # subsequence of the registered list, never introduce a model ranking.
        if ids != [key for key in allowed if key in set(ids)]:
            return fallback
        if (value.status in ('matched', 'needs_confirmation')) != bool(ids):
            return fallback
        if value.status == 'matched' and len(ids) != 1:
            return fallback
        if reload_destinations is not None and ids:
            # AI may finish after registration data changes. Check both the
            # original allow-list and the current catalog, then bind fresh facts.
            current = {d.destinationId: d for d in reload_destinations()}
            if not set(ids).issubset(current):
                return fallback
            allowed = current
        if monotonic() > deadline:
            return fallback
        # Never expose model-generated explanations; backend owns reason codes.
        reasons = {'matched': 'MATCHED', 'needs_confirmation': 'USER_CONFIRMATION_REQUIRED',
                   'no_match': 'NO_REGISTERED_MATCH', 'unavailable': 'AI_UNAVAILABLE'}
        # The current catalog owns ordering as well as coordinates and distance.
        # An adapter that completes after location updates must not restore its
        # earlier ranking when the catalog has been reloaded.
        candidates = [destination for key, destination in allowed.items() if key in set(ids)]
        return s.InterpretationData(status=value.status, candidates=candidates,
                                     reasonCode=reasons[value.status])
    except (ValidationError, TypeError, ValueError):
        return fallback


async def interpret(boundary, text, destinations, data_mode, *, reload_destinations=None):
    deadline = monotonic() + boundary.budget
    raw = await boundary.call('interpret_destination', interpretation_payload(text, destinations, data_mode))
    return checked_interpretation(raw, destinations, reload_destinations, deadline)


async def understand(boundary, text, destinations, data_mode, *, reload_destinations):
    deadline = monotonic() + boundary.budget
    raw = await boundary.call('understand_request', interpretation_payload(text, destinations, data_mode)) or {}
    result = checked_interpretation(raw.get('destination'), destinations, reload_destinations, deadline)
    preference = raw.get('preference')
    sort = preference.get('sort') if isinstance(preference, dict) else None
    clarification = None
    if result.status == 'needs_confirmation':
        names = [candidate.model_dump(include={'destinationId', 'name'}) for candidate in result.candidates]
        message = explain.clarify({'candidates': names})
        if message['status'] == 'ok':
            clarification = s.Clarification(question=message['question'], options=message['options'])
    return s.ConversationData(**result.model_dump(), clarification=clarification,
                              sort=sort if result.status != 'unavailable' and sort in SORTS else None)


def explain_search(search, sort):
    for option in search.routeOptions:
        if option.routeNames:
            result = explain.explain_route({'routeOption': option.model_dump(), 'sort': sort if sort in SORTS else None})
            option.reasonText = result['text']
    return search


async def answer(boundary, detail, question, previous_intent):
    route = detail.model_dump(mode='json')
    payload = {'routeDetail': route, 'question': question}
    raw = await boundary.call('answer_question', payload)
    if not raw or raw.get('status') != 'ok':
        return s.AnswerData(status='unavailable')
    # Bind the selected intent to the current route. Repeating a reply never
    # requires accepting arbitrary display or speech text from the client.
    intent = raw.get('intent')
    if intent not in dialogue.INTENTS:
        return s.AnswerData(status='unavailable')
    if intent == 'repeat' and previous_intent:
        try:
            payload['previousAnswer'] = dialogue.reply(previous_intent, route)
        except (KeyError, ValueError, TypeError):
            pass
    result = dialogue.answer(payload, classify_intent=lambda _: intent)
    return s.AnswerData.model_validate(result)


def print_headline(detail):
    return explain.print_headline({'routeDetail': detail.model_dump(mode='json')})['text']


def spoken_stop(station):
    return f'{station.name} {station.arsId}번 정류장' if station.arsId else station.name


def template_text(segment):
    if segment.type == 'bus':
        direction = f'{segment.directionLabel}입니다. ' if segment.directionLabel else ''
        movement = '이동 후' if direction else '지나'
        return (f'{spoken_stop(segment.boardStation)}에서 {segment.routeName} 버스를 타세요. '
                f'{direction}{segment.stopCount}개 정류장을 {movement} {spoken_stop(segment.alightStation)}에서 내리세요.')
    if segment.type == 'transfer':
        return f'{spoken_stop(segment.atStation)}에서 다음 안내의 버스로 갈아타세요.'
    if segment.distanceMeters is None and segment.durationSeconds is None:
        return f'{segment.fromLabel}에서 {segment.toLabel}까지 걸어가세요. 거리와 이동 시간은 확인되지 않았습니다.'
    distance = (f' 거리는 {segment.distanceMeters}미터입니다.' if segment.distanceMeters is not None
                else ' 거리는 확인되지 않았습니다.')
    seconds = segment.durationSeconds
    if seconds is None:
        duration = ' 이동 시간은 확인되지 않았습니다.'
    elif seconds < 60:
        duration = f' 이동 시간은 {seconds}초입니다.'
    else:
        # Match the kiosk and printed guide's rounded-up minute display.
        minutes = (seconds + 59) // 60
        duration = f' 이동 시간은 약 {minutes}분입니다.'
    return f'{segment.fromLabel}에서 {segment.toLabel}까지 걸어가세요.' + distance + duration


def fixed_guidance(detail, data_mode='demo'):
    steps = [s.Step(segmentId=p.segmentId, text=template_text(p)) for p in detail.segments]
    if data_mode == 'demo' and steps:
        steps[0].text = s.NOTICE + '. ' + steps[0].text
    elif detail.dataSource == 'cheonan-bis-static' and steps and detail.estimatedTravelSeconds is not None:
        minutes = (detail.estimatedTravelSeconds + 59) // 60
        steps[0].text = f'대기시간을 제외한 예상 이동시간은 약 {minutes}분입니다. ' + steps[0].text
    return s.GuidanceData(routeSnapshotVersion=detail.routeSnapshotVersion, mode='template_fallback', steps=steps)


async def guidance(boundary, detail, data_mode):
    started = monotonic()
    fallback = fixed_guidance(detail, data_mode)
    payload = {'routeSnapshotVersion': detail.routeSnapshotVersion, 'dataMode': data_mode,
        'verifiedSegments': [{'segmentId': p.segmentId, 'type': p.type, 'allowedTemplateIds': [p.type + '.basic']}
                             for p in detail.segments]}
    raw = await boundary.call('choose_guidance', payload)
    try:
        if (type(raw) is not dict or type(raw.get('steps')) is not list or
                len(raw['steps']) != len(detail.segments) or any(type(p) is not dict for p in raw['steps'])):
            return fallback
        value = s.AIGuidance.model_validate(raw)
        expected = [(p.segmentId, p.type + '.basic') for p in detail.segments]
        actual = [(p.segmentId, p.templateId) for p in value.steps]
        if (value.status == 'ok' and value.routeSnapshotVersion == detail.routeSnapshotVersion and
                actual == expected and monotonic() - started <= boundary.budget):
            return fallback.model_copy(update={'mode': 'ai_assisted'})
    except (ValidationError, TypeError, ValueError):
        pass
    return fallback

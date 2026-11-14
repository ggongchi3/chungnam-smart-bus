from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from backend.models import schemas as s
from backend.integrations.providers import read_provider
from backend.integrations.cheonan_live import arrival_state, arrival_state_many
from backend.api.errors import changed, unavailable
from backend.services import ai, catalog, journeys

router = APIRouter(prefix='/api/v1', responses={status: {'model': s.Envelope[None]} for status in (400,404,409,410,503,500)})
cheonan_router = APIRouter(prefix=router.prefix, responses=router.responses)


def session(request: Request):
    with request.app.state.database.session() as value:
        yield value


Session = Annotated[object, Depends(session)]


def state(request):
    now = request.app.state.clock()
    return now, read_provider(request.app.state.provider, now)


def response(request, data):
    return {'data': data, 'error': None, 'meta': {
        'requestId': request.state.request_id, 'generatedAt': request.app.state.clock(),
        'dataMode': request.app.state.settings.data_mode}}


@router.get('/stations/{stationId}', response_model=s.Envelope[s.StationData], response_model_exclude_unset=True)
async def station(stationId: s.Identifier, request: Request, db: Session):
    now, provider = state(request)
    journeys.require_core(provider)
    transport = request.app.state.transport
    station_data = transport.station(stationId) if transport else catalog.station(db, stationId)
    return response(request, s.StationData(station=station_data))


@router.get('/destinations', response_model=s.Envelope[s.DestinationData])
async def destinations(request: Request, db: Session, params: Annotated[s.DestinationQuery, Query()]):
    now, provider = state(request)
    journeys.require_core(provider)
    return response(request, s.DestinationData(destinations=catalog.destinations(
        db, params.originStationId, params.query, params.category, visible_ids=request.app.state.place_ids,
        kind=params.kind, sort=params.sort, transport=request.app.state.transport)))


@router.post('/route-searches', response_model=s.Envelope[s.SearchData])
def search(body: s.SearchRequest, request: Request, db: Session):
    # FastAPI runs this CPU/SQLite-only handler in its worker pool. Cold graph
    # matching must not block station/live requests on the ASGI event loop.
    now, provider = state(request)
    result = journeys.create_search(db, body, provider, now, request.app.state.settings.data_mode, transport=request.app.state.transport)
    return response(request, ai.explain_search(result, body.sort) if body.explain else result)


@router.get('/route-searches/{routeSearchId}/options/{routeOptionId}', response_model=s.Envelope[s.RouteDetail])
async def detail(routeSearchId: s.Identifier, routeOptionId: s.Identifier, request: Request, db: Session):
    now, provider = state(request)
    result = journeys.checked_detail(db, routeSearchId, routeOptionId, provider, now, request.app.state.settings.data_mode, transport=request.app.state.transport)
    return response(request, result)


@router.get('/route-searches/{routeSearchId}/options/{routeOptionId}/live', response_model=s.Envelope[s.LiveData])
async def live(routeSearchId: s.Identifier, routeOptionId: s.Identifier, request: Request, db: Session):
    now, provider = state(request)
    result = journeys.checked_detail(db, routeSearchId, routeOptionId, provider, now, request.app.state.settings.data_mode, transport=request.app.state.transport)
    if result.dataSource == 'cheonan-bis-static':
        provider = await arrival_state(result, now)
    return response(request, journeys.live_info(result, provider, now, session=db))


@cheonan_router.get('/route-searches/{routeSearchId}/arrivals', response_model=s.Envelope[s.SearchArrivals])
async def search_arrivals(routeSearchId: s.Identifier, request: Request, db: Session):
    now, provider = state(request)
    search = journeys.checked_search(db, routeSearchId, now)
    data_mode = request.app.state.settings.data_mode
    transport = request.app.state.transport
    journeys.require_core(provider)
    if search.data_mode != data_mode or search.origin_station_id != transport.origin['stationId']:
        changed()
    if len(search.snapshot) > 12:
        unavailable()
    details = [journeys.checked_detail(db, routeSearchId, option_id, provider, now, data_mode,
        transport=transport) for option_id in search.snapshot]
    arrivals = await arrival_state_many(details, now)
    return response(request, s.SearchArrivals(routeSearchId=routeSearchId, options={
        detail.routeOptionId: s.OptionArrivals(routeSnapshotVersion=detail.routeSnapshotVersion,
            arrivals=journeys.arrival_values(detail, arrivals, now)) for detail in details
    }))


@router.post('/destination-interpretations', response_model=s.Envelope[s.InterpretationData])
async def interpretation(body: s.InterpretationRequest, request: Request, db: Session):
    return await interpret_request(body, request, db, ai.interpret)


@router.post('/conversation/understand', response_model=s.Envelope[s.ConversationData])
async def understand(body: s.InterpretationRequest, request: Request, db: Session):
    return await interpret_request(body, request, db, ai.understand)


async def interpret_request(body, request, db, interpret):
    now, provider = state(request)
    journeys.require_core(provider)
    allowed = catalog.destinations(db, body.originStationId, visible_ids=request.app.state.place_ids, transport=request.app.state.transport)

    def current_candidates():
        _, latest_provider = state(request)
        journeys.require_core(latest_provider)
        with request.app.state.database.session() as latest_db:
            return catalog.destinations(latest_db, body.originStationId, visible_ids=request.app.state.place_ids, transport=request.app.state.transport)

    result = await interpret(request.app.state.ai, body.text, allowed, request.app.state.settings.data_mode,
                             reload_destinations=current_candidates)
    return response(request, result)


def selected(request, db, body):
    now, provider = state(request)
    detail = journeys.checked_detail(db, body.routeSearchId, body.routeOptionId, provider, now,
        request.app.state.settings.data_mode, body.expectedRouteSnapshotVersion, transport=request.app.state.transport)
    return now, provider, detail


@router.post('/easy-guidance', response_model=s.Envelope[s.GuidanceData])
async def guidance(body: s.SelectionRequest, request: Request, db: Session):
    now, provider, detail = selected(request, db, body)
    result = await ai.guidance(request.app.state.ai, detail, request.app.state.settings.data_mode)
    selected(request, db, body)  # A slow adapter must not bypass expiration / changed transport.
    return response(request, result)


@router.post('/print-guides', response_model=s.Envelope[s.PrintData])
async def print_guide(body: s.SelectionRequest, request: Request, db: Session):
    now, provider, detail = selected(request, db, body)
    return response(request, journeys.print_guide(detail, provider, now, session=db,
                    data_mode=request.app.state.settings.data_mode))


@router.post('/conversation/answers', response_model=s.Envelope[s.AnswerData])
async def answer(body: s.QuestionRequest, request: Request, db: Session):
    _, _, detail = selected(request, db, body)
    result = await ai.answer(request.app.state.ai, detail, body.question, body.previousIntent)
    selected(request, db, body)
    return response(request, result)

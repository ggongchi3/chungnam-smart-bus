from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from backend.models import schemas as s
from backend.integrations.providers import read_provider
from backend.services import ai, catalog, journeys

router = APIRouter(prefix='/api/v1', responses={status: {'model': s.Envelope[None]} for status in (400,404,409,410,503,500)})


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


@router.get('/stations/{stationId}', response_model=s.Envelope[s.StationData])
async def station(stationId: s.Identifier, request: Request, db: Session):
    now, provider = state(request)
    journeys.require_core(provider)
    return response(request, s.StationData(station=catalog.station(db, stationId)))


@router.get('/destinations', response_model=s.Envelope[s.DestinationData])
async def destinations(request: Request, db: Session, params: Annotated[s.DestinationQuery, Query()]):
    now, provider = state(request)
    journeys.require_core(provider)
    return response(request, s.DestinationData(destinations=catalog.destinations(
        db, params.originStationId, params.query, params.category)))


@router.post('/route-searches', response_model=s.Envelope[s.SearchData])
async def search(body: s.SearchRequest, request: Request, db: Session):
    now, provider = state(request)
    return response(request, journeys.create_search(db, body, provider, now, request.app.state.settings.data_mode))


@router.get('/route-searches/{routeSearchId}/options/{routeOptionId}', response_model=s.Envelope[s.RouteDetail])
async def detail(routeSearchId: s.Identifier, routeOptionId: s.Identifier, request: Request, db: Session):
    now, provider = state(request)
    result = journeys.checked_detail(db, routeSearchId, routeOptionId, provider, now, request.app.state.settings.data_mode)
    return response(request, result)


@router.get('/route-searches/{routeSearchId}/options/{routeOptionId}/live', response_model=s.Envelope[s.LiveData])
async def live(routeSearchId: s.Identifier, routeOptionId: s.Identifier, request: Request, db: Session):
    now, provider = state(request)
    result = journeys.checked_detail(db, routeSearchId, routeOptionId, provider, now, request.app.state.settings.data_mode)
    return response(request, journeys.live_info(result, provider, now, session=db))


@router.post('/destination-interpretations', response_model=s.Envelope[s.InterpretationData])
async def interpretation(body: s.InterpretationRequest, request: Request, db: Session):
    now, provider = state(request)
    journeys.require_core(provider)
    allowed = catalog.destinations(db, body.originStationId)

    def current_candidates():
        _, latest_provider = state(request)
        journeys.require_core(latest_provider)
        with request.app.state.database.session() as latest_db:
            return catalog.destinations(latest_db, body.originStationId)

    result = await ai.interpret(request.app.state.ai, body.text, allowed, request.app.state.settings.data_mode,
                                reload_destinations=current_candidates)
    return response(request, result)


def selected(request, db, body):
    now, provider = state(request)
    detail = journeys.checked_detail(db, body.routeSearchId, body.routeOptionId, provider, now,
        request.app.state.settings.data_mode, body.expectedRouteSnapshotVersion)
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

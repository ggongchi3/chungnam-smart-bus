from datetime import datetime, timezone
from uuid import uuid4
from contextlib import asynccontextmanager
from dataclasses import replace

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from fastapi.openapi.utils import get_openapi
from pydantic import ValidationError

from ai.adapter import RuleBasedAIAdapter

from backend.api.errors import ServiceError
from backend.config import Settings
from backend.database import Database
from backend.integrations.ai import AIBoundary
from backend.integrations.providers import DemoProvider, UnconnectedLiveProvider, StaticReferenceProvider
from backend.seed import seed
from backend.api.routes import router
from backend.config import ROOT
from backend.services.places import load_places, register_places
from backend.services.cheonan_routing import CheonanNetwork


def create_app(settings=None, clock=None, provider=None, ai_adapter=None, *, place_catalog='legacy', transport_catalog='legacy'):
    settings = settings or Settings.from_env()
    if transport_catalog not in ('legacy', 'cheonan'):
        raise ValueError('Unknown transport catalogue')
    transport = CheonanNetwork() if transport_catalog == 'cheonan' else None
    if transport and provider is None and settings.data_mode == 'demo':
        settings = replace(settings, data_mode='static')
    if settings.data_mode not in ('demo', 'live', 'static'):
        raise ValueError('BUS_DATA_MODE must be demo, static or live')
    database = Database(settings.database_url)
    if place_catalog not in ('legacy', 'cheonan'):
        raise ValueError('Unknown place catalogue')
    places = load_places() if place_catalog == 'cheonan' else None

    @asynccontextmanager
    async def lifespan(app):
        try:
            database.initialize()
            if settings.data_mode == 'demo':
                seed(database)
            if places is not None:
                register_places(database, places)
            if transport is not None:
                transport.register_origin(database)
            yield
        finally:
            database.engine.dispose()

    app = FastAPI(title='천안 스마트 버스 · 경로 안내 API', version='1.0.0', lifespan=lifespan)
    app.state.settings = settings
    app.state.clock = clock or (lambda: datetime.now(timezone.utc))
    app.state.database = database
    app.state.transport = transport
    app.state.provider = provider or (StaticReferenceProvider() if settings.data_mode == 'static' else DemoProvider(settings.demo_scenario, ROOT / '.local/scenario.json')
        if settings.data_mode == 'demo' else UnconnectedLiveProvider())
    app.state.ai = AIBoundary(ai_adapter)
    app.state.place_ids = {p['destinationId'] for p in places} if places is not None else None
    app.include_router(router)

    @app.middleware('http')
    async def common_server_errors(request, call_next):
        # Return the common 500 inside CORS. Starlette's outer error handler
        # otherwise bypasses CORS and hides the error from an allowed frontend.
        try:
            return await call_next(request)
        except Exception as exc:
            return await internal_error(request, exc)

    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins),
                       allow_methods=['GET', 'POST'], allow_headers=['Content-Type'])

    @app.middleware('http')
    async def request_id(request, call_next):
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers['X-Request-ID'] = request.state.request_id
        response.headers['Cache-Control'] = 'no-store'
        return response

    def error_response(request, status, code, message, retryable=False, headers=None):
        response_headers = dict(headers or {})
        response_headers.update({'X-Request-ID': request.state.request_id, 'Cache-Control': 'no-store'})
        return JSONResponse(status_code=status, headers=response_headers, content={
            'data': None, 'error': {'code': code, 'message': message, 'retryable': retryable},
            'meta': {'requestId': request.state.request_id,
                     'generatedAt': app.state.clock().isoformat(), 'dataMode': settings.data_mode},
        })

    @app.exception_handler(ServiceError)
    async def service_error(request: Request, exc: ServiceError):
        return error_response(request, exc.status, exc.code, exc.message, exc.retryable)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return error_response(request, 400, 'INVALID_REQUEST', '입력 형식과 허용 범위를 확인해 주세요.')

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return error_response(request, exc.status_code, 'NOT_FOUND' if exc.status_code == 404 else 'INVALID_REQUEST',
                              '요청 주소와 메서드를 확인해 주세요.', headers=exc.headers)

    @app.exception_handler(ValidationError)
    async def stored_data_error(request: Request, exc: ValidationError):
        return error_response(request, 503, 'TRANSPORT_DATA_UNAVAILABLE', '자료를 검증할 수 없습니다.', True)

    @app.exception_handler(ResponseValidationError)
    async def response_error(request: Request, exc: ResponseValidationError):
        return error_response(request, 503, 'TRANSPORT_DATA_UNAVAILABLE', '응답 자료를 검증할 수 없습니다.', True)

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception):
        return error_response(request, 500, 'INTERNAL_ERROR', '요청을 처리하지 못했습니다.', True)

    def openapi():
        if app.openapi_schema is None:
            schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
            for path in schema['paths'].values():
                for operation in path.values():
                    operation.get('responses', {}).pop('422', None)
            app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = openapi
    return app


app = create_app(ai_adapter=RuleBasedAIAdapter(), place_catalog='cheonan', transport_catalog='cheonan')

from datetime import datetime, timezone
from uuid import uuid4
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from fastapi.openapi.utils import get_openapi

from backend.api.errors import ServiceError
from backend.config import Settings
from backend.database import Database
from backend.integrations.ai import AIBoundary
from backend.integrations.providers import DemoProvider, UnconnectedLiveProvider
from backend.seed import seed
from backend.api.routes import router
from backend.config import ROOT


def create_app(settings=None, clock=None, provider=None, ai_adapter=None):
    settings = settings or Settings.from_env()
    if settings.data_mode not in ('demo', 'live'):
        raise ValueError('BUS_DATA_MODE must be demo or live')
    database = Database(settings.database_url)

    @asynccontextmanager
    async def lifespan(app):
        database.initialize()
        if settings.data_mode == 'demo':
            seed(database)
        try:
            yield
        finally:
            database.engine.dispose()

    app = FastAPI(title='충남 스마트 버스 · 합성 시연 API', version='1.0.0', lifespan=lifespan)
    app.state.settings = settings
    app.state.clock = clock or (lambda: datetime.now(timezone.utc))
    app.state.database = database
    app.state.provider = provider or (DemoProvider(settings.demo_scenario, ROOT / '.local/scenario.json')
        if settings.data_mode == 'demo' else UnconnectedLiveProvider())
    app.state.ai = AIBoundary(ai_adapter)
    app.include_router(router)
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins),
                       allow_methods=['GET', 'POST'], allow_headers=['Content-Type'])

    @app.middleware('http')
    async def request_id(request, call_next):
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers['X-Request-ID'] = request.state.request_id
        response.headers['Cache-Control'] = 'no-store'
        return response

    def error_response(request, status, code, message, retryable=False):
        return JSONResponse(status_code=status, content={
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
                              '요청 주소와 메서드를 확인해 주세요.')

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


app = create_app()

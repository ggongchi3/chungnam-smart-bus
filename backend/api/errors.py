class ServiceError(Exception):
    def __init__(self, status, code, message, retryable=False):
        self.status, self.code, self.message, self.retryable = status, code, message, retryable


def not_found():
    raise ServiceError(404, 'NOT_FOUND', '등록된 대상을 찾을 수 없습니다.')


def unavailable():
    raise ServiceError(503, 'TRANSPORT_DATA_UNAVAILABLE', '핵심 경로 자료를 확인할 수 없습니다.', True)


def changed(message='경로 정보가 바뀌었습니다. 다시 검색해 주세요.'):
    raise ServiceError(409, 'ROUTE_VERSION_CHANGED', message, True)


def route_unavailable():
    raise ServiceError(409, 'ROUTE_UNAVAILABLE', '선택 경로를 이용할 수 없습니다. 다시 검색해 주세요.', True)

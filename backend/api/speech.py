from fastapi import APIRouter, Request
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from backend.api.errors import ServiceError
from backend.api.routes import response, router
from backend.models.schemas import Envelope


speech_router = APIRouter(prefix=router.prefix, responses=router.responses)
MAX_AUDIO_BYTES = 2 * 1024 * 1024
AUDIO_FORMATS = {'audio/webm': 'matroska', 'audio/ogg': 'ogg', 'audio/mp4': 'mov', 'audio/wav': 'wav'}


class Transcription(BaseModel):
    text: str


@speech_router.post('/speech/transcriptions', response_model=Envelope[Transcription])
async def transcribe(request: Request):
    content_type = request.headers.get('content-type', '').split(';', 1)[0].strip().lower()
    audio_format = AUDIO_FORMATS.get(content_type)
    if audio_format is None:
        raise ServiceError(415, 'UNSUPPORTED_AUDIO', '이 녹음 형식은 사용할 수 없어요. 글로 입력해 주세요.')

    recording = bytearray()
    async for chunk in request.stream():
        if len(recording) + len(chunk) > MAX_AUDIO_BYTES:
            raise ServiceError(413, 'SPEECH_TOO_LONG', '짧게 나누어 다시 말해 주세요.')
        recording.extend(chunk)
    if not recording:
        raise ServiceError(400, 'INVALID_AUDIO', '녹음된 소리가 없어요. 다시 말해 주세요.')

    text = await run_in_threadpool(request.app.state.speech.transcribe, recording, audio_format)
    return response(request, Transcription(text=text))

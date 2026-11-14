from importlib.util import find_spec
from io import BytesIO
from threading import Lock

from backend.api.errors import ServiceError
from backend.config import ROOT


MODEL_PATH = ROOT / '.local/speech-model'
MODEL_FILES = ('config.json', 'model.bin', 'tokenizer.json', 'vocabulary.txt')
SAMPLE_RATE = 16_000
MAX_SAMPLES = 12 * SAMPLE_RATE


class SpeechTranscriber:
    def __init__(self):
        self.model = None
        self._lock = Lock()

    def transcribe(self, recording, audio_format):
        if not self._lock.acquire(blocking=False):
            raise ServiceError(503, 'SPEECH_BUSY', '다른 음성을 처리 중이에요. 잠시 뒤 다시 말해 주세요.', True)
        try:
            return self._transcribe(recording, audio_format)
        finally:
            self._lock.release()

    def _transcribe(self, recording, audio_format):
        if self.model is None and (find_spec('faster_whisper') is None or
                                   not all((MODEL_PATH / name).is_file() for name in MODEL_FILES)):
            raise ServiceError(503, 'SPEECH_UNAVAILABLE', '음성 인식이 준비되지 않았어요. 다시 말하거나 글로 입력해 주세요.', True)

        import av
        import numpy as np

        chunks = []
        samples = 0
        resampler = av.AudioResampler(format='s16', layout='mono', rate=SAMPLE_RATE)
        try:
            with av.open(BytesIO(recording), format=audio_format) as container:
                if not container.streams.audio:
                    raise ValueError('Missing audio stream')
                for frame in container.decode(audio=0):
                    for resampled in resampler.resample(frame):
                        samples += resampled.samples
                        if samples > MAX_SAMPLES:
                            raise ServiceError(413, 'SPEECH_TOO_LONG', '짧게 나누어 다시 말해 주세요.')
                        chunks.append(resampled.to_ndarray().ravel())
        except (av.FFmpegError, ValueError) as exc:
            raise ServiceError(400, 'INVALID_AUDIO', '녹음한 소리를 읽지 못했어요. 다시 말해 주세요.') from exc

        if not chunks:
            return ''
        if self.model is None:
            from faster_whisper import WhisperModel

            self.model = WhisperModel(str(MODEL_PATH), device='cpu', compute_type='int8', cpu_threads=4, local_files_only=True)
        waveform = np.concatenate(chunks).astype(np.float32) / 32768
        segments, _ = self.model.transcribe(waveform, language='ko', vad_filter=True, beam_size=1,
                                             condition_on_previous_text=False, temperature=0.0)
        return ' '.join(segment.text.strip() for segment in segments).strip()[:200]

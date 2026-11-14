const AUDIO_TYPES = ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus', 'audio/mp4'];
const MAX_RECORDING_MS = 9000;

export function recordingType() {
  if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') return undefined;
  return AUDIO_TYPES.find(type => MediaRecorder.isTypeSupported(type));
}

export async function recordSpeech(mimeType: string, signal: AbortSignal, onStart: () => void) {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  const release = () => stream.getTracks().forEach(track => track.stop());
  try {
    signal.throwIfAborted();
    const recorder = new MediaRecorder(stream, { mimeType });
    const chunks: Blob[] = [];
    let timer: number | undefined;
    const stop = () => { if (recorder.state === 'recording') recorder.stop(); };
    signal.addEventListener('abort', stop, { once: true });
    try {
      return await new Promise<Blob>((resolve, reject) => {
        recorder.ondataavailable = ({ data }) => { if (data.size) chunks.push(data); };
        recorder.onstop = () => resolve(new Blob(chunks, { type: recorder.mimeType || mimeType }));
        recorder.onerror = () => reject(new Error('Recording failed'));
        recorder.start();
        timer = window.setTimeout(stop, MAX_RECORDING_MS);
        onStart();
      });
    } finally {
      window.clearTimeout(timer);
      signal.removeEventListener('abort', stop);
    }
  } finally {
    release();
  }
}

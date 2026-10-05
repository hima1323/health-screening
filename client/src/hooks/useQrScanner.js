import { useCallback, useEffect, useRef, useState } from 'react';
import jsQR from 'jsqr';

/**
 * Opens the device camera and decodes QR codes from the live feed.
 *
 * state: 'starting' | 'scanning' | 'checking' | 'found' | 'failed'
 * `verify(text)` (optional) decides whether a decoded code counts: resolve to accept it,
 * reject with an Error to keep scanning — its message lands in `rejection`.
 * When failed, `failure` says why: { reason, name, message } — reason is one of
 * 'blocked' | 'insecure' | 'missing' | 'busy' | 'unsupported' | 'unknown'.
 * Attach `videoRef` to a <video> and `canvasRef` to a hidden <canvas>.
 */

/** Map a getUserMedia error to a reason the patient can act on. */
function classify(err) {
  switch (err?.name) {
    case 'NotAllowedError':
    case 'PermissionDeniedError':
      return 'blocked';
    case 'SecurityError':
      return 'insecure';
    case 'NotFoundError':
    case 'DevicesNotFoundError':
    case 'OverconstrainedError':
      return 'missing';
    case 'NotReadableError':
    case 'TrackStartError':
    case 'AbortError':
      return 'busy';
    default:
      return 'unknown';
  }
}
export default function useQrScanner({ onDecode, verify, holdMs = 900 } = {}) {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);
  const frameRef = useRef(null);
  const settledRef = useRef(false);
  const rejectedRef = useRef(null); // the last refused code, so the same one in view isn't re-checked every frame
  const verifyRef = useRef(verify);
  verifyRef.current = verify;

  const [state, setState] = useState('starting');
  const [code, setCode] = useState(null);
  const [failure, setFailure] = useState(null);
  const [attempt, setAttempt] = useState(0);
  const [rejection, setRejection] = useState(null);

  const stopCamera = useCallback(() => {
    cancelAnimationFrame(frameRef.current);
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }, []);

  /** Finish the scan — used by a decoded code and by the no-camera fallback alike. */
  const settle = useCallback(
    (text, verified) => {
      if (settledRef.current) return;
      settledRef.current = true;
      setCode(text);
      setRejection(null);
      setState('found');
      stopCamera();
      setTimeout(() => onDecode?.(text, verified), holdMs);
    },
    [onDecode, holdMs, stopCamera]
  );

  useEffect(() => {
    let cancelled = false;

    function readFrame() {
      const video = videoRef.current;
      const canvas = canvasRef.current;
      if (!video || !canvas || video.readyState !== video.HAVE_ENOUGH_DATA) {
        frameRef.current = requestAnimationFrame(readFrame);
        return;
      }

      // sample the centre square of the feed, matching what the viewfinder shows
      const size = Math.min(video.videoWidth, video.videoHeight);
      canvas.width = size;
      canvas.height = size;
      const ctx = canvas.getContext('2d', { willReadFrequently: true });
      ctx.drawImage(
        video,
        (video.videoWidth - size) / 2,
        (video.videoHeight - size) / 2,
        size,
        size,
        0,
        0,
        size,
        size
      );

      const image = ctx.getImageData(0, 0, size, size);
      const result = jsQR(image.data, image.width, image.height, { inversionAttempts: 'dontInvert' });
      if (result?.data) {
        const text = result.data;
        const refused = rejectedRef.current;
        const recentlyRefused = refused?.text === text && Date.now() - refused.at < 2500;
        if (!recentlyRefused) {
          if (!verifyRef.current) {
            settle(text);
            return;
          }
          // pause reading frames while the server checks the code
          setState('checking');
          verifyRef.current(text).then(
            (verified) => !cancelled && settle(text, verified),
            (err) => {
              if (cancelled) return;
              rejectedRef.current = { text, at: Date.now() };
              setRejection(err.message);
              setState('scanning');
              frameRef.current = requestAnimationFrame(readFrame);
            }
          );
          return;
        }
      }
      frameRef.current = requestAnimationFrame(readFrame);
    }

    function fail(reason, err) {
      // the error log: kept on screen for the patient, and in the console for staff
      console.warn('[camera]', reason, err?.name, err?.message);
      setFailure({ reason, name: err?.name ?? null, message: err?.message ?? null });
      setState('failed');
    }

    async function start() {
      // browsers hide mediaDevices entirely outside https:// and localhost
      if (!window.isSecureContext) return fail('insecure');
      if (!navigator.mediaDevices?.getUserMedia) return fail('unsupported');
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: 'environment' }, width: { ideal: 720 }, height: { ideal: 720 } },
          audio: false,
        });
        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }
        streamRef.current = stream;
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
        setState('scanning');
        readFrame();
      } catch (err) {
        if (cancelled) return;
        stopCamera();
        fail(classify(err), err);
      }
    }

    start();
    return () => {
      cancelled = true;
      stopCamera();
    };
  }, [settle, stopCamera, attempt]);

  const retry = () => {
    setFailure(null);
    setRejection(null);
    setState('starting');
    setAttempt((n) => n + 1);
  };

  return { state, code, failure, rejection, videoRef, canvasRef, retry, skip: () => settle(null) };
}

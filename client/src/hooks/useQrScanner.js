import { useCallback, useEffect, useRef, useState } from 'react';
import jsQR from 'jsqr';

/**
 * Opens the device camera and decodes QR codes from the live feed.
 *
 * state: 'starting' | 'scanning' | 'found' | 'denied' | 'unavailable'
 * Attach `videoRef` to a <video> and `canvasRef` to a hidden <canvas>.
 */
export default function useQrScanner({ onDecode, holdMs = 900 } = {}) {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);
  const frameRef = useRef(null);
  const settledRef = useRef(false);

  const [state, setState] = useState('starting');
  const [code, setCode] = useState(null);

  const stopCamera = useCallback(() => {
    cancelAnimationFrame(frameRef.current);
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }, []);

  /** Finish the scan — used by a decoded code and by the no-camera fallback alike. */
  const settle = useCallback(
    (text) => {
      if (settledRef.current) return;
      settledRef.current = true;
      setCode(text);
      setState('found');
      stopCamera();
      setTimeout(() => onDecode?.(text), holdMs);
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
        settle(result.data);
        return;
      }
      frameRef.current = requestAnimationFrame(readFrame);
    }

    async function start() {
      if (!navigator.mediaDevices?.getUserMedia) {
        setState('unavailable');
        return;
      }
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
        setState(err.name === 'NotAllowedError' ? 'denied' : 'unavailable');
      }
    }

    start();
    return () => {
      cancelled = true;
      stopCamera();
    };
  }, [settle, stopCamera]);

  return { state, code, videoRef, canvasRef, skip: () => settle(null) };
}

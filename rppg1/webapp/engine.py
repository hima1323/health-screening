"""
Background capture + inference engine for the live rPPG dashboard.

Runs the camera at its native frame rate on its own thread, so the model
sees a properly-sampled window and the measured frame rate (not an assumed
one) is used for every frequency-domain calculation. The Streamlit UI only
reads snapshots of this state, which keeps rendering independent of capture
speed.
"""
import collections
import threading
import time

import cv2
import numpy as np
import torch

import vitals
from bench.infer import pulse
from bench.preprocess import face_box


class RPPGEngine:
    def __init__(self, predictor, camera_index=0, stride=15, waveform_seconds=60,
                 display_width=480, vitals_interval=1.0, display_fps=15.0,
                 jpeg_quality=70, infer_threads=2):
        # predictor: bench.infer.Predictor -- 160-frame windows of 128x128
        # face crops, DiffNormalized input, exactly as in the benchmark
        self.predictor = predictor
        self.camera_index = camera_index
        self.clip_len = predictor.clip_len
        self.img_size = predictor.img_size
        self.stride = stride
        self.waveform_seconds = waveform_seconds
        self.display_width = display_width
        self.vitals_interval = vitals_interval
        # The browser cannot consume frames faster than the UI fragment
        # reruns, so encoding every captured frame is wasted CPU that
        # competes with capture and inference. Encode at display rate only.
        self.display_fps = display_fps
        self.jpeg_quality = jpeg_quality
        # Torch defaults to one thread per core. On a 4-performance-core
        # machine that lets a ~0.5s forward pass saturate every core and
        # starve both the capture thread and Streamlit's script runner,
        # which is what makes the video look choppy.
        self.infer_threads = infer_threads

        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._capture_thread = None
        self._infer_thread = None

        self.status = "idle"
        self.error = None
        self.face_found = None
        self._frame_jpeg = None
        self._frame_times = collections.deque(maxlen=60)
        self._fps = 0.0
        self._waveform = collections.deque(maxlen=int(30 * waveform_seconds))
        # overlap-add of the window predictions, one slot per captured frame
        self._max_samples = int(30 * waveform_seconds)
        self._acc = np.zeros(0)
        self._cnt = np.zeros(0)
        self._vitals = {}
        self._frames_seen = 0
        self._last_vitals_at = 0.0
        # one extra frame: the model input is the T frame differences
        self._buffer = collections.deque(maxlen=self.clip_len + 1)
        self._last_infer_frame = 0
        self._last_encode_at = 0.0

    # ---- lifecycle -------------------------------------------------

    def start(self):
        if self.running:
            return
        self._stop.clear()
        self.status = "starting"
        self.error = None
        if self.infer_threads:
            torch.set_num_threads(self.infer_threads)
        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._capture_thread.start()
        self._infer_thread = threading.Thread(target=self._infer_loop, daemon=True)
        self._infer_thread.start()

    def stop(self):
        self._stop.set()
        for t in (self._capture_thread, self._infer_thread):
            if t is not None:
                t.join(timeout=3.0)
        self._capture_thread = None
        self._infer_thread = None
        self.status = "idle"

    @property
    def running(self):
        return self._capture_thread is not None and self._capture_thread.is_alive()

    def reset_buffers(self):
        with self._lock:
            self._waveform.clear()
            self._acc, self._cnt = np.zeros(0), np.zeros(0)
            self._vitals = {}
            self._frames_seen = 0
            self._last_infer_frame = 0

    # ---- state access ----------------------------------------------

    def snapshot(self):
        with self._lock:
            return {
                "status": self.status,
                "face_found": self.face_found,
                "error": self.error,
                "frame_jpeg": self._frame_jpeg,
                "fps": self._fps,
                "waveform": np.array(self._waveform, dtype=np.float32),
                "vitals": dict(self._vitals),
                "buffer_seconds": (len(self._waveform) / self._fps) if self._fps > 0 else 0.0,
            }

    # ---- worker ----------------------------------------------------

    def _open_camera(self):
        cap = cv2.VideoCapture(self.camera_index)
        first = None
        for _ in range(25):
            ok, frame = cap.read()
            if ok:
                first = frame
                break
            time.sleep(0.2)
        if first is None:
            cap.release()
            return None, None
        return cap, first

    def _capture_loop(self):
        """Camera I/O only -- deliberately free of model inference so the
        capture rate stays at the sensor's native fps (the model window is
        only valid if it is sampled at the rate the model was trained on)."""
        cap, first = self._open_camera()
        if cap is None:
            with self._lock:
                self.status = "error"
                self.error = "Could not read from the webcam. Check camera permissions."
            self._stop.set()
            return

        # same crop as training: largest Haar face in the first frame,
        # box enlarged 1.5x, then fixed (no tracking -- keep still)
        (x, y, w, h), found = face_box(cv2.cvtColor(first, cv2.COLOR_BGR2RGB))
        with self._lock:
            self.status = "running"
            self.face_found = found

        while not self._stop.is_set():
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.01)
                continue

            crop = frame[y:y + h, x:x + w]
            crop = cv2.resize(crop, (self.img_size, self.img_size), interpolation=cv2.INTER_AREA)
            rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)

            # Encode for display at display_fps, not at capture rate: the
            # model needs every frame, the browser does not.
            now = time.time()
            jpg = None
            if now - self._last_encode_at >= 1.0 / self.display_fps:
                scale = self.display_width / frame.shape[1]
                small = cv2.resize(frame, (self.display_width, int(frame.shape[0] * scale)))
                cv2.rectangle(small, (int(x * scale), int(y * scale)),
                              (int((x + w) * scale), int((y + h) * scale)), (80, 220, 120), 2)
                ok_jpg, buf = cv2.imencode(
                    ".jpg", small, [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality])
                if ok_jpg:
                    jpg = buf.tobytes()
                self._last_encode_at = now

            with self._lock:
                self._buffer.append(rgb)
                self._frames_seen += 1
                self._frame_times.append(now)
                if len(self._frame_times) >= 2:
                    span = self._frame_times[-1] - self._frame_times[0]
                    if span > 0:
                        self._fps = (len(self._frame_times) - 1) / span
                if jpg is not None:
                    self._frame_jpeg = jpg

        cap.release()
        with self._lock:
            self.status = "idle"

    def _infer_loop(self):
        while not self._stop.is_set():
            with self._lock:
                ready = (len(self._buffer) == self.clip_len + 1 and
                         self._frames_seen - self._last_infer_frame >= self.stride)
                if ready:
                    clip_frames = list(self._buffer)
                    frame_mark = self._frames_seen
                    advance = min(frame_mark - self._last_infer_frame, self.clip_len)
                    fps_now = self._fps if self._fps > 5 else 30.0
                else:
                    clip_frames = None

            if clip_frames is None:
                time.sleep(0.01)
                continue

            # The model predicts the pulse derivative. Successive windows
            # overlap by clip_len - stride frames: normalise each, average
            # every frame over all windows that saw it, then integrate and
            # band-pass the whole buffer at once (as the benchmark does per
            # video). Filtering each window alone and keeping only its newest
            # (edge) samples made the HR drift.
            pred = self.predictor.window(np.stack(clip_frames), fps_now)
            std = pred.std()
            if std > 1e-8:
                pred = (pred - pred.mean()) / std

            with self._lock:
                n = self._max_samples
                self._acc = np.concatenate([self._acc, np.zeros(advance)])[-n:]
                self._cnt = np.concatenate([self._cnt, np.zeros(advance)])[-n:]
                k = min(len(pred), len(self._acc))
                self._acc[-k:] += pred[-k:]
                self._cnt[-k:] += 1
                raw = self._acc / np.maximum(self._cnt, 1)
            waveform = pulse(raw, fps_now) if raw.size > 3 * self.stride else raw
            waveform = waveform / (waveform.std() + 1e-8)

            now = time.time()
            with self._lock:
                self._waveform.clear()
                self._waveform.extend(waveform.tolist())
                self._last_infer_frame = frame_mark
                due = (now - self._last_vitals_at) >= self.vitals_interval

            if due and fps_now > 1.0 and waveform.size >= fps_now * 3:
                computed = vitals.compute_all(waveform, fps_now)
                with self._lock:
                    self._vitals = computed
                    self._last_vitals_at = now

"""Measurement agents on synthetic recordings with a known answer."""
import json

import cv2
import numpy as np
import pytest

from triage.measure import devices, hr_rppg, measure_recordings, thermal_vitals

FPS = 30.0


def skin_trace(hr_bpm, seconds=40, fps=FPS, seed=0, keyframe=None):
    """Mean skin RGB with a pulse (strongest in green), slow drift and noise; optional codec steps every N frames."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * fps)) / fps
    pulse = np.sin(2 * np.pi * hr_bpm / 60 * t)
    base = np.array([180.0, 120.0, 100.0])
    rgb = base * (1 + 0.003 * np.outer(pulse, [0.3, 1.0, 0.5])) + np.outer(0.5 * np.sin(0.1 * t), [1, 1, 1])
    rgb += rng.normal(0, 0.05, rgb.shape)
    if keyframe:                                       # a colour step at every keyframe: a 'pulse' at fps / keyframe
        rgb += np.outer((np.arange(len(t)) // keyframe) % 2, [2.0, 2.0, 2.0])
    return rgb


@pytest.mark.parametrize("hr", [55, 72, 110])
def test_pos_and_chrom_find_the_pulse(hr):
    _, halves, _ = hr_rppg.hr_from_rgb(skin_trace(hr), FPS)
    assert len(halves) == 2
    for h in halves:
        assert abs(h["hr_pos"] - hr) <= 2 and abs(h["hr_chrom"] - hr) <= 2 and h["snr_db"] > 0


def test_keyframe_steps_are_removed_and_ignored():
    rgb = skin_trace(80, seconds=60, keyframe=30)      # steps every 30 frames = a 1 Hz square wave at 30 fps
    _, halves, codec = hr_rppg.hr_from_rgb(rgb, FPS)
    assert codec["keyframe_period_frames"] == 30 and 60.0 in codec["ignored_bpm"]
    assert all(abs(h["hr_pos"] - 80) <= 2 for h in halves)


def test_video_without_face_gives_no_heart_rate(tmp_path):
    p = str(tmp_path / "blank.avi")
    w = cv2.VideoWriter(p, cv2.VideoWriter_fourcc(*"MJPG"), FPS, (64, 48))
    for _ in range(int(8 * FPS)):
        w.write(np.full((48, 64, 3), 128, np.uint8))
    w.release()
    ms, flags, diag = measure_recordings(video=p)
    assert ms[0]["value"] is None and ms[0]["quality"] == 0 and flags == ["face_not_found"]


def thermal_frames(rr_bpm=15, seconds=40, fps=8.0, face_c=34.5, canthus_c=36.1):
    t = np.arange(int(seconds * fps)) / fps
    f = np.full((len(t), 48, 64), 22.0, np.float32)             # room
    f[:, 8:44, 16:48] = face_c                                   # face
    f[:, 14:17, 28:31] = canthus_c                               # inner canthus: the hottest 3x3 spot
    f[:, 32:36, 28:36] += (0.6 * np.sin(2 * np.pi * rr_bpm / 60 * t))[:, None, None]   # nostrils
    return f + np.random.default_rng(0).normal(0, 0.02, f.shape).astype(np.float32), fps


def test_thermal_npy(tmp_path):
    frames, fps = thermal_frames()
    p = tmp_path / "thermal.npy"
    np.save(p, frames)
    ms, diag = thermal_vitals.measure(p, fps=fps)
    temp, rr = {m["name"]: m for m in ms}["temperature"], {m["name"]: m for m in ms}["resp_rate"]
    assert abs(temp["value"] - 36.1) < 0.15 and temp["quality"] > 0.8
    assert abs(rr["value"] - 15) <= 1 and len(rr["repeat_values"]) == 2


def test_thermal_frames_bin_format(tmp_path):
    frames, fps = thermal_frames(seconds=12)
    lo, hi = 20.0, 37.0
    ((frames - lo) / (hi - lo) * 255).round().clip(0, 255).astype(np.uint8).tofile(tmp_path / "x.frames.bin")
    meta = {"frames": {"width": 64, "height": 48, "count": len(frames), "fps": fps, "tempMinC": lo, "tempMaxC": hi}}
    (tmp_path / "x.json").write_text(json.dumps(meta))
    ms, diag = thermal_vitals.measure(tmp_path / "x.frames.bin", meta=tmp_path / "x.json")
    assert [m["name"] for m in ms] == ["temperature"] and abs(ms[0]["value"] - 36.1) < 0.2
    assert "shorter than" in diag["resp"]["error"]                # 12 s: no breathing rate


def ecg(hr_bpm=75, seconds=30, fs=250.0):
    t = np.arange(int(seconds * fs)) / fs
    x = np.zeros_like(t)
    for beat in np.arange(0.5, seconds, 60 / hr_bpm):
        x += np.exp(-((t - beat) / 0.012) ** 2)                 # R peaks
    return x + 0.05 * np.sin(2 * np.pi * 0.3 * t), fs


def test_ecg_csv(tmp_path):
    x, fs = ecg()
    p = tmp_path / "ecg.csv"
    p.write_text("time,ecg\n" + "\n".join(f"{i / fs:.4f},{v:.5f}" for i, v in enumerate(x)))
    m, d = devices.measure(p, "ecg")
    assert abs(m["value"] - 75) <= 1 and m["quality"] == 1.0 and m["source"] == "ecg"


def test_contact_heart_rate_wins_over_camera(tmp_path):
    x, fs = ecg(90)
    p = tmp_path / "ecg.csv"
    p.write_text("\n".join(f"{v:.5f}" for v in x))
    ms, flags, diag = measure_recordings(contact=p, contact_fs=fs, devices={"spo2": ("%", [97, 98])})
    assert [(m["name"], m["source"]) for m in ms] == [("heart_rate", "ecg"), ("spo2", "device")]
    assert abs(ms[0]["value"] - 90) <= 1

"""
Streamlit dashboard for live rPPG measurement with PhysFormer.

Capture and inference run on a background thread (see engine.py) at the
camera's native frame rate. The UI updates through st.fragment, so only the
live panels re-render -- the previous st.rerun()-per-frame approach
re-rendered the whole page each frame, which is what caused the flicker.

Run with: streamlit run streamlit_app.py
"""
import base64
import os
import sys

import numpy as np
import pandas as pd
import streamlit as st
import torch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from model import PhysFormer
from engine import RPPGEngine

st.set_page_config(page_title="PhysFormer Live rPPG", page_icon="💓", layout="wide")

st.markdown("""
<style>
    .block-container { padding-top: 2.5rem; padding-bottom: 3rem; }
    div[data-testid="stMetricValue"] { font-size: 1.9rem; }
    div[data-testid="stMetricLabel"] p { font-size: 0.78rem; color: #8a9099; }
    .hero div[data-testid="stMetricValue"] { font-size: 3.4rem; color: #34d399; }
    .pill {
        display: inline-flex; align-items: center; gap: 8px; font-size: 0.82rem;
        color: #9aa1aa; padding: 5px 14px; border: 1px solid #2a2f37;
        border-radius: 999px; margin-right: 8px;
    }
    .dot { width: 8px; height: 8px; border-radius: 50%; background: #6b7280; }
    .dot.live { background: #34d399; }
    .dot.warn { background: #f59e0b; }
    .note { color: #8a9099; font-size: 0.78rem; line-height: 1.55; }
    img.cam { width: 100%; border-radius: 10px; display: block; background: #000; }
    .sec { font-size: 0.95rem; font-weight: 600; margin: 0.2rem 0 0.4rem 0; }
</style>
""", unsafe_allow_html=True)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CKPT = os.path.join(ROOT, "checkpoints_mcd", "physformer_last.pt")


@st.cache_resource(show_spinner="Loading PhysFormer checkpoint…")
def load_model(ckpt_path, clip_len, norm_type):
    model = PhysFormer(dim=48, ff_hidden=72, depth=6, heads=4, theta=0.7, tau=2.0,
                        tube_size=(4, 4, 4), frames=clip_len, norm_type=norm_type)
    model.load_state_dict(torch.load(ckpt_path, map_location="cpu"))
    model.eval()
    return model


if "engine" not in st.session_state:
    st.session_state.engine = None

st.title("💓 PhysFormer Live rPPG")
st.caption("Contactless physiological measurement from webcam video")

engine = st.session_state.engine
is_running = engine is not None and engine.running

with st.sidebar:
    st.header("Capture settings")
    camera_index = st.number_input("Camera index", 0, 5, 0, disabled=is_running)
    clip_len = st.select_slider("Model window (frames)", [64, 96, 128], value=96,
                                 disabled=is_running)
    stride = st.slider("Inference every N frames", 5, 30, 15, disabled=is_running)
    window_s = st.select_slider("Analysis window (seconds)", [30, 60, 90, 120], value=60,
                                 disabled=is_running)
    st.caption("Settings apply when you press Start.")
    st.divider()
    st.markdown(
        "**Model** PhysFormer · dim 48 · depth 6  \n"
        "**Checkpoint** MCD-rPPG, 18 subjects, 23 epochs"
    )

col_a, col_b = st.columns([3, 2], gap="large")

with col_b:
    b1, b2, b3 = st.columns(3)
    start_clicked = b1.button("▶ Start", use_container_width=True, type="primary",
                               disabled=is_running)
    stop_clicked = b2.button("■ Stop", use_container_width=True, disabled=not is_running)
    reset_clicked = b3.button("↻ Reset", use_container_width=True, disabled=not is_running,
                               help="Clear the accumulated waveform and restart measurement")

if start_clicked:
    model = load_model(CKPT, clip_len, "bn")
    eng = RPPGEngine(model, camera_index=camera_index, clip_len=clip_len,
                     img_size=96, stride=stride, waveform_seconds=window_s)
    eng.start()
    st.session_state.engine = eng
    st.rerun()

if stop_clicked and engine is not None:
    engine.stop()
    st.session_state.engine = None
    st.rerun()

if reset_clicked and engine is not None:
    engine.reset_buffers()


def fmt(value, spec="{:.1f}", dash="—"):
    return dash if value is None else spec.format(value)


# 1/15s: matches the engine's display encode rate. Asking for reruns faster
# than new frames exist only queues work on the single script-runner thread
# that every fragment shares, which delays the video rather than smoothing it.
@st.fragment(run_every=1 / 15)
def video_panel():
    eng = st.session_state.engine
    if eng is None:
        st.info("Press **Start** to begin measuring.")
        return
    snap = eng.snapshot()
    if snap["error"]:
        st.error(snap["error"])
        return
    if snap["frame_jpeg"] is None:
        st.info("Opening camera…")
        return
    # Inline data URI rather than st.image(): st.image routes every frame
    # through Streamlit's media file manager and serves it from a /media
    # URL, which the browser cannot re-fetch reliably at video rates -- the
    # frames end up not rendering at all. Embedding the bytes in the
    # websocket delta makes the swap immediate.
    b64 = base64.b64encode(snap["frame_jpeg"]).decode("ascii")
    st.markdown(
        f'<img class="cam" src="data:image/jpeg;base64,{b64}" alt="live camera">',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<span class="pill"><span class="dot live"></span>{snap["fps"]:.0f} fps capture</span>'
        f'<span class="pill">{snap["buffer_seconds"]:.0f}s analysed</span>',
        unsafe_allow_html=True,
    )


@st.fragment(run_every=0.5)
def vitals_panel():
    eng = st.session_state.engine
    if eng is None:
        st.markdown('<div class="note">Metrics appear once measurement starts. '
                    'Heart rate needs a few seconds; respiration and HRV need '
                    'a longer window.</div>', unsafe_allow_html=True)
        return

    snap = eng.snapshot()
    v = snap["vitals"]
    secs = snap["buffer_seconds"]
    snr = v.get("snr_db")

    st.markdown('<div class="hero">', unsafe_allow_html=True)
    st.metric("Heart rate", f'{fmt(v.get("hr_bpm"))} bpm')
    st.markdown('</div>', unsafe_allow_html=True)

    if snr is None:
        quality, dot = "measuring…", "dot"
    elif snr >= 6:
        quality, dot = f"good signal · {snr:.1f} dB SNR", "dot live"
    elif snr >= 2:
        quality, dot = f"weak signal · {snr:.1f} dB SNR", "dot warn"
    else:
        quality, dot = f"poor signal · {snr:.1f} dB SNR — hold still, face the light", "dot warn"
    st.markdown(f'<span class="pill"><span class="{dot}"></span>{quality}</span>',
                unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    c1.metric("Respiration", f'{fmt(v.get("rr_brpm"))} br/min',
              help="From the low-frequency (0.1–0.5 Hz) component of the rPPG waveform. Needs ≥20 s.")
    c2.metric("Beats detected", f'{v.get("n_beats", 0)}')

    if secs < 20:
        st.progress(min(secs / 20.0, 1.0), text=f"Respiration unlocks at 20 s ({secs:.0f}s)")
    elif v.get("lf_nu") is None:
        st.progress(min(secs / 60.0, 1.0), text=f"HRV frequency metrics need ~60 s ({secs:.0f}s)")


# Charts are the most expensive re-render on the page; at 0.5s they stole
# script-runner time from the video fragment for no visible benefit.
@st.fragment(run_every=1.0)
def waveform_panel():
    eng = st.session_state.engine
    if eng is None:
        return
    snap = eng.snapshot()
    wave, fps = snap["waveform"], snap["fps"]
    if wave.size < 10 or fps <= 0:
        return
    show = wave[-int(fps * 10):] if wave.size > fps * 10 else wave
    if show.size > 400:
        show = show[np.linspace(0, show.size - 1, 400).astype(int)]
    st.markdown('<div class="sec">rPPG waveform · last 10 s</div>', unsafe_allow_html=True)
    st.line_chart(pd.DataFrame({"rPPG": show}), height=150)


@st.fragment(run_every=1.0)
def hrv_panel():
    eng = st.session_state.engine
    if eng is None:
        return
    v = eng.snapshot()["vitals"]

    st.markdown('<div class="sec">Heart-rate variability · time domain</div>',
                unsafe_allow_html=True)
    t1, t2, t3, t4 = st.columns(4)
    t1.metric("Mean IBI", f'{fmt(v.get("mean_ibi_ms"), "{:.0f}")} ms',
              help="Average inter-beat interval")
    t2.metric("SDNN", f'{fmt(v.get("sdnn_ms"), "{:.0f}")} ms',
              help="Std-dev of inter-beat intervals — overall variability")
    t3.metric("RMSSD", f'{fmt(v.get("rmssd_ms"), "{:.0f}")} ms',
              help="Root mean square of successive differences — parasympathetic tone")
    t4.metric("pNN50", f'{fmt(v.get("pnn50_pct"))} %',
              help="Share of successive intervals differing by >50 ms")

    st.markdown('<div class="sec">Heart-rate variability · frequency domain</div>',
                unsafe_allow_html=True)
    f1, f2, f3 = st.columns(3)
    f1.metric("LF", f'{fmt(v.get("lf_nu"), "{:.3f}")} n.u.', help="0.04–0.15 Hz, normalised units")
    f2.metric("HF", f'{fmt(v.get("hf_nu"), "{:.3f}")} n.u.', help="0.15–0.40 Hz, normalised units")
    f3.metric("LF/HF", f'{fmt(v.get("lf_hf_ratio"), "{:.2f}")}',
              help="Sympathovagal balance proxy — the ratio the paper reports in Table 2")


with col_a:
    video_panel()
with col_b:
    vitals_panel()

waveform_panel()
hrv_panel()

st.markdown(
    '<div class="note">All measures are derived from the model\'s predicted rPPG '
    'waveform, so they inherit its accuracy. This checkpoint was trained on 18 '
    'subjects for 23 epochs and is <b>not clinically valid</b> — use the SNR '
    'indicator above as the honest confidence signal, and treat HRV and '
    'respiration as demonstrations of the pipeline rather than real readings.</div>',
    unsafe_allow_html=True,
)

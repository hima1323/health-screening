# Aura Screen

### 🌐 Live website: **https://aura-screen.onrender.com**

A contactless health pre-screening app. A patient scans the QR code at a screening station with their phone; the
station reads their vital signs without touching them, a **reasoning model** decides how urgently they should see a
doctor and explains why, and the patient gets a plain-language report they can track over time and share with their
doctor.

| Part | Folder | What it does |
|---|---|---|
| **Patient app** | `client/`, `server/` | React app + Express/MongoDB API: QR-started scan, report, timeline, doctor portal |
| **Reasoning model** | `reasoning_model/src/triage/` | Triage expert system: ordered rules decide the level, the explainer words it, a verifier checks every number |
| **rPPG model** | `rppg1/`, `cvprlab/` | Heart rate from an ordinary face video. Trained model **CVPR Lab P4** (4.8M parameters), weights in `rppg1/runs/*/best.pt` |
| **Triage Lab** | `reasoning_model/src/triage/lab_app.py` | Streamlit page: try a case, benchmark a dataset, measure heart rate from a video |

| Link | |
|---|---|
| Code | https://github.com/hima1323/health-screening |
| Presentation (PPT) | _add link here_ |
| Demo video | _add link here_ |
| Case QR codes | [`docs/demo-qr/`](docs/demo-qr/): print one and scan it from the Scan Hub |

The live site runs on Render's free plan: the first visit after a quiet spell can take about 50 seconds.

## Problem statement

Routine health checks need a clinic visit, a trained operator and contact sensors, so most people are only screened
when something is already wrong. A self-service kiosk can measure vital signs without touching the patient: a camera
reads the pulse from the face (rPPG) and a thermal camera reads skin temperature. The measurements are only useful if
a patient with no medical training can start a scan, understand what the numbers mean and what to do next, and track
them over time. This project designs and builds that patient-facing side, and the reasoning model that turns
readings into advice.

## Objectives

1. **Start a scan from the phone** by scanning the station's QR code, with no operator present.
2. **Explain, don't just measure:** a reasoning model gives a clear level (urgent, see a doctor soon, self-care) with
   the reasons, every reading against its normal range, and advice.
3. **Trustworthy explanations:** rules decide, the language model only words the result, and a verifier rejects any
   number that is not in the record.
4. **Track over time:** a timeline of past sessions, with a step-by-step explanation of each.
5. **Share with a doctor** through a share code; the doctor sees only what patients share.
6. **Apply HCI methods throughout:** build (Lab 6), user testing (Lab 7) and improvements from the findings (Lab 8).

## Team members

| Name | Entry number |
|------|--------------|
| Himanshu Patel | 2024AIB1007 |
| Nongmaithem Hans | 2024AIB1011 |

CVPR Lab & ACAI Lab, School of AI & Data Engineering, IIT Ropar.

## Technologies used

| Layer | Tools |
|-------|-------|
| Frontend | React 19, Vite, React Router, CSS Modules, lucide-react, jsQR (QR scanning) |
| Backend | Node.js, Express 5, MongoDB with Mongoose, JWT auth, Google sign-in, Multer (uploads) |
| Reasoning model | Python, YAML rule tables, NumPy, pandas, SciPy; local LLM (Ollama, Qwen2.5-3B) for wording only |
| rPPG model | Python, PyTorch, OpenCV, SciPy; CVPR Lab model and PhysFormer (`rppg1/`, `cvprlab/`) |
| Lab tools | Streamlit (Triage Lab, live webcam heart rate), pytest |
| Hosting | Render (one Docker service), MongoDB Atlas, GitHub Actions (keep-awake ping) |

## Workflow

### Architecture

<img src="docs/diagrams/architecture.png" alt="Architecture: browsers, the Render web service with the Express API, built client and reasoning model, MongoDB Atlas and the GitHub Actions ping" width="900">

Everything runs as one web service on Render: Express serves the built React client and the API, and starts the
reasoning model (Python) beside it. Patients, the kiosk screen and doctors all use the same site in a browser. Data
lives in MongoDB Atlas. A GitHub Actions job pings the site every 5 minutes so the free instance never sleeps.

### Patient journey

<img src="docs/diagrams/patient-journey.png" alt="Patient journey from the welcome screen to the report, timeline and doctor portal" width="520">

### Starting a scan

<img src="docs/diagrams/scan-sequence.png" alt="Sequence: kiosk code, phone verifies it, scan starts, the reasoning model answers, the report is saved" width="900">

The kiosk's QR code is signed by the server and expires after 10 minutes, so a photo of an old code stops working.
A printed case QR code skips the station and opens the result straight away.

### Reasoning model

<img src="docs/diagrams/reasoning-model.png" alt="Reasoning model: case, evidence record, rule engine, reasoning chain, explainer, verifier, result card" width="900">

The rules decide the level; the language model never does. Rules are data in `reasoning_model/configs/triage/*.yaml`
and are marked **draft** until a clinician signs them off, so the output is a prototype and not medical advice.
Details: `reasoning_model/TRIAGE_EXPERT_SYSTEM_STATUS.md`.

### rPPG model

<img src="docs/diagrams/rppg-model.png" alt="rPPG model: face crop, video and STMap branches, DCEB, frequency stages, GTCN, decoder, waveform, heart rate" width="900">

| Weights (`rppg1/runs/<run>/best.pt`) | Model | Note |
|------|-------|------|
| `CVPR_P4_e30_MCD` | CVPR Lab P4, 4 blocks, 30 epochs | default; MAE 1.96 (MCD) / 4.48 (UBFC) / 3.52 (MPSC) bpm |
| `CVPR_P4_d12_e30_aug_MCD`, `CVPR_P4_d12_e30_MCD` | P4, 12 blocks | best on MCD / UBFC |
| `MCD_MCD` | plain PhysFormer | baseline |
| `CVPR_phase1..4_*` | ablation ladder | phase 1 PhysFormer to phase 4 frequency |

Benchmark tables: [`rppg1/runs/REPORT.md`](rppg1/runs/REPORT.md). The datasets (MCD-rPPG, UBFC-rPPG, MPSC) are not in
the repository.

### Training and evaluation

<img src="docs/diagrams/training.png" alt="Training: rPPG data, preprocessing, training, weights, test; triage data, derivation, clinician review, rules, tests and benchmark" width="900">

How to run each step: [Models: setup, training and evaluation](#models-setup-training-and-evaluation).

## Screens

Captured from the running app, in the order a patient meets them.

### 1. Introduction and account

| Welcome · 1 of 3 | Welcome · 2 of 3 | Welcome · 3 of 3 | Create account |
|:-:|:-:|:-:|:-:|
| <img src="docs/screenshots/welcome.png" width="200"> | <img src="docs/screenshots/welcome-2.png" width="200"> | <img src="docs/screenshots/welcome-3.png" width="200"> | <img src="docs/screenshots/signin.png" width="200"> |

### 2. Onboarding

| Your details + consent | Past reports (optional) | Scan Hub | How it works |
|:-:|:-:|:-:|:-:|
| <img src="docs/screenshots/onboarding-details.png" width="200"> | <img src="docs/screenshots/onboarding-reports.png" width="200"> | <img src="docs/screenshots/scan-hub.png" width="200"> | <img src="docs/screenshots/how-it-works.png" width="200"> |

### 3. Contactless scan

| Kiosk shows a QR | Phone scans it | Active scan | ECG fallback | Capture complete |
|:-:|:-:|:-:|:-:|:-:|
| <img src="docs/screenshots/kiosk.png" width="160"> | <img src="docs/screenshots/qr-scanner.png" width="160"> | <img src="docs/screenshots/active-scan.png" width="160"> | <img src="docs/screenshots/ecg-fallback.png" width="160"> | <img src="docs/screenshots/scan-complete.png" width="160"> |

### 4. Results and sharing

| Session report | Report, continued | Share with doctor |
|:-:|:-:|:-:|
| <img src="docs/screenshots/session-report.png" width="200"> | <img src="docs/screenshots/session-report-2.png" width="200"> | <img src="docs/screenshots/share-with-doctor.png" width="200"> |

### 5. Timeline and step-by-step analysis

| Past sessions | What this session shows | Steps 3–5 | Full analysis: thermal | Full analysis: signals |
|:-:|:-:|:-:|:-:|:-:|
| <img src="docs/screenshots/timeline.png" width="160"> | <img src="docs/screenshots/session-analysis.png" width="160"> | <img src="docs/screenshots/session-analysis-2.png" width="160"> | <img src="docs/screenshots/session-analysis-3.png" width="160"> | <img src="docs/screenshots/session-analysis-4.png" width="160"> |

### 6. Doctor portal

<img src="docs/screenshots/doctor-login.png" width="640">

A doctor signs in separately and sees only the reports patients have shared with them, by share code.

## Structure

```
health-screening/
├── client/                 Vite React app (patient screens, kiosk, triage result, doctor portal)
├── server/                 Express + Mongoose API (auth, screening data, live scans, doctor, /api/triage proxy)
│   └── scripts/            seed.js (demo data), load-sessions.js, demo-qr.js (printable demo QR codes)
├── model_service/          the earlier stress model (LightGBM + fusion on ADABase); no longer run by the app
├── rppg1/                  rPPG training, benchmark and live dashboard
│   ├── model/              PhysFormer
│   ├── bench/              preprocessing, training harness, infer.py (Predictor), benchmark
│   ├── webapp/             live webcam dashboard (Streamlit)
│   └── runs/               trained weights best.pt + REPORT.md
├── cvprlab/                CVPR Lab model (the one used: phase4_frequency)
├── reasoning_model/        expert triage system
│   ├── configs/triage/     rules, ranges, red flags, questionnaire, contacts (YAML)
│   ├── src/triage/         rules_engine, reasoning_chain, explainer, verify, session,
│   │                       lab_app (Triage Lab), kiosk_app, demo_service, bench/, derive/, measure/
│   ├── vignettes/ templates/ evidence/   sample cases and clinician templates
│   └── tests/              244 tests
├── docs/                   diagrams, screenshots, demo-qr/ (printable QR codes for the triage demo)
├── .github/workflows/      keep-awake.yml: pings the live site every 5 min so it never sleeps
├── Dockerfile              one image: built client + API + both Python services
└── render.yaml             Render deployment
```

## Setup and execution

Tested on Windows 11 and macOS. Every command runs from a fresh clone; commands are written for macOS/Linux, with
the Windows form beside them where it differs.

### Prerequisites

| Tool | Version | Used for |
|------|---------|----------|
| Git | any | cloning |
| Node.js | 22 or newer (with npm) | the app and the API |
| Python | 3.12 or 3.13 | the reasoning model and the Triage Lab |
| MongoDB | 7 or newer, running locally — or a MongoDB Atlas database | the app's data |

### 1. Get the code

```bash
git clone https://github.com/hima1323/health-screening.git
cd health-screening
```

### 2. Python environment (once)

One virtual environment serves the Triage Lab and the reasoning model the app runs. The server finds it at
`reasoning_model/.venv` by itself.

```bash
cd reasoning_model
python3 -m venv .venv                   # Windows: python -m venv .venv
source .venv/bin/activate               # Windows: .venv\Scripts\activate
pip install -r requirements-lab.txt
cd src && python -m triage.demo_samples --build && cd ..   # the demo cases (one test and the app use them)
python -m pytest -q                     # expect: 244 passed
cd ..
```

### 3. Triage Lab (reasoning model and rPPG model) — no database needed

```bash
cd reasoning_model
streamlit run src/triage/lab_app.py     # opens http://localhost:8501 (venv from step 2 active)
```

1. Tab **0 - Try a sample**: choose "Draft vignettes" (or "Template sample"), pick a case. Section 1 shows the input,
   section 2 the triage level, the reason and the advice. Open "Show full detail" for the reasoning chain.
2. Tab **1 - Benchmark a dataset**: choose "Template sample", press **Run the benchmark** (metrics vs the baselines).
3. Tab **3 - Face video**: upload a 30-60 s face video, pick model `p4` and press **Measure heart rate**. It uses the
   committed weights `rppg1/runs/CVPR_P4_e30_MCD/best.pt`. Picking a dataset sample there needs the datasets
   (`rppg1/data/cache`), which are not in the repository.
4. The Yale and MIMIC-IV-ED sets in tabs 0 and 1 need their data downloaded into `reasoning_model/data/public`; the
   vignettes and the template work without it.

The explanation text uses fixed templates by default. To use the local LLM, install Ollama, run
`ollama pull qwen2.5:3b-instruct`, and switch on "Write the explanation with the local LLM".

### 4. Patient app

**Terminal 1 — API** (MongoDB must be running):

```bash
cd server
npm install
cp .env.example .env                    # Windows: copy .env.example .env
npm run seed                            # demo patient, station, past sessions, demo doctor
npm start                               # http://localhost:4000 — also starts the reasoning model
```

`.env` works as copied for a local MongoDB. For Atlas, set `MONGODB_URI` in it (see [Environment](#environment)).

**Terminal 2 — app:**

```bash
cd client
npm install
npm run dev                             # open http://localhost:5173
```

### 5. Try it

1. Open http://localhost:5173, step through the introduction (or **Skip the introduction**), choose
   **Create account** and fill in the details.
2. **Triage demo:** on the Scan Hub press **Begin contactless scan** and scan a printed code from
   [`docs/demo-qr/`](docs/demo-qr/) (or show it on a second screen). The app shows the triage result for that case:
   level, reason, readings against their ranges and the explanation.
3. **Live scan:** open http://localhost:5173/kiosk on a second screen and scan its QR from the Scan Hub. After the
   capture countdown the model answers and **View session report** opens the report
   ([details](#live-scan-and-the-reasoning-model)).
4. **Doctor:** http://localhost:5173/doctor/login. With `DEMO_DOCTOR_EMAIL` left empty the demo doctor is
   `doctor@aura.test`, password `aura-5e9394ee` (from `server/scripts/seed.js`); with your Google address there,
   sign in with Google.

A phone allows the camera only on https or localhost. To scan from a phone on the same Wi-Fi, start the app with
`HTTPS=1 npm run dev` (Windows: `set HTTPS=1&& npm run dev`) and open `https://<laptop IP>:5173`, accepting the
certificate warning once. `start_aura_demo.bat` starts all three terminals on Windows.

### Rebuilding data

After changing the analysis, rebuild the study sessions and reload just those —
`npm run sessions` leaves user accounts alone, so nobody gets signed out.
`npm run seed` also resets the demo patient, and keeps accounts too.

```bash
python3 analysis/build_sessions.py && (cd server && npm run sessions)
```

`cd server && npm run demo-qr` remakes the printable QR codes after the demo cases change.

## Models: setup, training and evaluation

The app needs none of this: the trained rPPG weights are committed and the triage rules are plain YAML. This is how
to rebuild or retrain each model. Every command assumes the venv from [step 2](#2-python-environment-once) is active.

| Model | Folder | Used by the app | What "training" means |
|-------|--------|-----------------|-----------------------|
| rPPG (heart rate from a face video) | `rppg1/`, `cvprlab/` | Triage Lab face-video tab, live webcam dashboard | Deep learning (PyTorch) on MCD-rPPG, tested on UBFC-rPPG |
| Triage reasoning model | `reasoning_model/src/triage/`, `configs/triage/` | Live scans and the printed QR codes | No fitting: rules are written, checked against ED data and benchmarked |
| Earlier stress model | `reasoning_model/src/*.py`, `model_service/` | No longer (kept for the report) | LightGBM + fusion, leave-one-subject-out on ADABase |

### A. rPPG model (CVPR Lab P4 and PhysFormer)

**Setup.** `requirements-lab.txt` (step 2) already has PyTorch, OpenCV and SciPy. Training needs an NVIDIA GPU with
6 GB or more (runs use fp16); inference and the tests run on CPU.

**1. Get the data** (from `rppg1/`; each script is resumable):

```bash
cd rppg1
python -m bench.download_mcd --n 100 --camera IriunWebcam     # MCD-rPPG (Hugging Face, CC-BY-4.0): video + synced PPG
python -m bench.fetch_ubfc                                    # UBFC-rPPG DATASET_2, cached and raw deleted (~4 GB)
```

UBFC-rPPG is for research use; faces of subjects 21 and 27 must not appear in any report or presentation.

**2. Preprocess** (face crop, 128 × 128, DiffNormalized) into `rppg1/data/cache`:

```bash
python -m bench.preprocess --dataset mcd --raw data/raw/MCD-rPPG --camera IriunWebcam --max-seconds 60
```

(`fetch_ubfc` already writes UBFC-rPPG to the cache.)

**3. Train.** Subject-disjoint split: 64 train / 16 validation / 20 held-out test subjects; best epoch by validation
heart-rate RMSE. Weights go to `rppg1/runs/<name>/best.pt`.

```bash
# the model the app uses: CVPR Lab phase 4 (frequency), 30 epochs
python -m bench.run train --arch cvprlab:phase4_frequency --train mcd_IriunWebcam --test mcd_IriunWebcam \
    --epochs 30 --name CVPR_P4_e30_MCD
# the PhysFormer baseline (rppg1/model/physformer.py)
python -m bench.run train --train mcd_IriunWebcam --test mcd_IriunWebcam --name MCD_MCD

python -m bench.ladder       # ablation: CVPR Lab phase 1 -> 2 -> 3 -> 4, each also tested on UBFC-rPPG
python -m bench.campaign     # the longer / deeper runs (30 epochs, depth 12, augmentation)
```

**4. Evaluate:**

```bash
python -m bench.run test --arch cvprlab:phase4_frequency --ckpt runs/CVPR_P4_e30_MCD/best.pt --test ubfc
python -m bench.run pos --test ubfc        # classical POS baseline, no training
python -m bench.run report                 # -> runs/REPORT.md (every run vs rPPG-Toolbox published numbers)
python -m bench.tables_figure              # -> runs/comparison_tables*.png
```

**5. Use a trained model:**

```bash
python -m bench.infer --list                          # the trained models
python -m bench.infer --video my_face.mp4             # heart rate from a 30-60 s face video (best model, P4)
streamlit run webapp/streamlit_app.py                 # live webcam heart rate in the browser
```

**Tests:** `cd cvprlab && python -m pytest tests -q` (18 tests: the architecture's claims, not just shapes).
Results so far are in [`rppg1/runs/REPORT.md`](rppg1/runs/REPORT.md); the architecture is described in
[`cvprlab/README.md`](cvprlab/README.md).

### B. Triage reasoning model (the one the app runs)

It is an expert system, so there is nothing to fit: ordered rules in `configs/triage/rules.yaml` decide the level,
ranges come from `vital_ranges.yaml`, red flags from `red_flags.yaml`. The data is used to **check and tune** the
draft rules and to **benchmark** them. All commands run from `reasoning_model/src`.

**1. Tests** (no data needed): `cd reasoning_model && python -m pytest -q` (244 tests).

**2. Get the open ED data** into `reasoning_model/data/public/` (not committed):

| Dataset | Source | Put it at |
|---------|--------|-----------|
| MIMIC-IV-ED Demo v2.2 | https://physionet.org/content/mimic-iv-ed-demo/2.2/ (open) | `data/public/mimic_iv_ed_demo/mimic-iv-ed-demo-2.2/ed/*.csv.gz` |
| Yale ED triage (Hong et al. 2018) | Zenodo 1308993 (repo `yaleemmlc/admissionprediction`) | `data/public/yale_triage/yaleemmlc-admissionprediction-5cf50bc/Results/5v_cleandf.RData` |
| NHANES 2017-2018 (DEMO_J, BPX_J) | CDC | fetched by `--download` below |

```bash
cd reasoning_model/src
python -m triage.bench.yale --build                    # streams the 972-column RData -> cases.parquet
```

**3. Check and tune the rules** (dev split only; outputs are aggregates in `results/triage/derive/`):

```bash
python -m triage.derive.mimic_dev_bands                # urgent-visit rates per vital-sign band, per cut-off
python -m triage.derive.nhanes_overreferral --download # how many healthy adults each cut-off would flag
python -m triage.derive.rule_learning --yale           # small decision tree: rule suggestions for the clinician
python -m triage.derive.source_check                   # every range and score against its official source
python -m triage.derive.delphi --round 1               # Delphi pack for the clinicians to rate the rules
```

A rule changes only in `configs/triage/rules.yaml`, after review; the tests then pin its behaviour.

**4. Benchmark** on the held-out data (Yale test split and MIMIC-IV-ED Demo) against NEWS2, always-refer and
learned baselines:

```bash
python -m triage.bench.run_bench                       # -> results/triage/REPORT.md, bench_results.json
python -m triage.bench.vignettes                       # the draft vignettes
```

**5. Explanations with the local LLM** (optional; templates otherwise): install Ollama, `ollama pull
qwen2.5:3b-instruct`. The model only words the explanation; the verifier rejects any number not in the record.

**6. The app's cases:** `python -m triage.demo_samples --build` writes `reasoning_model/demo_samples/` (MIMIC, Yale
and rPPG cases when that data is present, else the draft vignettes); `cd server && npm run demo-qr` prints their QR
codes. The server builds the cases by itself on first start.

### C. Earlier stress model (ADABase; kept for the report, not run by the app)

Predicts high vs low mental load from physiological signals with per-modality LightGBM agents and a fusion model,
leave-one-subject-out over 30 ADABase subjects, with SHAP evidence and an LLM explanation checked by a verifier.
Details in [`reasoning_model/CLAUDE.md`](reasoning_model/CLAUDE.md).

```bash
cd reasoning_model
pip install -r requirements.txt                          # full set (mlx / mlx-lm only on Apple Silicon)
export ADABASE_PASSWORD='<share password>'               # from the ADABase authors; never commit it
python src/features.py --all --delete-raw                # download -> features -> delete raw, one subject at a time
python src/train.py --task binary --tune                 # LightGBM, LOSO, isotonic calibration, SHAP
python src/fusion.py                                     # modality agents + fusion
python src/evidence.py --all --fusion                    # evidence records
python src/reasoner.py --subject 0 --fusion              # explanation (Ollama, else template) + verifier
python src/evaluate.py --ablations                       # metrics, ablations, calibration, faithfulness
sh run_pipeline.sh                                       # all of the above, plus the LoRA fine-tune
```

## Live scan and the reasoning model

A scan runs end to end on real requests, and the reasoning model is the triage expert system in
`reasoning_model/src/triage/` (rules decide the level, the explainer words it, the verifier checks it):

1. The kiosk (`/kiosk`) shows a QR code the server signed; it changes every 10 minutes.
2. The phone scans it (**Begin contactless scan**); the server checks the signature and starts a scan
   (`POST /api/scans`). The kiosk screen follows along (`GET /api/stations/:id/live`).
3. The station "captures". This demo station has no sensors, so it sends one of the reasoning model's demo cases
   (readings and answers, `reasoning_model/demo_samples/`), in turn.
4. The server runs the triage on that case (`server/lib/reasoning.js` → `python -m triage.demo_service`). It returns
   the level (Urgent / See a doctor soon / Self-care / …), the rule that fired and why, every reading against its
   normal and urgent range, and the explanation card.
5. The answer becomes a report with its own share code. The patient sees the result screen; a doctor who enters the
   code sees the same, and it lists under **Model results**.

The server starts the reasoning model itself (Python from `reasoning_model/.venv`, else `python3`, or `MODEL_PYTHON`),
building the demo cases first if they are missing. Reports from before this change carry the earlier stress model's
output (`model_service/`) and still display.

### Presentation run-through

For the reasoning-model triage demo instead, scan a printed code from `docs/demo-qr/` in step 2; the result shows
straight away.

1. Laptop / projector: open `https://<app>/kiosk` — the QR code.
2. Phone (app or browser): create an account, fill in details, **Begin contactless scan**, point at the QR.
   If the camera won't start, **Continue without camera** links to the same station.
3. Watch both screens: capture countdown → case sent → the reasoning model answers (about 15 s).
   **View session report**.
4. On the report, **Share with doctor** shows the code.
5. Doctor: `/doctor/login` (or **I'm a doctor** on the sign-in screen) → **Add shared report** → the code.
   The report shows the reasoning model's result; **Model results** lists every scan with its level and the rule
   that fired. Add a note on the patient page. The dashboard refreshes every 10 s.

Scans rotate through the demo cases (self-care, urgent, see a doctor soon, not suitable), so a second scan shows a
different result.

## Deployment

`render.yaml` defines one free Docker web service (`Dockerfile`): the built client, the Express API and the
reasoning model, all on one HTTPS URL. The image build makes the demo cases with the model's own code, so a broken
model fails the deploy instead of the demo.

1. Render dashboard → **New → Blueprint** → pick this repo and branch.
2. Fill in `MONGODB_URI` (MongoDB Atlas; allow `0.0.0.0/0` in Network Access),
   `GOOGLE_CLIENT_ID` and `DEMO_DOCTOR_EMAIL`. `JWT_SECRET` is generated.
3. Load the demo data into Atlas once, from this machine:
   `cd server && MONGODB_URI='<atlas uri>' npm run seed`
4. For Google sign-in, add the `https://<name>.onrender.com` URL to the OAuth
   client's Authorised JavaScript origins.

The server pings its own `/api/health` every 5 minutes (when `RENDER_EXTERNAL_URL`
is set, which Render does) so the free instance doesn't sleep. `/api/health` also reports whether the model
service is up (`"model": true`) — check it before presenting.

The site works in any phone or laptop browser at the onrender.com URL.
Uploaded past reports live on the instance's disk and are lost on each redeploy.

The triage demo runs on the hosted site too: scan a printed code from `docs/demo-qr/` with **Begin contactless
scan** on the Scan Hub. The image builds its demo cases with `python -m triage.demo_samples --build`; without the MIMIC/Yale/rPPG
data in the image that gives the draft vignette cases only, and explanations use the fixed templates (no Ollama).

## Environment

`server/.env` — see `server/.env.example`.

| Variable | Needed for |
| --- | --- |
| `MONGODB_URI` | anything other than a local MongoDB |
| `JWT_SECRET` | signing sessions — set a long random string outside development |
| `GOOGLE_CLIENT_ID` | the Google sign-in button; the app falls back to email + password without it |
| `PORT` | moving the API off 4000 |

For Google sign-in, add `http://localhost:5173` to the OAuth client's
**Authorised JavaScript origins** in Google Cloud Console. No client secret is
needed — the browser gets the ID token and the server only verifies it.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/auth/register` · `/api/auth/login` | email + password accounts |
| `POST` | `/api/auth/google` | exchange a Google ID token for a session |
| `GET` | `/api/auth/me` | restore a remembered session |
| `PUT` | `/api/auth/me/profile` | onboarding details |
| `POST`/`DELETE` | `/api/auth/me/reports[/:id]` | attach or drop past reports |
| `GET` | `/api/primary` | resolve the signed-in patient and session ids |
| `GET` | `/api/patients/:id/scan-hub` · `/timeline` | screen data |
| `GET` | `/api/sessions/:sessionId/report` | screen data |
| `POST` | `/api/scans` | start a live scan from a kiosk code → `GET /api/scans/:id` to follow it |
| `GET` | `/api/stations/:id/live` | the kiosk's view of its current scan (stage only) |
| `GET`/`POST`/`DELETE` | `/api/doctor/patients/:id/notes` · `/api/doctor/notes/:id` | a doctor's own notes |

## Related project: MMAC Study Hub

The data-collection side of this work: the website and capture dashboards for the **Multimodal Affective Computing
(MMAC) study** at IIT Ropar (thermal, ECG, EMG and rPPG recorded together).

**Repository:** https://github.com/h4444n55555/Multimodal-Analysis-Dashboards

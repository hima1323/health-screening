# Aura Screen — Patient App

Contactless biometric screening for patients: an introduction, an account, a
QR-triggered scan, and the report and timeline that come out of it. React +
Vite on the front, Express + Mongoose on the back — every screen reads its data
from MongoDB, nothing is hardcoded in the client.

## Problem statement

Routine health checks need a clinic visit, a trained operator and contact
sensors, so most people only get screened when something is already wrong.
A self-service kiosk can measure vitals without touching the patient: a camera
reads the pulse from the face (rPPG) and a thermal camera reads skin
temperature. The measurements are only useful if a patient with no medical
training can start a scan, understand the results and track them over time.
This project designs and builds that patient-facing side.

## Objectives

- Let a patient start a kiosk scan from their phone by scanning a QR code,
  with no operator present.
- Present each session's results (heart rate, temperature, ECG, EMG) in plain
  language, with a step-by-step explanation of how each value was measured.
- Show a timeline of past sessions so patients can see trends.
- Let patients share a report with their doctor.
- Apply HCI methods throughout: build (Lab 6), user testing (Lab 7), and
  improvements based on the test findings (Lab 8).

## Team members

| Name | Roll number | Role |
|------|-------------|------|
| TODO | TODO | TODO |

## Technologies used

| Layer | Tools |
|-------|-------|
| Frontend | React 19, Vite, React Router, CSS Modules, lucide-react, jsQR (QR scanning) |
| Backend | Node.js, Express 5, MongoDB with Mongoose, JWT auth, Google sign-in, Multer (uploads) |
| Signal analysis | Python, NumPy; rPPG with POS/CHROM and a PhysFormer model in PyTorch (`rppg1/`) |
| Tooling | Git and GitHub, oxlint |

## Workflow

### Patient journey

<img src="docs/diagrams/patient-journey.png" alt="Patient journey" width="420">

### System architecture

<img src="docs/diagrams/architecture.png" alt="System architecture" width="760">

### Starting a scan

<img src="docs/diagrams/scan-sequence.png" alt="Starting a scan" width="620">

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
webapp/
├── client/                 Vite React app (see client/README.md)
└── server/                 Express + Mongoose API
    ├── index.js            app entry — mounts the routers, connects, listens
    ├── db.js               mongoose connection
    ├── lib/                token.js (JWT), google.js (ID-token verification)
    ├── middleware/         requireUser.js — bearer token → req.user
    ├── models/             User, Patient, Station, ScreeningSession,
    │                       Report, VitalTimeline, ScreeningLog
    ├── routes/             api.js (screening data), auth.js (accounts)
    ├── scripts/seed.js     demo patient + session S-8841
    └── uploads/            past reports patients attach (gitignored)
```

## Run it

Needs MongoDB on `mongodb://127.0.0.1:27017`, or set `MONGODB_URI`.

```bash
# 1. configure and seed (once)
cd server && npm install && cp .env.example .env && npm run seed

# 2. API
npm start                       # http://localhost:4000

# 3. client, in a second terminal
cd ../client && npm install && npm run dev    # http://localhost:5173
```

After changing the analysis, rebuild the study sessions and reload just those —
`npm run sessions` leaves user accounts alone, so nobody gets signed out.
`npm run seed` also resets the demo patient, and keeps accounts too.

```bash
python3 analysis/build_sessions.py && (cd server && npm run sessions)
```

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
| `GET` | `/api/sessions/:sessionId/active-scan` · `/report` | screen data |

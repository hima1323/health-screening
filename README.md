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

```mermaid
flowchart LR
    A[Welcome<br/>3-step intro] --> B[Sign in<br/>email or Google]
    B --> C[Onboarding<br/>profile + past reports]
    C --> D[Scan Hub]
    K[Kiosk screen<br/>shows signed QR] -. patient scans QR .-> D
    D --> E[Active scan<br/>camera + thermal]
    E --> F[Session report]
    F --> G[Biometric timeline]
    G --> H[Session analysis<br/>step-by-step]
    F -- share code --> I[Doctor portal]
```

### System architecture

```mermaid
flowchart LR
    subgraph Kiosk station
        CAM[Camera / thermal / ECG / EMG]
        KS[Kiosk page<br/>rotating QR]
    end
    subgraph Client [React client · Vite]
        P[Patient app]
        DR[Doctor portal]
    end
    subgraph Server [Express API]
        AUTH["/api/auth<br/>JWT + Google"]
        API["/api<br/>scan hub, sessions, reports"]
        DOC["/api/doctor<br/>shared reports"]
    end
    DB[(MongoDB)]
    PY[Python analysis<br/>rPPG POS/CHROM, PhysFormer]

    KS -- QR --> P
    P --> AUTH & API
    DR --> DOC
    AUTH & API & DOC --> DB
    CAM --> PY -- session JSON --> DB
```

### Starting a scan

```mermaid
sequenceDiagram
    participant K as Kiosk
    participant S as Server
    participant P as Patient phone
    K->>S: GET /api/stations/:id/code
    S-->>K: signed, short-lived code
    K->>K: show code as QR
    P->>P: scan QR with camera (jsQR)
    P->>S: POST /api/stations/verify
    S-->>P: valid → scan starts
    S-->>P: results → session report
```

## Screens

| Welcome | Sign in | Kiosk | Doctor sign-in |
|:-:|:-:|:-:|:-:|
| <img src="docs/screenshots/welcome.png" width="200"> | <img src="docs/screenshots/signin.png" width="200"> | <img src="docs/screenshots/kiosk.png" width="200"> | <img src="docs/screenshots/doctor-login.png" width="200"> |

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

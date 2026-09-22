# Aura Screen — Patient App

Contactless biometric screening for patients: an introduction, an account, a
QR-triggered scan, and the report and timeline that come out of it. React +
Vite on the front, Express + Mongoose on the back — every screen reads its data
from MongoDB, nothing is hardcoded in the client.

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

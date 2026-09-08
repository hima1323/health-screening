# Aura Screen — Patient App

React implementation of the Aura Screen patient app (Scan Hub, Active Scan,
Session Report, Biometric Timeline), backed by an Express API that reads all
patient/session/report/timeline data from MongoDB — nothing is hardcoded in
the frontend.

## Structure

- `server/` — Express + Mongoose API
  - `models/` — Patient, Station, ScreeningSession, Report, VitalTimeline, ScreeningLog
  - `routes/api.js` — REST endpoints consumed by the client
  - `scripts/seed.js` — seeds MongoDB with the demo patient (Ramesh, 54) and session S-8841
- `client/` — React app (Vite)
  - `src/pages/` — ScanHub, ActiveScan, SessionReport, BiometricTimeline
  - `src/api.js` — fetch helpers
  - `src/PrimaryContext.jsx` — resolves the demo patient/session ids from `/api/primary` so the frontend never hardcodes an id

## Run it

Requires a local MongoDB running on `mongodb://127.0.0.1:27017` (or set `MONGODB_URI`).

```bash
# 1. seed the database (one-time, or whenever you want to reset demo data)
cd server && npm install && npm run seed

# 2. start the API
npm start          # http://localhost:4000

# 3. start the client (separate terminal)
cd ../client && npm install && npm run dev   # http://localhost:5173
```

The Vite dev server proxies `/api/*` to `http://localhost:4000`.

## API endpoints

- `GET /api/primary` — resolves the demo patient/session ids
- `GET /api/patients/:id/scan-hub`
- `GET /api/sessions/:sessionId/active-scan`
- `GET /api/sessions/:sessionId/report`
- `GET /api/patients/:id/timeline`

# Aura Screen — client

React 19 on Vite. `npm run dev` serves it on http://localhost:5173 and proxies
`/api` to the Express server on port 4000 (`vite.config.js`).

```bash
npm run dev       # dev server with HMR
npm run build     # production bundle into dist/
npm run preview   # serve that bundle
npm run lint      # oxlint
```

## Structure

The Vite scaffold, grown out: `index.html` → `src/main.jsx` → `src/App.jsx`,
with `index.css` and `App.css` in their usual places.

```
client/
├── public/              served as-is at the site root (favicon)
├── index.html           the single HTML entry
└── src/
    ├── main.jsx         mounts React, imports index.css
    ├── index.css        design tokens + element reset
    ├── App.jsx          routes and providers, imports App.css
    ├── App.css          page frame + shared utility classes
    ├── api/             client.js (fetch + token), index.js, auth.js
    ├── context/         AuthContext, PrimaryContext
    ├── hooks/           useAuth, usePrimary, useResource, useCountdown, useQrScanner
    ├── components/      one folder per component
    │   └── ui/          the reusable primitives: Button, Card, Field, …
    └── pages/           one folder per route
```

Each component and page folder holds `Name.jsx`, `Name.module.css` and an
`index.js` that re-exports it, so imports stay `from '../components/Card'`.
Anything used across screens is a class in `App.css`; anything belonging to one
component is a CSS module beside it.

## Routes

`/welcome` → `/signin` → `/onboarding` → `/` (Scan Hub) · `/report` · `/timeline`

`RequireGuest` keeps an onboarded patient out of the first two; `RequireAccount`
guards the last three and supplies `PrimaryContext`.

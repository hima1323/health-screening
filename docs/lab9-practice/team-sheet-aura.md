# Lab 9 — Inspection & Accessibility Checklist (Aura Screen part, pre-checked)

Date checked: 14 Oct 2026 · Checked by: code review + headless Chrome on the local build (ports 5173 / 5174)
**Confirm each row yourselves on a real phone before signing.** Study Hub rows (W1–W10, U2, U4, U5, U7) are left
blank — the Study Hub site is not on this machine, so walk through T2 together and mark them.

## 1. Lab 7 issues — fixed or not?

| ID | Lab 7 problem | Sev | Lab 8 change | F/P/N | Evidence (what was checked) |
|---|---|---|---|---|---|
| A1 | Phone/kiosk view only via dev tools | 3 | Phone / Kiosk / Full toggle | **F** | Toggle visible above the frame: Phone 390×844 · Kiosk 834×1112 · Full screen; `?device=` also works |
| A2 | Scan Hub scrolls in phone view | 3 | No-scroll phone screens | **F** | Phone frame: content height 844 = frame height 844, no scroll |
| A3 | Third heart-rate tile cut off | 3 | Shorter, fixed report | **P** | Report still scrolls in phone view (1083 px content in an 844 px frame); the third tile (Breathing rate) sits under the bottom tabs until you scroll |
| A4 | Navigation out of thumb reach | 2 | Bottom tabs: Scan, Report, Timeline | **F** | Bottom tab bar on every patient screen in phone view |
| A5 | 13 px inputs make iOS zoom | 2 | 16 px inputs | **F** | Inputs are 16 px on touch screens (`@media (pointer: coarse)` in Field); 13 px only with a mouse — confirm on an iPhone |
| A6 | Hover stays after a tap | 1 | Not changed yet | **P** | Buttons guard hover with `@media (hover: hover)`; 15 other style files still use plain `:hover` (cards, tabs, links) |
| A7 | Kiosk screens leave empty space | 2 | Kiosk-first layout | — | Check visually in Kiosk view (not measurable from code) |
| W1–W10 | Study Hub | | | — | Not on this machine — mark together |
| U1 | Report numbers not explained | 3 | Plain verdict + normal range | **F** | Report: each value has its normal range and a plain sentence ("Normal is 72–96 bpm — yours is above it"); session pages show Normal / Not normal + Fine / Check |
| U2 | Sample data has no explanation | 3 | Study Hub | — | Mark together |
| U3 | Camera blocked, no message | 3 | Camera errors explained | **F** | Blocked / insecure / missing / busy cameras each get their own on-screen message ("Camera blocked by the browser" …) — confirm by blocking the camera once |
| U4, U5, U7 | Study Hub | | | — | Mark together |
| U6 | Google is the only sign-in | 1 | Email + password added | **F** | Email + password form on Sign in. Note: Google sign-in fails on port 5174 (origin not registered) |

**Aura subtotal:** Fixed **6** (A1, A2, A4, A5, U1, U3) + U6 = **7** · Partly **2** (A3, A6) · Not fixed **0** · A7 to check.
Totals out of 24: add the Study Hub rows.

**New problems found this round** (screen — problem — heuristic — severity):

- Report (phone view) — third result tile hidden behind the bottom tab bar until scrolled — H8 Aesthetic & minimalist design / visibility — **2**
- Session page, version B — "All your data" charts use model terms (fixed in B with plain labels; still in the doctor view, which is fine for clinicians) — H2 Match with the real world — **1**
- Phone frame — device toggle buttons and Sign out are 29 px tall (below 44 px) — H7 Flexibility / accessibility — **1** (only in the laptop preview; on a real phone there is no toggle)
- Version B on port 5174 — Google sign-in error `origin_mismatch` — H9 Help users recover from errors — **2** (register the origin, or use email sign-in)

## 2. Accessibility check — before vs after (Aura Screen)

| Check | How we checked | Lab 7 | Lab 9 | What we saw |
|---|---|---|---|---|
| Text contrast | Computed from the colour tokens | Fail | **Fail** | Lowest ratio **2.33 : 1** (faded grey `--ink-3` on pink cards; 2.44 : 1 on version B's white). Secondary grey 4.18 : 1 on pink (fail), 4.59 : 1 on white (pass) |
| Chart labels | Session charts in version B | Fail | **Partly** | Labels now plain words in B ("Mental effort, all sensors"); axis numbers still small — check Fig 11 on the Study Hub |
| Text size | Style sheets | Partly | **Partly** | 19 rules still set 8–10 px text (eyebrows, badges, captions) |
| Keyboard | Focus styles in code | Partly | **Partly** | Default focus ring on most controls; session cards and the chart have custom focus; inputs replace the ring with a border glow. Tab through Scan → Report → Timeline to confirm |
| Labels | Every visible link/button/input scanned for a name | Partly | **Pass** (Aura) | 0 unnamed controls on Scan Hub, Report and Session pages; 0 images without alt. Check the Study Hub theme toggle / close buttons separately |
| Zoom / touch | 240 px-wide viewport (= 200 % zoom of a 480 px phone); tap targets measured | new | **Partly** | No horizontal overflow at 200 %. Under 44 px: device toggle and Sign out (29 px), "Past sessions" (31 px), "Source" link (17 px) |
| Lighthouse | DevTools → Lighthouse → Accessibility | new | — | Not run here — run it on home, /ecg, /emg, /rppg and the Aura report and write the five scores |

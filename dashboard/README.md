# dashboard/  (OWNER: M5 — built by M3 for M5 review)

The live operations view judges see. React + Vite + TypeScript, no map or chart libraries (pure SVG, works offline).

```bash
cd dashboard && npm install      # once
npm run dev                      # http://localhost:5173  (or: make dashboard)
```

## Modes
- **Offline demo data** (default, `VITE_USE_MOCKS=true` in the repo `.env`): reads `tests/fixtures/wildfire_demo_01`
  directly, so it matches the Python tests exactly. Plans exist for 17:00 (hour 9).
- **Live** (`VITE_USE_MOCKS=false`, `VITE_API_BASE_URL=http://localhost:8000/api` with `make api` running, or the
  CloudFront URL + `/api` after deploy). Any hour, real re-plans, real gate log.

## Recording the video

**Narrated (your Mac's voice reads each step, about 2 minutes):**
1. Install **OBS Studio** (free, obsproject.com). QuickTime cannot record the sound your Mac plays; OBS can.
   In OBS add a *macOS Screen Capture* source; desktop audio is included. Set the canvas to 1920×1080.
2. Open `http://localhost:5173/?record=1&narrate=1` in Chrome, full screen (Ctrl+Cmd+F).
3. Start recording in OBS, then **click once** on the page. The story plays with voice, captions and sounds.
4. Stop recording after step 7. Trim the first second in iMovie/OBS.
- Pick a voice with `&voice=Daniel` (or Samantha, Karen…). Nicer voices: System Settings → Accessibility →
  Spoken Content → System voice → Manage Voices → download "Ava (Premium)"; the dashboard prefers it automatically.

**Silent (for a human voice-over):** `http://localhost:5173/?record=1` plays by itself with captions, no sound.

**Driving it by hand:** **Play the story**, or keys **→ / ←** (next / previous step), **Space** (play / pause),
**N** (narration), **S** (sound effects), **C** (captions), **Esc** (close overlays). The narration and sound
buttons are also at the top right of the map.

## What's on screen
- **Map**: fresh counts glow blue; silent sites fade and grow a grey fog that widens with every hour of old data.
  Routes flow in their gate colour; blocked routes stop with a red ✕. Gold beams = scouts from the ops centre.
- **Timeline**: drag to watch the outage unfold hour by hour.
- **Gate moment** (step 4): the insulin draws fill a meter and spill past the safety limit.
- **Stock strip**: shaded band = where stock may really be; tick = most likely; hollow mark = last count.
- **Results chart** and **Simulate app offline** buttons (top right of the map).

The results chart uses a preliminary 3-seed run until M2's final `eval/results/` are in; live mode reads the API.

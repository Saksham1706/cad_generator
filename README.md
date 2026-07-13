# CAD Generator — Enhanced Edition

Generate 3D CAD models just by describing them in plain English — or, for full precision, by
submitting parameters directly. Every model can be downloaded as STL, GLB, or STEP, comes with
computed volume/weight/bounding-box, and supports undo/redo editing history.

## What's new in this version

**More shapes** — box, cylinder, hollow cylinder (pipe), sphere, hemisphere (dome), cone, torus,
n-sided prism, pyramid/frustum, and parametric stars.

**Hole patterns** — bolt-circle (polar) and grid (linear) patterns for both circular and square
holes, not just single holes.

**Multiple text features** — emboss/engrave several labels on different faces in one model,
instead of just one.

**Shell / hollow-out** — turn any solid into a hollow shell with a chosen wall thickness, with
an optional open face.

**Mass properties** — every generated model reports volume, bounding box, and estimated weight
across 13 material presets (PLA, ABS, aluminum, steel, titanium, oak, and more).

**STEP export** — in addition to STL and GLB, every model can be downloaded as a STEP file for
use in traditional CAD software (SolidWorks, Fusion 360, FreeCAD, etc).

**Undo / redo** — every generate/edit call is versioned per session, with `/undo` and `/redo`
endpoints and matching buttons in the UI.

**Persistent sessions** — session history is written to disk, so it survives a server restart
instead of living only in memory.

**JSON / power-user mode** — a `/generate_manual` endpoint (and a toggle in the UI) that skips
the language model entirely and takes exact CAD parameters directly. Useful for precision work,
scripting, or when you don't have a Groq API key.

**Template gallery** — a categorized set of ready-to-run example prompts in the UI, from basic
shapes to functional parts like bolt-pattern flanges and perforated plates.

**Sturdier validation & error handling** — sanity limits on dimensions, pattern-fit checks (do
these holes actually fit on this face without overlapping?), retrying LLM calls, and clear
errors when `GROQ_API_KEY` isn't set instead of a crash.

## Supported shapes & parameters

| Shape | Required fields |
|---|---|
| `box` | `width_mm`, `height_mm`, `depth_mm` |
| `cylinder` | `diameter_mm`, `height_mm` |
| `hollow_cylinder` | `outer_diameter_mm`, `inner_diameter_mm`, `height_mm` |
| `sphere` | `diameter_mm` |
| `hemisphere` | `diameter_mm` |
| `cone` | `base_diameter_mm`, `top_diameter_mm`, `height_mm` |
| `torus` | `torus_diameter_mm`, `tube_diameter_mm` |
| `prism` | `sides` (3–20), `width_mm`, `height_mm` |
| `pyramid` | `base_width_mm`, `base_depth_mm`, `height_mm` (add `top_width_mm`/`top_depth_mm` for a frustum) |
| `star` | `points` (3–16), `outer_diameter_mm`, `inner_diameter_mm`, `height_mm` |

Optional features that can be layered onto any shape: circular/square holes (single or
bolt-circle/grid patterns), fillets/chamfers, multiple emboss/engrave text features, and
shell/hollow-out.

## Example prompts
- "a box 50mm wide 30mm tall 20mm deep"
- "a torus with an overall diameter of 60mm and a tube thickness of 10mm"
- "a cylinder 60mm diameter and 10mm tall with 6 bolt holes of 4mm diameter in a circle of 20mm radius on the top"
- "a box 80mm wide, 80mm deep, 10mm tall with a 3x3 grid of 5mm square holes spaced 20mm apart"
- "a box 60mm wide, 60mm deep, 40mm tall, hollowed out with a 3mm wall thickness and the top face open"
- "a box 100mm wide, 100mm deep, and 20mm tall, engrave 'CHRISTOPHER' 3mm deep into the top face, fillet the edges by 2mm"

## API endpoints

| Method & path | Purpose |
|---|---|
| `POST /generate` | Natural-language prompt → model |
| `POST /edit` | Natural-language edit of an existing session |
| `POST /generate_manual` | Exact JSON parameters → model (no LLM) |
| `POST /undo` / `POST /redo` | Step through a session's edit history |
| `GET /history/{session_id}` | Full parameter history for a session |
| `GET /templates` | Preset prompt gallery |
| `GET /materials` | Available materials + densities |
| `GET /health` | Liveness check |

## Setup

Clone the repo and create a `.env` file with your Groq API key:
```text
GROQ_API_KEY=your_key_here
```

Then:
```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `frontend/index.html` (served automatically at `/frontend/index.html`) in your browser.

No Groq key yet? You can still use everything except natural-language prompts — flip on
**JSON Mode** in the UI, or call `POST /generate_manual` directly, to build models from exact
parameters.

# Prompt Based CAD Generator

Generate 3D CAD models from plain English or exact JSON, then analyze, document, and cost them
in one workspace. Built on CadQuery + FastAPI with a full engineering toolkit in the UI.

**LLM:** Groq via `GROQ_API_KEY` — model from `GROQ_MODEL` (default `openai/gpt-oss-120b`).

## Core CAD

- **10 primitives** — box, cylinder, hollow cylinder, sphere, hemisphere, cone, torus, prism, pyramid/frustum, star
- **16 everyday compounds (prompt-only)** — water bottle, mug, chair, table, bed, stool, vase, bowl, bookshelf, phone stand, lamp, goblet, dumbbell, picture frame, coaster, plate. Describe them in plain English; defaults fill missing sizes.
- **FDM print estimate** — rough filament weight/length and print time from solid volume
- **Material cost compare** — same part priced across materials
- **Example chips + prompt history** — quick starts and local recent prompts
- **Features** — circular/square holes, polar & grid patterns, multi-face emboss/engrave, shell, fillet/chamfer
- **Exports** — STL, GLB, STEP, plus a **ZIP pack** (all formats + params JSON + drawings)
- **Mass properties** — volume, bounding box, weight, estimated material cost (13 materials)
- **Undo / redo / timeline** — versioned sessions with clickable history restore
- **JSON / power-user mode** — skip the LLM and submit exact parameters
- **Template gallery** — categorized starter prompts
- **Parametric inspector** — edit dimensions in a form and rebuild
- **Natural-language edit** — “make it taller”, “add 6 bolt holes”, etc.

## Engineering & manufacturing

| Feature | What it does |
|---|---|
| **Beam Engineer** | Deterministic bending/deflection (SS or cantilever × point/UDL). Material FoS check or ranked recommendations. One-click **Generate CAD beam**. |
| **Technical drawings** | 3-view orthographic SVG/PDF with title block (Windows-safe temp paths) |
| **BOM** | Multi-part bill of materials with qty, weight, and cost totals |
| **DFM score** | Printability / manufacturability grade (walls, holes, edge clearance, aspect ratio, text depth) |
| **Metric fasteners** | M2–M12 clearance/tap bolt circles applied to the current part |
| **Part library** | Save / load / delete named designs |
| **Scale & clone** | Uniform scale factor; duplicate into a new session |
| **Share links** | `?session=` URL restore |
| **Material-synced viewer** | PBR finish presets follow the selected CAD material |

## Quick start

```text
GROQ_API_KEY=your_key_here
GROQ_MODEL=openai/gpt-oss-120b
```

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000 — the UI is served at `/frontend/index.html`.

No Groq key? Use **JSON Mode** or `POST /generate_manual`.

### Keyboard shortcuts
- `Ctrl+Enter` — generate (or apply edit when focused in the edit box)
- `Ctrl+Z` / `Ctrl+Y` — undo / redo (when not typing in a field)

## API map

| Method & path | Purpose |
|---|---|
| `POST /generate` | NL → model |
| `POST /edit` | NL edit |
| `POST /generate_manual` | JSON params → model |
| `POST /undo` `/redo` `/restore` | History |
| `POST /clone` `/scale` | Duplicate / resize |
| `GET /history/{id}` `/sessions` | Session data |
| `GET /templates` `/materials` `/fasteners` `/health` `/examples` | Catalogs + LLM status |
| `POST /compare_materials` | Cost/weight across materials |
| `POST /calculate_beam` `/beam_to_cad` | Beam analysis → CAD |
| `GET /structural_materials` | Structural alloys |
| `POST /bom` `/drawing` `/dfm` | BOM, drawings, DFM |
| `POST /apply_bolt_circle` | Standards hole pattern |
| `GET/POST/DELETE /library…` | Named part library |
| `GET /export_pack/{id}` | ZIP of all exports |

## Example prompts
- "a box 50mm wide 30mm tall 20mm deep"
- "a cylinder 60mm diameter and 10mm tall with 6 bolt holes of 4mm diameter in a circle of 20mm radius on the top"
- "a box 60mm wide, 60mm deep, 40mm tall, hollowed out with a 3mm wall thickness and the top face open"
- "a water bottle"
- "a simple wooden chair"
- "a bed 1600mm wide"
- "a coffee mug 90mm tall"
- "a bookshelf with 4 shelves"

## Speed notes

- **Text engraving** — fillet runs *before* text; CadQuery `text(..., clean=False)`. Nameplates are ~6× faster than fillet-after-glyphs.
- **LLM pipeline** — one Groq call (not normalize+extract). Simple prompts / everyday objects use local heuristics (0 LLM). Repeat prompts hit an in-memory cache.
- **Export** — STEP and GLB conversion run in parallel after STL.

## Architecture notes

Phase 1 engineering agents (beam, BOM, drawings) are deterministic — no LLM math.
The LLM is only used for natural-language → parameter extraction and edits.

Deferred to a later phase: LangGraph multi-agent orchestration, PostgreSQL, React/Three.js
rewrite, full FEA / topology optimization.

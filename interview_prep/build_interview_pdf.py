"""Build CAD Forge backend-interview cheat sheet PDF."""
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, KeepTogether, HRFlowable, ListFlowable, ListItem,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os

OUT = os.path.join(os.path.dirname(__file__), "CAD_Forge_Backend_Interview_Prep.pdf")

NAVY = HexColor("#0F2744")
TEAL = HexColor("#0E7490")
AMBER = HexColor("#B45309")
RED = HexColor("#9F1239")
SLATE = HexColor("#334155")
LIGHT = HexColor("#F1F5F9")
CARD = HexColor("#E2E8F0")
GREEN = HexColor("#166534")


def styles():
    s = getSampleStyleSheet()
    s.add(ParagraphStyle("CoverH", fontName="Times-Bold", fontSize=22, textColor=NAVY, leading=26, spaceAfter=4))
    s.add(ParagraphStyle("CoverS", fontName="Times-Italic", fontSize=11, textColor=TEAL, leading=14, spaceAfter=10))
    s.add(ParagraphStyle("H1", fontName="Times-Bold", fontSize=13, textColor=NAVY, leading=16, spaceBefore=10, spaceAfter=6))
    s.add(ParagraphStyle("H2", fontName="Times-Bold", fontSize=11, textColor=TEAL, leading=14, spaceBefore=8, spaceAfter=4))
    s.add(ParagraphStyle("Body", fontName="Times-Roman", fontSize=9.5, textColor=SLATE, leading=12.4, alignment=TA_JUSTIFY, spaceAfter=5))
    s.add(ParagraphStyle("BodyBullet", fontName="Times-Roman", fontSize=9.5, textColor=SLATE, leading=12.2, leftIndent=12, spaceAfter=2))
    s.add(ParagraphStyle("Q", fontName="Times-Bold", fontSize=9.5, textColor=NAVY, leading=12.2, spaceBefore=6, spaceAfter=1))
    s.add(ParagraphStyle("A", fontName="Times-Roman", fontSize=9.5, textColor=SLATE, leading=12.2, leftIndent=8, alignment=TA_JUSTIFY, spaceAfter=3))
    s.add(ParagraphStyle("Warn", fontName="Times-Bold", fontSize=9.5, textColor=RED, leading=12.2, spaceBefore=4, spaceAfter=4))
    s.add(ParagraphStyle("Tip", fontName="Times-Italic", fontSize=9, textColor=AMBER, leading=12, spaceBefore=2, spaceAfter=4))
    s.add(ParagraphStyle("Small", fontName="Times-Roman", fontSize=8, textColor=HexColor("#64748B"), leading=10.5, spaceAfter=3))
    s.add(ParagraphStyle("Footer", fontName="Times-Roman", fontSize=8, textColor=HexColor("#64748B")))
    s.add(ParagraphStyle("Cell", fontName="Times-Roman", fontSize=8.2, textColor=SLATE, leading=10.8))
    s.add(ParagraphStyle("CellH", fontName="Times-Bold", fontSize=8.2, textColor=white, leading=10.8))
    s.add(ParagraphStyle("CellB", fontName="Times-Bold", fontSize=8.2, textColor=NAVY, leading=10.8))
    return s


def header_footer(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(NAVY)
    canvas.rect(0, A4[1] - 14 * mm, A4[0], 14 * mm, fill=1, stroke=0)
    canvas.setFillColor(white)
    canvas.setFont("Times-Bold", 9)
    canvas.drawString(18 * mm, A4[1] - 9 * mm, "CAD Forge  |  Text-to-CAD  |  Backend interview sheet")
    canvas.setFont("Times-Roman", 8)
    canvas.drawRightString(A4[0] - 18 * mm, A4[1] - 9 * mm, "Say what the code does — not more")
    canvas.setFillColor(TEAL)
    canvas.rect(0, 0, A4[0], 10 * mm, fill=1, stroke=0)
    canvas.setFillColor(white)
    canvas.setFont("Times-Roman", 8)
    canvas.drawString(18 * mm, 4 * mm, "Internal prep only  ·  Hybrid parser + deterministic CadQuery kernel")
    canvas.drawRightString(A4[0] - 18 * mm, 4 * mm, f"Page {doc.page}")
    canvas.restoreState()


def cell(text, style):
    return Paragraph(text, style)


def table(data, col_widths, header=True):
    t = Table(data, colWidths=col_widths, repeatRows=1 if header else 0)
    cmds = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("GRID", (0, 0), (-1, -1), 0.3, HexColor("#94A3B8")),
        ("BACKGROUND", (0, 1), (-1, -1), LIGHT),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [LIGHT, white]),
    ]
    if header:
        cmds.append(("BACKGROUND", (0, 0), (-1, 0), NAVY))
    t.setStyle(TableStyle(cmds))
    return t


def build():
    S = styles()
    story = []
    W = 174 * mm

    story.append(Paragraph("CAD Forge — Backend Interview Prep", S["CoverH"]))
    story.append(Paragraph(
        "Text-to-CAD: natural language → parametric 3D solids. 60-minute cheat sheet aligned to YOUR resume and the actual codebase.",
        S["CoverS"]))
    story.append(Paragraph(
        "<b>How to use this:</b> The first two pages are a 3-minute pitch. Pages after that are Q&amp;A. "
        "If they only ask about the resume bullets, stay on pages 1–4. If they say “agentic / LLM / scale”, use pages 5–7.",
        S["Body"]))
    story.append(Paragraph(
        "CRITICAL: Do not claim a LangGraph multi-agent system. README and code: LLM is a parameter extractor; beam/BOM/drawings are deterministic. LangGraph is explicitly deferred.",
        S["Warn"]))

    # ---------- PITCH ----------
    story.append(Paragraph("1. 45-second pitch (memorize this)", S["H1"]))
    story.append(Paragraph(
        "I built a FastAPI service that turns an English prompt into a real CAD solid. The language model never draws geometry. "
        "It only emits a constrained JSON schema of shape, dimensions, holes, fillets, and text. A validator rejects illegal sizes. "
        "A CadQuery kernel then runs a fixed operation order: primitive → holes → shell → fillet/chamfer → text. "
        "We export STL, GLB, and STEP in parallel, store a versioned session for undo/redo, and can skip the LLM entirely with a JSON endpoint. "
        "Simple prompts never hit the network — regex heuristics plus an in-memory cache.",
        S["Body"]))

    story.append(Paragraph("2. Map each resume bullet to the code (so you don’t oversell)", S["H1"]))
    h = S["CellH"]
    b = S["CellB"]
    c = S["Cell"]
    story.append(table([
        [cell("Resume claim", h), cell("What you actually built", h), cell("Say this if probed", h)],
        [cell("Text-to-CAD / NL → parametric 3D", b),
         cell("POST /generate → extract_params → validate_geometry → build_final_model → STL/GLB/STEP", c),
         cell("End-to-end product: parse, constrain, kernel, visualize, export.", c)],
        [cell("Rule-based NLP parsing pipeline", b),
         cell("Hybrid. (1) Regex heuristics for box/cylinder/sphere/compounds. (2) Groq llama-3.3-70b JSON extract. (3) Local edits like “10mm taller”. Cache SHA1 of prompt.", c),
         cell("“Rule-based first; LLM only when heuristics fail. Schema is the contract.”", c)],
        [cell("Primitives + holes, fillet, chamfer, text", b),
         cell("10 primitives + 16 compound builders. Polar/linear hole patterns. Fillet/chamfer on all edges. Emboss/engrave via CadQuery text, max 24 chars.", c),
         cell("CSG: fuse/cut/shell. Fillet BEFORE text for speed.", c)],
        [cell("Modular geometry pipeline / realtime / export", b),
         cell("SHAPE_BUILDERS dict + sequential features. Viewer uses GLB. Exports STL (mesh), STEP (BRep), ZIP pack + params JSON.", c),
         cell("Params JSON is the source of truth; mesh is a view.", c)],
    ], [42 * mm, 68 * mm, 64 * mm]))

    story.append(Paragraph("3. System architecture (draw this on a whiteboard)", S["H1"]))
    story.append(Paragraph(
        "<b>Client</b> (static HTML/JS) → <b>FastAPI</b> → <b>Parser</b> (heuristic | Groq JSON | cache | local edit) → "
        "<b>sanitize + validate</b> → <b>CadQuery kernel</b> (Open CASCADE) → <b>mass props + print estimate</b> → "
        "<b>export thread pool</b> (STEP ∥ GLB) → <b>SessionStore</b> (JSON file, undo cursor).",
        S["Body"]))
    story.append(Paragraph(
        "Side modules (no LLM): Beam Engineer (bending formulas), BOM, 3-view drawings, DFM score, fastener bolt circles, part library, material cost.",
        S["Body"]))

    story.append(Paragraph("Request lifecycle — POST /generate", S["H2"]))
    story.append(Paragraph(
        "1. extract_params(prompt)  ·  2. unknown shape → error + suggestion  ·  3. missing_fields on primitives → ask user (compounds fill defaults)  ·  "
        "4. validate_geometry (dims, walls, hole vs body, fillet vs min side, 2000 mm cap / 4000 mm furniture)  ·  "
        "5. uuid session_id  ·  6. generate_model  ·  7. sessions.save  ·  8. JSON: params, properties, file URLs.",
        S["BodyBullet"]))
    story.append(Paragraph(
        "<b>POST /edit</b> loads previous params, applies local regex or LLM “full JSON rewrite”, same validate+rebuild. "
        "<b>POST /generate_manual</b> is the backend-friendly path: exact params, zero LLM — use this in the interview as your contract/test seam.",
        S["Body"]))

    # ---------- KERNEL ----------
    story.append(Paragraph("4. Geometry kernel — sequential CAD ops (deterministic)", S["H1"]))
    story.append(Paragraph(
        "build_final_model is a compiler: JSON in, BRep solid out. Order is intentional for topology and CPU:",
        S["Body"]))
    story.append(table([
        [cell("Step", h), cell("Why this order", h)],
        [cell("1. Primitive / compound builder", b),
         cell("Untouched solid so face centers/normals stay predictable for later workplanes.", c)],
        [cell("2. Circular then square holes (polar or grid)", b),
         cell("Cuts on a face workplane. Chair/bed/table skip generic holes (they own their holes).", c)],
        [cell("3. Shell / hollow", b),
         cell("Before fillet+text — cheaper, cleaner topology. Optional open face.", c)],
        [cell("4. Fillet or chamfer ALL edges", b),
         cell("If done after glyphs, OCCT tries to fillet every letter — slow/fail. So body first.", c)],
        [cell("5. Text last (engrave cut / emboss add)", b),
         cell("clean=False ~10× faster; depth sign + mode; fontsize clamped to face width; 24-char cap.", c)],
    ], [55 * mm, 119 * mm]))
    story.append(Paragraph(
        "<b>Boolean CSG:</b> holes are extruded tools fused then cut from the body. Text uses combine='cut' or 'a'. Failures in features are often non-fatal (print + skip) so one bad fillet doesn’t kill the whole part — mention as a product choice, then admit it can hide bugs.",
        S["Body"]))
    story.append(Paragraph(
        "<b>Parametric vs mesh:</b> STEP is the CAD-native BRep. STL/GLB are tessellations for 3D print and the web viewer. If they ask “why not just generate a mesh with an ML model?” — because dimensions must be exact, editable, and rebuildable. Params JSON + CadQuery is the parametric source of truth.",
        S["Body"]))

    story.append(Paragraph("5. Parsing pipeline — what “NLP” really is", S["H1"]))
    story.append(Paragraph(
        "This is <b>not</b> a classical NLP stack (no spaCy NER, no CFG compiler). It is a <b>constrained extraction pipeline</b> with three fast paths and one slow path:",
        S["Body"]))
    story.append(Paragraph("• <b>Cache:</b> SHA1(normalized prompt), 64 entries, FIFO eviction — identical prompts are instant.", S["BodyBullet"]))
    story.append(Paragraph("• <b>Heuristic (0 LLM):</b> regex for box/cylinder/sphere; keyword match for 16 everyday objects; unit conversion mm/cm/m/in.", S["BodyBullet"]))
    story.append(Paragraph("• <b>LLM single shot:</b> Groq JSON mode, temperature 0, system prompt enumerates shapes, required dims, hole patterns, edge_treatment, text_features. One call (old design was normalize+extract = 2 RTTs).", S["BodyBullet"]))
    story.append(Paragraph("• <b>Local edit:</b> “make it 10mm taller”, set width/height/diameter, remove hole — no LLM.", S["BodyBullet"]))
    story.append(Paragraph("• <b>Offline compounds:</b> if API key missing, bottle/chair/… still work from defaults.", S["BodyBullet"]))
    story.append(Paragraph(
        "The LLM output is then _finalize: alias map (desk→table), compound defaults, engrave depth forced negative. "
        "That is how you get “deterministic interpretation” despite a stochastic model: <b>schema + post-process + validator + kernel</b>.",
        S["Body"]))
    story.append(Paragraph(
        "If they say “your resume says rule-based NLP”: “The durable part is rules and schema. The LLM is a fuzzy front-end that I don’t trust with numbers for engineering.”",
        S["Tip"]))

    # ---------- BACKEND ----------
    story.append(PageBreak())
    story.append(Paragraph("6. Backend engineering (this is what a BE interviewer wants)", S["H1"]))
    story.append(table([
        [cell("Topic", h), cell("Implementation", h), cell("If they go deeper", h)],
        [cell("API contract", b),
         cell("Pydantic request models. Success JSON vs {success:false, errors[]}. Partial params when dims missing.", c),
         cell("Idempotency: generate always new session; edit is stateful.", c)],
        [cell("Validation as a gate", b),
         cell("Never kernel-run illegal JSON. Walls ≥0.4 mm, fillet &lt; half min side, hole vs body, text depth ≠ 0.", c),
         cell("Fail closed on dims; fail open (skip) on some feature exceptions.", c)],
        [cell("Session / history", b),
         cell("SessionStore: history[] + cursor. New edit truncates redo branch. File lock + JSON persist.", c),
         cell("Single-process lock. Not multi-instance safe. Admit this.", c)],
        [cell("Concurrency", b),
         cell("ThreadPoolExecutor(2): STEP export ∥ STL→GLB. CadQuery/OCCT is not great under many threads.", c),
         cell("Scale-out: queue workers, one kernel per process.", c)],
        [cell("LLM I/O", b),
         cell("1 retry, JSON mode fallback, never log API key (/health configured bool only).", c),
         cell("Timeouts/circuit breaker not fully productized.", c)],
        [cell("CORS", b),
         cell("allow_origins=* — fine for a demo, wrong for production.", c),
         cell("Lock origins, auth, signed export URLs.", c)],
        [cell("Testing seam", b),
         cell("/generate_manual + params JSON. Heuristics tagged _pipeline.", c),
         cell("Golden STL hashes; property-based dim tests.", c)],
    ], [38 * mm, 72 * mm, 64 * mm]))

    story.append(Paragraph("Why FastAPI + CadQuery (not Three.js-only, not Blender bpy as the kernel)", S["H2"]))
    story.append(Paragraph(
        "CadQuery sits on Open CASCADE: real BRep, fillets, STEP. FastAPI is the orchestration layer a backend team understands: typed routes, sync CPU work, static frontend. "
        "The UI is not the product; the params schema + kernel is.",
        S["Body"]))

    # ---------- AGENTIC ----------
    story.append(Paragraph("7. “Agentic AI” — honest answer (memorize)", S["H1"]))
    story.append(Paragraph(
        "If they ask “is this agentic?”, do <b>not</b> say yes-and-stop. Use this framing:",
        S["Body"]))
    story.append(Paragraph(
        "<b>What we have today:</b> a <i>tool-using pipeline</i> with specialist modules. The LLM has one job: map language → CAD JSON. "
        "Downstream “agents” in the README (beam, BOM, drawing, DFM) are <b>deterministic functions</b>, not LLM agents. "
        "They never invent numbers. That is a feature for manufacturing.",
        S["A"]))
    story.append(Paragraph(
        "<b>What “agentic” would mean:</b> a planner that decomposes “design a printable nameplate that fits this envelope and costs under $2”, "
        "calls tools in a loop (extract → DFM → resize → re-export), uses memory, and stops on a success criterion. "
        "That is LangGraph/supervisor+tools — explicitly deferred in the repo.",
        S["A"]))
    story.append(Paragraph(
        "<b>Why we didn’t agent-loop the kernel:</b> CAD booleans are expensive and non-associative here (fillet-all-edges is not a feature tree). "
        "An agent retrying fillets can hang OCCT. Better: constrained JSON + validator + one-shot kernel.",
        S["A"]))
    story.append(Paragraph("Degrees of agency (use this ladder)", S["H2"]))
    story.append(table([
        [cell("Level", h), cell("CAD Forge today", h), cell("Next if they ask “roadmap”", h)],
        [cell("L0 Chatbot", b), cell("No — we emit solids + files, not just text.", c), cell("—", c)],
        [cell("L1 Tool call", b), cell("Yes: LLM → structured tool args (the JSON schema).", c), cell("JSON schema / function-calling strictly typed.", c)],
        [cell("L2 Multi-step agent", b), cell("Partial: /edit is a second step with prior state. No autonomous loop.", c), cell("LangGraph: extract → DFM critique → auto-fix dims → stop.", c)],
        [cell("L3 Multi-agent", b), cell("No. Modules are functions, not chatting agents.", c), cell("Planner + CAD + DFM + cost critic with shared state.", c)],
    ], [40 * mm, 72 * mm, 62 * mm]))
    story.append(Paragraph(
        "Phrase that sounds senior: “I used the LLM as a probabilistic parser behind a deterministic compiler. Agency without a compiler is a liability in CAD.”",
        S["Tip"]))

    story.append(Paragraph("8. Cross-questions they will actually ask", S["H1"]))

    qa = [
        ("How do you guarantee the model matches the prompt?",
         "You don’t 100%. You guarantee the solid matches the JSON. Confidence comes from: temp=0, JSON mode, required-field list, validator, and heuristic bypass. Ambiguous English (“a small box”) either hits missing_fields or compound defaults. Show the params JSON in the UI so the user can audit."),
        ("Why JSON as the intermediate representation?",
         "It is serializable, versionable, editable without the LLM, cacheable, and the session history is just a list of JSON snapshots. That’s undo. It’s also your API for /generate_manual and tests. A free-form CadQuery script from the LLM would be an RCE and non-reproducible."),
        ("Why not let the LLM write CadQuery/Python?",
         "Codegen is unbounded: import os, infinite loops, topology that never returns. A schema is a capability sandbox. Backend answer: least privilege."),
        ("How do fillets fail?",
         "Fillet radius larger than local curvature/thickness, or after holes creating tiny edges. We validate radius vs min dimension, then try/except skip. Production should return a structured warning, not a print()."),
        ("Holes on a cylinder?",
         "Side faces of curved shapes are forced to >Z (flat). Polar pattern on the top of a cylinder is the intended bolt-circle case. Radial holes through the barrel are a known gap."),
        ("Units?",
         "Prompt may be cm/m/inch; kernel is always mm. Conversion is in the extractor. Internally never mix units."),
        ("How would you test this in CI without Groq?",
         "Golden tests on /generate_manual and heuristics. Mock Groq to return fixtures. Don’t snapshot binary STL only — assert volume, bbox, and key params. Optional: hash tessellation with fixed linearDeflection."),
        ("How would you scale to 1k concurrent users?",
         "LLM: queue + Groq RPM limits + cache (Redis). Kernel: process pool, not threads (OCCT). Sessions: Postgres, not a JSON file. Object storage for STL/STEP. Don’t run CadQuery inside the FastAPI event loop for long jobs — background worker (Celery/RQ/arq). Idempotent job ids."),
        ("Is the session store safe?",
         "threading.Lock + rewrite of one JSON file. Fine for a single Uvicorn worker demo. Race across workers, no TTL, no auth, files in /outputs are guessable 8-char ids. Production: DB + auth + signed URLs."),
        ("Async FastAPI but CadQuery is blocking?",
         "Correct observation. generate is async def wrapping sync OCCT. Under load it blocks the event loop. Fix: run_in_executor or make those routes sync and use more workers, or a job queue."),
        ("What’s parametric about this?",
         "The part is defined by named dimensions. Changing height_mm and rebuilding is parametric. It is NOT a full feature tree (no parent-child sketch constraints like SolidWorks). Compounds are scripts with defaults, not a constraint solver."),
        ("Difference STL vs STEP?",
         "STL: triangles, 3D print, lossy. STEP: BRep, CAD interchange, exact cylinders stay cylinders. GLB: web viewer."),
        ("How does DFM relate?",
         "Separate analyzer on params/solid: thin walls, hole clearance, aspect ratio, text depth. Grade is advice, not a hard gate (except validator mins). Could close the loop agentically later."),
        ("Prompt injection?",
         "User text goes into the LLM. Kernel only consumes parsed JSON fields we expect. Still: huge text, unexpected keys. sanitize_params + ignore unknown ops. Never exec() LLM text."),
        ("Cost/latency of LLM?",
         "One Groq call, max_tokens ~700, temp 0. Heuristic and cache avoid it. Was 2 calls, now 1. Nameplates: fillet-before-text ~6× faster than fillet-after-glyphs."),
        ("Why Groq / llama-3.3-70b?",
         "Low latency JSON, cheap for a demo. Tradeoff vs GPT-4o: more schema misses. Mitigated by JSON mode, aliases, validator. Model is env-configurable."),
        ("Compounds vs primitives?",
         "Primitives are generic CSG. Compounds are named recipes (mug = body + handle, etc.) with defaults so “a chair” works. Tradeoff: 16 hand-authored shapes, not open-world generation."),
        ("Can it do assemblies / mates?",
         "No. Single solid (or compound as one solid). BOM is a list of session parts, not a constraint assembly."),
        ("Material / mass?",
         "Volume from OCCT solid.Volume(); density table; cost = volume × price. Print estimate uses volume + bbox heuristic, not slicer G-code."),
    ]
    for q, a in qa:
        story.append(Paragraph("Q: " + q, S["Q"]))
        story.append(Paragraph(a, S["A"]))

    # ---------- DRAWBACKS ----------
    story.append(PageBreak())
    story.append(Paragraph("9. Current drawbacks (say these before they do — huge credibility)", S["H1"]))
    story.append(table([
        [cell("Gap", h), cell("Reality in this repo", h), cell("What you’d do next", h)],
        [cell("Not a full CAD feature tree", b),
         cell("Ops are a linear script. Edit “move the hole” is fuzzy. Fillet is all-edges, not selected edges.", c),
         cell("Explicit feature list with ids; per-edge selection.", c)],
        [cell("Open-world geometry", b),
         cell("10 primitives + 16 compounds. “Turbine blade” or “phone enclosure with snaps” will fail or become a box.", c),
         cell("More recipes, or LLM→feature graph with human confirm.", c)],
        [cell("LLM schema drift", b),
         cell("Wrong keys, missing pattern type, hallucinated dims. Heuristics don’t cover fillets/holes (those force LLM).", c),
         cell("Pydantic output model + retry-on-validate + few-shot.", c)],
        [cell("Topology robustness", b),
         cell("try/except skip on hole/shell/fillet/text. User may get a part missing the feature they asked for.", c),
         cell("Return warnings[] in API; never silent skip.", c)],
        [cell("Sessions / multi-worker", b),
         cell("JSON file + process lock. CORS *. 8-char ids in /outputs.", c),
         cell("Postgres, auth, object storage, tighter CORS.", c)],
        [cell("Blocking kernel on async routes", b),
         cell("OCCT on event loop; no job queue; no progress SSE for long fillets.", c),
         cell("Worker queue + job status endpoint.", c)],
        [cell("No true FEA", b),
         cell("Beam formulas only (SS/cantilever, point/UDL). Not mesh FEA.", c),
         cell("Be honest: closed-form first; FEA later.", c)],
        [cell("Text / fonts", b),
         cell("Arial, 24 chars, clean=False. Not true CAM engraving toolpaths.", c),
         cell("Outline curves + depth as a proper cut.", c)],
        [cell("No auth / multi-tenant", b),
         cell("Local demo. Library and sessions are shared-disk.", c),
         cell("User isolation is table-stakes for a product.", c)],
        [cell("Cache invalidation", b),
         cell("In-process dict, 64 items, not shared, no TTL on meaning of “box”.", c),
         cell("Redis keyed by prompt+schema version.", c)],
        [cell("Agent loop missing", b),
         cell("Cannot autonomously satisfy DFM then rebuild.", c),
         cell("LangGraph: critic tool on DFM grade.", c)],
        [cell("Units / locale", b),
         cell("Inch supported in parser; UI is mm-centric.", c),
         cell("Display unit preference, store canonical mm.", c)],
    ], [42 * mm, 68 * mm, 64 * mm]))

    story.append(Paragraph("10. Design tradeoffs (they love these)", S["H1"]))
    story.append(Paragraph("• <b>Schema vs codegen:</b> less flexible, much safer and testable. Choose schema.", S["BodyBullet"]))
    story.append(Paragraph("• <b>One LLM call vs agent loop:</b> latency and cost; agent loop better for DFM but needs hard stop conditions.", S["BodyBullet"]))
    story.append(Paragraph("• <b>Heuristic before LLM:</b> determinism and $0 for “box 50×30×20”; worse for messy English.", S["BodyBullet"]))
    story.append(Paragraph("• <b>Fillet all edges:</b> one parameter, looks “designed”; cannot fillet only the top rim of a mug without a compound-specific path.", S["BodyBullet"]))
    story.append(Paragraph("• <b>Fail-open features:</b> demo never hard-crashes; manufacturing user may not notice a missing hole — you’d fail-closed in v2.", S["BodyBullet"]))
    story.append(Paragraph("• <b>Compounds as Python, not LLM meshes:</b> a “chair” is always your recipe, so it’s printable-ish and parametric; it will never be a designer chair.", S["BodyBullet"]))

    story.append(Paragraph("11. If they ask you to design v2 on a whiteboard", S["H1"]))
    story.append(Paragraph(
        "1) <b>Canonical Feature Graph</b> (shape node + feature nodes with ids). 2) <b>Pydantic v2 schema</b> as the LLM tool. "
        "3) <b>Job queue</b> + object storage. 4) <b>Redis cache</b> keyed by schema version. 5) <b>warnings[]</b> never silent skip. "
        "6) Optional <b>LangGraph</b>: extractor → kernel → DFM tool → if grade &lt; B, propose param patches → max 3 retries → human confirm. "
        "7) Postgres sessions. 8) Don’t put LLM on beam math.",
        S["Body"]))

    story.append(Paragraph("12. Resume-risk questions (fix your wording live)", S["H1"]))
    story.append(Paragraph(
        "They may read “rule-based NLP” and expect tokenization, POS tags, dependency parse, or a CFG. "
        "<b>Correction in interview:</b> “I used rule-based extraction and a constrained LLM, not a linguistics NLP pipeline.” "
        "They may read “agentic” if you say it — only use it as the L1–L2 ladder above. "
        "They may read “realtime” — you mean interactive request/response (seconds), not a 60 fps CAD kernel. "
        "They may read “diverse geometric configurations” — be concrete: primitives, patterns, compounds; not arbitrary B-rep from a photo.",
        S["Body"]))

    story.append(Paragraph("13. Mini glossary (backend + CAD)", S["H1"]))
    story.append(Paragraph(
        "<b>BRep</b> — boundary representation (faces/edges/vertices), what STEP stores.  "
        "<b>CSG</b> — constructive solid geometry (union/cut/intersect).  "
        "<b>Workplane</b> — local 2D sketch plane on a face.  "
        "<b>Parametric</b> — rebuild from dimensions.  "
        "<b>Tessellation</b> — BRep → triangles (STL).  "
        "<b>DFM</b> — design for manufacturability.  "
        "<b>FoS</b> — factor of safety (beam module).  "
        "<b>Polar pattern</b> — N holes on a pitch circle (bolt circle).",
        S["Body"]))

    story.append(Paragraph("14. Closing line", S["H1"]))
    story.append(Paragraph(
        "“The interesting backend problem wasn’t generating a mesh. It was putting an untrusted language model behind a schema, a validator, and a deterministic geometry compiler so the output is inspectable, cacheable, and exportable as STEP.”",
        S["Body"]))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "Files to mention if they want code: app/llm.py (extract/edit/cache), app/validator.py, app/cad_engine.py (build_final_model), app/main.py (/generate /edit /generate_manual), app/session.py.",
        S["Small"]))

    doc = SimpleDocTemplate(
        OUT, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=20 * mm, bottomMargin=16 * mm,
        title="CAD Forge — Backend Interview Prep",
        author="CAD Forge interview notes",
    )
    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)
    print(OUT)


if __name__ == "__main__":
    build()

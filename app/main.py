from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, FileResponse
from pydantic import BaseModel
from typing import Optional, Any, Dict, List
import zipfile
import io
import json

from app.llm import extract_params, edit_params, llm_status
from app.validator import validate_geometry
from app.cad_engine import generate_model, build_final_model
from app.session import SessionStore
from app.templates import list_templates
from app.materials import list_materials, DEFAULT_MATERIAL, material_cost, weight_grams, MATERIALS
from app.engineering_materials import list_structural_materials
from app.calculations import analyze_beam
from app.bom import build_bom
from app.drawing import generate_drawing
from app.dfm import analyze_dfm
from app.standards import list_fasteners, bolt_circle_params
from app.library import PartLibrary
from app.compounds import list_compounds, apply_compound_defaults, COMPOUND_BUILDERS
from app.params_utils import sanitize_params

import uuid
import os

APP_VERSION = "3.1"
app = FastAPI(title="CAD Forge", version=APP_VERSION)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

os.makedirs("outputs", exist_ok=True)
app.mount("/outputs", StaticFiles(directory="outputs"), name="outputs")
app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")

sessions = SessionStore()
library = PartLibrary()


@app.get("/")
async def root():
    return RedirectResponse(url="/frontend/index.html")


class PromptRequest(BaseModel):
    prompt: str
    material: Optional[str] = None


class EditRequest(BaseModel):
    session_id: str
    edit: str
    material: Optional[str] = None


class ManualRequest(BaseModel):
    """Bypass the LLM entirely and submit CAD parameters directly (power-user / offline mode)."""
    params: Dict[str, Any]
    material: Optional[str] = None
    session_id: Optional[str] = None


class SessionIdRequest(BaseModel):
    session_id: str


class RestoreRequest(BaseModel):
    session_id: str
    version_index: int  # 0-based


class CloneRequest(BaseModel):
    session_id: str
    material: Optional[str] = None


class BeamCalcRequest(BaseModel):
    span_mm: float
    load_kg: float
    width_mm: Optional[float] = None
    height_mm: Optional[float] = None
    diameter_mm: Optional[float] = None
    support: str = "simply_supported"
    load_type: str = "point_center"
    material: Optional[str] = None
    min_fos: float = 1.5


class BomLineRequest(BaseModel):
    part_number: Optional[str] = None
    description: Optional[str] = None
    session_id: str
    quantity: int = 1


class BomRequest(BaseModel):
    items: list[BomLineRequest]


class DrawingRequest(BaseModel):
    session_id: str
    part_number: Optional[str] = None
    description: Optional[str] = None


class DfmRequest(BaseModel):
    session_id: Optional[str] = None
    params: Optional[Dict[str, Any]] = None


class BoltCircleRequest(BaseModel):
    session_id: str
    fastener: str = "M4"
    count: int = 6
    pitch_diameter_mm: Optional[float] = None
    hole_type: str = "clearance"
    face: str = "top"
    material: Optional[str] = None


class LibrarySaveRequest(BaseModel):
    name: str
    session_id: Optional[str] = None
    params: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    notes: Optional[str] = ""


class LibraryLoadRequest(BaseModel):
    part_id: str
    material: Optional[str] = None


class ScaleRequest(BaseModel):
    session_id: str
    factor: float
    material: Optional[str] = None


class BeamToCadRequest(BaseModel):
    """Turn a successful beam analysis into a CAD beam (box or cylinder)."""
    span_mm: float
    width_mm: Optional[float] = None
    height_mm: Optional[float] = None
    diameter_mm: Optional[float] = None
    material: Optional[str] = "steel"


def _model_response(session_id: str, params: dict, result: dict, extra: dict = None) -> dict:
    meta = sessions.meta(session_id)
    try:
        dfm = analyze_dfm(params)
    except Exception as e:  # noqa: BLE001 — never 500 the client over advisory DFM
        print(f"DFM skipped: {e}")
        dfm = {"score": 0, "grade": "?", "summary": "DFM unavailable", "checks": [], "printable": True}
    payload = {
        "success": True,
        "session_id": session_id,
        "glb_url": f"/outputs/{session_id}.glb",
        "stl_url": f"/outputs/{session_id}.stl",
        "step_url": f"/outputs/{session_id}.step",
        "params": params,
        "properties": result["properties"],
        "can_undo": meta["can_undo"],
        "can_redo": meta["can_redo"],
        "history_version": meta["version"],
        "history_total": meta["total"],
        "understood_as": params.get("_clarified_as", ""),
        "pipeline": params.get("_pipeline", ""),
        "dfm": dfm,
    }
    if extra:
        payload.update(extra)
    return payload


def _safe_generate(params: dict, session_id: str, material: str = None):
    """Build model; return (result, None) or (None, error_response)."""
    try:
        params = sanitize_params(params)
        result = generate_model(params, session_id, material=material)
        return params, result, None
    except Exception as e:  # noqa: BLE001
        print(f"CAD build error: {e}")
        return params, None, {
            "success": False,
            "errors": [
                f"Could not build that model: {e}",
                "Try a smaller hole, a different face (e.g. backrest), or simpler dimensions.",
            ],
        }


def _scale_params(params: dict, factor: float) -> dict:
    out = dict(params)
    for k, v in list(out.items()):
        if k.endswith("_mm") and isinstance(v, (int, float)):
            out[k] = round(v * factor, 4)
        elif k.endswith("_mm") is False and k in ("sides", "points"):
            continue
    # nested patterns
    for key in ("circ_hole_pattern", "square_hole_pattern"):
        pat = out.get(key)
        if isinstance(pat, dict):
            new_pat = dict(pat)
            for pk, pv in pat.items():
                if isinstance(pv, (int, float)) and ("mm" in pk or pk in ("radius_mm", "spacing_mm", "pitch_mm")):
                    new_pat[pk] = round(pv * factor, 4)
            out[key] = new_pat
    feats = out.get("text_features")
    if isinstance(feats, list):
        new_feats = []
        for f in feats:
            nf = dict(f)
            if isinstance(nf.get("depth_mm"), (int, float)):
                nf["depth_mm"] = round(nf["depth_mm"] * factor, 4)
            if isinstance(nf.get("fontsize"), (int, float)):
                nf["fontsize"] = round(nf["fontsize"] * factor, 2)
            new_feats.append(nf)
        out["text_features"] = new_feats
    return out


@app.post("/generate")
async def generate(req: PromptRequest):
    try:
        params = extract_params(req.prompt)
    except RuntimeError as e:
        return {"success": False, "errors": [str(e)]}

    params = sanitize_params(params)

    if params.get("shape") == "unknown":
        return {
            "success": False,
            "errors": [params.get("_error", "Could not understand your description."),
                       params.get("_suggestion", "")],
        }

    if params.get("missing_fields") and params.get("shape") not in COMPOUND_BUILDERS:
        missing = params["missing_fields"]
        return {
            "success": False,
            "errors": [f"Please specify: {', '.join(missing)}"],
            "partial_params": params,
            "hint": f"I understood you want a {params.get('shape')} — just need the missing dimensions.",
        }

    errors = validate_geometry(params)
    if errors:
        return {"success": False, "errors": errors}

    session_id = str(uuid.uuid4())[:8]
    if req.material:
        params["material"] = req.material
    params, result, err = _safe_generate(params, session_id, material=req.material)
    if err:
        return err
    sessions.save(session_id, params)

    return _model_response(session_id, params, result)


@app.post("/edit")
async def edit(req: EditRequest):
    prev = sessions.get(req.session_id)
    if not prev:
        return {"success": False, "errors": ["Unknown session — please generate a model first."]}

    try:
        params = edit_params(prev, req.edit)
    except RuntimeError as e:
        return {"success": False, "errors": [str(e)]}

    params = sanitize_params(params)
    errors = validate_geometry(params)
    if errors:
        return {"success": False, "errors": errors}

    if req.material:
        params["material"] = req.material
    params, result, err = _safe_generate(params, req.session_id, material=req.material)
    if err:
        return err
    sessions.save(req.session_id, params)

    return _model_response(req.session_id, params, result)


@app.post("/generate_manual")
async def generate_manual(req: ManualRequest):
    """Power-user path: submit exact CAD parameters as JSON, no LLM involved."""
    params = sanitize_params(req.params)
    if params.get("shape") in COMPOUND_BUILDERS:
        params = apply_compound_defaults(params)
    errors = validate_geometry(params)
    if errors:
        return {"success": False, "errors": errors}

    session_id = req.session_id or str(uuid.uuid4())[:8]
    if req.material:
        params["material"] = req.material
    params, result, err = _safe_generate(params, session_id, material=req.material)
    if err:
        return err
    sessions.save(session_id, params)

    return _model_response(session_id, params, result)


@app.get("/compounds")
async def compounds():
    """List everyday compound shapes available via prompt (not template buttons)."""
    return {"compounds": list_compounds()}


@app.post("/undo")
async def undo(req: SessionIdRequest):
    params = sessions.undo(req.session_id)
    if params is None:
        return {"success": False, "errors": ["Nothing to undo."]}
    result = generate_model(params, req.session_id)
    return _model_response(req.session_id, params, result)


@app.post("/redo")
async def redo(req: SessionIdRequest):
    params = sessions.redo(req.session_id)
    if params is None:
        return {"success": False, "errors": ["Nothing to redo."]}
    result = generate_model(params, req.session_id)
    return _model_response(req.session_id, params, result)


@app.post("/restore")
async def restore(req: RestoreRequest):
    params = sessions.restore_version(req.session_id, req.version_index)
    if params is None:
        return {"success": False, "errors": ["Invalid version index."]}
    result = generate_model(params, req.session_id)
    return _model_response(req.session_id, params, result)


@app.post("/clone")
async def clone(req: CloneRequest):
    prev = sessions.get(req.session_id)
    if not prev:
        return {"success": False, "errors": ["Unknown session."]}
    params = dict(prev)
    new_id = str(uuid.uuid4())[:8]
    if req.material:
        params["material"] = req.material
    result = generate_model(params, new_id, material=req.material)
    sessions.save(new_id, params)
    return _model_response(new_id, params, result, {"cloned_from": req.session_id})


@app.post("/scale")
async def scale(req: ScaleRequest):
    prev = sessions.get(req.session_id)
    if not prev:
        return {"success": False, "errors": ["Unknown session."]}
    if req.factor <= 0 or req.factor > 100:
        return {"success": False, "errors": ["Scale factor must be between 0 and 100."]}
    params = _scale_params(prev, req.factor)
    errors = validate_geometry(params)
    if errors:
        return {"success": False, "errors": errors}
    if req.material:
        params["material"] = req.material
    result = generate_model(params, req.session_id, material=req.material)
    sessions.save(req.session_id, params)
    return _model_response(req.session_id, params, result)


@app.get("/history/{session_id}")
async def history(session_id: str):
    hist = sessions.history(session_id)
    meta = sessions.meta(session_id)
    return {"history": hist, **meta}


@app.get("/sessions")
async def list_sessions():
    return {"sessions": sessions.list_sessions()}


@app.get("/templates")
async def templates():
    return {"templates": list_templates()}


@app.get("/materials")
async def materials():
    return {"materials": list_materials(), "default": DEFAULT_MATERIAL}


@app.get("/health")
async def health():
    status = llm_status()
    return {
        "status": "ok",
        "version": APP_VERSION,
        "llm": status,
    }


@app.get("/examples")
async def examples():
    """Curated prompts for the empty-state / quick chips."""
    return {
        "examples": [
            {"label": "Water bottle", "prompt": "a water bottle 220mm tall"},
            {"label": "Coffee mug", "prompt": "a coffee mug 90mm tall"},
            {"label": "Simple chair", "prompt": "a simple wooden chair"},
            {"label": "Bolt flange", "prompt": "a cylinder 60mm diameter and 10mm tall with 6 bolt holes of 4mm diameter in a circle of 20mm radius on the top"},
            {"label": "Hollow box", "prompt": "a box 60mm wide, 60mm deep, 40mm tall, hollowed out with a 3mm wall thickness and the top face open"},
            {"label": "Bookshelf", "prompt": "a bookshelf with 4 shelves"},
            {"label": "Phone stand", "prompt": "a phone stand"},
            {"label": "Nameplate", "prompt": "a box 80mm wide 40mm deep 5mm tall, engrave CAD FORGE 1.5mm deep on the top, fillet 1mm"},
        ]
    }


class MaterialCompareRequest(BaseModel):
    session_id: str
    materials: Optional[List[str]] = None


@app.post("/compare_materials")
async def compare_materials(req: MaterialCompareRequest):
    """Compare weight/cost of the current solid across materials (no rebuild)."""
    params = sessions.get(req.session_id)
    if not params:
        return {"success": False, "errors": ["Unknown session."]}
    result = generate_model(params, req.session_id)
    vol = result["properties"]["volume_mm3"]
    ids = req.materials or list(MATERIALS.keys())
    rows = []
    for mid in ids:
        if mid not in MATERIALS:
            continue
        rows.append({
            "id": mid,
            "label": MATERIALS[mid]["label"],
            "density_g_cm3": MATERIALS[mid]["density_g_cm3"],
            "cost_per_kg": MATERIALS[mid]["cost_per_kg"],
            "weight_g": weight_grams(vol, mid),
            "cost_usd": material_cost(vol, mid),
        })
    rows.sort(key=lambda r: r["cost_usd"])
    return {"success": True, "volume_mm3": vol, "materials": rows}


# ---------------------------------------------------------------------
# PHASE 1+: Engineering, DFM, standards, library, export pack
# ---------------------------------------------------------------------

@app.post("/calculate_beam")
async def calculate_beam(req: BeamCalcRequest):
    try:
        result = analyze_beam(
            span_mm=req.span_mm, load_kg=req.load_kg,
            width_mm=req.width_mm, height_mm=req.height_mm, diameter_mm=req.diameter_mm,
            support=req.support, load_type=req.load_type,
            material=req.material, min_fos=req.min_fos,
        )
        return {"success": True, "result": result}
    except ValueError as e:
        return {"success": False, "errors": [str(e)]}


@app.post("/beam_to_cad")
async def beam_to_cad(req: BeamToCadRequest):
    """Generate a CAD solid matching the analyzed beam cross-section × span."""
    if req.diameter_mm:
        params = {
            "shape": "cylinder",
            "diameter_mm": req.diameter_mm,
            "height_mm": req.span_mm,
            "material": req.material or "steel",
            "_clarified_as": f"Beam: Ø{req.diameter_mm}mm × {req.span_mm}mm span",
        }
    elif req.width_mm and req.height_mm:
        params = {
            "shape": "box",
            "width_mm": req.width_mm,
            "depth_mm": req.height_mm,
            "height_mm": req.span_mm,
            "material": req.material or "steel",
            "_clarified_as": f"Beam: {req.width_mm}×{req.height_mm}mm × {req.span_mm}mm span",
        }
    else:
        return {"success": False, "errors": ["Provide diameter_mm or width_mm + height_mm."]}

    errors = validate_geometry(params)
    if errors:
        return {"success": False, "errors": errors}

    session_id = str(uuid.uuid4())[:8]
    result = generate_model(params, session_id, material=req.material)
    sessions.save(session_id, params)
    return _model_response(session_id, params, result)


@app.get("/structural_materials")
async def structural_materials():
    return {"materials": list_structural_materials()}


@app.post("/bom")
async def bom(req: BomRequest):
    items = []
    for line in req.items:
        params = sessions.get(line.session_id)
        if not params:
            return {"success": False, "errors": [f"Unknown session_id: {line.session_id}"]}
        result = generate_model(params, line.session_id)
        items.append({
            "part_number": line.part_number or line.session_id,
            "description": line.description or params.get("shape", "part"),
            "quantity": line.quantity,
            "properties": result["properties"],
        })
    return {"success": True, "bom": build_bom(items)}


@app.post("/drawing")
async def drawing(req: DrawingRequest):
    params = sessions.get(req.session_id)
    if not params:
        return {"success": False, "errors": [f"Unknown session_id: {req.session_id}"]}

    result = generate_model(params, req.session_id)
    model = build_final_model(params)

    files = generate_drawing(
        model, req.session_id,
        part_number=req.part_number or req.session_id,
        description=req.description or params.get("shape", "part"),
        material=result["properties"]["material"],
        properties=result["properties"],
    )
    return {
        "success": True,
        "svg_url": f"/outputs/{req.session_id}_drawing.svg",
        "pdf_url": f"/outputs/{req.session_id}_drawing.pdf" if files["pdf"] else None,
    }


@app.post("/dfm")
async def dfm(req: DfmRequest):
    if req.params:
        params = req.params
    elif req.session_id:
        params = sessions.get(req.session_id)
        if not params:
            return {"success": False, "errors": ["Unknown session."]}
    else:
        return {"success": False, "errors": ["Provide session_id or params."]}
    return {"success": True, "dfm": analyze_dfm(params)}


@app.get("/fasteners")
async def fasteners():
    return {"fasteners": list_fasteners()}


@app.post("/apply_bolt_circle")
async def apply_bolt_circle(req: BoltCircleRequest):
    prev = sessions.get(req.session_id)
    if not prev:
        return {"success": False, "errors": ["Unknown session."]}
    try:
        fragment = bolt_circle_params(
            req.fastener, req.count, req.pitch_diameter_mm, req.hole_type, req.face,
        )
    except ValueError as e:
        return {"success": False, "errors": [str(e)]}

    params = dict(prev)
    params.update({k: v for k, v in fragment.items() if not k.startswith("_")})
    params["_fastener"] = fragment.get("_fastener")
    errors = validate_geometry(params)
    if errors:
        return {"success": False, "errors": errors}
    if req.material:
        params["material"] = req.material
    result = generate_model(params, req.session_id, material=req.material)
    sessions.save(req.session_id, params)
    return _model_response(req.session_id, params, result)


@app.get("/library")
async def library_list():
    return {"parts": library.list()}


@app.post("/library/save")
async def library_save(req: LibrarySaveRequest):
    if req.params:
        params = req.params
        sid = req.session_id
    elif req.session_id:
        params = sessions.get(req.session_id)
        if not params:
            return {"success": False, "errors": ["Unknown session."]}
        sid = req.session_id
    else:
        return {"success": False, "errors": ["Provide session_id or params."]}
    item = library.save(req.name, params, session_id=sid, tags=req.tags, notes=req.notes or "")
    return {"success": True, "part": item}


@app.post("/library/load")
async def library_load(req: LibraryLoadRequest):
    item = library.get(req.part_id)
    if not item:
        return {"success": False, "errors": ["Part not found in library."]}
    params = dict(item["params"])
    if req.material:
        params["material"] = req.material
    errors = validate_geometry(params)
    if errors:
        return {"success": False, "errors": errors}
    session_id = str(uuid.uuid4())[:8]
    result = generate_model(params, session_id, material=req.material)
    sessions.save(session_id, params)
    return _model_response(session_id, params, result, {"library_part": item["name"]})


@app.delete("/library/{part_id}")
async def library_delete(part_id: str):
    ok = library.delete(part_id)
    if not ok:
        return {"success": False, "errors": ["Part not found."]}
    return {"success": True}


@app.get("/export_pack/{session_id}")
async def export_pack(session_id: str):
    """ZIP of STL + GLB + STEP + params JSON (+ drawing if present)."""
    params = sessions.get(session_id)
    if not params:
        return {"success": False, "errors": ["Unknown session."]}

    # Ensure files exist
    generate_model(params, session_id)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for ext in ("stl", "glb", "step"):
            path = f"outputs/{session_id}.{ext}"
            if os.path.exists(path):
                zf.write(path, f"{session_id}.{ext}")
        zf.writestr(f"{session_id}_params.json", json.dumps(params, indent=2))
        for suffix in ("_drawing.svg", "_drawing.pdf"):
            path = f"outputs/{session_id}{suffix}"
            if os.path.exists(path):
                zf.write(path, f"{session_id}{suffix}")
    buf.seek(0)
    tmp = f"outputs/{session_id}_pack.zip"
    with open(tmp, "wb") as f:
        f.write(buf.read())
    return FileResponse(tmp, filename=f"{session_id}_cad_pack.zip", media_type="application/zip")

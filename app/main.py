from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Any, Dict

from app.llm import extract_params, edit_params
from app.validator import validate_geometry
from app.cad_engine import generate_model
from app.session import SessionStore
from app.templates import list_templates
from app.materials import list_materials, DEFAULT_MATERIAL

import uuid
import os

app = FastAPI(title="CAD Generator", version="2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

os.makedirs("outputs", exist_ok=True)
app.mount("/outputs", StaticFiles(directory="outputs"), name="outputs")
app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")

sessions = SessionStore()


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


def _model_response(session_id: str, params: dict, result: dict, extra: dict = None) -> dict:
    payload = {
        "success": True,
        "session_id": session_id,
        "glb_url": f"/outputs/{session_id}.glb",
        "stl_url": f"/outputs/{session_id}.stl",
        "step_url": f"/outputs/{session_id}.step",
        "params": params,
        "properties": result["properties"],
        "can_undo": sessions.can_undo(session_id),
        "can_redo": sessions.can_redo(session_id),
        "understood_as": params.get("_clarified_as", ""),
    }
    if extra:
        payload.update(extra)
    return payload


@app.post("/generate")
async def generate(req: PromptRequest):
    try:
        params = extract_params(req.prompt)
    except RuntimeError as e:
        return {"success": False, "errors": [str(e)]}

    if params.get("shape") == "unknown":
        return {
            "success": False,
            "errors": [params.get("_error", "Could not understand your description."),
                       params.get("_suggestion", "")],
        }

    if params.get("missing_fields"):
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
    result = generate_model(params, session_id, material=req.material)
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

    errors = validate_geometry(params)
    if errors:
        return {"success": False, "errors": errors}

    result = generate_model(params, req.session_id, material=req.material)
    sessions.save(req.session_id, params)

    return _model_response(req.session_id, params, result)


@app.post("/generate_manual")
async def generate_manual(req: ManualRequest):
    """Power-user path: submit exact CAD parameters as JSON, no LLM involved."""
    params = req.params
    errors = validate_geometry(params)
    if errors:
        return {"success": False, "errors": errors}

    session_id = req.session_id or str(uuid.uuid4())[:8]
    result = generate_model(params, session_id, material=req.material)
    sessions.save(session_id, params)

    return _model_response(session_id, params, result)


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


@app.get("/history/{session_id}")
async def history(session_id: str):
    return {"history": sessions.history(session_id)}


@app.get("/templates")
async def templates():
    return {"templates": list_templates()}


@app.get("/materials")
async def materials():
    return {"materials": list_materials(), "default": DEFAULT_MATERIAL}


@app.get("/health")
async def health():
    return {"status": "ok"}

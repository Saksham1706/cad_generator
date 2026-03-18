from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from app.llm import extract_params, edit_params
from app.validator import validate_geometry
from app.cad_engine import generate_model
from app.session import SessionStore
import uuid, os

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/outputs", StaticFiles(directory="outputs"), name="outputs")
app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")

sessions = SessionStore()

class PromptRequest(BaseModel):
    prompt: str

class EditRequest(BaseModel):
    session_id: str
    edit: str

@app.post("/generate")
async def generate(req: PromptRequest):
    params = extract_params(req.prompt)
    
    # LLM couldn't understand the shape
    if params.get("shape") == "unknown":
        return {
            "success": False,
            "errors": [
                params.get("_error", "Could not understand your description."),
                params.get("_suggestion", "")
            ]
        }
    
    # Missing required fields — ask user to be specific
    if params.get("missing_fields"):
        missing = params["missing_fields"]
        return {
            "success": False,
            "errors": [f"Please specify: {', '.join(missing)}"],
            "partial_params": params,
            "hint": f"I understood you want a {params.get('shape')} — just need the missing dimensions."
        }
    
    errors = validate_geometry(params)
    if errors:
        return {"success": False, "errors": errors}
    
    session_id = str(uuid.uuid4())[:8]
    paths = generate_model(params, session_id)
    sessions.save(session_id, params)
    
    return {
        "success": True,
        "session_id": session_id,
        "glb_url": f"/outputs/{session_id}.glb",
        "stl_url": f"/outputs/{session_id}.stl",
        "params": params,
        "understood_as": params.get("_clarified_as", "")
    }
    
@app.post("/edit")
async def edit(req: EditRequest):
    prev = sessions.get(req.session_id)
    params = edit_params(prev, req.edit)
    errors = validate_geometry(params)
    if errors:
        return {"success": False, "errors": errors}

    paths = generate_model(params, req.session_id)
    sessions.save(req.session_id, params)

    return {
        "success": True,
        "session_id": req.session_id,        # ← this was missing
        "glb_url": f"/outputs/{req.session_id}.glb",
        "stl_url": f"/outputs/{req.session_id}.stl",
        "params": params
    }
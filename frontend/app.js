console.log("CAD Forge app.js v11");
const API = window.location.origin.includes("null") || window.location.protocol === "file:"
  ? "http://127.0.0.1:8000"
  : window.location.origin;

const PROMPT_HISTORY_KEY = "cadforge_prompt_history";
const MAX_PROMPT_HISTORY = 12;

let currentSession = null;
let currentParams = null;
let currentProps = null;
let jsonMode = false;
let lastBeamPayload = null;
let allTemplates = [];
let autoRotateOn = true;
let bomLines = [];

const EDITABLE_KEYS = [
  "shape", "width_mm", "height_mm", "depth_mm", "diameter_mm",
  "outer_diameter_mm", "inner_diameter_mm", "base_diameter_mm", "top_diameter_mm",
  "torus_diameter_mm", "tube_diameter_mm", "base_width_mm", "base_depth_mm",
  "top_width_mm", "top_depth_mm", "sides", "points",
  "circ_hole_dia_mm", "sq_hole_side_mm", "square_hole_size_mm",
  "shell_thickness_mm", "edge_treatment", "edge_radius_mm", "material",
  "seat_width_mm", "seat_depth_mm", "seat_height_mm", "back_height_mm",
  "body_diameter_mm", "wall_mm", "shelf_count", "leg_count",
];

document.addEventListener("DOMContentLoaded", () => {
  loadHealth();
  loadExamples();
  loadTemplates();
  loadMaterials();
  loadStructuralMaterials();
  loadFasteners();
  loadLibrary();
  syncAutoRotateButton();
  restoreFromUrl();
  bindShortcuts();
});

// ---------------------------------------------------------------------
// Tabs / toasts / shortcuts / loading
// ---------------------------------------------------------------------
function switchTab(name) {
  document.querySelectorAll(".tab").forEach(t => t.classList.toggle("active", t.dataset.tab === name));
  document.querySelectorAll(".tab-panel").forEach(p => p.classList.toggle("active", p.id === "tab-" + name));
}

function toast(msg, type = "info") {
  const host = document.getElementById("toast-host");
  const el = document.createElement("div");
  el.className = "toast " + type;
  el.textContent = msg;
  host.appendChild(el);
  setTimeout(() => el.classList.add("show"), 10);
  setTimeout(() => {
    el.classList.remove("show");
    setTimeout(() => el.remove(), 300);
  }, 3200);
}

function setLoading(on, text) {
  const overlay = document.getElementById("loading-overlay");
  const label = document.getElementById("loading-text");
  if (text) label.textContent = text;
  overlay.classList.toggle("hidden", !on);
}

function isTypingTarget(e) {
  const tag = ((e.target || {}).tagName || "");
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || (e.target && e.target.isContentEditable);
}

function isBusy() {
  const overlay = document.getElementById("loading-overlay");
  return overlay && !overlay.classList.contains("hidden");
}

function bindShortcuts() {
  document.addEventListener("keydown", (e) => {
    if (isBusy()) return;
    const key = (e.key || "").toLowerCase();
    if ((e.ctrlKey || e.metaKey) && key === "enter") {
      e.preventDefault();
      const editFocused = document.activeElement && document.activeElement.id === "edit-prompt";
      if (editFocused) {
        if (!document.getElementById("edit-btn").disabled) editModel();
      } else if (jsonMode) {
        if (!document.getElementById("json-generate-btn").disabled) generateManual();
      } else if (!document.getElementById("generate-btn").disabled) {
        generate();
      }
    }
    if ((e.ctrlKey || e.metaKey) && key === "z" && !e.shiftKey) {
      if (isTypingTarget(e)) return;
      e.preventDefault();
      if (!document.getElementById("undo-btn").disabled) doUndo();
    }
    if ((e.ctrlKey || e.metaKey) && (key === "y" || (key === "z" && e.shiftKey))) {
      if (isTypingTarget(e)) return;
      e.preventDefault();
      if (!document.getElementById("redo-btn").disabled) doRedo();
    }
  });
}

async function parseJsonResponse(res) {
  const text = await res.text();
  try {
    return JSON.parse(text);
  } catch {
    throw new Error(res.ok
      ? "Server returned non-JSON"
      : `Server error ${res.status}: ${text.slice(0, 120)}`);
  }
}

function copyShareLink() {
  if (!currentSession) {
    toast("Generate a model first", "warn");
    return;
  }
  const url = `${window.location.origin}${window.location.pathname}?session=${currentSession}`;
  navigator.clipboard.writeText(url).then(() => toast("Share link copied")).catch(() => {
    prompt("Copy this link:", url);
  });
}

function errorList(data) {
  if (!data) return ["Request failed"];
  if (Array.isArray(data.errors) && data.errors.filter(Boolean).length) {
    return data.errors.filter(Boolean);
  }
  if (Array.isArray(data.detail)) {
    return data.detail.map(d => (d && (d.msg || d.message)) || JSON.stringify(d));
  }
  if (typeof data.detail === "string") return [data.detail];
  return ["Request failed"];
}

async function restoreFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const sid = params.get("session");
  if (!sid) return;
  try {
    setLoading(true, "Restoring session…");
    const res = await fetch(API + "/history/" + sid);
    const data = await parseJsonResponse(res);
    if (!data.history || !data.history.length) {
      toast("No saved model for that link", "warn");
      return;
    }
    const index = Math.max(0, (data.version || data.history.length) - 1);
    const man = await fetch(API + "/restore", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sid, version_index: index }),
    });
    handleResponse(await parseJsonResponse(man), "Restore");
  } catch (err) {
    toast(err.message || "Could not restore that session", "err");
  } finally {
    setLoading(false);
  }
}

// ---------------------------------------------------------------------
// Catalogs
// ---------------------------------------------------------------------
async function loadHealth() {
  try {
    const res = await fetch(API + "/health");
    const data = await res.json();
    const badge = document.getElementById("model-badge");
    const llm = data.llm || {};
    const model = llm.model || "unknown";
    const short = model.includes("/") ? model.split("/").pop() : model;
    badge.textContent = llm.configured ? short : "JSON only";
    badge.title = llm.configured
      ? `Groq · ${model}`
      : "No GROQ_API_KEY — use JSON Mode or everyday object names";
    badge.classList.toggle("warn", !llm.configured);
  } catch (err) {
    const badge = document.getElementById("model-badge");
    badge.textContent = "offline";
    badge.classList.add("warn");
  }
}

async function loadExamples() {
  try {
    const res = await fetch(API + "/examples");
    const data = await res.json();
    const chips = document.getElementById("example-chips");
    const empty = document.getElementById("empty-chips");
    const render = (host) => {
      if (!host) return;
      host.innerHTML = "";
      (data.examples || []).forEach(ex => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "chip";
        btn.textContent = ex.label;
        btn.title = ex.prompt;
        btn.onclick = () => {
          document.getElementById("prompt").value = ex.prompt;
          switchTab("design");
          document.getElementById("prompt").focus();
        };
        host.appendChild(btn);
      });
    };
    render(chips);
    render(empty);
  } catch (err) {
    console.error("examples:", err);
  }
}

async function loadTemplates() {
  try {
    const res = await fetch(API + "/templates");
    const data = await res.json();
    allTemplates = data.templates || [];
    renderTemplates(allTemplates);
  } catch (err) {
    console.error("templates:", err);
  }
}

function renderTemplates(groups) {
  const container = document.getElementById("template-groups");
  container.innerHTML = "";
  groups.forEach(group => {
    const groupEl = document.createElement("div");
    groupEl.className = "template-group";
    const title = document.createElement("div");
    title.className = "template-group-title";
    title.textContent = group.category;
    groupEl.appendChild(title);
    const row = document.createElement("div");
    row.className = "template-row";
    group.items.forEach(item => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "template-btn";
      btn.textContent = item.label;
      btn.title = item.prompt;
      btn.onclick = () => {
        document.getElementById("prompt").value = item.prompt;
        document.getElementById("prompt").focus();
        switchTab("design");
      };
      row.appendChild(btn);
    });
    groupEl.appendChild(row);
    container.appendChild(groupEl);
  });
  if (!container.children.length) {
    container.innerHTML = '<p class="muted">No templates match.</p>';
  }
}

async function loadMaterials() {
  try {
    const res = await fetch(API + "/materials");
    const data = await res.json();
    const select = document.getElementById("material-select");
    const jsonSelect = document.getElementById("json-material");
    select.innerHTML = "";
    if (jsonSelect) jsonSelect.innerHTML = "";
    data.materials.forEach(m => {
      const opt = document.createElement("option");
      opt.value = m.id;
      opt.textContent = `${m.label} · ${m.density_g_cm3} g/cm³ · $${m.cost_per_kg}/kg`;
      if (m.id === data.default) opt.selected = true;
      select.appendChild(opt);
      if (jsonSelect) jsonSelect.appendChild(opt.cloneNode(true));
    });
  } catch (err) {
    console.error("materials:", err);
  }
}

async function loadStructuralMaterials() {
  try {
    const res = await fetch(API + "/structural_materials");
    const data = await res.json();
    const select = document.getElementById("beam-material");
    data.materials.forEach(m => {
      const opt = document.createElement("option");
      opt.value = m.id;
      opt.textContent = `${m.label} (σy ${m.yield_strength_mpa} MPa)`;
      select.appendChild(opt);
    });
  } catch (err) {
    console.error("structural mats:", err);
  }
}

function currentMaterial() {
  const select = document.getElementById("material-select");
  return select ? select.value : undefined;
}

function toggleMode() {
  jsonMode = !jsonMode;
  document.getElementById("json-card").classList.toggle("hidden", !jsonMode);
  document.getElementById("prompt-card").classList.toggle("hidden", jsonMode);
  document.getElementById("template-card").classList.toggle("hidden", jsonMode);
  document.getElementById("example-card").classList.toggle("hidden", jsonMode);
  document.getElementById("mode-toggle").textContent = jsonMode ? "Prompt Mode" : "JSON Mode";
}

function toggleBeamSection() {
  const circ = document.getElementById("beam-section").value === "circ";
  document.getElementById("beam-rect-fields").classList.toggle("hidden", circ);
  document.getElementById("beam-circ-fields").classList.toggle("hidden", !circ);
}

// ---------------------------------------------------------------------
// Prompt history (localStorage)
// ---------------------------------------------------------------------
function getPromptHistory() {
  try {
    return JSON.parse(localStorage.getItem(PROMPT_HISTORY_KEY) || "[]");
  } catch {
    return [];
  }
}

function savePromptHistory(prompt) {
  if (!prompt) return;
  let hist = getPromptHistory().filter(p => p !== prompt);
  hist.unshift(prompt);
  hist = hist.slice(0, MAX_PROMPT_HISTORY);
  localStorage.setItem(PROMPT_HISTORY_KEY, JSON.stringify(hist));
}

function showPromptHistory() {
  const panel = document.getElementById("prompt-history");
  const hist = getPromptHistory();
  if (!hist.length) {
    toast("No recent prompts yet", "warn");
    return;
  }
  if (!panel.classList.contains("hidden")) {
    panel.classList.add("hidden");
    return;
  }
  panel.innerHTML = hist.map((p, i) =>
    `<button type="button" class="history-item" data-i="${i}">${escapeHtml(p).slice(0, 90)}</button>`
  ).join("");
  panel.querySelectorAll("button").forEach(btn => {
    btn.onclick = () => {
      document.getElementById("prompt").value = hist[+btn.dataset.i];
      panel.classList.add("hidden");
    };
  });
  panel.classList.remove("hidden");
}

// ---------------------------------------------------------------------
// Generate / edit / history
// ---------------------------------------------------------------------
async function generate() {
  const prompt = document.getElementById("prompt").value.trim();
  if (!prompt) {
    toast("Enter a description", "warn");
    return;
  }
  const btn = document.getElementById("generate-btn");
  btn.textContent = "Generating…";
  btn.disabled = true;
  setLoading(true, "Generating model…");
  try {
    const res = await fetch(API + "/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt, material: currentMaterial() }),
    });
    const data = await parseJsonResponse(res);
    if (data.success) savePromptHistory(prompt);
    handleResponse(data);
  } catch (err) {
    showError(err.message || "Could not reach the server. Is uvicorn running?");
  }
  btn.textContent = "Generate Model";
  btn.disabled = false;
  setLoading(false);
}

async function generateManual() {
  const raw = document.getElementById("json-input").value.trim();
  if (!raw) {
    toast("Paste JSON parameters first", "warn");
    return;
  }
  let params;
  try {
    params = JSON.parse(raw);
  } catch (err) {
    showError("Invalid JSON: " + err.message);
    return;
  }
  const btn = document.getElementById("json-generate-btn");
  btn.textContent = "Generating…";
  btn.disabled = true;
  setLoading(true, "Building from JSON…");
  try {
    const body = { params, session_id: currentSession || undefined };
    if (!params.material) {
      const jsonMat = document.getElementById("json-material");
      body.material = (jsonMat && jsonMat.value) || currentMaterial();
    }
    const res = await fetch(API + "/generate_manual", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    handleResponse(await parseJsonResponse(res), "JSON build");
  } catch (err) {
    showError(err.message || "Could not reach the server.");
  }
  btn.textContent = "Generate from JSON";
  btn.disabled = false;
  setLoading(false);
}

async function editModel() {
  const edit = document.getElementById("edit-prompt").value.trim();
  if (!edit) {
    toast("Describe the change", "warn");
    return;
  }
  if (!currentSession) {
    toast("Generate a model first", "warn");
    return;
  }
  const btn = document.getElementById("edit-btn");
  btn.textContent = "Applying…";
  btn.disabled = true;
  setLoading(true, "Applying edit…");
  try {
    const res = await fetch(API + "/edit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: currentSession, edit, material: currentMaterial() }),
    });
    handleResponse(await parseJsonResponse(res));
  } catch (err) {
    showError(err.message || "Could not reach the server.");
  }
  btn.textContent = "Apply Edit";
  btn.disabled = false;
  setLoading(false);
}

async function doUndo() {
  if (!currentSession || document.getElementById("undo-btn").disabled) return;
  setLoading(true, "Undo…");
  try {
    const res = await fetch(API + "/undo", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: currentSession }),
    });
    handleResponse(await parseJsonResponse(res), "Undo");
  } catch (err) {
    toast(err.message || "Undo failed", "err");
  } finally {
    setLoading(false);
  }
}

async function doRedo() {
  if (!currentSession || document.getElementById("redo-btn").disabled) return;
  setLoading(true, "Redo…");
  try {
    const res = await fetch(API + "/redo", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: currentSession }),
    });
    handleResponse(await parseJsonResponse(res), "Redo");
  } catch (err) {
    toast(err.message || "Redo failed", "err");
  } finally {
    setLoading(false);
  }
}

// ---------------------------------------------------------------------
// Viewer materials
// ---------------------------------------------------------------------
function setMaterial(metallic, roughness, el = null) {
  const viewer = document.getElementById("viewer");
  document.querySelectorAll(".mat-btn").forEach(b => {
    if (!["auto-rotate-btn"].includes(b.id)) b.classList.remove("active");
  });
  if (el && el.id !== "auto-rotate-btn") el.classList.add("active");
  function apply() {
    if (viewer.model) {
      const mat = viewer.model.materials[0];
      mat.pbrMetallicRoughness.setMetallicFactor(metallic);
      mat.pbrMetallicRoughness.setRoughnessFactor(roughness);
    }
  }
  viewer.addEventListener("load", function onLoad() {
    apply();
    viewer.removeEventListener("load", onLoad);
  });
  apply();
}

function setColor(hex, el = null) {
  const viewer = document.getElementById("viewer");
  document.querySelectorAll(".color-btn").forEach(b => b.classList.remove("active"));
  if (el) el.classList.add("active");
  const r = parseInt(hex.slice(1, 3), 16) / 255;
  const g = parseInt(hex.slice(3, 5), 16) / 255;
  const b = parseInt(hex.slice(5, 7), 16) / 255;
  function apply() {
    if (viewer.model) {
      const material = viewer.model.materials[0];
      material.pbrMetallicRoughness.setBaseColorFactor([r, g, b, 1]);
    }
  }
  viewer.addEventListener("load", function onLoad() {
    apply();
    viewer.removeEventListener("load", onLoad);
  });
  apply();
}

function syncViewerToMaterial(matId) {
  const presets = {
    pla: ["#6b8cae", 0.15, 0.55],
    abs: ["#3d3d4a", 0.1, 0.6],
    petg: ["#2d8a5e", 0.2, 0.45],
    nylon: ["#c8c4b8", 0.05, 0.7],
    resin: ["#c45c26", 0.3, 0.35],
    aluminum: ["#b0b8c0", 0.95, 0.25],
    steel: ["#8a9098", 1.0, 0.2],
    stainless: ["#c0c4c8", 1.0, 0.15],
    brass: ["#c9a227", 0.9, 0.3],
    titanium: ["#9aa0a8", 0.85, 0.28],
    copper: ["#b87333", 0.95, 0.22],
    oak: ["#8b5a2b", 0.05, 0.75],
    acrylic: ["#88ccee", 0.1, 0.15],
  };
  const p = presets[matId] || presets.pla;
  setColor(p[0]);
  setMaterial(p[1], p[2]);
}

function syncAutoRotateButton() {
  const btn = document.getElementById("auto-rotate-btn");
  if (btn) btn.classList.toggle("active", autoRotateOn);
}

function toggleAutoRotate() {
  const viewer = document.getElementById("viewer");
  autoRotateOn = !autoRotateOn;
  if (viewer) {
    if (autoRotateOn) viewer.setAttribute("auto-rotate", "");
    else viewer.removeAttribute("auto-rotate");
  }
  syncAutoRotateButton();
}

function resetCamera() {
  const viewer = document.getElementById("viewer");
  if (viewer && typeof viewer.resetTurntableRotation === "function") {
    viewer.resetTurntableRotation();
  }
  if (viewer && typeof viewer.jumpCameraToGoal === "function") {
    viewer.cameraOrbit = "0deg 75deg 105%";
    viewer.jumpCameraToGoal();
  }
  toast("View reset");
}

// ---------------------------------------------------------------------
// Response handling
// ---------------------------------------------------------------------
function showClarification(data) {
  const box = document.getElementById("clarify-box");
  if (!box) return;
  const partial = data && data.partial_params;
  const missing = (partial && partial.missing_fields) || [];
  if (!partial || !missing.length) {
    box.classList.add("hidden");
    box.innerHTML = "";
    return;
  }
  box.classList.remove("hidden");
  box.innerHTML = `<p class="hint">${escapeHtml(data.hint || "Add the missing dimensions.")}</p>` +
    missing.map(f => `<label>${escapeHtml(f)}<input type="number" min="0.1" step="0.1" data-miss="${escapeHtml(f)}"></label>`).join("") +
    `<button type="button" class="btn-primary" id="clarify-build">Build with these sizes</button>`;
  document.getElementById("clarify-build").onclick = () => submitClarification(partial);
}

async function submitClarification(partial) {
  const params = JSON.parse(JSON.stringify(partial));
  let complete = true;
  document.querySelectorAll("#clarify-box input").forEach(input => {
    const v = parseFloat(input.value);
    if (!input.value || Number.isNaN(v) || v <= 0) complete = false;
    else params[input.dataset.miss] = v;
  });
  if (!complete) {
    toast("Fill every missing dimension", "warn");
    return;
  }
  delete params.missing_fields;
  setLoading(true, "Building…");
  try {
    const res = await fetch(API + "/generate_manual", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        params,
        material: params.material || currentMaterial(),
        session_id: currentSession || undefined,
      }),
    });
    handleResponse(await parseJsonResponse(res), "Build");
  } catch (err) {
    toast(err.message || "Could not build", "err");
  } finally {
    setLoading(false);
  }
}

function handleResponse(data, op) {
  const errBox = document.getElementById("errors");
  if (!data || data.success !== true) {
    const messages = errorList(data);
    let html = "<b>Fix these issues:</b><ul>" +
      messages.map(e => "<li>" + escapeHtml(e) + "</li>").join("") + "</ul>";
    if (data && data.hint) html += '<p class="hint">' + escapeHtml(data.hint) + "</p>";
    errBox.innerHTML = html;
    errBox.classList.remove("hidden");
    showClarification(data);
    toast((op || "Generation") + " failed", "err");
    return false;
  }

  errBox.classList.add("hidden");
  showClarification(null);
  if (data.session_id) currentSession = data.session_id;
  currentParams = data.params || {};
  currentProps = data.properties || {};

  document.getElementById("empty-state").classList.add("hidden");
  const viewerSection = document.getElementById("viewer-section");
  viewerSection.classList.remove("hidden");

  const glbUrl = API + data.glb_url;
  const oldViewer = document.getElementById("viewer");
  const parent = oldViewer.parentNode;
  oldViewer.remove();
  const newViewer = document.createElement("model-viewer");
  newViewer.id = "viewer";
  newViewer.setAttribute("camera-controls", "");
  if (autoRotateOn) newViewer.setAttribute("auto-rotate", "");
  newViewer.setAttribute("shadow-intensity", "1");
  newViewer.setAttribute("exposure", "0.85");
  newViewer.setAttribute("src", glbUrl + "?t=" + Date.now());
  parent.insertBefore(newViewer, parent.firstChild);
  syncAutoRotateButton();

  document.getElementById("dl-glb").href = glbUrl;
  document.getElementById("dl-stl").href = API + data.stl_url;
  document.getElementById("dl-step").href = API + data.step_url;

  const badge = document.getElementById("session-badge");
  badge.textContent = "session " + currentSession;
  badge.classList.remove("hidden");

  const cleanParams = {};
  for (const key in data.params) {
    if (!key.startsWith("_")) cleanParams[key] = data.params[key];
  }
  const paramsBox = document.getElementById("params-box");
  paramsBox.textContent = JSON.stringify(cleanParams, null, 2);
  paramsBox.classList.remove("hidden");
  document.getElementById("json-input").value = JSON.stringify(cleanParams, null, 2);

  document.getElementById("edit-section").classList.remove("hidden");
  document.getElementById("inspector-section").classList.remove("hidden");

  const clarified = data.understood_as || data.params?._clarified_as || "";
  const pipeline = data.pipeline || data.params?._pipeline || "";
  const banner = document.getElementById("clarify-banner");
  if (clarified || pipeline) {
    banner.textContent = (clarified ? "Understood as: " + clarified : "")
      + (pipeline ? (clarified ? "  ·  " : "") + "via " + pipeline : "");
    banner.classList.remove("hidden");
  } else {
    banner.classList.add("hidden");
  }

  if (cleanParams.material) {
    const sel = document.getElementById("material-select");
    if (sel && [...sel.options].some(o => o.value === cleanParams.material)) {
      sel.value = cleanParams.material;
    }
    const jsonSel = document.getElementById("json-material");
    if (jsonSel && [...jsonSel.options].some(o => o.value === cleanParams.material)) {
      jsonSel.value = cleanParams.material;
    }
  }

  renderProperties(data.properties);
  renderPrintEstimate(data.properties);
  renderDfm(data.dfm);
  renderHistoryControls(data);
  renderInspector(cleanParams);
  syncViewerToMaterial(cleanParams.material || currentMaterial());
  const shape = cleanParams.shape || "part";
  toast(op ? (op + " complete") : ("Model ready · " + shape));
  return true;
}

function renderProperties(props) {
  const panel = document.getElementById("properties-panel");
  if (!props) {
    panel.innerHTML = "";
    return;
  }
  const bb = props.bounding_box_mm || {};
  const cost = props.cost_usd != null ? `$${props.cost_usd}` : "—";
  panel.innerHTML = `
    <div class="prop-item"><span class="prop-label">Volume</span><span class="prop-value">${props.volume_cm3} cm³</span></div>
    <div class="prop-item"><span class="prop-label">Bounding box</span><span class="prop-value">${bb.x} × ${bb.y} × ${bb.z} mm</span></div>
    <div class="prop-item"><span class="prop-label">Weight</span><span class="prop-value">${props.weight_g} g <span class="prop-material">(${props.material})</span></span></div>
    <div class="prop-item"><span class="prop-label">Est. material cost</span><span class="prop-value">${cost}</span></div>
  `;
}

function renderPrintEstimate(props) {
  const panel = document.getElementById("print-panel");
  const pe = props && props.print_estimate;
  if (!pe) {
    panel.classList.add("hidden");
    return;
  }
  panel.classList.remove("hidden");
  if (!pe.applicable) {
    panel.innerHTML = `<div class="muted">${escapeHtml(pe.note || "Print estimate N/A for this material.")}</div>`;
    return;
  }
  const time = pe.est_hours >= 1
    ? `${pe.est_hours} h`
    : `${pe.est_minutes} min`;
  panel.innerHTML = `
    <div class="dfm-head">
      <span class="print-icon" aria-hidden="true">P</span>
      <div>
        <strong>FDM print estimate</strong>
        <div class="muted">${pe.layer_height_mm}mm layers · ${pe.infill_pct}% infill · rough guide</div>
      </div>
    </div>
    <div class="stat-grid mt">
      <div><span class="prop-label">Time</span><div class="prop-value sm">${time}</div></div>
      <div><span class="prop-label">Filament</span><div class="prop-value sm">${pe.filament_g} g</div></div>
      <div><span class="prop-label">Length</span><div class="prop-value sm">${pe.filament_m} m</div></div>
    </div>`;
}

function renderDfm(dfm) {
  const panel = document.getElementById("dfm-panel");
  if (!dfm) {
    panel.classList.add("hidden");
    return;
  }
  panel.classList.remove("hidden");
  const gradeClass = "grade-" + (dfm.grade || "C").toLowerCase();
  let html = `<div class="dfm-head"><span class="dfm-grade ${gradeClass}">${dfm.grade}</span>
    <div><strong>DFM score ${dfm.score}/100</strong><div class="muted">${escapeHtml(dfm.summary || "")}</div></div></div><ul class="dfm-list">`;
  (dfm.checks || []).forEach(c => {
    html += `<li class="dfm-${c.level}"><span class="dot"></span>${escapeHtml(c.message)}</li>`;
  });
  html += "</ul>";
  panel.innerHTML = html;
}

function renderHistoryControls(data) {
  document.getElementById("undo-btn").disabled = !data.can_undo;
  document.getElementById("redo-btn").disabled = !data.can_redo;
  const count = document.getElementById("history-count");
  const v = data.history_version || 1;
  const t = data.history_total || 1;
  count.textContent = `v${v} / ${t}`;
}

async function toggleHistoryPanel() {
  const panel = document.getElementById("history-panel");
  if (!panel.classList.contains("hidden")) {
    panel.classList.add("hidden");
    return;
  }
  if (!currentSession) return;
  const res = await fetch(API + "/history/" + currentSession);
  const data = await res.json();
  panel.innerHTML = "";
  (data.history || []).forEach((p, i) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "history-item" + (i === (data.version - 1) ? " active" : "");
    const shape = p.shape || "?";
    const note = p._clarified_as || ["width_mm", "depth_mm", "height_mm", "diameter_mm"]
      .filter(k => p[k] != null)
      .map(k => k.replace("_mm", "") + " " + p[k])
      .join(", ");
    btn.textContent = `v${i + 1} · ${shape} — ${note}`.slice(0, 80);
    btn.onclick = () => restoreVersion(i);
    panel.appendChild(btn);
  });
  panel.classList.remove("hidden");
}

async function restoreVersion(index) {
  setLoading(true, "Restoring version…");
  try {
    const res = await fetch(API + "/restore", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: currentSession, version_index: index }),
    });
    if (handleResponse(await parseJsonResponse(res), "Restore")) {
      document.getElementById("history-panel").classList.add("hidden");
    }
  } catch (err) {
    toast(err.message || "Restore failed", "err");
  } finally {
    setLoading(false);
  }
}

function renderInspector(params) {
  const grid = document.getElementById("inspector-fields");
  grid.innerHTML = "";
  const keys = Object.keys(params).filter(k =>
    EDITABLE_KEYS.includes(k) || k.endsWith("_mm") || ["sides", "points", "shape", "edge_treatment", "material", "shelf_count", "leg_count"].includes(k)
  );
  const seen = new Set();
  keys.forEach(k => {
    if (seen.has(k)) return;
    seen.add(k);
    const val = params[k];
    if (typeof val === "object") return;
    const label = document.createElement("label");
    label.textContent = k;
    const input = document.createElement("input");
    input.dataset.key = k;
    input.value = val;
    if (typeof val === "number") input.type = "number";
    else input.type = "text";
    label.appendChild(input);
    grid.appendChild(label);
  });
}

async function applyInspector() {
  if (!currentParams) return;
  const params = JSON.parse(JSON.stringify(currentParams));
  document.querySelectorAll("#inspector-fields input").forEach(input => {
    const k = input.dataset.key;
    const raw = input.value.trim();
    if (raw === "") return;
    if (input.type === "number") {
      const v = parseFloat(raw);
      if (Number.isNaN(v)) return;
      params[k] = v;
    } else {
      params[k] = raw;
    }
  });
  setLoading(true, "Rebuilding…");
  try {
    const res = await fetch(API + "/generate_manual", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ params, material: params.material || currentMaterial(), session_id: currentSession }),
    });
    handleResponse(await parseJsonResponse(res), "Rebuild");
  } catch (err) {
    toast(err.message || "Rebuild failed", "err");
  } finally {
    setLoading(false);
  }
}

function showError(msg) {
  const errBox = document.getElementById("errors");
  errBox.innerHTML = "<b>Error:</b> " + escapeHtml(msg);
  errBox.classList.remove("hidden");
}

function cleanParamsForExport() {
  if (!currentParams) return null;
  const clean = {};
  for (const key in currentParams) {
    if (!key.startsWith("_")) clean[key] = currentParams[key];
  }
  return clean;
}

function copyParams() {
  const clean = cleanParamsForExport();
  if (!clean) {
    toast("No params yet", "warn");
    return;
  }
  const text = JSON.stringify(clean, null, 2);
  navigator.clipboard.writeText(text).then(() => toast("Params copied")).catch(() => {
    prompt("Copy params:", text);
  });
}

// ---------------------------------------------------------------------
// Beam engineer
// ---------------------------------------------------------------------
async function runBeamCalc() {
  const section = document.getElementById("beam-section").value;
  const payload = {
    span_mm: +document.getElementById("beam-span").value,
    load_kg: +document.getElementById("beam-load").value,
    support: document.getElementById("beam-support").value,
    load_type: document.getElementById("beam-load-type").value,
    min_fos: +document.getElementById("beam-fos").value,
    material: document.getElementById("beam-material").value || null,
  };
  if (section === "circ") {
    payload.diameter_mm = +document.getElementById("beam-d").value;
  } else {
    payload.width_mm = +document.getElementById("beam-w").value;
    payload.height_mm = +document.getElementById("beam-h").value;
  }
  lastBeamPayload = payload;

  const box = document.getElementById("beam-result");
  try {
    const res = await fetch(API + "/calculate_beam", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await parseJsonResponse(res);
    if (!data.success) {
      box.innerHTML = "<b>Error:</b> " + errorList(data).map(escapeHtml).join(", ");
      box.classList.remove("hidden");
      toast("Beam analysis failed", "err");
      return false;
    }
    const r = data.result;
    const sectionDesc = (r.inputs && r.inputs.section) || "—";
    let html = `
      <div class="stat-grid">
        <div><span class="prop-label">Max stress</span><div class="prop-value">${r.max_bending_stress_mpa} MPa</div></div>
        <div><span class="prop-label">Section</span><div class="prop-value sm">${sectionDesc}</div></div>
        <div><span class="prop-label">I</span><div class="prop-value sm">${r.section_properties.I_mm4} mm⁴</div></div>
      </div>`;
    if (r.material) {
      const c = r.material;
      html += `<p class="mt">Material <b>${c.label || c.id}</b> — FoS <b>${c.factor_of_safety}</b>, deflection <b>${c.deflection_mm} mm</b>
        ${c.passes_min_fos ? '<span class="tag ok">PASS</span>' : '<span class="tag fail">FAIL</span>'}</p>`;
    }
    if (r.recommended_materials && r.recommended_materials.length) {
      html += "<p class='mt'><b>Recommended (cheapest OK):</b></p><ul>";
      r.recommended_materials.slice(0, 4).forEach(m => {
        html += `<li>${m.label} — FoS ${m.fos}, defl. ${m.deflection_mm}mm, $${m.cost_per_kg}/kg</li>`;
      });
      html += "</ul>";
    }
    if (r.warning) html += `<p class="mt" style="color:#f0b0a0">${escapeHtml(r.warning)}</p>`;
    html += `<p class="mt muted">Formula: ${escapeHtml(r.deflection_formula || "")} · M<sub>max</sub> ${r.max_bending_moment_Nmm} N·mm</p>`;
    box.innerHTML = html;
    box.classList.remove("hidden");
    toast("Beam analysis complete");
    return true;
  } catch (err) {
    box.innerHTML = "<b>Error:</b> " + escapeHtml(err.message || "Could not reach the server");
    box.classList.remove("hidden");
    toast("Beam analysis failed", "err");
    return false;
  }
}

async function beamToCad() {
  if (!lastBeamPayload) {
    const ok = await runBeamCalc();
    if (!ok) return;
  }
  const p = lastBeamPayload || {};
  const chosen = document.getElementById("beam-material").value;
  const body = {
    span_mm: p.span_mm || +document.getElementById("beam-span").value,
    material: chosen || p.material || "steel",
  };
  if (p.diameter_mm || document.getElementById("beam-section").value === "circ") {
    body.diameter_mm = p.diameter_mm || +document.getElementById("beam-d").value;
  } else {
    body.width_mm = p.width_mm || +document.getElementById("beam-w").value;
    body.height_mm = p.height_mm || +document.getElementById("beam-h").value;
  }
  setLoading(true, "Generating beam CAD…");
  try {
    const res = await fetch(API + "/beam_to_cad", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (handleResponse(await parseJsonResponse(res), "Beam CAD")) {
      switchTab("design");
    }
  } catch (err) {
    toast(err.message || "Beam CAD failed", "err");
  } finally {
    setLoading(false);
  }
}

// ---------------------------------------------------------------------
// Exports (viewer toolbar)
// ---------------------------------------------------------------------
async function generateDrawing() {
  if (!currentSession) {
    toast("Generate a part first", "warn");
    return;
  }
  toast("Generating drawing…");
  setLoading(true, "Drawing…");
  try {
    const res = await fetch(API + "/drawing", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: currentSession,
        part_number: currentSession,
        description: (currentParams && currentParams.shape) || "part",
      }),
    });
    const data = await parseJsonResponse(res);
    if (!data.success) {
      toast(errorList(data).join(", "), "err");
      return;
    }
    window.open(API + data.svg_url, "_blank");
    toast("Drawing ready");
  } catch (err) {
    toast(err.message || "Drawing failed", "err");
  } finally {
    setLoading(false);
  }
}

async function downloadPack() {
  if (!currentSession) {
    toast("Generate a part first", "warn");
    return;
  }
  setLoading(true, "Packing ZIP…");
  try {
    const res = await fetch(API + "/export_pack/" + currentSession);
    const ctype = res.headers.get("content-type") || "";
    if (!res.ok || ctype.includes("application/json") || ctype.includes("text/")) {
      let data = {};
      try { data = await res.json(); } catch { /* not json */ }
      toast(errorList(data).join(", "), "err");
      return;
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = currentSession + "_cad_pack.zip";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    toast("ZIP pack downloaded");
  } catch (err) {
    toast(err.message || "Download failed", "err");
  } finally {
    setLoading(false);
  }
}

function requireSession() {
  if (!currentSession) {
    toast("Generate a model first", "warn");
    return false;
  }
  return true;
}

async function scaleModel() {
  if (!requireSession()) return;
  const factor = parseFloat(document.getElementById("scale-factor").value);
  if (!(factor > 0) || factor > 100) {
    toast("Scale factor must be between 0 and 100", "warn");
    return;
  }
  setLoading(true, "Scaling…");
  try {
    const res = await fetch(API + "/scale", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: currentSession, factor }),
    });
    if (handleResponse(await parseJsonResponse(res), "Scale")) switchTab("design");
  } catch (err) {
    toast(err.message || "Scale failed", "err");
  } finally {
    setLoading(false);
  }
}

async function cloneModel() {
  if (!requireSession()) return;
  setLoading(true, "Cloning…");
  try {
    const res = await fetch(API + "/clone", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: currentSession }),
    });
    if (handleResponse(await parseJsonResponse(res), "Clone")) switchTab("design");
  } catch (err) {
    toast(err.message || "Clone failed", "err");
  } finally {
    setLoading(false);
  }
}

async function loadFasteners() {
  try {
    const res = await fetch(API + "/fasteners");
    const data = await res.json();
    const select = document.getElementById("fastener-select");
    if (!select) return;
    select.innerHTML = "";
    (data.fasteners || []).forEach(f => {
      const opt = document.createElement("option");
      opt.value = f.id;
      opt.textContent = `${f.id} · clearance ${f.clearance_mm}mm`;
      if (f.id === "M4") opt.selected = true;
      select.appendChild(opt);
    });
  } catch (err) {
    console.error("fasteners:", err);
  }
}

async function applyBoltCircle() {
  if (!requireSession()) return;
  const pitchRaw = document.getElementById("bolt-pitch").value;
  const body = {
    session_id: currentSession,
    fastener: document.getElementById("fastener-select").value || "M4",
    count: Math.max(1, parseInt(document.getElementById("bolt-count").value, 10) || 6),
    hole_type: document.getElementById("bolt-type").value,
    face: document.getElementById("bolt-face").value,
  };
  if (pitchRaw) body.pitch_diameter_mm = parseFloat(pitchRaw);
  setLoading(true, "Applying bolt circle…");
  try {
    const res = await fetch(API + "/apply_bolt_circle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (handleResponse(await parseJsonResponse(res), "Bolt circle")) switchTab("design");
  } catch (err) {
    toast(err.message || "Bolt circle failed", "err");
  } finally {
    setLoading(false);
  }
}

async function compareMaterials() {
  if (!requireSession()) return;
  setLoading(true, "Comparing materials…");
  try {
    const res = await fetch(API + "/compare_materials", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: currentSession }),
    });
    const data = await parseJsonResponse(res);
    const box = document.getElementById("compare-result");
    if (!data.success) {
      box.innerHTML = "<b>Error:</b> " + errorList(data).map(escapeHtml).join(", ");
      box.classList.remove("hidden");
      toast("Compare failed", "err");
      return;
    }
    let html = `<p class="muted">Volume ${data.volume_mm3} mm³ · cheapest first</p><table class="bom-table"><tr><th>Material</th><th>Weight</th><th>Cost</th></tr>`;
    (data.materials || []).forEach(m => {
      html += `<tr><td>${escapeHtml(m.label)}</td><td>${m.weight_g} g</td><td>$${m.cost_usd}</td></tr>`;
    });
    html += "</table>";
    box.innerHTML = html;
    box.classList.remove("hidden");
    toast("Material comparison ready");
  } catch (err) {
    toast(err.message || "Compare failed", "err");
  } finally {
    setLoading(false);
  }
}

async function loadLibrary() {
  const host = document.getElementById("library-list");
  if (!host) return;
  try {
    const res = await fetch(API + "/library");
    const data = await res.json();
    host.innerHTML = "";
    const parts = data.parts || [];
    if (!parts.length) {
      host.innerHTML = '<p class="muted">No saved parts yet.</p>';
      return;
    }
    parts.forEach(part => {
      const row = document.createElement("div");
      row.className = "list-row";
      const label = document.createElement("span");
      label.textContent = part.name;
      const actions = document.createElement("span");
      const loadBtn = document.createElement("button");
      loadBtn.type = "button";
      loadBtn.className = "btn-ghost sm";
      loadBtn.textContent = "Load";
      loadBtn.onclick = () => loadLibraryPart(part.id);
      const delBtn = document.createElement("button");
      delBtn.type = "button";
      delBtn.className = "btn-ghost sm";
      delBtn.textContent = "Delete";
      delBtn.onclick = () => deleteLibraryPart(part.id);
      actions.appendChild(loadBtn);
      actions.appendChild(delBtn);
      row.appendChild(label);
      row.appendChild(actions);
      host.appendChild(row);
    });
  } catch (err) {
    host.innerHTML = '<p class="muted">Library unavailable.</p>';
  }
}

async function saveToLibrary() {
  if (!requireSession()) return;
  const name = document.getElementById("library-name").value.trim();
  if (!name) {
    toast("Name the part first", "warn");
    return;
  }
  try {
    const res = await fetch(API + "/library/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, session_id: currentSession }),
    });
    const data = await parseJsonResponse(res);
    if (!data.success) {
      toast(errorList(data).join(", "), "err");
      return;
    }
    toast("Saved “" + name + "”");
    loadLibrary();
  } catch (err) {
    toast(err.message || "Save failed", "err");
  }
}

async function loadLibraryPart(partId) {
  setLoading(true, "Loading library part…");
  try {
    const res = await fetch(API + "/library/load", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ part_id: partId }),
    });
    if (handleResponse(await parseJsonResponse(res), "Library")) switchTab("design");
  } catch (err) {
    toast(err.message || "Load failed", "err");
  } finally {
    setLoading(false);
  }
}

async function deleteLibraryPart(partId) {
  try {
    const res = await fetch(API + "/library/" + partId, { method: "DELETE" });
    const data = await parseJsonResponse(res);
    if (!data.success) {
      toast(errorList(data).join(", "), "err");
      return;
    }
    toast("Part removed");
    loadLibrary();
  } catch (err) {
    toast(err.message || "Delete failed", "err");
  }
}

function renderBomLines() {
  const host = document.getElementById("bom-lines");
  if (!host) return;
  host.innerHTML = "";
  if (!bomLines.length) {
    host.innerHTML = '<p class="muted">No lines yet.</p>';
    return;
  }
  bomLines.forEach((line, i) => {
    const row = document.createElement("div");
    row.className = "list-row";
    row.innerHTML = `<span>${escapeHtml(line.description)} × ${line.quantity}</span>`;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn-ghost sm";
    btn.textContent = "Remove";
    btn.onclick = () => {
      bomLines.splice(i, 1);
      renderBomLines();
      refreshBom();
    };
    row.appendChild(btn);
    host.appendChild(row);
  });
}

async function refreshBom() {
  const box = document.getElementById("bom-result");
  if (!bomLines.length) {
    box.classList.add("hidden");
    box.innerHTML = "";
    return;
  }
  try {
    const res = await fetch(API + "/bom", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        items: bomLines.map(line => ({
          session_id: line.session_id,
          quantity: line.quantity,
          description: line.description,
          part_number: line.session_id,
        })),
      }),
    });
    const data = await parseJsonResponse(res);
    if (!data.success) {
      box.innerHTML = "<b>Error:</b> " + errorList(data).map(escapeHtml).join(", ");
      box.classList.remove("hidden");
      return;
    }
    const bom = data.bom || {};
    const lines = bom.lines || bom.items || [];
    let html = `<table class="bom-table"><tr><th>Part</th><th>Qty</th><th>Weight</th><th>Cost</th></tr>`;
    lines.forEach(line => {
      html += `<tr><td>${escapeHtml(line.description || line.part_number || "")}</td><td>${line.quantity}</td><td>${line.line_weight_g} g</td><td>$${line.line_cost_usd}</td></tr>`;
    });
    html += "</table>";
    const totals = bom.totals || bom;
    if (totals.total_weight_g != null || totals.total_cost_usd != null) {
      html += `<p class="mt"><b>Total</b> ${totals.total_weight_g ?? "—"} g · $${totals.total_cost_usd ?? "—"}</p>`;
    }
    box.innerHTML = html;
    box.classList.remove("hidden");
  } catch (err) {
    box.innerHTML = "<b>Error:</b> " + escapeHtml(err.message || "BOM failed");
    box.classList.remove("hidden");
  }
}

function addBomLine() {
  if (!requireSession()) return;
  const qty = Math.max(1, parseInt(document.getElementById("bom-qty").value, 10) || 1);
  const desc = document.getElementById("bom-desc").value.trim()
    || (currentParams && currentParams.shape)
    || currentSession;
  const existing = bomLines.find(line => line.session_id === currentSession && line.description === desc);
  if (existing) existing.quantity += qty;
  else bomLines.push({ session_id: currentSession, quantity: qty, description: desc });
  renderBomLines();
  refreshBom();
}

function clearBom() {
  bomLines = [];
  renderBomLines();
  refreshBom();
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

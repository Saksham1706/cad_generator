console.log("app.js version 4 loaded");
// Same-origin by default so this works both locally (http://127.0.0.1:8000)
// and once deployed (e.g. https://your-app.onrender.com) without any edits.
const API = window.location.origin.includes("null") || window.location.protocol === "file:"
  ? "http://127.0.0.1:8000"
  : window.location.origin;
let currentSession = null;
let jsonMode = false;

document.addEventListener("DOMContentLoaded", () => {
  loadTemplates();
  loadMaterials();
});

// ---------------------------------------------------------------------
// Templates
// ---------------------------------------------------------------------
async function loadTemplates() {
  try {
    const res = await fetch(API + "/templates");
    const data = await res.json();
    const container = document.getElementById("template-groups");
    container.innerHTML = "";
    data.templates.forEach(group => {
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
        };
        row.appendChild(btn);
      });
      groupEl.appendChild(row);
      container.appendChild(groupEl);
    });
  } catch (err) {
    console.error("Could not load templates:", err);
  }
}

// ---------------------------------------------------------------------
// Materials
// ---------------------------------------------------------------------
async function loadMaterials() {
  try {
    const res = await fetch(API + "/materials");
    const data = await res.json();
    const select = document.getElementById("material-select");
    select.innerHTML = "";
    data.materials.forEach(m => {
      const opt = document.createElement("option");
      opt.value = m.id;
      opt.textContent = `${m.label} (${m.density_g_cm3} g/cm³)`;
      if (m.id === data.default) opt.selected = true;
      select.appendChild(opt);
    });
  } catch (err) {
    console.error("Could not load materials:", err);
  }
}

function currentMaterial() {
  const select = document.getElementById("material-select");
  return select ? select.value : undefined;
}

// ---------------------------------------------------------------------
// Mode toggle: natural language vs raw JSON
// ---------------------------------------------------------------------
function toggleMode() {
  jsonMode = !jsonMode;
  document.getElementById("json-card").classList.toggle("hidden", !jsonMode);
  document.getElementById("prompt-card").classList.toggle("hidden", jsonMode);
  document.getElementById("template-card").classList.toggle("hidden", jsonMode);
  document.getElementById("mode-toggle").textContent = jsonMode ? "💬 Prompt Mode" : "⚙ JSON Mode";
}

// ---------------------------------------------------------------------
// Generate (natural language)
// ---------------------------------------------------------------------
async function generate() {
  const prompt = document.getElementById("prompt").value.trim();
  if (!prompt) {
    alert("Please enter a description.");
    return;
  }

  const btn = document.getElementById("generate-btn");
  btn.textContent = "Generating...";
  btn.disabled = true;

  try {
    const res = await fetch(API + "/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt: prompt, material: currentMaterial() })
    });
    const data = await res.json();
    handleResponse(data);
  } catch (err) {
    showError("Could not reach the server. Is uvicorn running?");
  }

  btn.textContent = "Generate Model";
  btn.disabled = false;
}

// ---------------------------------------------------------------------
// Generate (raw JSON / power-user mode)
// ---------------------------------------------------------------------
async function generateManual() {
  const raw = document.getElementById("json-input").value.trim();
  if (!raw) {
    alert("Paste some CAD parameters as JSON first.");
    return;
  }

  let params;
  try {
    params = JSON.parse(raw);
  } catch (err) {
    showError("That's not valid JSON: " + err.message);
    return;
  }

  const btn = document.getElementById("json-generate-btn");
  btn.textContent = "Generating...";
  btn.disabled = true;

  try {
    const res = await fetch(API + "/generate_manual", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ params: params, material: currentMaterial() })
    });
    const data = await res.json();
    handleResponse(data);
  } catch (err) {
    showError("Could not reach the server. Is uvicorn running?");
  }

  btn.textContent = "Generate from JSON";
  btn.disabled = false;
}

// ---------------------------------------------------------------------
// Edit
// ---------------------------------------------------------------------
async function editModel() {
  let edit = document.getElementById("edit-prompt").value.trim();
  if (!edit) {
    alert("Describe what to change.");
    return;
  }
  if (!currentSession) {
    alert("Please generate a model first.");
    return;
  }

  let btn = document.getElementById("edit-btn");
  btn.textContent = "Applying...";
  btn.disabled = true;

  try {
    const res = await fetch(API + "/edit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: currentSession, edit: edit, material: currentMaterial() })
    });
    const data = await res.json();
    handleResponse(data);
  } catch (err) {
    console.error("EDIT ERROR:", err);
    showError("Could not reach the server.");
  }

  btn.textContent = "Apply Edit";
  btn.disabled = false;
}

// ---------------------------------------------------------------------
// Undo / Redo
// ---------------------------------------------------------------------
async function doUndo() {
  if (!currentSession) return;
  const res = await fetch(API + "/undo", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: currentSession })
  });
  const data = await res.json();
  handleResponse(data);
}

async function doRedo() {
  if (!currentSession) return;
  const res = await fetch(API + "/redo", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: currentSession })
  });
  const data = await res.json();
  handleResponse(data);
}

// ---------------------------------------------------------------------
// Viewer material finish presets
// ---------------------------------------------------------------------
function setMaterial(metallic, roughness, el = null) {
  const viewer = document.getElementById("viewer");

  document.querySelectorAll(".mat-btn").forEach(b => b.classList.remove("active"));
  if (el) el.classList.add("active");

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
      material.pbrMetallicRoughness.setMetallicFactor(0.3);
      material.pbrMetallicRoughness.setRoughnessFactor(0.5);
    }
  }

  viewer.addEventListener("load", function onLoad() {
    apply();
    viewer.removeEventListener("load", onLoad);
  });

  apply();
}

// ---------------------------------------------------------------------
// Response handling
// ---------------------------------------------------------------------
function handleResponse(data) {
  const errBox        = document.getElementById("errors");
  const viewerSection = document.getElementById("viewer-section");
  const paramsBox     = document.getElementById("params-box");
  const editSection   = document.getElementById("edit-section");
  const dlGlb         = document.getElementById("dl-glb");
  const dlStl         = document.getElementById("dl-stl");
  const dlStep        = document.getElementById("dl-step");

  if (!data.success) {
    let html = "<b>Fix these issues:</b><ul>" +
      (data.errors || []).filter(Boolean).map(function(e) {
        return "<li>" + e + "</li>";
      }).join("") + "</ul>";

    if (data.hint) {
      html += '<p style="margin-top:8px;color:#88ccff">💡 ' + data.hint + "</p>";
    }

    errBox.innerHTML = html;
    errBox.style.display = "block";
    errBox.classList.remove("hidden");
    return;
  }

  errBox.style.display = "none";
  errBox.classList.add("hidden");

  if (data.session_id) {
    currentSession = data.session_id;
  }

  const glbUrl = API + data.glb_url;
  const stlUrl = API + data.stl_url;
  const stepUrl = API + data.step_url;

  const viewerContainer = document.getElementById("viewer-section");
  const oldViewer = document.getElementById("viewer");
  oldViewer.remove();

  const newViewer = document.createElement("model-viewer");
  newViewer.id = "viewer";
  newViewer.setAttribute("camera-controls", "");
  newViewer.setAttribute("auto-rotate", "");
  newViewer.setAttribute("shadow-intensity", "1");
  newViewer.setAttribute("exposure", "0.8");
  newViewer.setAttribute("min-camera-orbit", "auto auto auto");
  newViewer.setAttribute("max-camera-orbit", "Infinity Infinity auto");
  newViewer.setAttribute("src", glbUrl + "?t=" + Date.now());
  newViewer.style.cssText = "width:100%; height:450px; background:#1a1a2e; border-radius:12px;";

  const colorRow = document.querySelector(".color-row");
  viewerContainer.insertBefore(newViewer, colorRow);

  viewerSection.style.display = "block";
  viewerSection.classList.remove("hidden");

  dlGlb.href = glbUrl;
  dlStl.href = stlUrl;
  dlStep.href = stepUrl;

  const cleanParams = {};
  for (const key in data.params) {
    if (!key.startsWith("_")) {
      cleanParams[key] = data.params[key];
    }
  }

  paramsBox.textContent = JSON.stringify(cleanParams, null, 2);
  paramsBox.style.display = "block";
  paramsBox.classList.remove("hidden");

  editSection.style.display = "block";
  editSection.classList.remove("hidden");

  renderProperties(data.properties);
  renderHistoryControls(data);
}

function renderProperties(props) {
  const panel = document.getElementById("properties-panel");
  if (!props) {
    panel.innerHTML = "";
    return;
  }
  const bb = props.bounding_box_mm || {};
  panel.innerHTML = `
    <div class="prop-item"><span class="prop-label">Volume</span><span class="prop-value">${props.volume_cm3} cm³</span></div>
    <div class="prop-item"><span class="prop-label">Bounding box</span><span class="prop-value">${bb.x} × ${bb.y} × ${bb.z} mm</span></div>
    <div class="prop-item"><span class="prop-label">Est. weight</span><span class="prop-value">${props.weight_g} g <span class="prop-material">(${props.material})</span></span></div>
  `;
}

function renderHistoryControls(data) {
  const undoBtn = document.getElementById("undo-btn");
  const redoBtn = document.getElementById("redo-btn");
  undoBtn.disabled = !data.can_undo;
  redoBtn.disabled = !data.can_redo;
}

function showError(msg) {
  const errBox = document.getElementById("errors");
  errBox.innerHTML = "<b>Error:</b> " + msg;
  errBox.style.display = "block";
  errBox.classList.remove("hidden");
}

document.addEventListener("click", function (e) {
  if (e.target.classList.contains("color-btn")) {
    document.querySelectorAll(".color-btn").forEach(b => b.classList.remove("active"));
    e.target.classList.add("active");
  }

  if (e.target.classList.contains("mat-btn")) {
    document.querySelectorAll(".mat-btn").forEach(b => b.classList.remove("active"));
    e.target.classList.add("active");
  }
});

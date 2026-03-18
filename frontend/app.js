console.log("app.js version 3 loaded");
const API = "http://127.0.0.1:8000";
let currentSession = null;

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
      body: JSON.stringify({ prompt: prompt })
    });
    const data = await res.json();
    handleResponse(data);
  } catch (err) {
    showError("Could not reach the server. Is uvicorn running?");
  }

  btn.textContent = "Generate Model";
  btn.disabled = false;
}

async function editModel() {
  console.log("editModel called, session:", currentSession);

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
      body: JSON.stringify({ session_id: currentSession, edit: edit })
    });
    const data = await res.json();
    console.log("EDIT RESPONSE:", JSON.stringify(data));
    handleResponse(data);
  } catch (err) {
    console.error("EDIT ERROR:", err);
    showError("Could not reach the server.");
  }

  btn.textContent = "Apply Edit";
  btn.disabled = false;
}

function handleResponse(data) {
  const errBox        = document.getElementById("errors");
  const viewerSection = document.getElementById("viewer-section");
  const viewer        = document.getElementById("viewer");
  const paramsBox     = document.getElementById("params-box");
  const editSection   = document.getElementById("edit-section");
  const dlGlb         = document.getElementById("dl-glb");
  const dlStl         = document.getElementById("dl-stl");

  if (!data.success) {
    let html = "<b>Fix these issues:</b><ul>" +
      data.errors.filter(Boolean).map(function(e) {
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

 const viewerContainer = document.getElementById("viewer-section");
const oldViewer = document.getElementById("viewer");

// Remove old viewer completely and create fresh one
oldViewer.remove();

const newViewer = document.createElement("model-viewer");
newViewer.id = "viewer";
newViewer.setAttribute("camera-controls", "");
newViewer.setAttribute("auto-rotate", "");
newViewer.setAttribute("shadow-intensity", "1");
newViewer.setAttribute("exposure", "0.8");
newViewer.setAttribute("src", glbUrl + "?t=" + Date.now());
newViewer.style.cssText = "width:100%; height:450px; background:#1a1a2e; border-radius:12px;";

// Insert before the color-row div
const colorRow = document.querySelector(".color-row");
viewerContainer.insertBefore(newViewer, colorRow);

  viewerSection.style.display = "block";
  viewerSection.classList.remove("hidden");

  dlGlb.href = glbUrl;
  dlStl.href = stlUrl;

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
}

function showError(msg) {
  const errBox = document.getElementById("errors");
  errBox.innerHTML = "<b>Error:</b> " + msg;
  errBox.style.display = "block";
  errBox.classList.remove("hidden");
}

function setColor(hex) {
  const viewer = document.getElementById("viewer");
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

document.documentElement.classList.add("js-enabled");

const API = "http://localhost:8003";
const EMAIL = "test@truthcv.com";
 
const state = { resumeId: null };
 
const $ = (id) => document.getElementById(id);
const themeToggle   = $("theme-toggle");
const dropzone      = $("dropzone");
const fileInput     = $("file-input");
const uploadStatus  = $("upload-status");
const uploadDone    = $("upload-done");
const statusTitle   = $("status-title");
const statusSub     = $("status-sub");
const uploadFileEl  = $("upload-filename");
const uploadSummary = $("upload-summary");
const replaceBtn    = $("replace-file");
const jdInput       = $("jd-input");
const instrInput    = $("instructions-input");
const btnMatch      = $("btn-match");
const btnResume     = $("btn-resume");
const btnLetter     = $("btn-letter");
const emptyState    = $("empty-state");
const matchSection  = $("match-section");
const scoreNumber   = $("score-number");
const scoreFill     = $("score-fill");
const chipsMatched  = $("chips-matched");
const chipsMissing  = $("chips-missing");
const resumeSection = $("resume-section");
const resumeFrame   = $("resume-frame");
const dlResume      = $("btn-download-resume");
const letterSection = $("letter-section");
const letterFrame   = $("letter-frame");
const dlLetter      = $("btn-download-letter");
const qaSection     = $("qa-section");
const qaInput       = $("qa-input");
const btnAsk        = $("btn-ask");
const answersBox    = $("answers");
const toast         = $("toast");
const toastMsg      = $("toast-msg");

// ══════════════════════════════════════════════════════
// THEME
// ══════════════════════════════════════════════════════
function applyTheme(t) {
  document.documentElement.setAttribute("data-theme", t);
  localStorage.setItem("truthcv-theme", t);
}

const savedTheme = localStorage.getItem("truthcv-theme");
if (savedTheme) applyTheme(savedTheme);
else if (window.matchMedia("(prefers-color-scheme: light)").matches) applyTheme("light");
else applyTheme("dark");

themeToggle.addEventListener("click", () => {
  const cur = document.documentElement.getAttribute("data-theme");
  applyTheme(cur === "dark" ? "light" : "dark");
});
 
let toastTimer;
function showToast(msg) {
  toastMsg.textContent = msg;
  toast.hidden = false;
  requestAnimationFrame(() => toast.classList.add("show"));
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    toast.classList.remove("show");
    setTimeout(() => { toast.hidden = true; }, 250);
  }, 3500);
} 
function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s ?? "";
  return d.innerHTML;
}

function setRightPanelVisible() { 
  const hasContent = !matchSection.hidden || !resumeSection.hidden || !letterSection.hidden;
  emptyState.hidden = hasContent;
}
 
function refreshButtons() {
  const hasResume = !!state.resumeId;
  const hasJd = jdInput.value.trim().length >= 20;
  const enabled = hasResume && hasJd;
  btnMatch.disabled  = !enabled;
  btnResume.disabled = !enabled;
  btnLetter.disabled = !enabled;
}
jdInput.addEventListener("input", refreshButtons);
 
dropzone.addEventListener("click", () => fileInput.click());
replaceBtn.addEventListener("click", () => fileInput.click());

["dragenter", "dragover"].forEach(evt =>
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault(); dropzone.classList.add("drag");
  })
);
["dragleave", "drop"].forEach(evt =>
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault(); dropzone.classList.remove("drag");
  })
);
dropzone.addEventListener("drop", (e) => {
  const f = e.dataTransfer.files[0];
  if (f) handleFile(f);
});
fileInput.addEventListener("change", () => {
  if (fileInput.files[0]) handleFile(fileInput.files[0]);
});

async function handleFile(file) {
  if (!file.name.toLowerCase().endsWith(".pdf")) {
    return showToast("Please upload a PDF file.");
  }
  if (file.size > 10 * 1024 * 1024) {
    return showToast("File too large. Max 10 MB.");
  }

  // Show loading state
  dropzone.hidden = true;
  uploadDone.hidden = true;
  uploadStatus.hidden = false;

  const phases = [
    { t: "Reading PDF…",          s: "Parsing text and hyperlinks" },
    { t: "Extracting data…",      s: "Running the extraction model (~30s)" },
    { t: "Chunking & embedding…", s: "Building searchable vectors" },
    { t: "Saving…",               s: "Writing to Postgres" },
  ];
  let phaseIndex = 0;
  statusTitle.textContent = phases[0].t;
  statusSub.textContent = phases[0].s;
  const phaseTimer = setInterval(() => {
    phaseIndex = Math.min(phaseIndex + 1, phases.length - 1);
    statusTitle.textContent = phases[phaseIndex].t;
    statusSub.textContent = phases[phaseIndex].s;
  }, 12000);

  try {
    const form = new FormData();
    form.append("file", file);
    const r = await fetch(`${API}/resume/upload?email=${encodeURIComponent(EMAIL)}`, {
      method: "POST",
      body: form,
    });

    clearInterval(phaseTimer);
    uploadStatus.hidden = true;

    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      throw new Error(err.detail || `Upload failed (${r.status})`);
    }

    const data = await r.json();
    state.resumeId = data.resume_id;

    uploadDone.hidden = false;
    uploadFileEl.textContent = data.filename || file.name;
    uploadSummary.textContent = `${data.name || "Candidate"} · ${data.chunks} chunks indexed`;
    showToast("Resume indexed.");

    refreshButtons();
  } catch (err) {
    clearInterval(phaseTimer);
    uploadStatus.hidden = true;
    dropzone.hidden = false;
    showToast(err.message || "Upload failed.");
  }
}
 
async function checkExistingResume() {
  try {
    const r = await fetch(`${API}/resume/current?email=${encodeURIComponent(EMAIL)}`);
    if (!r.ok) return;
    const data = await r.json();
    state.resumeId = data.resume_id;
    dropzone.hidden = true;
    uploadDone.hidden = false;
    uploadFileEl.textContent = data.filename || "resume.pdf";
    const name = data.json_data?.name || "Candidate";
    uploadSummary.textContent = `${name} · loaded from database`;
    refreshButtons();
  } catch (_) {
    // No resume yet — nothing to do
  }
}
checkExistingResume();
 
btnMatch.addEventListener("click", async () => {
  const original = btnMatch.textContent;
  btnMatch.disabled = true;
  btnMatch.innerHTML = `<span class="spinner"></span><span>Scoring…</span>`;

  try {
    const r = await fetch(`${API}/generate/score?email=${encodeURIComponent(EMAIL)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ jd_text: jdInput.value.trim() }),
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      throw new Error(err.detail || "Scoring failed");
    }
    const data = await r.json();
    renderMatch(data);
  } catch (err) {
    showToast(err.message);
  } finally {
    btnMatch.disabled = false;
    btnMatch.textContent = original;
    refreshButtons();
  }
});

function renderMatch(data) {
  matchSection.hidden = false;
  setRightPanelVisible();

  const pct = data.match_percent ?? 0;
  scoreNumber.textContent = `${pct}%`;

  scoreFill.style.width = "0%";
  scoreFill.classList.remove("warn", "bad");
  if (pct >= 60) { /* default primary = good */ }
  else if (pct >= 40) scoreFill.classList.add("warn");
  else scoreFill.classList.add("bad");

  requestAnimationFrame(() => {
    setTimeout(() => { scoreFill.style.width = `${pct}%`; }, 50);
  });

  chipsMatched.innerHTML = "";
  chipsMissing.innerHTML = "";

  (data.matched || []).forEach(s => {
    const el = document.createElement("span");
    el.className = "chip matched";
    el.textContent = s;
    chipsMatched.appendChild(el);
  });
  (data.missing || []).forEach(s => {
    const el = document.createElement("span");
    el.className = "chip missing";
    el.textContent = s;
    chipsMissing.appendChild(el);
  });

  if (!(data.matched || []).length)
    chipsMatched.innerHTML = `<span class="muted">None</span>`;
  if (!(data.missing || []).length)
    chipsMissing.innerHTML = `<span class="muted">None</span>`;
}
 
btnResume.addEventListener("click", async () => {
  const original = btnResume.textContent;
  btnResume.disabled = true;
  btnResume.innerHTML = `<span class="spinner"></span><span>Generating… (~30s)</span>`;

  try {
    const r = await fetch(`${API}/generate/resume?email=${encodeURIComponent(EMAIL)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        jd_text: jdInput.value.trim(),
        user_instructions: instrInput.value.trim(),
      }),
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      throw new Error(err.detail || "Generation failed");
    }
    const data = await r.json();
    resumeSection.hidden = false;
    setRightPanelVisible();
    resumeFrame.src = `${API}${data.download_url}?inline=true`;
    dlResume.href = `${API}${data.download_url}`;
    showToast("Resume ready.");
  } catch (err) {
    showToast(err.message);
  } finally {
    btnResume.disabled = false;
    btnResume.textContent = original;
    refreshButtons();
  }
});
 
btnLetter.addEventListener("click", async () => {
  const original = btnLetter.textContent;
  btnLetter.disabled = true;
  btnLetter.innerHTML = `<span class="spinner"></span><span>Writing… (~25s)</span>`;

  try {
    const r = await fetch(`${API}/generate/cover-letter?email=${encodeURIComponent(EMAIL)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ jd_text: jdInput.value.trim() }),
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      throw new Error(err.detail || "Generation failed");
    }
    const data = await r.json();
    letterSection.hidden = false;
    setRightPanelVisible();
    letterFrame.src = `${API}${data.download_url}?inline=true`;
    dlLetter.href = `${API}${data.download_url}`;
    showToast("Cover letter ready.");
  } catch (err) {
    showToast(err.message);
  } finally {
    btnLetter.disabled = false;
    btnLetter.textContent = original;
    refreshButtons();
  }
}); 

btnAsk.addEventListener("click", async () => {
  const lines = qaInput.value.split("\n").map(l => l.trim()).filter(Boolean);
  if (!lines.length) return showToast("Type at least one question.");
  if (lines.length > 5) return showToast("Max 5 questions.");

  const original = btnAsk.textContent;
  btnAsk.disabled = true;
  btnAsk.innerHTML = `<span class="spinner"></span><span>Asking…</span>`;
  answersBox.innerHTML = "";

  try {
    const r = await fetch(`${API}/generate/answers?email=${encodeURIComponent(EMAIL)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        jd_text: jdInput.value.trim(),
        questions: lines,
        user_instructions: instrInput.value.trim(),
      }),
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      throw new Error(err.detail || "Failed");
    }
    const data = await r.json();
    (data.answers || []).forEach((a) => {
      const card = document.createElement("div");
      card.className = "answer-card";
      card.innerHTML = `
        <div class="answer-q">${escapeHtml(a.question)}</div>
        <div class="answer-a">${escapeHtml(a.answer)}</div>
      `;
      answersBox.appendChild(card);
    });
    showToast("Answers ready.");
  } catch (err) {
    showToast(err.message);
  } finally {
    btnAsk.disabled = false;
    btnAsk.textContent = original;
  }
});
 
const qaObserver = new MutationObserver(() => {
  if (!resumeSection.hidden && qaSection.hidden) {
    qaSection.hidden = false;
    setRightPanelVisible();
  }
});
qaObserver.observe(resumeSection, { attributes: true, attributeFilter: ["hidden"] });
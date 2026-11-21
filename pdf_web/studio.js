const get = (id) => document.getElementById(id);
const canvas = get("page");
const context = canvas.getContext("2d");
let source, policy, result, image, drag, generating = false, pageNo = 0, imageRevision = 0;
const regions = [];
let provableFields = [];
let suggestions = [], masked = [], revision = 0;
const theme = get("theme");
function setTheme(dark) {
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  theme.textContent = dark ? "Light mode" : "Dark mode";
  localStorage.setItem("legitzk-pdf-theme", dark ? "dark" : "light");
}
setTheme(localStorage.getItem("legitzk-pdf-theme") === "dark");
theme.addEventListener("click", () => setTheme(document.documentElement.dataset.theme !== "dark"));
const inputs = (form) => Object.fromEntries(new FormData(form));

function status(text, error = false) {
  get("status").hidden = !text;
  get("status").textContent = text;
  get("status").classList.toggle("failed", error);
}
async function api(path, data, workspace = source?.workspace) {
  const headers = {"X-LegitZK-Action":"1"};
  if (workspace) headers["X-LegitZK-Workspace"] = workspace;
  const options = {headers};
  if (data !== undefined) {
    options.method = "POST";
    options.body = data instanceof Blob ? data : JSON.stringify(data);
    if (!(data instanceof Blob)) headers["Content-Type"] = "application/json";
  }
  const response = await fetch("/api/" + path, options);
  if (!response.ok) throw new Error((await response.json()).detail || "Request failed.");
  return response;
}
function run(handler, button) {
  return async (event) => {
    event.preventDefault();
    if (button) button.disabled = true;
    try { await handler(event); }
    catch (error) { status(error.message, true); }
    finally { if (button && button.id !== "prove") button.disabled = false; update(); }
  };
}
function submit(form, handler) {
  form.addEventListener("submit", run(handler, form.querySelector("button")));
}
function click(id, handler) {
  get(id).addEventListener("click", run(handler, get(id)));
}
function save(blob, name) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 3000);
}
function binary(data) {
  return Uint8Array.from(atob(data), (char) => char.charCodeAt(0));
}
function update() {
  get("counts").textContent = String(regions.length);
  get("prove").disabled = !(source && policy && !generating);
  get("exports").hidden = !result;
  const count = source?.receipt.manifest.pages.length || 0;
  get("previous").disabled = pageNo <= 0;
  get("next").disabled = pageNo + 1 >= count;
}
function overlay(box, fill, outline) {
  const [page,x,y,right,bottom] = box;
  if (page !== pageNo) return;
  context.fillStyle = fill;
  context.fillRect(x,y,right-x,bottom-y);
  if (outline) {
    context.strokeStyle = outline;
    context.lineWidth = 1.5;
    context.strokeRect(x,y,right-x,bottom-y);
  }
}
function paint() {
  if (!image) return;
  context.drawImage(image, 0, 0);
  for (const box of masked) overlay(box, "#000");
  for (const rule of regions) {
    if (rule.kind === "keep") overlay(rule.box, "rgba(8,117,99,.24)", "#0b8b73");
    else if (!policy) overlay(rule.box, "rgba(24,29,40,.5)", "#23303b");
  }
  for (const item of suggestions) overlay(item.region, "rgba(255,174,0,.19)", "#bd7014");
  if (drag) {
    const [a,b] = drag;
    overlay([pageNo,Math.min(a.x,b.x),Math.min(a.y,b.y),Math.max(a.x,b.x),Math.max(a.y,b.y)],
            "rgba(6,148,123,.17)", "#1da38c");
  }
}
function reviewButton(label, handler) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "quiet";
  button.textContent = label;
  button.addEventListener("click", run(handler));
  return button;
}
function reviewRow(container, label, page, buttons) {
  const row = document.createElement("div");
  row.className = "review-row";
  const text = document.createElement("strong");
  text.textContent = label;
  const actions = document.createElement("div");
  actions.className = "actions";
  actions.append(reviewButton("Page " + (page + 1), () => loadPage(page)), ...buttons);
  row.append(text, actions);
  get(container).append(row);
}
function renderLists() {
  get("hide-identified").hidden = !suggestions.some(item => item.method === "labeled_identifier");
  get("suggestions").replaceChildren();
  get("approved").replaceChildren();
  for (const item of suggestions) {
    const group = item.group == null ? [] : suggestions.filter(candidate =>
      candidate.group === item.group && candidate.method === "labeled_identifier");
    const label = item.category.replaceAll("_", " ") + " · " + item.method.replaceAll("_", " ")
      + (item.group == null ? "" : ` · group ${item.group}`);
    const groupAction = group.length > 1 && item.method === "labeled_identifier"
      ? [reviewButton(`Hide ${group.length} exact matches`, () => hideIdentifiers(group))] : [];
    const apply = (kind) => {
      mark(item.region, kind);
      dismiss();
    };
    const dismiss = () => {
      suggestions = suggestions.filter((candidate) => candidate !== item);
      renderLists(); paint();
    };
    reviewRow("suggestions", label, item.region[0], [
      reviewButton("Hide", () => apply("hide")), reviewButton("Keep", () => apply("keep")),
      reviewButton("Dismiss", dismiss), ...groupAction]);
  }
  for (const [i, rule] of regions.entries()) {
    reviewRow("approved", rule.kind === "hide" ? "Hide region" : "Keep visible", rule.box[0], [
      reviewButton("Remove", () => { regions.splice(i,1); invalidatePolicy(); })]);
  }
}
function hideIdentifiers(items) {
  const accepted = new Set();
  const protectedBoxes = regions.filter(rule => rule.kind === "keep").map(rule => rule.box);
  for (const item of items) {
    if (item.method !== "labeled_identifier") continue;
    const [p,x,y,r,b] = item.region;
    const conflict = protectedBoxes.some(([q,l,t,rr,bb]) => p === q
      && Math.floor(x / 8) < Math.ceil(rr / 8) && Math.floor(l / 8) < Math.ceil(r / 8)
      && Math.floor(y / 8) < Math.ceil(bb / 8) && Math.floor(t / 8) < Math.ceil(b / 8));
    if (conflict) continue;
    const key = item.region.join();
    const duplicate = regions.some(rule => rule.kind === "hide" && rule.box.join() === key);
    if (!duplicate && regions.filter(rule => rule.kind === "hide").length >= 512) continue;
    accepted.add(key);
    if (!duplicate) regions.push({kind:"hide", box:item.region});
  }
  suggestions = suggestions.filter(item => !accepted.has(item.region.join()));
  invalidatePolicy();
  status(`${accepted.size} identified region(s) marked. Review the redaction plan before export.`);
}
click("hide-identified", () => hideIdentifiers(suggestions));

async function loadPage(index) {
  if (!source || !source.receipt.manifest.pages[index]) return;
  const revision = ++imageRevision;
  canvas.setAttribute("aria-busy", "true");
  pageNo = index;
  image?.close();
  image = null;
  get("page-index").textContent = `Page ${index + 1} of ${source.receipt.manifest.pages.length}`;
  try {
    const response = await api("page/" + index);
    const bitmap = await createImageBitmap(await response.blob());
    if (revision !== imageRevision) { bitmap.close(); return; }
    image = bitmap;
    canvas.width = bitmap.width;
    canvas.height = bitmap.height;
    paint();
  } finally {
    if (revision === imageRevision) canvas.setAttribute("aria-busy", "false");
  }
}
function invalidatePolicy() {
  revision++;
  policy = result = undefined;
  provableFields = [];
  get("field-registration").hidden = true;
  get("register-field").reset();
  get("registered-fields").replaceChildren();
  masked = [];
  get("plan-summary").textContent = "";
  for (const id of ["privacy-inference", "release-scan-status", "release-findings"]) get(id).replaceChildren();
  get("exposure-panel").hidden = true;
  renderLists(); paint(); update();
}
function mark(box, kind) {
  const [page, x, y, right, bottom] = box;
  const [w,h] = source.receipt.manifest.pages[page];
  if (![x,y,right,bottom].every(Number.isInteger) || x < 0 || y < 0 || right > w || bottom > h
      || right <= x || bottom <= y) throw new Error("Choose valid pixel bounds on this page.");
  if (regions.some((rule) => rule.kind === kind && rule.box.join() === box.join())) return;
  regions.push({kind,box});
  invalidatePolicy();
}
function cursor(event) {
  const box = canvas.getBoundingClientRect();
  return {x: Math.min(canvas.width, Math.max(0, (event.clientX - box.left) * canvas.width / box.width)),
          y: Math.min(canvas.height, Math.max(0, (event.clientY - box.top) * canvas.height / box.height))};
}
canvas.addEventListener("pointerdown", (event) => {
  if (!image || event.button !== 0) return;
  canvas.setPointerCapture(event.pointerId);
  const point = cursor(event);
  drag = [point,point];
});
canvas.addEventListener("pointermove", (event) => {
  if (drag) { drag[1] = cursor(event); paint(); }
});
canvas.addEventListener("pointercancel", () => { drag = undefined; paint(); });
canvas.addEventListener("pointerup", (event) => {
  if (!drag) return;
  const [a,b] = [drag[0],cursor(event)];
  drag = undefined;
  const box = [pageNo,Math.floor(Math.min(a.x,b.x)),Math.floor(Math.min(a.y,b.y)),
               Math.ceil(Math.max(a.x,b.x)),Math.ceil(Math.max(a.y,b.y))];
  if (box[1] < box[3] && box[2] < box[4]) mark(box, get("mode").value);
  paint();
});
submit(get("coordinates"), (event) => {
  const {x,y,right,bottom} = inputs(event.target);
  mark([pageNo,+x,+y,+right,+bottom], get("mode").value);
});
submit(get("upload-form"), async (event) => {
  status("Rendering and committing the original PDF…");
  const old = source?.workspace;
  const response = await api("v2/upload", inputs(event.target).pdf);
  if (old) await api("close", {}, old);
  source = await response.json();
  regions.length = 0; suggestions = [];
  get("detection-notice").textContent = "";
  invalidatePolicy();
  get("workspace").hidden = false;
  await loadPage(0);
  status("Original PDF committed. Review the suggested regions.");
  await scanFields({custom:[],ocr:false,financial:get("financial-detection").checked});
});
click("previous", () => loadPage(pageNo - 1));
click("next", () => loadPage(pageNo + 1));
click("save-source-receipt", () => {
  save(new Blob([JSON.stringify(source.receipt)], {type:"application/json"}), "source-receipt.json");
});
click("close", async () => {
  await api("close", {});
  image?.close();
  source = image = drag = undefined;
  regions.length = 0; suggestions = [];
  invalidatePolicy();
  imageRevision++;
  context.clearRect(0, 0, canvas.width, canvas.height);
  get("workspace").hidden = true;
  get("upload-form").reset();
  status("Source workspace closed.");
});
get("policy").addEventListener("input", invalidatePolicy);
let scanRevision = 0;
async function scanFields(data) {
  const workspace = source.workspace;
  const scan = ++scanRevision;
  get("detection-notice").textContent = "Scanning locally…";
  try {
    const response = await (await api("v2/detect", data, workspace)).json();
    if (source?.workspace !== workspace || scan !== scanRevision) return;
    suggestions = response.suggestions.filter(item => !regions.some(rule => rule.box.join() === item.region.join()));
    get("detection-notice").textContent = [`${suggestions.length} suggestions to review.`, ...response.warnings].join(" ");
    renderLists(); paint();
  } catch (error) {
    if (source?.workspace === workspace && scan === scanRevision) get("detection-notice").textContent = error.message;
  }
}
submit(get("detect-form"), async (event) => {
  const {custom,ocr,financial} = inputs(event.target);
  await scanFields({custom:custom.split(/\r?\n/).map(s => s.trim()).filter(Boolean),ocr:Boolean(ocr),financial:Boolean(financial)});
});
function showExposure(report) {
  const panel = get("exposure-panel");
  panel.hidden = false;
  get("exposure-summary").textContent = report.recorded_exports
    ? `Compared with ${report.recorded_exports} recorded export(s).`
    : "No prior exports are recorded for this source and recipient.";
  const list = get("exposure-pages");
  list.replaceChildren();
  for (const field of report.reconstructed_fields ?? []) {
    listItem("exposure-pages", `Combining releases exposes the full ${field.category.replaceAll("_", " ")} region on page ${field.page}.`);
  }
  for (const page of report.pages) {
    const row = document.createElement("li");
    const exposed = page.previously_visible_but_now_hidden;
    row.textContent = `Page ${page.page} · ${exposed.toLocaleString()} currently masked pixels were visible in recorded exports.`;
    list.append(row);
  }
}

submit(get("policy"), async (event) => {
  const {audience} = inputs(event.target);
  const version = revision;
  const boxes = (kind) => regions.filter((rule) => rule.kind === kind).map((rule) => rule.box);
  const payload = {audience, hide:boxes("hide"), keep:boxes("keep")};
  const plan = await (await api("v2/request", payload)).json();
  if (version !== revision) throw new Error("The approved regions changed. Build a fresh plan.");
  policy = plan.request;
  provableFields = [];
  get("register-field").reset();
  get("registered-fields").replaceChildren();
  const fieldRegions = get("register-field").elements.region;
  fieldRegions.replaceChildren(...policy.hide.map((box, i) =>
    new Option(`Region ${i + 1} · Page ${box[0] + 1} · ${box.slice(1).join(", ")}`, i)));
  get("field-registration").hidden = !policy.hide.length;
  result = undefined;
  masked = plan.masked;
  const metrics = plan.metrics;
  get("record-exposure").checked = false;
  showExposure(plan.exposure);
  get("privacy-inference").replaceChildren();
  for (const finding of plan.inference) {
    listItem("privacy-inference", `The age on page ${finding.age_page} and visit date on page ${finding.visit_page} suggest a birth month near ${finding.estimated_month}. ${finding.assumption}`);
  }
  get("plan-summary").textContent = `${metrics.tiles.toLocaleString()} proof tiles · ${metrics.extra_pixels.toLocaleString()} additional pixels hidden · Page coverage: ${metrics.page_percentages.map((pct) => pct + "%").join(", ")}.`;
  paint();
  status("Plan checked. Review the preview, then generate the PDF and proof ZIP.");
});
submit(get("register-field"), (event) => {
  if (!policy || generating) throw new Error("Wait for the export to finish and review the plan.");
  if (provableFields.length >= 16) throw new Error("Register up to 16 fields per export.");
  const {label, description, type, unit, value, region} = inputs(event.target);
  const field = {label, description: description.trim(), type, unit: unit.trim().toUpperCase(), value, region: policy.hide[Number(region)]};
  provableFields.push(field);
  const row = document.createElement("li");
  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "quiet";
  remove.textContent = "Remove";
  remove.onclick = () => {
    if (generating) return;
    provableFields = provableFields.filter(item => item !== field);
    result = undefined;
    row.remove();
    update();
  };
  row.append(`${label} · ${type}${unit ? " · " + field.unit : ""} `, remove);
  get("registered-fields").append(row);
  event.target.reset();
  result = undefined;
});

click("prove", async () => {
  status("Building the redacted PDF and proof…");
  const request = policy;
  generating = true;
  try {
    const record_exposure = get("record-exposure").checked;
    get("release-scan-status").replaceChildren();
    get("release-findings").replaceChildren();
    result = undefined;
    update();
    const scan_export = get("scan-export").checked;
    const artifact = await (await api("v2/export", {request, record_exposure, scan_export, provable_fields:provableFields})).json();
    if (policy !== request) throw new Error("The policy changed. Build a fresh plan.");
    const scan = artifact.leak_scan;
    if (scan) {
      get("release-scan-status").textContent = {
        findings:"Export paused. Review the readable protected values below and update the mask.",
        inconclusive:"OCR review inconclusive. Check the rendered pages before sharing.",
        no_matches:`OCR found no exact matches for ${scan.tracked_values} tracked value(s).`,
      }[scan.status];
      for (const finding of scan.findings) {
        const row = document.createElement("li");
        row.append(reviewButton(`Page ${finding.page} · ${finding.category.replaceAll("_", " ")}`,
          () => loadPage(finding.page - 1)));
        row.append(` · pixels ${finding.box.join(", ")}`);
        get("release-findings").append(row);
      }
      if (scan.unreadable_pages.length) listItem("release-findings",
        `Unreadable pages: ${scan.unreadable_pages.join(", ")}`);
      if (scan.unreadable_source_pages.length) listItem("release-findings",
        `Source pages without readable text: ${scan.unreadable_source_pages.join(", ")}`);
      if (scan.tracked_values === 0) listItem("release-findings", "The mask did not overlap any recognized labeled identifiers.");
      if (scan.status === "findings") {
        status("Export paused because the final PDF still has readable protected values.", true);
        return;
      }
    } else get("release-scan-status").textContent = "Final PDF OCR scan skipped.";
    result = artifact;
    if (artifact.exposure) showExposure(artifact.exposure);
    status(record_exposure ? "Export recorded locally. Download the redacted PDF and proof ZIP."
      : "Export checks passed. Download the redacted PDF and proof ZIP.");
  } finally {
    generating = false;
  }
});
click("save-pdf", () => save(new Blob([binary(result.pdf_base64)], {type:"application/pdf"}), "redacted.pdf"));
click("save-proof", () => save(new Blob([binary(result.zip_base64)], {type:"application/zip"}), "legitzk-proof.zip"));

const navLinks = [...document.querySelectorAll("[data-view]")];
function showView() {
  const hash = location.hash.slice(1);
  const view = ["studio", "verify", "lab", "zk"].includes(hash) ? hash : "studio";
  for (const link of navLinks) {
    const active = link.dataset.view === view;
    get("view-" + link.dataset.view).hidden = !active;
    if (active) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
  status("");
}
window.addEventListener("hashchange", showView);
showView();

const comparisonLabels = {
  byte_difference_only: "PDF bytes changed. No visible difference was found at the comparison resolution.",
  differences: "PDF bytes and visible content changed.",
  unreadable: "PDF bytes changed. The candidate could not be compared visually.",
};
async function inspect(demo = "") {
  const {zip,pdf,expected,forensic_ocr} = inputs(get("verify-form"));
  return inspectDisclosure(zip, pdf, expected, forensic_ocr, demo);
}
async function inspectDisclosure(zip, pdf, expected, forensic_ocr = false, demo = "") {
  if (!zip.size || !pdf.size) throw new Error("Select a redacted PDF and proof ZIP in Verify.");
  if (zip.size > 48_000_000 || pdf.size > 36_000_000) throw new Error("The ZIP or PDF exceeds the upload limit.");
  const headers = {"X-LegitZK-Action":"1", "X-LegitZK-Zip-Length":String(zip.size), "X-LegitZK-Demo":demo, "X-LegitZK-OCR-Forensics":forensic_ocr && !demo ? "1" : "0"};
  if (!demo && expected?.size) {
    if (expected.size > 3072) throw new Error("Expected source receipt is too large.");
    const bytes = new Uint8Array(await expected.arrayBuffer());
    headers["X-LegitZK-Expected-Receipt"] = btoa(String.fromCharCode(...bytes));
  }
  const response = await fetch("/api/v2/inspect", {
    method: "POST",
    headers,
    body: new Blob([zip, pdf]),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "Verification failed.");
  return data;
}

function showChanges(data, list, preview) {
  for (const page of data.changes) {
    const row = document.createElement("li");
    const pixels = page.changed_pixels ? ` · ${page.changed_pixels.toLocaleString()} changed pixels` : "";
    const rules = page.protected_regions?.length ? ` · Keep-visible rules ${page.protected_regions.join(", ")}` : "";
    row.textContent = `Page ${page.page} · ${page.status}${pixels}${rules}`;
    list.append(row);
  }
  if (data.preview) {
    const {png,page} = data.preview;
    const url = URL.createObjectURL(new Blob([binary(png)], {type:"image/png"}));
    preview.onload = preview.onerror = () => URL.revokeObjectURL(url);
    preview.src = url;
    preview.alt = `Page ${page} with changed regions outlined`;
    preview.hidden = false;
  }
}

let inspectionReport;
let inspectionRevision = 0;
click("save-inspection", () => {
  if (inspectionReport) {
    save(new Blob([JSON.stringify(inspectionReport, null, 2)], {type:"application/json"}), "legitzk-inspection.json");
  }
});
get("verify-form").addEventListener("change", () => {
  inspectionRevision++;
  inspectionReport = undefined;
  get("save-inspection").hidden = true;
});

submit(get("verify-form"), async () => {
  const revisionAtStart = ++inspectionRevision;
  const output = get("result"), inventory = get("file-checks"), comparison = get("verify-comparison");
  output.textContent = "Verifying…";
  inspectionReport = undefined;
  get("save-inspection").hidden = true;
  output.classList.remove("failed");
  inventory.replaceChildren();
  comparison.hidden = get("verify-preview").hidden = true;
  get("verify-changes").replaceChildren();
  get("verify-ocr-fields").replaceChildren();
  try {
    const data = await inspect();
    if (revisionAtStart !== inspectionRevision) {
      output.textContent = "Inputs changed. Verify the current selection.";
      return;
    }
    inspectionReport = {...data};
    if (data.ocr_fields) {
      for (const field of data.ocr_fields.changes) listItem("verify-ocr-fields",
        `OCR · Page ${field.page} · ${field.field} · ${field.baseline_value} → ${field.candidate_value}`);
      if (data.ocr_fields.manual_review_pages.length) listItem("verify-ocr-fields",
        `OCR needs manual review on page(s) ${data.ocr_fields.manual_review_pages.join(", ")}.`);
    }
    if (data.comparison) {
      const {preview, ...summary} = data.comparison;
      inspectionReport.comparison = summary;
    }
    get("save-inspection").hidden = false;
    output.textContent = data.valid ? `Verified ${data.pages} page(s) for ${data.audience}.`
      : `Verification failed. ${data.verification_error || "See the signed file checks below."}`;
    if (data.files["redacted.pdf"] === "changed") {
      output.textContent = "The uploaded PDF differs from the export recorded in this proof ZIP.";
      if (data.verification_error) output.textContent += ` Reference verification failed. ${data.verification_error}`;
    }
    if (data.source_match === "mismatch") {
      output.textContent = data.proof_valid ? "The submitted proof is valid. The signed source differs from the expected source."
        : "Verification failed. The signed source also differs from the expected source.";
    } else if (data.valid && data.source_match === "match") {
      output.textContent += " The signed source PDF fingerprint matches.";
    }
    output.classList.toggle("failed", !data.valid);
    for (const [name, state] of Object.entries(data.files)) {
      const row = document.createElement("li");
      const label = document.createElement("span");
      label.textContent = name;
      const badge = document.createElement("strong");
      badge.textContent = {match:"Matches export",changed:"Changed",missing:"Missing"}[state];
      badge.className = state === "match" ? "badge" : "badge failed";
      row.append(label, badge);
      inventory.append(row);
    }
    if (data.comparison) {
      comparison.textContent = comparisonLabels[data.comparison.status];
      comparison.hidden = false;
      showChanges(data.comparison, get("verify-changes"), get("verify-preview"));
    }
  } catch (error) {
    output.textContent = "Verification failed. " + error.message;
    output.classList.add("failed");
  }
});

let sourceInvestigation;
function listItem(id, text) {
  const row = document.createElement("li");
  row.textContent = text;
  get(id).append(row);
}
function provenanceItem(label, value) {
  const term = document.createElement("dt");
  const detail = document.createElement("dd");
  term.textContent = label;
  detail.textContent = value;
  get("investigation-provenance").append(term, detail);
}
let investigationRevision = 0;
function clearDisclosureComparison() {
  get("investigation-disclosure-changes").replaceChildren();
  const preview = get("investigation-disclosure-preview");
  preview.hidden = true;
  preview.removeAttribute("src");
}
get("source-investigation").addEventListener("change", () => {
  investigationRevision++;
  clearDisclosureComparison();
  get("investigation-result").textContent = "";
  sourceInvestigation = undefined;
  get("investigation-detail").hidden = true;
});
click("save-investigation", () => {
  if (!sourceInvestigation) return;
  const {preview, ...visual} = sourceInvestigation.visual;
  const summary = {...sourceInvestigation, visual};
  save(new Blob([JSON.stringify(summary, null, 2)], {type:"application/json"}), "source-investigation.json");
});
submit(get("source-investigation"), async (event) => {
  sourceInvestigation = undefined;
  const revisionAtStart = ++investigationRevision;
  clearDisclosureComparison();
  const output = get("investigation-result");
  get("investigation-detail").hidden = true;
  output.textContent = "Authenticating and comparing the PDFs…";
  output.classList.remove("failed");
  try {
    const {baseline,candidate,receipt,proof,include_values} = inputs(event.target);
    if (baseline.size > 16 * 1024 * 1024 || candidate.size > 16 * 1024 * 1024 || receipt.size > 3072) {
      throw new Error("A PDF or receipt exceeds the upload limit.");
    }
    if (proof.size) {
      const savedReceipt = JSON.parse(await receipt.text());
      if (savedReceipt?.manifest?.source_sha256 !== await sha256Hex(baseline)) {
        throw new Error("The baseline PDF does not match the saved source receipt.");
      }
      const data = await inspectDisclosure(proof, candidate, receipt);
      if (revisionAtStart !== investigationRevision) return;
      if (data.verification_error) throw new Error(data.verification_error);
      if (data.source_match !== "match") {
        throw new Error("The proof ZIP could not be authenticated against this source receipt.");
      }
      if (data.valid) {
        output.textContent = "Verified disclosure. The candidate matches the authorized redacted export.";
      } else if (data.files["redacted.pdf"] === "changed" && data.comparison) {
        output.textContent = "The candidate differs from the verified redacted export.";
        showChanges(data.comparison, get("investigation-disclosure-changes"), get("investigation-disclosure-preview"));
      } else {
        throw new Error("The disclosure could not be verified.");
      }
      return;
    }
    const encoded = btoa(String.fromCharCode(...new Uint8Array(await receipt.arrayBuffer())));
    const response = await fetch("/api/v2/forensics/compare", {
      method: "POST",
      headers: {"X-LegitZK-Action":"1", "X-LegitZK-Baseline-Length":String(baseline.size),
        "X-LegitZK-Expected-Receipt":encoded, "X-LegitZK-Include-Values":include_values ? "1" : "0"},
      body: new Blob([baseline, candidate]),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Investigation failed.");
    if (revisionAtStart === investigationRevision) renderSourceInvestigation(data, include_values);
  } catch (error) {
    if (revisionAtStart !== investigationRevision) return;
    output.textContent = error.message;
    output.classList.add("failed");
  }
});

function renderSourceInvestigation(data, include_values) {
  const output = get("investigation-result");
  sourceInvestigation = data;
  for (const id of ["investigation-provenance","investigation-fields","investigation-pages",
    "investigation-structure","investigation-limits"]) get(id).replaceChildren();
  const preview = get("investigation-preview");
  preview.hidden = true;
  output.textContent = data.candidate_matches_signed_bytes
    ? "Candidate bytes match the authenticated baseline."
    : "Candidate differs from the source. Add the export proof ZIP to check whether the differences are authorized redactions.";
  provenanceItem("Baseline version", data.baseline_version);
  provenanceItem("Verified baseline signing key", data.baseline_signing_key);
  provenanceItem("Baseline SHA-256", data.baseline_sha256);
  provenanceItem("Candidate SHA-256", data.candidate_sha256);
  for (const field of data.field_analysis.changes) {
    const values = include_values ? ` · ${field.baseline_value ?? "(absent)"} → ${field.candidate_value ?? "(absent)"}` : "";
    listItem("investigation-fields", `Page ${field.page} · ${field.field} · ${field.classification}${values}`);
  }
  if (!data.field_analysis.changes.length) listItem("investigation-fields", "No changes found in comparable native fields.");
  if (data.field_analysis.ambiguous_matches) listItem("investigation-fields",
    `${data.field_analysis.ambiguous_matches} changed duplicate labels require manual review.`);
  if (data.field_analysis.truncated) listItem("investigation-fields", "Field analysis reached its reporting limit.");
  showChanges(data.visual, get("investigation-pages"), preview);
  if (!data.visual.changes.length) listItem("investigation-pages", "No visible changes found in the compared raster.");
  for (const [name, entry] of Object.entries(data.structure_changes)) {
    listItem("investigation-structure", `${name.replaceAll("_", " ")} · ${entry.baseline} → ${entry.candidate}`);
  }
  listItem("investigation-structure", data.metadata_keys_changed.length
    ? `Changed metadata keys · ${data.metadata_keys_changed.join(", ")}`
    : "No differences in inspected metadata keys.");
  data.limitations.forEach(text => listItem("investigation-limits", text));
  get("investigation-detail").hidden = false;
}

let fieldExample;
click("field-example", async () => {
  const output = get("investigation-result");
  get("investigation-detail").hidden = true;
  const revisionAtStart = ++investigationRevision;
  clearDisclosureComparison();
  get("save-field-example").hidden = true;
  sourceInvestigation = fieldExample = undefined;
  output.classList.remove("failed");
  output.textContent = "Comparing the synthetic source versions…";
  try {
    const example = await (await api("v2/forensics/field-example", {})).json();
    if (revisionAtStart !== investigationRevision) return;
    fieldExample = example.zip_base64;
    renderSourceInvestigation(example.investigation, true);
    output.textContent = "Synthetic test: the candidate differs from the signed baseline.";
    get("save-field-example").hidden = false;
  } catch (error) {
    output.textContent = error.message;
    output.classList.add("failed");
  }
});
click("save-field-example", () => {
  if (fieldExample) save(new Blob([binary(fieldExample)], {type:"application/zip"}), "synthetic-field-test.zip");
});

const revisionForm = get("revision-editor");
const revisionCanvas = get("revision-canvas");
const revisionContext = revisionCanvas.getContext("2d");
let revisionImage, selectionStart, selectedBox, workingCopy;
let appliedEdits = 0;
let editorRevision = 0;
function paintRevision() {
  if (!revisionImage) return;
  revisionContext.drawImage(revisionImage, 0, 0);
  if (selectedBox) {
    const [x,y,r,b] = selectedBox;
    revisionContext.fillStyle = "rgba(255,174,0,.24)";
    revisionContext.fillRect(x, y, r-x, b-y);
    revisionContext.strokeStyle = "#bd7014";
    revisionContext.strokeRect(x, y, r-x, b-y);
  }
}
function revisionPoint(event) {
  const area = revisionCanvas.getBoundingClientRect();
  return [
    Math.max(0, Math.min(revisionCanvas.width, Math.round((event.clientX-area.left)*revisionCanvas.width/area.width))),
    Math.max(0, Math.min(revisionCanvas.height, Math.round((event.clientY-area.top)*revisionCanvas.height/area.height))),
  ];
}
revisionCanvas.addEventListener("pointerdown", event => {
  revisionCanvas.setPointerCapture(event.pointerId);
  selectionStart = revisionPoint(event);
});
function selectRevision(event) {
  if (!selectionStart) return;
  const [x,y] = revisionPoint(event), [a,b] = selectionStart;
  selectedBox = [Math.min(x,a), Math.min(y,b), Math.max(x,a), Math.max(y,b)];
  paintRevision();
}
revisionCanvas.addEventListener("pointermove", selectRevision);
revisionCanvas.addEventListener("pointerup", event => {
  selectRevision(event);
  selectionStart = undefined;
});
revisionCanvas.addEventListener("pointercancel", () => {
  selectionStart = selectedBox = undefined;
  paintRevision();
});
function clearRevisionPreview() {
  revisionImage?.close();
  revisionImage = selectedBox = selectionStart = undefined;
  revisionCanvas.hidden = true;
}
revisionForm.addEventListener("change", event => {
  if (!["file", "mode", "page"].includes(event.target.name)) return;
  editorRevision++;
  if (event.target.name === "file") {
    workingCopy = undefined;
    appliedEdits = 0;
    get("revision-hashes").hidden = true;
    get("revision-status").textContent = "";
    get("revision-download").disabled = true;
  }
  get("revision-old").hidden = revisionForm.elements.mode.value === "raster";
  get("revision-region").hidden = !get("revision-old").hidden;
  clearRevisionPreview();
});
async function revisionRequest(path, file, extra) {
  if (!file.size) throw new Error("Choose a PDF first.");
  const response = await fetch("/api/v2/forensics/" + path, {
    method: "POST", headers: {"X-LegitZK-Action":"1", ...extra}, body:file,
  });
  if (!response.ok) throw new Error((await response.json()).detail || "The edit request failed.");
  return response.blob();
}
click("revision-preview", async () => {
  const revision = editorRevision;
  const {file,page} = inputs(revisionForm);
  const incoming = await createImageBitmap(await revisionRequest("edit-preview", workingCopy ?? file, {"X-LegitZK-Page":page}));
  if (revision !== editorRevision || revisionForm.elements.mode.value !== "raster") {
    incoming.close();
    return;
  }
  revisionImage?.close();
  revisionImage = incoming;
  selectedBox = undefined;
  revisionCanvas.width = incoming.width;
  revisionCanvas.height = incoming.height;
  revisionCanvas.hidden = false;
  paintRevision();
});
async function sha256Hex(blob) {
  const hash = await crypto.subtle.digest("SHA-256", await blob.arrayBuffer());
  return [...new Uint8Array(hash)].map(byte => byte.toString(16).padStart(2, "0")).join("");
}
revisionForm.addEventListener("submit", run(async () => {
  const revisionAtStart = editorRevision;
  const {file,page,mode,old,replacement} = inputs(revisionForm);
  if (mode === "raster" && !selectedBox) throw new Error("Preview the page and select the visible value first.");
  const edit = {page:Number(page), old, replacement, box:mode === "raster" ? selectedBox : null};
  const encoded = btoa(String.fromCharCode(...new TextEncoder().encode(JSON.stringify(edit))));
  const revised = await revisionRequest("edit-copy", workingCopy ?? file, {"X-LegitZK-Edit":encoded});
  const [originalHash, editedHash] = await Promise.all([sha256Hex(file), sha256Hex(revised)]);
  if (revisionAtStart !== editorRevision) return;
  editorRevision++;
  workingCopy = revised;
  appliedEdits++;
  clearRevisionPreview();
  revisionForm.elements.old.value = "";
  revisionForm.elements.replacement.value = "";
  get("revision-original-hash").textContent = originalHash;
  get("revision-edited-hash").textContent = editedHash;
  get("revision-hashes").hidden = false;
  get("revision-download").disabled = false;
  get("revision-status").textContent = `${appliedEdits} ${appliedEdits === 1 ? "edit" : "edits"} applied. Preview a page for another visible edit, or download the working copy.`;
}, get("revision-apply")));
click("revision-download", () => {
  if (workingCopy) save(workingCopy, "edited-test-copy.pdf");
});

let verifiedDisclosure;
let disclosureRevision = 0;
const zkOutput = (id, message) => { get(id).textContent = message; };
function zkSubmit(id, output, handler) {
  submit(get(id), async (event) => {
    zkOutput(output, "Working…");
    try { await handler(event.target); }
    catch (error) { zkOutput(output, error.message); }
  });
}
async function zkJson(file) {
  if (!file?.size || file.size > 48_000) throw new Error("Choose a JSON file under 48 KB.");
  return JSON.parse(await file.text());
}
function saveZkJson(value, name) {
  save(new Blob([JSON.stringify(value, null, 2)], {type:"application/json"}), name);
}
function clearZkFields() {
  disclosureRevision++;
  verifiedDisclosure = undefined;
  get("zk-fields").hidden = true;
  clearZkDraft();
  zkOutput("zk-verify-result", "");
}
get("zk-disclosure").addEventListener("input", () => {
  clearZkFields();
  zkOutput("zk-recipient-result", "");
});
const zkForm = get("zk-request");
const zkSelect = zkForm.elements.field;
let draftRequest;
let draftRevision = 0;
function clearZkDraft() {
  draftRevision++;
  draftRequest = undefined;
  get("zk-download").hidden = true;
  get("zk-local").hidden = true;
}
function updateZkOperators() {
  const field = verifiedDisclosure?.records[zkSelect.selectedIndex]?.field;
  const operator = zkForm.elements.operator;
  for (const option of operator.options) {
    option.disabled = option.value !== "eq" && field?.encoding !== "bounded-integer";
  }
  if (operator.selectedOptions[0]?.disabled) operator.value = "eq";
  const upper = operator.value === "between";
  get("zk-upper").hidden = !upper;
  zkForm.elements.upper.required = upper;
}
zkForm.addEventListener("input", () => {
  clearZkDraft();
  updateZkOperators();
});
get("zk-question").addEventListener("input", clearZkDraft);
async function loadZkDisclosure(zip, pdf, workspace) {
  clearZkFields();
  const version = disclosureRevision;
  const report = await inspectDisclosure(zip, pdf, null);
  if (version !== disclosureRevision) return;
  if (!report.valid) throw new Error(report.verification_error || "The disclosure could not be verified. Check the PDF and ZIP in Verify.");
  if (!report.provable_fields?.length) throw new Error("This verified export has no registered fields.");
  verifiedDisclosure = {records:report.provable_fields, issuer:report.field_issuer, workspace};
  zkSelect.replaceChildren(...verifiedDisclosure.records.map(({field}) =>
    new Option(`${field.label} · ${field.type}${field.unit ? " · " + field.unit : ""}`, field.id)));
  updateZkOperators();
  get("zk-fields").hidden = false;
  zkOutput("zk-recipient-result", "Disclosure verified. Ask a question or enter a condition directly.");
}
zkSubmit("zk-disclosure", "zk-recipient-result", async (form) => {
  const {zip, pdf} = inputs(form);
  await loadZkDisclosure(zip, pdf);
});
click("zk-current", async () => {
  try {
    if (!source || !result) throw new Error("Register a field and generate a Redact export first.");
    const workspace = source.workspace;
    zkOutput("zk-recipient-result", "Loading current export…");
    await loadZkDisclosure(new Blob([binary(result.zip_base64)]), new Blob([binary(result.pdf_base64)]), workspace);
  } catch (error) {
    zkOutput("zk-recipient-result", error.message);
  }
});
async function zkApi(action, payload, workspace) {
  return (await api("v2/field-claim/" + action, payload, workspace)).json();
}
zkSubmit("zk-question", "zk-recipient-result", async (form) => {
  clearZkDraft();
  const version = draftRevision;
  const disclosure = verifiedDisclosure;
  if (!disclosure) throw new Error("Load a verified disclosure first.");
  const {question} = inputs(form);
  const proposal = await zkApi("interpret", {question, records:disclosure.records, issuer:disclosure.issuer});
  if (version !== draftRevision) return;
  zkSelect.value = proposal.field_id;
  zkForm.elements.operator.value = proposal.operator;
  zkForm.elements.candidate.value = proposal.values[0];
  zkForm.elements.upper.value = proposal.values[1] ?? "";
  updateZkOperators();
  zkOutput("zk-recipient-result", "Check the proposed field, comparison and values, then select Review condition.");
});
zkSubmit("zk-request", "zk-recipient-result", async (form) => {
  clearZkDraft();
  const version = draftRevision;
  const disclosure = verifiedDisclosure;
  const record = disclosure?.records[zkSelect.selectedIndex];
  if (!record) throw new Error("Load a verified disclosure first.");
  const {operator, candidate, upper} = inputs(form);
  const values = operator === "between" ? [candidate, upper] : [candidate];
  const draft = await zkApi("request", {record, issuer:disclosure.issuer, operator, values});
  if (version !== draftRevision) return;
  draftRequest = draft.request;
  zkOutput("zk-recipient-result", draft.claim);
  get("zk-download").hidden = false;
  get("zk-local").hidden = !source || (disclosure.workspace && disclosure.workspace !== source.workspace);
});
click("zk-local", async () => {
  const request = draftRequest;
  const disclosure = verifiedDisclosure;
  const workspace = source?.workspace;
  const version = draftRevision;
  const record = disclosure?.records.find(item => item.field.id === request?.field_id);
  if (!record || !workspace || (disclosure.workspace && disclosure.workspace !== workspace)) {
    zkOutput("zk-recipient-result", "Open the original Redact workspace for this export.");
    return;
  }
  try {
    zkOutput("zk-recipient-result", "Generating and verifying the proof…");
    const response = await zkApi("prove", {request, approved:true}, workspace);
    if (version !== draftRevision || source?.workspace !== workspace) return;
    if (!response.proof) {
      zkOutput("zk-recipient-result", "No proof was generated for this condition.");
      return;
    }
    const checked = await zkApi("verify", {record, request, proof:response.proof, issuer:disclosure.issuer});
    if (version !== draftRevision || source?.workspace !== workspace) return;
    zkOutput("zk-recipient-result", checked.valid ? `Proven · ${checked.claim}` : "Unverified condition.");
  } catch (error) {
    if (version === draftRevision && source?.workspace === workspace) zkOutput("zk-recipient-result", error.message);
  }
});
click("zk-download", () => {
  if (!draftRequest) return;
  saveZkJson(draftRequest, "claim-request.json");
  zkOutput("zk-recipient-result", "Keep your request and send a copy to the document owner.");
});
zkSubmit("zk-verify", "zk-verify-result", async (form) => {
  const disclosure = verifiedDisclosure;
  if (!disclosure) throw new Error("Load a verified disclosure first.");
  const files = inputs(form);
  const [request, response] = await Promise.all([zkJson(files.request), zkJson(files.response)]);
  const record = disclosure.records.find(item => item.field.id === request.field_id);
  if (!record) throw new Error("The requested field is absent from this verified export.");
  const checked = await zkApi("verify", {record, request, proof:response.proof, issuer:disclosure.issuer});
  if (disclosure !== verifiedDisclosure) return;
  zkOutput("zk-verify-result", checked.valid
    ? `Proven for the attested field · ${checked.claim} · Signing key ${disclosure.issuer}`
    : "Unverified condition.");
});
let reviewedRequest;
const ownerForm = get("zk-owner");
ownerForm.elements.request.addEventListener("change", async () => {
  reviewedRequest = undefined;
  ownerForm.elements.approved.checked = false;
  zkOutput("zk-candidate", "");
  zkOutput("zk-owner-result", "");
  const file = ownerForm.elements.request.files[0];
  if (!file) return;
  try {
    const request = await zkJson(file);
    if (ownerForm.elements.request.files[0] !== file) return;
    const review = await zkApi("review", request);
    if (ownerForm.elements.request.files[0] !== file) return;
    reviewedRequest = {file, request};
    zkOutput("zk-candidate", review.claim);
  } catch (error) {
    if (ownerForm.elements.request.files[0] === file) zkOutput("zk-owner-result", error.message);
  }
});
zkSubmit("zk-owner", "zk-owner-result", async (form) => {
  const reviewed = reviewedRequest;
  if (!source || reviewed?.file !== form.elements.request.files[0] || !reviewed || !form.elements.approved.checked) {
    throw new Error("Open the owner workspace and approve the displayed request.");
  }
  form.elements.approved.checked = false;
  const response = await zkApi("prove", {request:reviewed.request, approved:true});
  if (reviewed !== reviewedRequest) return;
  if (!response.proof) {
    zkOutput("zk-owner-result", "No proof was generated.");
    return;
  }
  saveZkJson(response, "claim-proof.json");
  zkOutput("zk-owner-result", "Claim proof downloaded. Send the proof to the recipient.");
});

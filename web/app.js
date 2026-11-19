const view = document.querySelector("#view");
const notice = document.querySelector("#notice");
const logout = document.querySelector("#logout");
const theme = document.querySelector("#theme");
const show = (html) => { view.innerHTML = html; };
const h = (value) => String(value).replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const id = (value) => encodeURIComponent(value);
const date = (ts) => new Date(ts * 1000).toLocaleString();
const formData = (form) => Object.fromEntries(new FormData(form));
const field = (label, name, type = "text", attrs = "") =>
  `<label>${label}<input required name="${name}" type="${type}" ${attrs}></label>`;

function message(text, error = false) {
  notice.hidden = !text;
  notice.textContent = text;
  notice.classList.toggle("error", error);
}
async function api(path, payload) {
  const options = payload === undefined ? {} : {
    method: "POST",
    headers: {"X-LegitZK-Action":"1", ...(payload instanceof Blob ? {} : {"Content-Type":"application/json"})},
    body: payload instanceof Blob ? payload : JSON.stringify(payload),
  };
  const response = await fetch("/api" + path, options);
  const content = await response.json();
  if (!response.ok) {
    const detail = typeof content.detail === "string" ? content.detail : "Check the submitted fields.";
    throw Object.assign(new Error(detail), { status: response.status });
  }
  return content;
}
function bind(selector, action, event = "submit") {
  const items = view.querySelectorAll(selector);
  for (const item of items) item.addEventListener(event, async (e) => {
    e.preventDefault();
    const button = event === "submit" ? item.querySelector("button") : item;
    button.disabled = true;
    const label = button.textContent;
    button.textContent = "Working…";
    message("");
    try { await action(item); }
    catch (err) { message(err.message, true); }
    finally { button.textContent = label; button.disabled = false; }
  });
}
function download(value, filename) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], {type:"application/json"}));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function setTheme(mode) {
  document.documentElement.dataset.theme = mode;
  theme.textContent = mode === "dark" ? "Light mode" : "Dark mode";
  localStorage.setItem("legitzk-theme", mode);
}
setTheme(localStorage.getItem("legitzk-theme") === "dark" ? "dark" : "light");
theme.onclick = () => setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
logout.onclick = async () => {
  try { await api("/logout", {}); await route(); }
  catch (err) { message(err.message, true); }
};

function landing() {
  show(`<section class="hero">
    <div><p class="eyebrow">Authenticated contract disclosure</p>
    <h1>Prove the terms you can’t share.</h1>
    <p class="lead">Give auditors the contract details they need and prove a private amount meets their threshold. Each disclosure traces back to a signed vendor record.</p>
    <div class="actions"><a class="button" href="#login">Open workspace</a><a class="button quiet" href="/verify">Verify evidence</a></div></div>
    <aside class="hero-card"><p class="eyebrow">What the auditor checks</p><h2>Vendor contract assurance</h2>
    <ul class="clean"><li>Issuer signature and source fingerprint</li><li>Disclosed terms and required fields</li><li>Private amount threshold</li><li>Recipient and request expiration</li></ul></aside>
    </section>
    <div class="grid"><article class="card"><h2>From signed record to disclosure</h2><p>An issuer signs the structured contract. The auditor chooses what the policy requires. The owner previews the disclosure PDF and shares a proof bound to the request.</p></article>
    <article class="card"><h2>What the proof covers</h2><p>LegitZK checks an issuer-attested schema and a PDF regenerated from public fields. Its research scope includes signed claims, selective disclosure, and private predicates.</p></article></div>
    <div class="grid" id="login"><section class="card"><h2>Sign in</h2><form id="signin">
      ${field("Email","email","email",'autocomplete="username"')}
      ${field("Password","password","password",'autocomplete="current-password" maxlength="128"')}
      <button>Sign in</button></form></section>
    <section class="card"><h2>Create an account</h2><form id="register">
      ${field("Email","email","email",'autocomplete="email"')}
      ${field("Password (12–128 characters)","password","password",'autocomplete="new-password" minlength="12" maxlength="128"')}
      <label>Role<select name="role"><option value="owner">Document owner</option><option value="auditor">Auditor</option></select></label>
      <button>Create account</button></form></section></div>
    <section class="card" id="metrics"><h2>Measured proof performance</h2><p>Loading benchmark results…</p></section>`);
  bind("#signin", async (form) => { await api("/session", formData(form)); await route(); });
  bind("#register", async (form) => {
    await api("/register", formData(form));
    form.reset();
    message("Account created. Sign in to continue.");
  });
  api("/benchmarks").then((data) => {
    const target = document.querySelector("#metrics");
    if (!target) return;
    target.innerHTML = `<h2>Measured proof performance</h2><p>${h(data.samples)} synthetic trials on ${h(data.environment)}</p>
      <div class="grid metrics"><div><span class="stat">${h(data.prove_ms)} ms</span>Median proving</div>
      <div><span class="stat">${h(data.verify_ms)} ms</span>Median verification</div>
      <div><span class="stat">${h(data.proof_bytes)} B</span>JSON proof</div></div>`;
  }).catch(() => {
    const target = document.querySelector("#metrics p");
    if (target) target.textContent = "Benchmark results are unavailable.";
  });
}

const issuerForm = `<section class="card"><h2>Issue a synthetic contract</h2><form id="issue">
  <div class="grid">${field("Owner email","owner","email")}${field("Vendor","vendor")}${field("Buyer","buyer")}${field("Effective date","effective_date","date")}
  ${field("Service","service")}${field("Synthetic bank reference","bank_reference")}
  ${field("Amount in USD cents","amount","number",'min="0" max="4294967295" step="1"')}</div>
  <button>Sign and issue</button></form></section>`;
const auditorForm = `<section class="card"><h2>Create an audit request</h2><form id="policy">
  ${field("Document reference","document_id","text",'pattern="[0-9a-f]{32}"')}
  ${field("Minimum contract amount in USD cents","threshold","number",'min="0" max="4294967295" step="1"')}
  <label class="check"><input type="checkbox" name="include_service"> Require service description</label>
  <p>Vendor, buyer, and effective date are required. Bank reference and exact amount are protected. The request is bound to your account and expires in one hour.</p><button>Create request</button></form></section>`;

function documentCard(doc) {
  const root = "/api/documents/" + id(doc.id);
  return `<article class="card"><h3>${h(doc.vendor)}</h3><code>${h(doc.id)}</code>
    <details><summary>Open source PDF</summary><a href="${root}/source.pdf" target="_blank" rel="noopener">Open PDF in a new tab</a></details>
    <form class="match" data-document="${h(doc.id)}">
    ${field("Match a downloaded source PDF","pdf","file",'accept=".pdf,application/pdf"')}
    <button type="submit" class="quiet">Check signed fingerprint</button></form></article>`;
}

function requestCard(item, role) {
  const {context, policy} = item.request;
  const key = id(item.id);
  const apiPath = "/api/requests/" + key;
  const expired = context.expires <= Math.floor(Date.now() / 1000);
  const active = !item.revoked && !expired;
  const status = item.revoked ? "Revoked" : expired ? "Expired" : item.consumed ? "Verified" : item.shared ? "Shared" : "Awaiting disclosure";
  const ownerActions = active && role === "owner" ? `<details><summary>Open redaction studio</summary>
    <p>Visible fields are fixed by the audit request. The preview is generated from these fields alone.</p>
    <ul>${policy.visible.map((name) => "<li>" + h(name.replaceAll("_", " ")) + "</li>").join("")}</ul>
    <p><a href="${apiPath}/preview.pdf" target="_blank" rel="noopener">Open the PDF preview in a new tab</a></p>
    <iframe loading="lazy" title="Disclosure PDF preview" src="${apiPath}/preview.pdf"></iframe>
    <div class="actions">
    ${item.shared ? `<a href="/share/${key}">Open share link</a><button type="button" class="quiet revoke" data-id="${key}">Revoke sharing</button>` :
      `<button type="button" class="publish" data-id="${key}">Generate proof and share</button>`}</div></details>` : "";
  const auditActions = role === "auditor" ? `<div class="actions">
    <button type="button" class="quiet request-export" data-id="${key}">Export request</button>
    ${item.shared && active ? `<a href="/share/${key}">Open evidence</a>` : ""}</div>` : "";
  return `<article class="card"><span class="badge">${status}</span><h3>Vendor contract request</h3><code>${h(context.document_id)}</code>
    <p>Threshold ≥ ${h(policy.threshold.toLocaleString())} USD cents<br>Auditor ${h(context.audience)}<br>
    Expires <time>${h(date(context.expires))}</time></p>${ownerActions}${auditActions}</article>`;
}
async function dashboard(data) {
  const {role, documents, requests, events} = data;
  show(`<p class="eyebrow">${h(role)} workspace</p><h1>Contract assurance</h1><p>${h(data.email)}</p>
    <div class="grid metrics"><div class="card"><span class="stat">${documents.length}</span>Recent contracts</div>
    <div class="card"><span class="stat">${requests.length}</span>Recent requests</div>
    <div class="card"><span class="stat">${requests.filter((item) => item.consumed).length}</span>Verified</div></div>
    ${role === "issuer" ? issuerForm : role === "auditor" ? auditorForm : `<h2>Signed contracts</h2>
      ${documents.map(documentCard).join("") || '<p class="card">Issued contracts will appear here.</p>'}`}
    ${role !== "issuer" ? `<h2>Disclosure requests</h2>${requests.map((item) => requestCard(item, role)).join("") || '<p class="card">No requests yet.</p>'}` : ""}
    <section class="card"><h2>Recent activity</h2>${events.length ? events.map((item) =>
      `<div class="result-row"><div>${h(item.kind)}<br><code>${h(item.ref)}</code></div><small>${h(date(item.occurred))}</small></div>`).join("") : "<p>No activity recorded.</p>"}</section>`);
  bind("#issue", async (form) => {
    const payload = formData(form); payload.amount = Number(payload.amount);
    const result = await api("/documents", payload);
    await route(); message("Signed contract issued. Reference " + result.id);
  });
  bind(".match", async (form) => {
    const file = new FormData(form).get("pdf");
    if (file.size > 65536) throw new Error("Choose a PDF under 64 KiB.");
    await api("/documents/" + id(form.dataset.document) + "/match", file);
    message("The uploaded PDF matches the signed source fingerprint.");
  });
  bind("#policy", async (form) => {
    const payload = formData(form);
    payload.threshold = Number(payload.threshold);
    payload.include_service = payload.include_service === "on";
    await api("/requests", payload); await route(); message("Audit request created.");
  });
  bind(".publish", async (button) => {
    const result = await api("/requests/" + button.dataset.id + "/publish", {});
    await route(); message("Disclosure shared. Link " + location.origin + result.share);
  }, "click");
  bind(".revoke", async (button) => {
    await api("/requests/" + button.dataset.id + "/revoke", {});
    await route(); message("Shared access revoked.");
  }, "click");
  bind(".request-export", async (button) => {
    const item = requests.find((entry) => entry.id === button.dataset.id);
    download(item.request, "auditor-request.json");
  }, "click");
}

function resultMarkup(result) {
  return `<section class="card" aria-label="Verification results">
    <h2 class="${result.valid ? "" : "failed"}">${result.valid ? "Disclosure verified" : "Verification failed"}</h2>
    ${result.checks.map(({check, passed}) =>
      `<div class="result-row"><span>${h(check)}</span><strong class="${passed ? "" : "failed"}">${passed ? "Passed" : "Failed"}</strong></div>`).join("")}
    </section>`;
}
function publicVerify() {
  show(`<p class="eyebrow">Independent verification</p><h1>Check a disclosure</h1><p class="lead">Use the policy, challenge, and issuer key you obtained separately from the disclosure package.</p>
    <section class="card"><form id="verify-form">
    ${field("Disclosure package","package","file",'accept=".json"')}
    ${field("Expected audit request","request","file",'accept=".json"')}
    ${field("Trusted issuer keys","trust","file",'accept=".json"')}
    <button>Verify package</button></form></section><div id="results" aria-live="polite"></div>`);
  bind("#verify-form", async (form) => {
    const files = formData(form);
    document.querySelector("#results").innerHTML = "";
    for (const [key, file] of Object.entries(files)) {
      if (file.size > 150000) throw new Error("Choose JSON files under 150 KB.");
      files[key] = await file.text();
    }
    const response = await fetch("/api/verify", {method:"POST",headers:{"Content-Type":"application/json","X-LegitZK-Action":"1"},
      body:JSON.stringify(files)});
    if (!response.ok) throw new Error("Verification service rejected the request.");
    document.querySelector("#results").innerHTML = resultMarkup(await response.json());
  });
}

function share(data, shareId) {
  const item = data.requests.find((request) => request.id === shareId);
  const ready = item?.shared && !item.revoked && item.request.context.expires > Date.now() / 1000;
  const authorized = ready && data.role === "auditor" && item.auditor === data.email;
  const root = "/api/requests/" + id(shareId);
  show(`<p class="eyebrow">Recipient workspace</p><h1>Shared disclosure</h1><p><a href="/">Back to workspace</a></p>
    <section class="card"><h2>${authorized ? "Issuer-attested evidence" : "Evidence unavailable"}</h2>
    <p>${authorized ? "Verify this disclosure against the stored audit request. The first successful check consumes the online request." :
      "The designated auditor can open a published disclosure before it expires."}</p>
    ${authorized ? `<div class="actions">${item.consumed ? '<span class="badge">Request already verified</span>' :
      '<button type="button" id="consume">Verify disclosure</button>'}
      <a class="button quiet" href="${root}/package">Download package</a><a href="${root}/disclosure.pdf" target="_blank" rel="noopener">Open disclosure PDF</a></div>` : ""}</section><div id="results" aria-live="polite"></div>`);
  bind("#consume", async (button) => {
    const result = await api("/requests/" + id(shareId) + "/verify", {});
    document.querySelector("#results").innerHTML = resultMarkup(result);
    if (result.valid) {
      button.hidden = true;
      message("Successful verification was recorded.");
    }
  }, "click");
}
async function route() {
  message("");
  if (location.pathname === "/verify") {
    publicVerify(); return;
  }
  try {
    const data = await api("/dashboard");
    logout.hidden = false;
    const match = location.pathname.match(/^\/share\/([0-9a-f]{64})$/);
    if (match) share(data, match[1]); else await dashboard(data);
  } catch (err) {
    if (err.status === 401) {
      logout.hidden = true; landing();
      if (location.pathname.startsWith("/share/")) message("Sign in with the designated auditor account to open this share.");
    } else {
      show("<h1>Service unavailable</h1>");
      message(err.message, true);
    }
  }
}
route();

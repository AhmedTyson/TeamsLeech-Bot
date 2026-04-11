"""
Dashboard HTML Generator.

Regenerates docs/index.html with an updated terminal-style dashboard UI.
Preserves the existing GIST_ID and GIST_READ_TOKEN values from the
current index.html so dynamic credentials are not lost on regeneration.

Usage
-----
    python scripts/redesign_minimal.py
"""

import os
import re

FILE_PATH = os.path.join(os.path.dirname(__file__), "..", "docs", "index.html")

with open(FILE_PATH, "r", encoding="utf-8") as f:
    content = f.read()

gist_id_match = re.search(r'const GIST_ID = "(.*?)";', content)
gist_id = gist_id_match.group(1) if gist_id_match else "PASTE_GIST_ID_HERE"

gist_read_token_match = re.search(r'const GIST_READ_TOKEN = "(.*?)";', content)
gist_read_token = gist_read_token_match.group(1) if gist_read_token_match else "PASTE_GIST_READ_TOKEN_HERE"

NEW_CONTENT = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>TeamsLeech | Terminal</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <style>
    :root {
      --bg: #000000;
      --bg-panel: #0a0a0a;
      --border: #1f1f1f;
      --border-highlight: #333333;
      --accent: #a855f7;
      --accent-glow: rgba(168, 85, 247, 0.15);
      --text: #f4f4f5;
      --text-muted: #a1a1aa;
      --text-dim: #52525b;
      --success: #10b981;
      --warning: #f59e0b;
      --danger: #ef4444;
      --font-ui: "Inter", -apple-system, sans-serif;
      --font-mono: "JetBrains Mono", monospace;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      font-family: var(--font-ui);
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      -webkit-font-smoothing: antialiased;
      background-image: radial-gradient(circle at 50% -20%, var(--accent-glow) 0%, transparent 50%);
    }

    /* ── Unlock Screen ── */
    #unlock-screen {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      width: 100%;
      padding: 24px;
      animation: fadeUp 0.6s cubic-bezier(0.16, 1, 0.3, 1);
    }

    @keyframes fadeUp {
      from { opacity: 0; transform: translateY(20px); }
      to { opacity: 1; transform: translateY(0); }
    }

    .unlock-logo {
      font-size: 40px;
      color: var(--text);
      margin-bottom: 24px;
      position: relative;
    }

    .unlock-logo::after {
      content: "";
      position: absolute;
      top: 50%; left: 50%;
      transform: translate(-50%, -50%);
      width: 60px; height: 60px;
      background: var(--accent);
      filter: blur(40px);
      z-index: -1;
      opacity: 0.3;
    }

    .unlock-form {
      width: 100%;
      max-width: 300px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }

    .input-wrapper { position: relative; }

    .input-icon {
      position: absolute;
      left: 14px; top: 50%;
      transform: translateY(-50%);
      color: var(--text-dim);
      font-size: 13px;
    }

    #master-password {
      width: 100%;
      padding: 12px 14px 12px 38px;
      font-family: var(--font-mono);
      font-size: 13px;
      background: rgba(255,255,255,0.03);
      border: 1px solid var(--border);
      border-radius: 8px;
      color: var(--text);
      outline: none;
      transition: all 0.2s;
    }

    #master-password:focus {
      border-color: var(--accent);
      background: rgba(168, 85, 247, 0.05);
    }

    #master-password:focus + .input-icon { color: var(--accent); }

    .btn {
      border: 1px solid transparent;
      border-radius: 8px;
      padding: 12px 16px;
      font-size: 14px;
      font-weight: 500;
      font-family: var(--font-ui);
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      transition: all 0.2s;
    }

    .btn:active { transform: scale(0.98); }
    .btn:disabled { opacity: 0.5; pointer-events: none; }

    .btn-submit {
      background: var(--text);
      color: var(--bg);
      width: 100%;
    }

    .btn-submit:hover { background: #d4d4d8; }

    .btn-outline {
      background: transparent;
      border-color: var(--border);
      color: var(--text);
    }
    .btn-outline:hover { background: var(--bg-panel); border-color: var(--border-highlight); }

    .btn-danger-outline {
      background: transparent;
      border-color: rgba(239, 68, 68, 0.3);
      color: var(--danger);
    }
    .btn-danger-outline:hover { background: rgba(239, 68, 68, 0.1); border-color: var(--danger); }

    #unlock-error, #biometric-status {
      font-size: 12px;
      text-align: center;
    }
    #unlock-error { color: var(--danger); display: none; }
    #biometric-status { color: var(--text-muted); display: none; margin-top: -4px; min-height: 16px; }

    /* ── Dashboard (Bespoke layout) ── */
    #dashboard {
      display: none;
      width: 100%;
      max-width: 540px;
      padding: 40px 24px 80px;
      animation: fadeUp 0.5s cubic-bezier(0.16, 1, 0.3, 1);
    }

    .top-bar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 40px;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .brand i { color: var(--text); font-size: 20px; }
    .brand-name { font-size: 16px; font-weight: 600; letter-spacing: -0.02em; }
    .brand-badge {
      font-family: var(--font-mono);
      font-size: 10px;
      padding: 2px 6px;
      background: var(--bg-panel);
      border: 1px solid var(--border);
      border-radius: 4px;
      color: var(--text-muted);
    }

    .lock-btn {
      background: transparent;
      border: none;
      color: var(--text-dim);
      font-size: 14px;
      cursor: pointer;
      transition: color 0.2s;
    }
    .lock-btn:hover { color: var(--text); }

    /* Layout Sections */
    .section {
      margin-bottom: 32px;
    }

    .section-title {
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: var(--text-dim);
      font-weight: 600;
      margin-bottom: 16px;
      display: flex;
      align-items: center;
      gap: 8px;
    }

    /* Terminal-style status block */
    .status-block {
      background: var(--bg-panel);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 20px;
      font-family: var(--font-mono);
    }

    .status-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 16px;
    }

    .status-indicator {
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .pulse-dot {
      width: 8px; height: 8px;
      border-radius: 50%;
    }
    .dot-grey { background: var(--text-dim); }
    .dot-green { background: var(--success); box-shadow: 0 0 10px rgba(16,185,129,0.4); }
    .dot-yellow { background: var(--warning); box-shadow: 0 0 10px rgba(245,158,11,0.4); animation: blink 1.5s infinite; }
    .dot-red { background: var(--danger); box-shadow: 0 0 10px rgba(239,68,68,0.4); }
    
    @keyframes blink { 0% { opacity: 0.4; } 50% { opacity: 1; } 100% { opacity: 0.4; } }

    .status-label { font-size: 13px; color: var(--text); }
    .status-time { font-size: 11px; color: var(--text-dim); }

    .status-logs {
      font-size: 12px;
      color: var(--text-muted);
      border-top: 1px dashed var(--border);
      padding-top: 16px;
      line-height: 1.6;
    }

    .log-line { display: flex; gap: 12px; }
    .log-prefix { color: var(--accent); user-select: none; }

    /* Action block (Execution) */
    .action-block {
      display: flex;
      gap: 12px;
    }

    #control-area { flex: 1; }

    /* Resource tracking (Usage) */
    .metric-group {
      display: flex;
      justify-content: space-between;
      align-items: flex-end;
      margin-bottom: 12px;
    }

    .metric-val {
      font-family: var(--font-mono);
      font-size: 24px;
      color: var(--text);
      line-height: 1;
    }
    .metric-val span { font-size: 12px; color: var(--text-dim); margin-left: 4px; }

    .track { width: 100%; height: 4px; background: var(--bg-panel); border-radius: 2px; overflow: hidden; }
    .fill { height: 100%; width: 0%; background: var(--text); transition: width 0.8s ease; }
    .fill.warn { background: var(--warning); }
    .fill.danger { background: var(--danger); }

    .error-toast {
      display: none;
      font-size: 12px;
      color: var(--danger);
      background: rgba(239, 68, 68, 0.1);
      padding: 8px 12px;
      border-radius: 6px;
      border: 1px solid rgba(239, 68, 68, 0.2);
      margin-top: 12px;
    }

  </style>
</head>
<body>

  <!-- ── Unlock Screen ── -->
  <div id="unlock-screen">
    <div class="unlock-logo"><i class="fa-solid fa-code-branch"></i></div>
    <div class="unlock-form">
      <div class="input-wrapper">
        <input type="password" id="master-password" autocomplete="current-password" placeholder="Enter master key">
        <i class="fa-solid fa-key input-icon"></i>
      </div>
      <p id="biometric-status"></p>
      <button class="btn btn-submit" id="unlock-btn" type="button">Access Console</button>
      <div id="unlock-error">Authentication failed</div>
    </div>
  </div>

  <!-- ── Dashboard ── -->
  <div id="dashboard">
    <div class="top-bar">
      <div class="brand">
        <i class="fa-solid fa-code-branch"></i>
        <div class="brand-name">TeamsLeech</div>
        <div class="brand-badge">PROD</div>
      </div>
      <button class="lock-btn" id="lock-btn" title="Lock Session"><i class="fa-solid fa-power-off"></i></button>
    </div>

    <!-- Section: Telemetry -->
    <div class="section">
      <div class="section-title"><i class="fa-solid fa-satellite-dish"></i> Telemetry</div>
      <div class="status-block">
        <div class="status-header">
          <div class="status-indicator">
            <div class="pulse-dot dot-grey" id="status-dot"></div>
            <span class="status-label" id="status-text">Connecting...</span>
          </div>
          <span class="status-time" id="status-time"></span>
        </div>
        <div class="status-logs">
          <div class="log-line"><span class="log-prefix">~</span><span id="log-msg">Awaiting workflow heartbeat.</span></div>
        </div>
        <div class="error-toast" id="status-auth-error">Authentication rejected by GitHub endpoint.</div>
      </div>
    </div>

    <!-- Section: Execution -->
    <div class="section">
      <div class="section-title"><i class="fa-solid fa-terminal"></i> Workflow Control</div>
      <div class="action-block">
        <div id="control-area" style="width: 100%;">
          <button class="btn btn-outline" style="width: 100%;" id="run-btn" type="button"><i class="fa-solid fa-play"></i> Initialize Run</button>
        </div>
      </div>
      <div class="error-toast" id="control-error"></div>
    </div>

    <!-- Section: Quota -->
    <div class="section">
      <div class="section-title"><i class="fa-solid fa-server"></i> Compute Quota</div>
      <div class="metric-group">
        <div class="metric-val" id="usage-text">--<span>/ 2000m</span></div>
      </div>
      <div class="track"><div class="fill" id="usage-bar"></div></div>
      <div class="error-toast" id="usage-auth-error">Quota endpoint unreachable.</div>
    </div>
  </div>

  <script>
    const GIST_ID = "{gist_id}";
    const GIST_READ_TOKEN = "{gist_read_token}";
    // Replace with your own GitHub username/repo after forking
    const REPO = "PASTE_YOUR_VALUE_HERE";
    const WORKFLOW_FILE = "workflow.yml";

    let gh_pat = null, bot_token = null, chat_id = null;
    let currentRunId = null, statusInterval = null, usageInterval = null;

    const $ = id => document.getElementById(id);
    const unlockScreen = $("unlock-screen"), dashboard = $("dashboard");
    const passwordInput = $("master-password"), unlockBtn = $("unlock-btn");
    const unlockError = $("unlock-error"), biometricStatus = $("biometric-status");
    
    // UI elements
    const statusDot = $("status-dot"), statusText = $("status-text");
    const statusTime = $("status-time"), logMsg = $("log-msg");
    const statusAuthErr = $("status-auth-error");
    const controlArea = $("control-area"), controlError = $("control-error");
    const usageText = $("usage-text"), usageBar = $("usage-bar"), usageAuthErr = $("usage-auth-error");

    function b64ToBytes(b64) { const bin=atob(b64); const arr=new Uint8Array(bin.length); for(let i=0;i<bin.length;i++) arr[i]=bin.charCodeAt(i); return arr; }
    function bytesToB64(uint8) { let bin=""; for(let i=0;i<uint8.length;i++) bin+=String.fromCharCode(uint8[i]); return btoa(bin); }

    async function registerBiometric() {
      if(!navigator.credentials || localStorage.getItem("webauthn_registered")==="true") return;
      try {
        const cred = await navigator.credentials.create({
          publicKey: { challenge: crypto.getRandomValues(new Uint8Array(32)), rp: {name:"TeamsLeech"}, user: {id:crypto.getRandomValues(new Uint8Array(16)),name:"owner",displayName:"Owner"}, pubKeyCredParams: [{type:"public-key",alg:-7},{type:"public-key",alg:-257}], authenticatorSelection: {authenticatorAttachment:"platform",userVerification:"required",residentKey:"discouraged"}, timeout: 60000}
        });
        localStorage.setItem("webauthn_registered","true");
        localStorage.setItem("webauthn_cred_id",bytesToB64(new Uint8Array(cred.rawId)));
      } catch(e) {}
    }

    async function verifyBiometric() {
      const storedId = localStorage.getItem("webauthn_cred_id");
      if(!storedId) return false;
      try {
        await navigator.credentials.get({ publicKey: { challenge: crypto.getRandomValues(new Uint8Array(32)), allowCredentials: [{id:b64ToBytes(storedId),type:"public-key"}], userVerification:"required", timeout:60000 } });
        return true;
      } catch(e) { return false; }
    }

    unlockBtn.addEventListener("click", handleUnlock);
    passwordInput.addEventListener("keydown", e => { if (e.key === "Enter") handleUnlock(); });

    async function handleUnlock() {
      const pwd = passwordInput.value;
      if (!pwd) return;

      unlockBtn.disabled = true; unlockBtn.textContent = "Authenticating..."; unlockError.style.display = "none";

      if (navigator.credentials && localStorage.getItem("webauthn_registered") === "true") {
        biometricStatus.textContent = "Tap sensor to proceed"; biometricStatus.style.display = "block";
        const ok = await verifyBiometric();
        biometricStatus.style.display = "none";
        if (!ok) { unlockError.textContent = "Biometric required"; unlockError.style.display="block"; unlockBtn.disabled=false; unlockBtn.textContent="Access Console"; return; }
      }

      try {
        let res;
        try { res = await fetch(`https://api.github.com/gists/${GIST_ID}`, { headers: {"Authorization": `token ${GIST_READ_TOKEN}`} }); } 
        catch(e) { throw new Error("Network"); }
        if(!res.ok) throw new Error("HTTP"+res.status);
        
        const data = await res.json();
        const creds = JSON.parse(data.files["teamsleech_credentials.json"].content);
        const salt=b64ToBytes(creds.salt), iv=b64ToBytes(creds.iv), cipher=b64ToBytes(creds.ciphertext);
        const keyMat = await crypto.subtle.importKey("raw", new TextEncoder().encode(pwd), "PBKDF2", false, ["deriveKey"]);
        const aesKey = await crypto.subtle.deriveKey({name:"PBKDF2",hash:"SHA-256",salt,iterations:310000}, keyMat, {name:"AES-GCM",length:256}, false, ["decrypt"]);
        const dec = await crypto.subtle.decrypt({name:"AES-GCM",iv}, aesKey, cipher);
        const dict = JSON.parse(new TextDecoder().decode(dec));

        gh_pat = dict.gh_pat; bot_token = dict.bot_token; chat_id = dict.chat_id;
        
        await registerBiometric();
        unlockScreen.style.display="none"; dashboard.style.display="block";
        passwordInput.value=""; unlockBtn.disabled=false; unlockBtn.textContent="Access Console";
        
        pollStatus(); pollUsage();
        statusInterval = setInterval(pollStatus, 10000); usageInterval = setInterval(pollUsage, 300000);
      } catch(err) {
        unlockError.textContent = "Access Denied"; unlockError.style.display="block";
        passwordInput.value=""; unlockBtn.disabled=false; unlockBtn.textContent="Access Console";
      }
    }

    $("lock-btn").addEventListener("click", () => {
      gh_pat=null; bot_token=null; chat_id=null;
      clearInterval(statusInterval); clearInterval(usageInterval);
      dashboard.style.display="none"; unlockScreen.style.display="flex";
      passwordInput.value=""; passwordInput.focus();
    });

    async function pollStatus() {
      if(!gh_pat) return;
      try {
        const res = await fetch(`https://api.github.com/repos/${REPO}/actions/runs?per_page=1`, { headers: {"Authorization": `token ${gh_pat}`} });
        if(res.status===401) { statusAuthErr.style.display="block"; return; }
        if(!res.ok) return;
        const data = await res.json();
        if(!data.workflow_runs || data.workflow_runs.length===0) {
          statusDot.className="pulse-dot dot-grey"; statusText.textContent="SYSTEM IDLE";
          logMsg.textContent = "No workflow history found.";
          renderBtn(false); return;
        }

        const run = data.workflow_runs[0]; currentRunId = run.id;
        const active = (run.status==="in_progress" || run.status==="queued");

        if(active) { statusDot.className="pulse-dot dot-yellow"; statusText.textContent="EXECUTING"; logMsg.textContent="Workflow is actively running in Github Actions."; }
        else if(run.conclusion==="success") { statusDot.className="pulse-dot dot-green"; statusText.textContent="COMPLETED"; logMsg.textContent="Last execution finished successfully."; }
        // THE FIX YOU ASKED FOR: Separate "cancelled" from "failure"
        else if(run.conclusion==="cancelled") { statusDot.className="pulse-dot dot-grey"; statusText.textContent="CANCELLED"; logMsg.textContent="Last execution was manually aborted."; }
        else { statusDot.className="pulse-dot dot-red"; statusText.textContent="FAILED"; logMsg.textContent=`Workflow terminated with error state: ${run.conclusion}`; }
        
        statusTime.textContent = new Date(run.updated_at||run.created_at).toLocaleTimeString();
        renderBtn(active);
      } catch(e){}
    }

    function renderBtn(active) {
      if(active) {
        controlArea.innerHTML = `<button class="btn btn-danger-outline" style="width: 100%;" id="cancel-btn" type="button"><i class="fa-solid fa-stop"></i> Abort Execution</button>`;
        $("cancel-btn").addEventListener("click", cancelRun);
      } else {
        controlArea.innerHTML = `<button class="btn btn-outline" style="width: 100%;" id="run-btn" type="button"><i class="fa-solid fa-terminal"></i> Initialize Run</button>`;
        $("run-btn").addEventListener("click", startRun);
      }
      controlError.style.display="none";
    }

    async function startRun() {
      const b=$("run-btn"); if(!b||!gh_pat) return;
      b.disabled=true; b.innerHTML='<i class="fa-solid fa-spinner fa-spin"></i> Triggering...'; controlError.style.display="none";
      try {
        const res=await fetch(`https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW_FILE}/dispatches`, {method:"POST",headers:{"Authorization":`token ${gh_pat}`,"Accept":"application/vnd.github.v3+json"},body:JSON.stringify({ref:"main",inputs:{mode:"normal"}})});
        if(!res.ok) throw new Error("API Error");
        setTimeout(()=>{ b.disabled=false; b.innerHTML='<i class="fa-solid fa-terminal"></i> Initialize Run'; pollStatus(); }, 3000);
      } catch(e) { controlError.textContent="Failed to trigger remote dispatch."; controlError.style.display="block"; b.disabled=false; b.innerHTML='<i class="fa-solid fa-terminal"></i> Initialize Run'; }
    }

    async function cancelRun() {
      const b=$("cancel-btn"); if(!b||!gh_pat||!currentRunId) return;
      b.disabled=true; b.innerHTML='<i class="fa-solid fa-spinner fa-spin"></i> Aborting...'; controlError.style.display="none";
      try {
        const res=await fetch(`https://api.github.com/repos/${REPO}/actions/runs/${currentRunId}/cancel`, {method:"POST",headers:{"Authorization":`token ${gh_pat}`,"Accept":"application/vnd.github.v3+json"}});
        if(!res.ok) throw new Error("API");
        setTimeout(pollStatus, 3000);
      } catch(e) { controlError.textContent="Failed to send abort signal."; controlError.style.display="block"; b.disabled=false; b.innerHTML='<i class="fa-solid fa-stop"></i> Abort Execution'; }
    }

    async function pollUsage() {
      if(!gh_pat) return;
      try {
        let u=null;
        const bRes=await fetch(`https://api.github.com/repos/${REPO}/actions/billing`,{headers:{"Authorization":`token ${gh_pat}`}});
        if(bRes.ok) { let dat=await bRes.json(); if(dat.total_minutes_used!==undefined) u=Math.round(dat.total_minutes_used); }
        if(u!==null) {
          usageText.innerHTML = `${u}<span>/ 2000m</span>`;
          const p = Math.min((u/2000)*100,100); usageBar.style.width=p+"%";
          usageBar.className = "fill" + (u>1800?" danger": u>1500?" warn":"");
        }
      } catch(e){}
    }
  </script>
</body>
</html>
"""

final = NEW_CONTENT.replace("{gist_id}", gist_id).replace("{gist_read_token}", gist_read_token)

with open(FILE_PATH, "w", encoding="utf-8") as f:
    f.write(final)

print("Applied ultra-minimalist custom styling and fixed status logic.")

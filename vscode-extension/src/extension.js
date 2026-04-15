'use strict';

const vscode = require('vscode');
const { exec, spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const https = require('https');
const http = require('http');

let outputChannel;
let statusBarItem;
let sidebarProvider;
let extensionContext;

// ─── Backend & License ────────────────────────────────────────────────────────

const BACKEND_URL = 'https://testpilot-backend-production.up.railway.app';
const FREE_MONTHLY_LIMIT = 20;
const GUMROAD_PRODUCT_ID = 'testpilot-ai-pro';

// ─── License state ────────────────────────────────────────────────────────────

async function getLicenseState() {
  const key = vscode.workspace.getConfiguration('testpilot').get('licenseKey', '').trim();
  if (!key) return { plan: 'free' };

  const cached = extensionContext.globalState.get('licenseCache');
  if (cached && cached.key === key && Date.now() - cached.ts < 86400000) {
    return cached.state;
  }

  try {
    const result = await gumroadVerify(key);
    const state = result.success
      ? { plan: 'pro', email: result.purchase?.email }
      : { plan: 'free', error: 'Invalid license key' };
    extensionContext.globalState.update('licenseCache', { key, ts: Date.now(), state });
    return state;
  } catch {
    return { plan: 'free', error: 'Could not verify license (offline?)' };
  }
}

function gumroadVerify(licenseKey) {
  return new Promise((resolve, reject) => {
    const body = `product_permalink=${GUMROAD_PRODUCT_ID}&license_key=${encodeURIComponent(licenseKey)}`;
    const req = https.request({
      hostname: 'api.gumroad.com',
      path: '/v2/licenses/verify',
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Content-Length': Buffer.byteLength(body)
      }
    }, res => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => { try { resolve(JSON.parse(data)); } catch { reject(new Error('Bad response')); } });
    });
    req.on('error', reject);
    req.write(body);
    req.end();
  });
}

function getUsageThisMonth() {
  const usage = extensionContext.globalState.get('usageLog', {});
  const month = new Date().toISOString().slice(0, 7);
  return usage[month] || 0;
}

function incrementUsage() {
  const usage = extensionContext.globalState.get('usageLog', {});
  const month = new Date().toISOString().slice(0, 7);
  usage[month] = (usage[month] || 0) + 1;
  const keys = Object.keys(usage).sort();
  if (keys.length > 3) delete usage[keys[0]];
  extensionContext.globalState.update('usageLog', usage);
  return usage[month];
}

async function checkGenerationQuota() {
  const license = await getLicenseState();
  if (license.plan === 'pro') return { allowed: true, plan: 'pro' };

  const used = getUsageThisMonth();
  if (used >= FREE_MONTHLY_LIMIT) {
    const action = await vscode.window.showWarningMessage(
      `TestPilot Free: ${used}/${FREE_MONTHLY_LIMIT} generations used this month.`,
      'Upgrade to Pro ($4.99/mo)',
      'Enter License Key'
    );
    if (action === 'Upgrade to Pro ($4.99/mo)') {
      vscode.env.openExternal(vscode.Uri.parse('https://classy5b.gumroad.com/l/testpilot-ai-pro'));
    } else if (action === 'Enter License Key') {
      vscode.commands.executeCommand('testpilot.enterLicense');
    }
    return { allowed: false };
  }
  return { allowed: true, plan: 'free', used, remaining: FREE_MONTHLY_LIMIT - used };
}

// ─── Activation ──────────────────────────────────────────────────────────────

function activate(context) {
  extensionContext = context;
  outputChannel = vscode.window.createOutputChannel('TestPilot AI');
  statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
  statusBarItem.command = 'testpilot.showPanel';
  statusBarItem.text = '$(beaker) TestPilot';
  statusBarItem.tooltip = 'TestPilot AI — Click to open dashboard';
  statusBarItem.show();

  sidebarProvider = new TestPilotSidebarProvider(context.extensionUri);

  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider('testpilot.sidebarView', sidebarProvider)
  );

  const commands = [
    ['testpilot.generateForFile',  () => generateForCurrentFile()],
    ['testpilot.generateForDiff',  () => generateForDiffWithQuota()],
    ['testpilot.runAll',           () => runTests('run', 'Running all tests...')],
    ['testpilot.runSolr',          () => runTests('solr', 'Running SOLR validation...')],
    ['testpilot.runReact',         () => runTests('react', 'Running React E2E...')],
    ['testpilot.setup',            () => setupProject()],
    ['testpilot.openConfig',       () => openConfig()],
    ['testpilot.showPanel',        () => sidebarProvider.focus()],
    ['testpilot.enterLicense',     () => enterLicense()],
    ['testpilot.showPlan',         () => showPlanStatus()],
  ];

  commands.forEach(([cmd, fn]) =>
    context.subscriptions.push(vscode.commands.registerCommand(cmd, fn))
  );

  context.subscriptions.push(
    vscode.workspace.onDidSaveTextDocument((doc) => {
      const cfg = vscode.workspace.getConfiguration('testpilot');
      if (cfg.get('autoGenOnSave') && doc.languageId === 'python') {
        generateForFileWithQuota(doc.uri.fsPath);
      }
    })
  );

  updateStatusBarPlan();
}

// ─── Status bar ──────────────────────────────────────────────────────────────

async function updateStatusBarPlan() {
  const license = await getLicenseState();
  if (license.plan === 'pro') {
    statusBarItem.text = '$(beaker) TestPilot Pro';
    statusBarItem.tooltip = 'TestPilot AI Pro — Unlimited generations';
  } else {
    const used = getUsageThisMonth();
    statusBarItem.text = `$(beaker) TestPilot (${used}/${FREE_MONTHLY_LIMIT})`;
    statusBarItem.tooltip = `TestPilot AI Free — ${used}/${FREE_MONTHLY_LIMIT} this month`;
  }
}

function setStatus(state, text) {
  const icons = { running: '$(sync~spin)', pass: '$(check)', fail: '$(error)', idle: '$(beaker)' };
  statusBarItem.text = `${icons[state] || '$(beaker)'} TestPilot${text ? ` — ${text}` : ''}`;
  statusBarItem.backgroundColor = state === 'fail'
    ? new vscode.ThemeColor('statusBarItem.errorBackground')
    : undefined;
}

// ─── License UI ──────────────────────────────────────────────────────────────

async function enterLicense() {
  const key = await vscode.window.showInputBox({
    prompt: 'Enter your TestPilot AI Pro license key',
    placeHolder: 'XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX',
    ignoreFocusOut: true
  });
  if (!key) return;

  vscode.window.withProgress({ location: vscode.ProgressLocation.Notification, title: 'Verifying license...' }, async () => {
    await vscode.workspace.getConfiguration('testpilot').update('licenseKey', key.trim(), vscode.ConfigurationTarget.Global);
    extensionContext.globalState.update('licenseCache', null);
    const state = await getLicenseState();
    if (state.plan === 'pro') {
      vscode.window.showInformationMessage(`✅ TestPilot AI Pro activated! ${state.email ? 'Welcome, ' + state.email : ''}`);
      updateStatusBarPlan();
    } else {
      vscode.window.showErrorMessage('Invalid license key. Get one at gumroad.com/l/testpilot-ai-pro');
    }
  });
}

async function showPlanStatus() {
  const license = await getLicenseState();
  const used = getUsageThisMonth();
  if (license.plan === 'pro') {
    vscode.window.showInformationMessage('TestPilot AI Pro — Unlimited generations active ✅');
  } else {
    const action = await vscode.window.showInformationMessage(
      `TestPilot AI Free — ${used}/${FREE_MONTHLY_LIMIT} generations used this month.`,
      'Upgrade to Pro ($4.99/mo)'
    );
    if (action === 'Upgrade to Pro ($4.99/mo)') {
      vscode.env.openExternal(vscode.Uri.parse('https://classy5b.gumroad.com/l/testpilot-ai-pro'));
    }
  }
}

// ─── AI Test Generation (Cloud API) ──────────────────────────────────────────

async function generateForCurrentFile() {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    vscode.window.showErrorMessage('TestPilot: Open a Python file first');
    return;
  }
  if (editor.document.languageId !== 'python') {
    vscode.window.showErrorMessage('TestPilot: Only works on Python files');
    return;
  }
  await generateForFileWithQuota(editor.document.uri.fsPath);
}

async function generateForFileWithQuota(filePath) {
  const quota = await checkGenerationQuota();
  if (!quota.allowed) return;
  await generateForFile(filePath);
}

async function generateForFile(filePath) {
  const rel = vscode.workspace.asRelativePath(filePath);
  const filename = path.basename(filePath);

  let code;
  try {
    code = fs.readFileSync(filePath, 'utf8');
  } catch (e) {
    vscode.window.showErrorMessage(`TestPilot: Cannot read file — ${e.message}`);
    return;
  }

  if (!code.trim()) {
    vscode.window.showWarningMessage('TestPilot: File is empty, nothing to test.');
    return;
  }

  setStatus('running', `Generating tests for ${filename}...`);
  sidebarProvider?.setRunning(`Generating tests for ${filename}...`);
  outputChannel.show(true);
  outputChannel.appendLine(`\n${'─'.repeat(60)}`);
  outputChannel.appendLine(`✨ Generating tests for: ${rel}`);
  outputChannel.appendLine(`${'─'.repeat(60)}`);

  const licenseKey = vscode.workspace.getConfiguration('testpilot').get('licenseKey', '').trim();
  const machineId = vscode.env.machineId;

  try {
    const result = await callBackend('/generate', {
      code,
      filename,
      machine_id: machineId,
      license_key: licenseKey,
    });

    // Update local usage counter from server response
    if (result.used !== undefined) {
      const usage = extensionContext.globalState.get('usageLog', {});
      const month = new Date().toISOString().slice(0, 7);
      usage[month] = result.used;
      extensionContext.globalState.update('usageLog', usage);
    }

    // Write test file
    const testFileName = result.test_filename || `test_ai_${filename}`;
    const testDir = path.join(getWorkspaceRoot(), 'tests', 'ai_generated');
    if (!fs.existsSync(testDir)) fs.mkdirSync(testDir, { recursive: true });

    // Ensure __init__.py exists
    const initPath = path.join(getWorkspaceRoot(), 'tests', '__init__.py');
    const initPathInner = path.join(testDir, '__init__.py');
    if (!fs.existsSync(initPath)) fs.writeFileSync(initPath, '', 'utf8');
    if (!fs.existsSync(initPathInner)) fs.writeFileSync(initPathInner, '', 'utf8');

    const testFilePath = path.join(testDir, testFileName);
    fs.writeFileSync(testFilePath, result.tests, 'utf8');

    setStatus('pass', `Tests generated`);
    updateStatusBarPlan();
    sidebarProvider?.setResult(true, 'Tests generated ✅', result.tests);
    outputChannel.appendLine(result.tests);
    outputChannel.appendLine(`\n✅ Written to: tests/ai_generated/${testFileName}`);

    const remaining = result.plan === 'pro' ? '∞' : `${FREE_MONTHLY_LIMIT - result.used} left`;
    const action = await vscode.window.showInformationMessage(
      `TestPilot: Tests generated → ${testFileName} (${remaining} this month)`,
      'Open File'
    );
    if (action === 'Open File') {
      const doc = await vscode.workspace.openTextDocument(testFilePath);
      vscode.window.showTextDocument(doc);
    }

  } catch (err) {
    setStatus('fail', 'Generation failed');
    sidebarProvider?.setResult(false, 'Generation failed', err.message);
    outputChannel.appendLine(`❌ Error: ${err.message}`);

    if (err.status === 429) {
      // Quota exceeded — prompt upgrade
      const action = await vscode.window.showWarningMessage(
        `TestPilot: ${err.message}`,
        'Upgrade to Pro ($4.99/mo)',
        'Enter License Key'
      );
      if (action === 'Upgrade to Pro ($4.99/mo)') {
        vscode.env.openExternal(vscode.Uri.parse('https://classy5b.gumroad.com/l/testpilot-ai-pro'));
      } else if (action === 'Enter License Key') {
        vscode.commands.executeCommand('testpilot.enterLicense');
      }
    } else {
      vscode.window.showErrorMessage(`TestPilot: ${err.message}`);
    }
  }
}

// Git diff mode — find changed Python files, generate for each
async function generateForDiffWithQuota() {
  const quota = await checkGenerationQuota();
  if (!quota.allowed) return;

  const root = getWorkspaceRoot();
  if (!root) {
    vscode.window.showErrorMessage('TestPilot: Open a workspace folder first');
    return;
  }

  exec('git diff --name-only HEAD~1 HEAD', { cwd: root }, async (err, stdout) => {
    if (err) {
      // Try staged files if HEAD~1 fails (e.g. first commit)
      exec('git diff --name-only --cached', { cwd: root }, async (err2, stdout2) => {
        if (err2) {
          vscode.window.showErrorMessage('TestPilot: Could not get git diff. Is this a git repo?');
          return;
        }
        await processChangedFiles(stdout2, root);
      });
      return;
    }
    await processChangedFiles(stdout, root);
  });
}

async function processChangedFiles(stdout, root) {
  const files = stdout.split('\n')
    .map(f => f.trim())
    .filter(f => f.endsWith('.py') && !f.includes('test_'))
    .map(f => path.join(root, f))
    .filter(f => fs.existsSync(f));

  if (files.length === 0) {
    vscode.window.showInformationMessage('TestPilot: No changed Python files found.');
    return;
  }

  vscode.window.showInformationMessage(`TestPilot: Generating tests for ${files.length} changed file(s)...`);
  for (const file of files) {
    await generateForFile(file);
  }
}

// ─── HTTP helper ─────────────────────────────────────────────────────────────

function callBackend(endpoint, body) {
  return new Promise((resolve, reject) => {
    const payload = JSON.stringify(body);
    const url = new URL(BACKEND_URL + endpoint);
    const isHttps = url.protocol === 'https:';
    const lib = isHttps ? https : http;

    const options = {
      hostname: url.hostname,
      port: url.port || (isHttps ? 443 : 80),
      path: url.pathname,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(payload),
      },
    };

    const req = lib.request(options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try {
          const parsed = JSON.parse(data);
          if (res.statusCode >= 400) {
            const err = new Error(parsed.detail || `Server error ${res.statusCode}`);
            err.status = res.statusCode;
            reject(err);
          } else {
            resolve(parsed);
          }
        } catch {
          reject(new Error('Invalid response from server'));
        }
      });
    });

    req.on('error', (e) => reject(new Error(`Network error: ${e.message}`)));
    req.setTimeout(60000, () => { req.destroy(); reject(new Error('Request timed out (60s)')); });
    req.write(payload);
    req.end();
  });
}

// ─── Test runner (local pytest) ───────────────────────────────────────────────

function getPython() {
  const cfg = vscode.workspace.getConfiguration('testpilot');
  const configured = cfg.get('pythonPath');
  if (configured && configured !== 'python') return configured;
  const pythonExt = vscode.extensions.getExtension('ms-python.python');
  if (pythonExt && pythonExt.isActive) {
    const interpreter = pythonExt.exports?.settings?.getExecutionDetails?.()?.execCommand?.[0];
    if (interpreter) return interpreter;
  }
  return 'python';
}

function getWorkspaceRoot() {
  return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || '';
}

function runTests(args, label) {
  const python = getPython();
  const cwd = getWorkspaceRoot();

  outputChannel.show(true);
  outputChannel.appendLine(`\n${'─'.repeat(60)}`);
  outputChannel.appendLine(`▶ ${label}`);
  outputChannel.appendLine(`${'─'.repeat(60)}`);

  setStatus('running', label);
  sidebarProvider?.setRunning(label);

  // For 'run', use pytest directly on the generated tests folder
  let spawnArgs;
  if (args === 'run') {
    spawnArgs = ['-m', 'pytest', 'tests/ai_generated', '-v', '--tb=short'];
  } else if (args === 'solr') {
    spawnArgs = ['-m', 'testpilot', 'solr'];
  } else if (args === 'react') {
    spawnArgs = ['-m', 'testpilot', 'react'];
  } else {
    spawnArgs = ['-m', 'testpilot', ...args.split(' ')];
  }

  const proc = spawn(python, spawnArgs, { cwd, shell: true, env: { ...process.env } });

  let output = '';
  proc.stdout.on('data', (data) => {
    const text = data.toString();
    output += text;
    outputChannel.append(text);
    sidebarProvider?.appendOutput(text);
  });
  proc.stderr.on('data', (data) => {
    const text = data.toString();
    output += text;
    outputChannel.append(text);
  });

  proc.on('close', (code) => {
    const success = code === 0;
    const summary = parseSummary(output);
    setStatus(success ? 'pass' : 'fail', summary);
    sidebarProvider?.setResult(success, summary, output);

    if (!success) {
      vscode.window.showWarningMessage(
        `TestPilot: ${summary || 'Tests failed'}`, 'Show Output'
      ).then(a => { if (a === 'Show Output') outputChannel.show(); });
    } else {
      vscode.window.showInformationMessage(`TestPilot: ${summary || '✅ All passed'}`);
    }
  });
}

function parseSummary(output) {
  const lines = output.split('\n').reverse();
  for (const line of lines) {
    if (/\d+ passed/.test(line) || /\d+ failed/.test(line)) {
      return line.trim().replace(/\x1b\[[0-9;]*m/g, '');
    }
  }
  return '';
}

// ─── Setup (simplified — no API key needed) ──────────────────────────────────

async function setupProject() {
  const root = getWorkspaceRoot();
  if (!root) {
    vscode.window.showErrorMessage('TestPilot: Open a workspace folder first');
    return;
  }

  // Create tests/ai_generated directory
  const testDir = path.join(root, 'tests', 'ai_generated');
  if (!fs.existsSync(testDir)) {
    fs.mkdirSync(testDir, { recursive: true });
    fs.writeFileSync(path.join(root, 'tests', '__init__.py'), '', 'utf8');
    fs.writeFileSync(path.join(testDir, '__init__.py'), '', 'utf8');
  }

  vscode.window.showInformationMessage(
    'TestPilot AI is ready! Right-click any Python file → "Generate Tests". No setup needed.',
    'Got it'
  );
}

async function openConfig() {
  vscode.window.showInformationMessage(
    'TestPilot AI v0.3.0 needs no config file. Just right-click a .py file → Generate Tests!',
    'Open Settings'
  ).then(a => {
    if (a === 'Open Settings') vscode.commands.executeCommand('workbench.action.openSettings', 'testpilot');
  });
}

// ─── Sidebar ─────────────────────────────────────────────────────────────────

class TestPilotSidebarProvider {
  constructor(extensionUri) {
    this.extensionUri = extensionUri;
    this._view = null;
  }

  focus() { if (this._view) this._view.show(true); }

  resolveWebviewView(webviewView) {
    this._view = webviewView;
    webviewView.webview.options = { enableScripts: true };
    webviewView.webview.html = this._getHtml();

    webviewView.webview.onDidReceiveMessage(msg => {
      const map = {
        runAll: 'testpilot.runAll',
        generateForDiff: 'testpilot.generateForDiff',
        runSolr: 'testpilot.runSolr',
        runReact: 'testpilot.runReact',
        showPlan: 'testpilot.showPlan',
        enterLicense: 'testpilot.enterLicense',
      };
      if (map[msg.command]) vscode.commands.executeCommand(map[msg.command]);
    });
  }

  setRunning(label) { this._post({ type: 'running', label }); }
  appendOutput(text) { this._post({ type: 'output', text }); }
  setResult(success, summary, fullOutput) { this._post({ type: 'result', success, summary, fullOutput }); }
  _post(msg) { if (this._view) this._view.webview.postMessage(msg); }

  _getHtml() {
    return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: var(--vscode-font-family); font-size: var(--vscode-font-size); color: var(--vscode-foreground); background: var(--vscode-sideBar-background); padding: 12px; }
  h2 { font-size: 13px; font-weight: 600; margin-bottom: 12px; opacity: 0.8; }
  .section { margin-bottom: 14px; }
  .section-title { font-size: 10px; font-weight: 600; opacity: 0.5; text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 5px; }
  button { display: flex; align-items: center; gap: 6px; width: 100%; text-align: left; background: var(--vscode-button-secondaryBackground); color: var(--vscode-button-secondaryForeground); border: 1px solid var(--vscode-button-border, transparent); border-radius: 4px; padding: 6px 10px; cursor: pointer; font-size: 12px; margin-bottom: 4px; transition: background 0.1s; }
  button:hover { background: var(--vscode-button-secondaryHoverBackground); }
  button.primary { background: var(--vscode-button-background); color: var(--vscode-button-foreground); font-weight: 500; }
  button.primary:hover { background: var(--vscode-button-hoverBackground); }
  #status-bar { display: flex; align-items: center; gap: 8px; padding: 8px 10px; border-radius: 4px; background: var(--vscode-editor-inactiveSelectionBackground); margin-bottom: 12px; font-size: 12px; }
  #dot { width: 8px; height: 8px; border-radius: 50%; background: #888; flex-shrink: 0; }
  #dot.pass { background: #4caf50; }
  #dot.fail { background: #f44336; }
  #dot.running { background: #ff9800; animation: pulse 1s infinite; }
  @keyframes pulse { 0%,100%{opacity:1}50%{opacity:.4} }
  #output { background: var(--vscode-terminal-background,#1e1e1e); color: var(--vscode-terminal-foreground,#ccc); font-family: monospace; font-size: 11px; border-radius: 4px; padding: 8px; max-height: 200px; overflow-y: auto; white-space: pre-wrap; word-break: break-all; display: none; margin-top: 8px; }
  .badge { display: inline-block; padding: 2px 6px; border-radius: 10px; font-size: 10px; font-weight: 600; background: var(--vscode-badge-background); color: var(--vscode-badge-foreground); }
</style>
</head>
<body>
<h2>⚗ TestPilot AI</h2>

<div id="status-bar">
  <div id="dot"></div>
  <span id="status-text">Ready</span>
</div>

<div class="section">
  <div class="section-title">Generate Tests</div>
  <button class="primary" onclick="send('generateForDiff')">✨ Changed Files (git diff)</button>
</div>

<div class="section">
  <div class="section-title">Run Tests</div>
  <button class="primary" onclick="send('runAll')">▶ Run All Tests</button>
  <button onclick="send('runSolr')">🗄 SOLR Validation</button>
  <button onclick="send('runReact')">🌐 React E2E</button>
</div>

<div class="section">
  <div class="section-title">Account</div>
  <button onclick="send('showPlan')">👤 View Plan & Usage</button>
  <button onclick="send('enterLicense')">🔑 Enter License Key</button>
</div>

<pre id="output"></pre>

<script>
  const vscode = acquireVsCodeApi();
  const dot = document.getElementById('dot');
  const txt = document.getElementById('status-text');
  const out = document.getElementById('output');
  function send(command) { vscode.postMessage({ command }); }
  window.addEventListener('message', e => {
    const m = e.data;
    if (m.type === 'running') { dot.className='running'; txt.textContent=m.label; out.style.display='block'; out.textContent=''; }
    else if (m.type === 'output') { out.textContent += m.text; out.scrollTop = out.scrollHeight; }
    else if (m.type === 'result') { dot.className = m.success?'pass':'fail'; txt.textContent = m.summary||(m.success?'✅ Done':'❌ Failed'); }
  });
</script>
</body>
</html>`;
  }
}

function deactivate() {}
module.exports = { activate, deactivate };

'use strict';

const vscode = require('vscode');
const { exec, spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const https = require('https');

let outputChannel;
let statusBarItem;
let sidebarProvider;
let extensionContext;

// ─── License & Usage ─────────────────────────────────────────────────────────

const FREE_MONTHLY_LIMIT = 20;
const GUMROAD_PRODUCT_ID = 'testpilot-ai-pro'; // set after Gumroad product created

async function getLicenseState() {
  const key = vscode.workspace.getConfiguration('testpilot').get('licenseKey', '').trim();
  if (!key) return { plan: 'free' };

  // Return cached result if validated within last 24h
  const cached = extensionContext.globalState.get('licenseCache');
  if (cached && cached.key === key && Date.now() - cached.ts < 86400000) {
    return cached.state;
  }

  // Validate against Gumroad license API
  try {
    const result = await gumroadVerify(key);
    const state = result.success ? { plan: 'pro', email: result.purchase?.email } : { plan: 'free', error: 'Invalid license key' };
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
      headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'Content-Length': Buffer.byteLength(body) }
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
  const month = new Date().toISOString().slice(0, 7); // "2026-04"
  return usage[month] || 0;
}

function incrementUsage() {
  const usage = extensionContext.globalState.get('usageLog', {});
  const month = new Date().toISOString().slice(0, 7);
  usage[month] = (usage[month] || 0) + 1;
  // Keep only last 3 months
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
      'Upgrade to Pro',
      'Enter License Key'
    );
    if (action === 'Upgrade to Pro') {
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

  // Register sidebar
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider('testpilot.sidebarView', sidebarProvider)
  );

  // Register commands
  const commands = [
    ['testpilot.generateForFile',  () => generateForCurrentFile()],
    ['testpilot.generateForDiff',  () => generateForDiffWithQuota()],
    ['testpilot.runAll',           () => runTestpilot('run', 'Running all tests...')],
    ['testpilot.runSolr',          () => runTestpilot('solr', 'Running SOLR validation...')],
    ['testpilot.runReact',         () => runTestpilot('react', 'Running React E2E...')],
    ['testpilot.setup',            () => setupProject()],
    ['testpilot.openConfig',       () => openConfig()],
    ['testpilot.showPanel',        () => sidebarProvider.focus()],
    ['testpilot.enterLicense',     () => enterLicense()],
    ['testpilot.showPlan',         () => showPlanStatus()],
  ];

  commands.forEach(([cmd, fn]) =>
    context.subscriptions.push(vscode.commands.registerCommand(cmd, fn))
  );

  // Auto-gen on save (if enabled)
  context.subscriptions.push(
    vscode.workspace.onDidSaveTextDocument((doc) => {
      const cfg = vscode.workspace.getConfiguration('testpilot');
      if (cfg.get('autoGenOnSave') && doc.languageId === 'python') {
        generateForFileWithQuota(doc.uri.fsPath);
      }
    })
  );

  // Check if testpilot is installed
  checkInstallation();

  // Show plan badge on startup
  updateStatusBarPlan();
}

async function updateStatusBarPlan() {
  const license = await getLicenseState();
  if (license.plan === 'pro') {
    statusBarItem.tooltip = 'TestPilot AI Pro — Click to open dashboard';
  } else {
    const used = getUsageThisMonth();
    statusBarItem.tooltip = `TestPilot AI Free (${used}/${FREE_MONTHLY_LIMIT} this month) — Click to open dashboard`;
  }
}

async function enterLicense() {
  const key = await vscode.window.showInputBox({
    prompt: 'Enter your TestPilot AI Pro license key',
    placeHolder: 'XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX',
    ignoreFocusOut: true
  });
  if (!key) return;

  vscode.window.withProgress({ location: vscode.ProgressLocation.Notification, title: 'Verifying license...' }, async () => {
    await vscode.workspace.getConfiguration('testpilot').update('licenseKey', key.trim(), vscode.ConfigurationTarget.Global);
    extensionContext.globalState.update('licenseCache', null); // clear cache
    const state = await getLicenseState();
    if (state.plan === 'pro') {
      vscode.window.showInformationMessage(`TestPilot AI Pro activated! Welcome${state.email ? ', ' + state.email : ''}.`);
      updateStatusBarPlan();
    } else {
      vscode.window.showErrorMessage('License key invalid. Check your key or purchase at gumroad.com/l/testpilot-ai-pro');
    }
  });
}

async function showPlanStatus() {
  const license = await getLicenseState();
  const used = getUsageThisMonth();
  if (license.plan === 'pro') {
    vscode.window.showInformationMessage('TestPilot AI Pro — Unlimited generations active.');
  } else {
    const action = await vscode.window.showInformationMessage(
      `TestPilot AI Free — ${used}/${FREE_MONTHLY_LIMIT} generations used this month.`,
      'Upgrade to Pro'
    );
    if (action === 'Upgrade to Pro') {
      vscode.env.openExternal(vscode.Uri.parse('https://classy5b.gumroad.com/l/testpilot-ai-pro'));
    }
  }
}

// ─── Core runner ─────────────────────────────────────────────────────────────

function getPython() {
  const cfg = vscode.workspace.getConfiguration('testpilot');
  const configured = cfg.get('pythonPath');
  if (configured && configured !== 'python') return configured;

  // Try to use VS Code's active Python interpreter
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

function runTestpilot(args, label, onDone) {
  const python = getPython();
  const cwd = getWorkspaceRoot();
  const cmd = `${python} -m testpilot ${args}`;

  outputChannel.show(true);
  outputChannel.appendLine(`\n${'─'.repeat(60)}`);
  outputChannel.appendLine(`▶ ${label || cmd}`);
  outputChannel.appendLine(`${'─'.repeat(60)}`);

  setStatus('running', label);
  sidebarProvider?.setRunning(label);

  const proc = spawn(python, ['-m', 'testpilot', ...args.split(' ')], {
    cwd,
    shell: true,
    env: { ...process.env }
  });

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
    if (onDone) onDone(success, output);

    if (!success) {
      vscode.window.showWarningMessage(
        `TestPilot: ${summary || 'Tests failed'}`,
        'Show Output'
      ).then(action => {
        if (action === 'Show Output') outputChannel.show();
      });
    } else {
      vscode.window.showInformationMessage(`TestPilot: ${summary || '✅ All passed'}`);
    }
  });
}

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

async function generateForDiffWithQuota() {
  const quota = await checkGenerationQuota();
  if (!quota.allowed) return;
  incrementUsage();
  updateStatusBarPlan();
  runTestpilot('generate --diff HEAD~1', 'Generating tests for changed files...');
}

async function generateForFileWithQuota(filePath) {
  const quota = await checkGenerationQuota();
  if (!quota.allowed) return;
  incrementUsage();
  updateStatusBarPlan();
  generateForFile(filePath);
}

function generateForFile(filePath) {
  const rel = vscode.workspace.asRelativePath(filePath);
  runTestpilot(`generate --source "${filePath}"`, `Generating tests for ${rel}...`, (success) => {
    if (success) {
      // Offer to open the generated test file
      const testFileName = `test_ai_${path.basename(filePath, '.py')}.py`;
      const testDir = path.join(getWorkspaceRoot(), 'tests', 'ai_generated', testFileName);
      if (fs.existsSync(testDir)) {
        vscode.window.showInformationMessage(
          `TestPilot: Tests generated → ${testFileName}`,
          'Open File'
        ).then(action => {
          if (action === 'Open File') {
            vscode.workspace.openTextDocument(testDir).then(doc =>
              vscode.window.showTextDocument(doc)
            );
          }
        });
      }
    }
  });
}

// ─── Setup ───────────────────────────────────────────────────────────────────

async function setupProject() {
  const root = getWorkspaceRoot();
  if (!root) {
    vscode.window.showErrorMessage('TestPilot: Open a workspace folder first');
    return;
  }

  const configPath = path.join(root, 'config.yaml');
  if (fs.existsSync(configPath)) {
    const action = await vscode.window.showInformationMessage(
      'TestPilot: config.yaml already exists. Open it?',
      'Open', 'Cancel'
    );
    if (action === 'Open') openConfig();
    return;
  }

  // Copy config.example.yaml if it exists
  const examplePath = path.join(root, 'config.example.yaml');
  if (fs.existsSync(examplePath)) {
    fs.copyFileSync(examplePath, configPath);
  } else {
    // Write a minimal config
    fs.writeFileSync(configPath, getDefaultConfig(), 'utf8');
  }

  // Create .vscode/tasks.json
  createVSCodeTasks(root);

  // Open config
  const doc = await vscode.workspace.openTextDocument(configPath);
  await vscode.window.showTextDocument(doc);

  vscode.window.showInformationMessage(
    'TestPilot: config.yaml created. Fill in your Anthropic key, Siebel URL, SOLR URL.',
    'Open Install Guide'
  ).then(action => {
    if (action === 'Open Install Guide') {
      const installPath = path.join(root, 'INSTALL.txt');
      if (fs.existsSync(installPath)) {
        vscode.workspace.openTextDocument(installPath).then(doc =>
          vscode.window.showTextDocument(doc)
        );
      }
    }
  });
}

function createVSCodeTasks(root) {
  const vscodePath = path.join(root, '.vscode');
  if (!fs.existsSync(vscodePath)) fs.mkdirSync(vscodePath, { recursive: true });

  const tasksPath = path.join(vscodePath, 'tasks.json');
  if (!fs.existsSync(tasksPath)) {
    fs.writeFileSync(tasksPath, JSON.stringify({
      version: '2.0.0',
      tasks: [
        {
          label: 'TestPilot: Run All Tests',
          type: 'shell',
          command: 'python -m testpilot run',
          group: { kind: 'test', isDefault: true },
          presentation: { reveal: 'always', panel: 'shared' },
          problemMatcher: []
        },
        {
          label: 'TestPilot: Generate Tests for Changed Files',
          type: 'shell',
          command: 'python -m testpilot generate --diff HEAD~1',
          presentation: { reveal: 'always', panel: 'shared' },
          problemMatcher: []
        },
        {
          label: 'TestPilot: SOLR Checks',
          type: 'shell',
          command: 'python -m testpilot solr',
          presentation: { reveal: 'always', panel: 'shared' },
          problemMatcher: []
        }
      ]
    }, null, 2), 'utf8');
  }
}

async function openConfig() {
  const root = getWorkspaceRoot();
  const configPath = path.join(root, 'config.yaml');
  if (!fs.existsSync(configPath)) {
    const action = await vscode.window.showWarningMessage(
      'TestPilot: config.yaml not found. Create it?',
      'Create', 'Cancel'
    );
    if (action === 'Create') setupProject();
    return;
  }
  const doc = await vscode.workspace.openTextDocument(configPath);
  vscode.window.showTextDocument(doc);
}

// ─── Installation check ───────────────────────────────────────────────────────

function checkInstallation() {
  const python = getPython();
  exec(`${python} -m testpilot --help`, (error) => {
    if (error) {
      vscode.window.showWarningMessage(
        'TestPilot AI: Python package not installed.',
        'Install Now',
        'See Instructions'
      ).then(action => {
        if (action === 'Install Now') {
          const terminal = vscode.window.createTerminal('TestPilot Setup');
          terminal.show();
          terminal.sendText('pip install git+https://github.com/saikatpatra-23/testpilot-ai.git');
        } else if (action === 'See Instructions') {
          vscode.env.openExternal(vscode.Uri.parse('https://github.com/saikatpatra-23/testpilot-ai#quickstart-15-minutes'));
        }
      });
    }
  });
}

// ─── Status bar ──────────────────────────────────────────────────────────────

function setStatus(state, text) {
  const icons = { running: '$(sync~spin)', pass: '$(check)', fail: '$(error)', idle: '$(beaker)' };
  statusBarItem.text = `${icons[state] || '$(beaker)'} TestPilot ${text ? `— ${text}` : ''}`;
  statusBarItem.backgroundColor = state === 'fail'
    ? new vscode.ThemeColor('statusBarItem.errorBackground')
    : undefined;
}

function parseSummary(output) {
  const lines = output.split('\n').reverse();
  for (const line of lines) {
    if (/\d+ passed/.test(line) || /\d+ failed/.test(line)) {
      return line.trim().replace(/\x1b\[[0-9;]*m/g, '');
    }
    if (/TOTAL:/.test(line)) return line.replace('TOTAL:', '').trim();
  }
  return '';
}

// ─── Sidebar webview provider ─────────────────────────────────────────────────

class TestPilotSidebarProvider {
  constructor(extensionUri) {
    this.extensionUri = extensionUri;
    this._view = null;
  }

  focus() {
    if (this._view) this._view.show(true);
  }

  resolveWebviewView(webviewView) {
    this._view = webviewView;
    webviewView.webview.options = { enableScripts: true };
    webviewView.webview.html = this._getInitialHtml();

    webviewView.webview.onDidReceiveMessage(msg => {
      switch (msg.command) {
        case 'runAll':           vscode.commands.executeCommand('testpilot.runAll'); break;
        case 'generateForDiff':  vscode.commands.executeCommand('testpilot.generateForDiff'); break;
        case 'runSolr':          vscode.commands.executeCommand('testpilot.runSolr'); break;
        case 'runReact':         vscode.commands.executeCommand('testpilot.runReact'); break;
        case 'setup':            vscode.commands.executeCommand('testpilot.setup'); break;
        case 'openConfig':       vscode.commands.executeCommand('testpilot.openConfig'); break;
      }
    });
  }

  setRunning(label) {
    this._post({ type: 'running', label });
  }

  appendOutput(text) {
    this._post({ type: 'output', text });
  }

  setResult(success, summary, fullOutput) {
    this._post({ type: 'result', success, summary, fullOutput });
  }

  _post(msg) {
    if (this._view) this._view.webview.postMessage(msg);
  }

  _getInitialHtml() {
    return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: var(--vscode-font-family);
    font-size: var(--vscode-font-size);
    color: var(--vscode-foreground);
    background: var(--vscode-sideBar-background);
    padding: 12px;
  }
  h2 { font-size: 13px; font-weight: 600; margin-bottom: 12px; opacity: 0.8; letter-spacing: 0.5px; }
  .section { margin-bottom: 16px; }
  .section-title { font-size: 11px; font-weight: 600; opacity: 0.6; text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 6px; }
  button {
    display: flex; align-items: center; gap: 6px;
    width: 100%; text-align: left;
    background: var(--vscode-button-secondaryBackground);
    color: var(--vscode-button-secondaryForeground);
    border: 1px solid var(--vscode-button-border, transparent);
    border-radius: 4px;
    padding: 6px 10px;
    cursor: pointer;
    font-size: 12px;
    margin-bottom: 4px;
    transition: background 0.1s;
  }
  button:hover { background: var(--vscode-button-secondaryHoverBackground); }
  button.primary {
    background: var(--vscode-button-background);
    color: var(--vscode-button-foreground);
    font-weight: 500;
  }
  button.primary:hover { background: var(--vscode-button-hoverBackground); }
  button:disabled { opacity: 0.5; cursor: not-allowed; }
  #status-bar {
    display: flex; align-items: center; gap: 8px;
    padding: 8px 10px; border-radius: 4px;
    background: var(--vscode-editor-inactiveSelectionBackground);
    margin-bottom: 12px; font-size: 12px;
  }
  #status-dot { width: 8px; height: 8px; border-radius: 50%; background: #888; flex-shrink: 0; }
  #status-dot.pass { background: #4caf50; }
  #status-dot.fail { background: #f44336; }
  #status-dot.running { background: #ff9800; animation: pulse 1s infinite; }
  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }
  #output {
    background: var(--vscode-terminal-background, #1e1e1e);
    color: var(--vscode-terminal-foreground, #ccc);
    font-family: var(--vscode-editor-font-family, monospace);
    font-size: 11px; border-radius: 4px;
    padding: 8px; max-height: 200px; overflow-y: auto;
    white-space: pre-wrap; word-break: break-all;
    display: none;
  }
  .icon { font-size: 14px; width: 16px; text-align: center; }
</style>
</head>
<body>
<h2>⚗ TestPilot AI</h2>

<div id="status-bar">
  <div id="status-dot"></div>
  <span id="status-text">Ready</span>
</div>

<div class="section">
  <div class="section-title">Generate</div>
  <button class="primary" onclick="send('generateForDiff')">
    <span class="icon">✨</span> Generate Tests (Changed Files)
  </button>
</div>

<div class="section">
  <div class="section-title">Run</div>
  <button class="primary" onclick="send('runAll')">
    <span class="icon">▶</span> Run All Tests
  </button>
  <button onclick="send('runSolr')">
    <span class="icon">🗄</span> SOLR Validation
  </button>
  <button onclick="send('runReact')">
    <span class="icon">🌐</span> React E2E (Playwright)
  </button>
</div>

<div class="section">
  <div class="section-title">Setup</div>
  <button onclick="send('setup')">
    <span class="icon">⚙</span> Initialize Project
  </button>
  <button onclick="send('openConfig')">
    <span class="icon">📄</span> Open config.yaml
  </button>
</div>

<div class="section">
  <div class="section-title">Output</div>
  <pre id="output"></pre>
</div>

<script>
  const vscode = acquireVsCodeApi();
  const dot = document.getElementById('status-dot');
  const txt = document.getElementById('status-text');
  const out = document.getElementById('output');
  let outputLines = [];

  function send(command) { vscode.postMessage({ command }); }

  window.addEventListener('message', e => {
    const msg = e.data;
    if (msg.type === 'running') {
      dot.className = 'running';
      txt.textContent = msg.label;
      outputLines = [];
      out.style.display = 'block';
      out.textContent = '';
    } else if (msg.type === 'output') {
      out.textContent += msg.text;
      out.scrollTop = out.scrollHeight;
    } else if (msg.type === 'result') {
      dot.className = msg.success ? 'pass' : 'fail';
      txt.textContent = msg.summary || (msg.success ? '✅ All passed' : '❌ Tests failed');
    }
  });
</script>
</body>
</html>`;
  }
}

function getDefaultConfig() {
  return `# TestPilot AI Configuration
# Generated by VS Code extension

anthropic:
  api_key: ""              # Get from https://console.anthropic.com

backend:
  url: "http://localhost:8000"
  source_dirs:
    - "src/"

siebel:
  enabled: false
  mode: "rest"
  rest:
    base_url: "https://siebel.yourorg.com/siebel/v1.0/data"
    username: ""
    password: ""

solr:
  enabled: false
  base_url: "http://localhost:8983/solr"
  collections:
    - name: "your_collection"
      required_fields: ["id", "title"]

frontend:
  enabled: false
  url: "http://localhost:3000"
  auth:
    email: ""
    password: ""

notifications:
  telegram:
    enabled: false
    bot_token: ""
    chat_id: ""
`;
}

function deactivate() {}

module.exports = { activate, deactivate };

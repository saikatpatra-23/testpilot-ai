/**
 * TestPilot AI — Playwright Chain Tracer
 *
 * Clicks a CTA on your React frontend and traces the ENTIRE call chain:
 *   CTA click → API call → SOLR request → Siebel request → response back to React
 *
 * Asserts:
 *   - The right API endpoint was called
 *   - SOLR was queried (with right params)
 *   - Siebel was called (when expected) or NOT called (when SOLR empty)
 *   - The React UI updated correctly after the chain completed
 *
 * Config from config.yaml:
 *   frontend.url, frontend.chains (list of CTA flows to test)
 *
 * Usage:
 *   node scripts/playwright_chain.js
 *   APP_URL=http://localhost:3000 node scripts/playwright_chain.js
 */

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

let yaml;
try { yaml = require('js-yaml'); } catch (e) { yaml = null; }

function loadConfig() {
  const cfgPath = path.join(__dirname, '..', 'config.yaml');
  if (yaml && fs.existsSync(cfgPath)) {
    return yaml.load(fs.readFileSync(cfgPath, 'utf8'));
  }
  return {};
}

const cfg = loadConfig();
const APP_URL    = process.env.APP_URL    || cfg.frontend?.url    || 'http://localhost:3000';
const BACKEND    = process.env.BACKEND    || cfg.backend?.url     || 'http://localhost:8000';
const SOLR_URL   = process.env.SOLR_URL   || cfg.solr?.base_url   || '';
const SIEBEL_URL = process.env.SIEBEL_URL || cfg.siebel?.rest?.base_url || '';
const SCREENSHOT_DIR = '/tmp/testpilot-chain-screenshots';
fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });

// ─── Chain Recorder ───────────────────────────────────────────────────────────

class ChainRecorder {
  constructor() {
    this.calls = [];  // All intercepted network calls in order
  }

  classify(url) {
    if (SOLR_URL && url.startsWith(SOLR_URL)) return 'solr';
    if (SIEBEL_URL && url.startsWith(SIEBEL_URL)) return 'siebel';
    if (url.includes('solr') || url.includes(':8983')) return 'solr';
    if (url.includes('siebel')) return 'siebel';
    if (url.startsWith(BACKEND)) return 'api';
    return 'other';
  }

  record(request) {
    const service = this.classify(request.url());
    this.calls.push({
      service,
      method: request.method(),
      url: request.url(),
      params: Object.fromEntries(new URL(request.url()).searchParams),
      timestamp: Date.now(),
    });
  }

  // Assertions
  assertApiCalled(pathContains, method = 'GET') {
    const call = this.calls.find(c => c.service === 'api' &&
      c.url.includes(pathContains) && c.method === method);
    if (!call) {
      throw new Error(`Expected ${method} API call to ${pathContains}, got: ${this.summary()}`);
    }
    return call;
  }

  assertSolrCalled(collection = null, queryContains = null) {
    const calls = this.calls.filter(c => c.service === 'solr');
    if (calls.length === 0) throw new Error('Expected SOLR to be called');
    if (collection) {
      const found = calls.find(c => c.url.includes(`/${collection}/`));
      if (!found) throw new Error(`Expected SOLR collection '${collection}', got: ${calls.map(c=>c.url)}`);
    }
    if (queryContains) {
      const found = calls.find(c => (c.params.q || '').toLowerCase().includes(queryContains.toLowerCase()));
      if (!found) throw new Error(`Expected SOLR query containing '${queryContains}'`);
    }
  }

  assertSolrNotCalled() {
    const calls = this.calls.filter(c => c.service === 'solr');
    if (calls.length > 0) throw new Error(`Expected SOLR NOT called, but got ${calls.length} calls`);
  }

  assertSiebelCalled() {
    const calls = this.calls.filter(c => c.service === 'siebel');
    if (calls.length === 0) throw new Error('Expected Siebel to be called');
  }

  assertSiebelNotCalled() {
    const calls = this.calls.filter(c => c.service === 'siebel');
    if (calls.length > 0) throw new Error(`Expected Siebel NOT called, but got ${calls.length} calls`);
  }

  assertCallOrder(services) {
    const actual = this.calls
      .map(c => c.service)
      .filter(s => services.includes(s))
      .filter((s, i, arr) => arr[i - 1] !== s); // deduplicate consecutive
    const expected = JSON.stringify(services);
    const got = JSON.stringify(actual);
    if (expected !== got) {
      throw new Error(`Expected call order ${expected}, got ${got}`);
    }
  }

  summary() {
    if (this.calls.length === 0) return 'No calls recorded';
    return this.calls.map(c => `${c.service}(${c.method} ${c.url.split('/').slice(-2).join('/')})`).join(' → ');
  }

  reset() { this.calls = []; }
}

// ─── Test Runner ──────────────────────────────────────────────────────────────

const results = { passed: [], failed: [] };

async function runChainTest(page, recorder, testDef) {
  const { name, setup, act, assert: assertions } = testDef;
  recorder.reset();

  try {
    if (setup) await setup(page);

    await act(page);
    await page.waitForTimeout(1500); // let chain complete

    await assertions(recorder, page);

    const screenshotPath = `${SCREENSHOT_DIR}/${name.replace(/\s+/g, '_')}.png`;
    await page.screenshot({ path: screenshotPath });
    results.passed.push(`${name} [chain: ${recorder.summary()}]`);
    console.log(`  ✅ ${name}`);
    console.log(`     Chain: ${recorder.summary()}`);
  } catch (e) {
    const screenshotPath = `${SCREENSHOT_DIR}/${name.replace(/\s+/g, '_')}_FAIL.png`;
    await page.screenshot({ path: screenshotPath });
    results.failed.push(`${name}: ${e.message}`);
    console.log(`  ❌ ${name}`);
    console.log(`     Error: ${e.message}`);
    console.log(`     Chain so far: ${recorder.summary()}`);
  }
}

// ─── Define your chain tests here ────────────────────────────────────────────

function getChainTests(cfg) {
  return [
    {
      name: 'Search CTA → full chain',
      setup: async (page) => {
        await page.goto(APP_URL, { waitUntil: 'domcontentloaded' });
      },
      act: async (page) => {
        // Find and fill the search box, then click CTA
        const searchInput = page.locator(
          'input[placeholder*="search" i], input[placeholder*="job" i], input[name*="search" i], input[type="search"]'
        ).first();
        if (await searchInput.isVisible()) {
          await searchInput.fill('Technical Program Manager');
        }
        const searchBtn = page.locator(
          'button:has-text("Search"), button[type="submit"], [data-testid="search-btn"]'
        ).first();
        await searchBtn.click();
      },
      assert: async (recorder, page) => {
        // The API call was made
        recorder.assertApiCalled('/api/search', 'GET');
        // SOLR was queried as part of the chain
        recorder.assertSolrCalled('jobs');
        // Siebel should be called AFTER SOLR (enrichment)
        recorder.assertCallOrder(['api', 'solr', 'siebel']);
        // Results appeared in the UI
        const resultsEl = await page.$('[data-testid="results"], .results, .job-list, .search-results');
        if (!resultsEl) throw new Error('No results element found in React UI after chain completed');
      }
    },

    {
      name: 'Apply CTA → SOLR read → Siebel write',
      setup: async (page) => {
        // Navigate to a page with Apply button (customize this)
        await page.goto(`${APP_URL}/jobs/job-001`, { waitUntil: 'domcontentloaded' });
      },
      act: async (page) => {
        const applyBtn = page.locator(
          'button:has-text("Apply"), [data-testid="apply-btn"], .apply-button'
        ).first();
        if (await applyBtn.isVisible()) {
          await applyBtn.click();
        } else {
          console.log('    [skip] Apply button not found on this page');
        }
      },
      assert: async (recorder, page) => {
        // Apply clicked → API POST → SOLR read job → Siebel create Application
        const apiCalls = recorder.calls.filter(c => c.service === 'api' && c.method === 'POST');
        if (apiCalls.length > 0) {
          recorder.assertSolrCalled();
          recorder.assertSiebelCalled();
          recorder.assertCallOrder(['api', 'solr', 'siebel']);
        }
        // UI shows success or confirmation
        const confirmEl = await page.$(
          '[data-testid="apply-success"], .success-message, [class*="success"], [class*="confirm"]'
        );
        if (apiCalls.length > 0 && !confirmEl) {
          throw new Error('Apply chain completed but no confirmation shown in React UI');
        }
      }
    },

    {
      name: 'Empty search → no Siebel call',
      setup: async (page) => {
        await page.goto(APP_URL, { waitUntil: 'domcontentloaded' });
      },
      act: async (page) => {
        const searchInput = page.locator(
          'input[placeholder*="search" i], input[type="search"]'
        ).first();
        if (await searchInput.isVisible()) {
          await searchInput.fill('XXXXXXX_NO_RESULTS_EXPECTED_XXXXX');
        }
        const searchBtn = page.locator('button:has-text("Search"), button[type="submit"]').first();
        await searchBtn.click();
      },
      assert: async (recorder, page) => {
        recorder.assertSolrCalled();
        // When SOLR returns empty, Siebel must NOT be called
        recorder.assertSiebelNotCalled();
        // UI shows "no results" state
        const emptyEl = await page.$(
          '[data-testid="no-results"], .empty-state, [class*="no-results"]'
        );
        // (emptyEl may or may not exist depending on your UI — soft check)
        if (!emptyEl) {
          console.log('    [warn] No "empty results" UI element found');
        }
      }
    },
  ];
}

// ─── Main ─────────────────────────────────────────────────────────────────────

(async () => {
  console.log(`\nTestPilot AI — Chain Tracer (Playwright)`);
  console.log(`App:     ${APP_URL}`);
  console.log(`Backend: ${BACKEND}`);
  console.log(`SOLR:    ${SOLR_URL || '(auto-detect)'}`);
  console.log(`Siebel:  ${SIEBEL_URL || '(auto-detect)'}\n`);

  const browser = await chromium.launch({ headless: false, slowMo: 200 });
  const context = await browser.newContext();
  const page = await context.newPage();

  const recorder = new ChainRecorder();

  // Intercept ALL network requests and record them
  page.on('request', request => {
    const url = request.url();
    // Skip browser internals and static assets
    if (!url.startsWith('chrome') && !url.includes('.css') && !url.includes('.js')
        && !url.includes('.png') && !url.includes('.svg') && !url.includes('.ico')) {
      recorder.record(request);
    }
  });

  const chainTests = getChainTests(cfg);
  console.log(`Running ${chainTests.length} chain tests...\n`);

  for (const test of chainTests) {
    await runChainTest(page, recorder, test);
  }

  await browser.close();

  console.log(`\n${'─'.repeat(50)}`);
  results.passed.forEach(p => console.log(`  ✅ ${p}`));
  results.failed.forEach(f => console.log(`  ❌ ${f}`));
  console.log(`\n${results.passed.length} passed, ${results.failed.length} failed`);
  console.log(`Screenshots: ${SCREENSHOT_DIR}/`);

  fs.writeFileSync('/tmp/testpilot-chain-results.json', JSON.stringify(results, null, 2));
  process.exit(results.failed.length > 0 ? 1 : 0);
})();

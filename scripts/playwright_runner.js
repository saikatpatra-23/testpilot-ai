/**
 * TestPilot AI — Playwright Runner (React Frontend)
 * Runs smoke tests + visual snapshots on your React app.
 *
 * Usage:
 *   node scripts/playwright_runner.js
 *   APP_URL=http://localhost:3000 node scripts/playwright_runner.js
 *
 * Config is read from ../config.yaml (APP_URL env var overrides)
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const yaml = require('js-yaml');

// Load config
function loadConfig() {
  const configPath = path.join(__dirname, '..', 'config.yaml');
  if (fs.existsSync(configPath)) {
    return yaml.load(fs.readFileSync(configPath, 'utf8'));
  }
  return {};
}

const cfg = loadConfig();
const APP_URL = process.env.APP_URL || cfg.frontend?.url || 'http://localhost:3000';
const AUTH = cfg.frontend?.auth || {};
const SMOKE_TESTS = cfg.frontend?.smoke_tests || [{ path: '/', wait_for: 'body' }];
const SCREENSHOT_DIR = '/tmp/testpilot-screenshots';
fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });

const results = { passed: [], failed: [], screenshots: [] };

async function runSmokeTests(page) {
  for (const test of SMOKE_TESTS) {
    const url = `${APP_URL}${test.path}`;
    const name = `smoke_${test.path.replace(/\//g, '_') || 'home'}`;

    try {
      await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 15000 });

      if (test.requires_auth) {
        // Check if redirected to login
        const currentUrl = page.url();
        if (currentUrl.includes('/login') || currentUrl.includes('/signin')) {
          results.passed.push(`${test.path}: auth guard working`);
          continue;
        }
      }

      if (test.wait_for) {
        await page.waitForSelector(test.wait_for, { timeout: 8000 });
      }

      // Take screenshot
      const screenshotPath = `${SCREENSHOT_DIR}/${name}.png`;
      await page.screenshot({ path: screenshotPath, fullPage: true });
      results.screenshots.push(screenshotPath);
      results.passed.push(`${test.path}: loaded OK, screenshot saved`);

    } catch (e) {
      results.failed.push(`${test.path}: ${e.message.split('\n')[0]}`);
    }
  }
}

async function runLoginFlow(page) {
  if (!AUTH.email || !AUTH.password) return;

  console.log('  Testing login flow...');
  try {
    await page.goto(`${APP_URL}/login`, { timeout: 15000 });

    const emailInput = page.locator('input[type="email"], input[name="email"], input[placeholder*="email" i]').first();
    const passInput = page.locator('input[type="password"]').first();
    const submitBtn = page.locator('button[type="submit"], button:has-text("Login"), button:has-text("Sign in")').first();

    await emailInput.fill(AUTH.email);
    await passInput.fill(AUTH.password);

    const screenshotPath = `${SCREENSHOT_DIR}/login_filled.png`;
    await page.screenshot({ path: screenshotPath });
    results.screenshots.push(screenshotPath);

    await submitBtn.click();
    await page.waitForTimeout(2000);

    const afterUrl = page.url();
    if (!afterUrl.includes('/login')) {
      results.passed.push(`Login flow: redirected to ${afterUrl.replace(APP_URL, '')}`);
    } else {
      // Check for error message
      const errorEl = await page.$('[class*="error"], [class*="alert"], [role="alert"]');
      if (errorEl) {
        const errorText = await errorEl.innerText();
        results.failed.push(`Login flow: error shown — "${errorText.trim()}"`);
      } else {
        results.failed.push(`Login flow: still on login page after submit`);
      }
    }
  } catch (e) {
    results.failed.push(`Login flow: ${e.message.split('\n')[0]}`);
  }
}

async function runResponsiveCheck(page) {
  console.log('  Testing responsive layouts...');
  const viewports = [
    { name: 'desktop', width: 1440, height: 900 },
    { name: 'tablet', width: 768, height: 1024 },
    { name: 'mobile', width: 375, height: 812 },
  ];

  for (const vp of viewports) {
    try {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.goto(APP_URL, { waitUntil: 'domcontentloaded', timeout: 10000 });
      await page.waitForTimeout(500);
      const screenshotPath = `${SCREENSHOT_DIR}/responsive_${vp.name}.png`;
      await page.screenshot({ path: screenshotPath, fullPage: true });
      results.screenshots.push(screenshotPath);
      results.passed.push(`Responsive ${vp.name} (${vp.width}x${vp.height}): OK`);
    } catch (e) {
      results.failed.push(`Responsive ${vp.name}: ${e.message.split('\n')[0]}`);
    }
  }
}

(async () => {
  console.log(`\nTestPilot AI — React E2E`);
  console.log(`Target: ${APP_URL}\n`);

  const browser = await chromium.launch({ headless: false });
  const page = await browser.newPage();

  try {
    console.log('  Running smoke tests...');
    await runSmokeTests(page);

    console.log('  Running login flow...');
    await runLoginFlow(page);

    console.log('  Running responsive checks...');
    await runResponsiveCheck(page);

  } finally {
    await browser.close();
  }

  // Print results
  console.log('\n--- Results ---');
  results.passed.forEach(p => console.log(`  ✅ ${p}`));
  results.failed.forEach(f => console.log(`  ❌ ${f}`));
  console.log(`\n${results.passed.length} passed, ${results.failed.length} failed`);
  console.log(`Screenshots saved to: ${SCREENSHOT_DIR}/`);

  // Write JSON results for CI
  fs.writeFileSync('/tmp/testpilot-playwright-results.json', JSON.stringify(results, null, 2));

  process.exit(results.failed.length > 0 ? 1 : 0);
})();

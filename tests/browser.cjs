/* Optional integration QA. Install Playwright separately; normal builds need no Node.js. */
const assert = require("node:assert/strict");
const path = require("node:path");
const fs = require("node:fs");
const os = require("node:os");
const { execFileSync } = require("node:child_process");
const { pathToFileURL } = require("node:url");
const { chromium } = require(process.env.WIKI_PLAYWRIGHT || "playwright");

(async () => {
  const browser = await chromium.launch({
    ...(process.env.WIKI_BROWSER_EXECUTABLE
      ? { executablePath: process.env.WIKI_BROWSER_EXECUTABLE }
      : { channel: process.env.WIKI_BROWSER || "msedge" }),
    headless: true,
  });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1100 },
    colorScheme: "light",
  });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const root = path.resolve(__dirname, "..");
  const fixtureRoot = fs.mkdtempSync(path.join(os.tmpdir(), "wiki-library-series-qa-"));
  const sampleSource = path.join(fixtureRoot, "samples");
  const sampleSite = path.join(fixtureRoot, "sample-site");
  const home = pathToFileURL(path.join(sampleSite, "index.html")).href;
  const visible = () => page.locator(".catalogue .work-row:visible").count();
  const search = async (value) => {
    await page.locator('input[name="q"]').fill(value);
    await page.waitForTimeout(180);
  };
  const options = (name) =>
    page.locator(`select[name="${name}"] option`).evaluateAll((items) =>
      items.map((option) => option.value),
    );
  try {
    // Keep the six sample works independent of additions to the real library.
    for (const relative of [
      "novel/solaris", "film/stalker", "animation/ghost-in-the-shell",
      "game/outer-wilds", "academic/imagined-communities", "comic/pluto",
    ]) {
      fs.cpSync(path.join(root, "data", relative), path.join(sampleSource, relative), { recursive: true });
    }
    execFileSync("python", ["build.py", "--source", sampleSource, "--output", sampleSite], {
      cwd: root, env: { ...process.env, PYTHONUTF8: "1" }, stdio: "pipe",
    });
    await page.goto(home);
    assert.equal(await visible(), 6);
    assert.equal(await page.locator(".library-hero, .work-card").count(), 0);
    const rowBounds = await page
      .locator(".catalogue .work-row")
      .evaluateAll((rows) =>
        rows.map((row) => {
          const box = row.getBoundingClientRect();
          return { top: box.top, bottom: box.bottom, height: box.height };
        }),
      );
    assert.equal(
      rowBounds.every(
        (row, index) =>
          index === 0 || row.top >= rowBounds[index - 1].bottom - 1,
      ),
      true,
    );
    assert.equal(
      rowBounds[5].bottom <= 1100,
      true,
      "All six examples should fit in the desktop viewport.",
    );
    await search("非線性探索");
    assert.equal(await visible(), 1); // Search the new work-feature field.
    await search("");
    await page
      .locator('select[name="category"]')
      .selectOption("social-science");
    assert.equal(await visible(), 1);
    assert.deepEqual(await options("media"), ["", "academic"]);
    assert.deepEqual(await options("tag"), ["", "政治學", "歷史學", "民族主義", "社會學"]);
    await page.locator('select[name="tag"]').selectOption("政治學");
    assert.equal(await visible(), 1);
    assert.equal((await options("tag")).includes("歷史學"), true);
    await page.locator('select[name="tag"]').selectOption("歷史學");
    assert.equal(await visible(), 1);
    await page.getByRole("button", { name: "清除篩選" }).click();
    await page.waitForTimeout(50);
    await page.screenshot({
      path: path.join(root, "preview-desktop.png"),
      fullPage: true,
    });
    await search("星際拓荒");
    assert.equal(await visible(), 1);
    await search("Outer Wilds");
    assert.equal(await visible(), 1);
    await search("索拉力星");
    assert.equal(await visible(), 1);
    await search("bill johnston");
    assert.equal(await visible(), 1);
    await search("ｂｉｌｌ Ｊｏｈｎｓｔｏｎ");
    assert.equal(await visible(), 1);
    await search("波蘭 外星");
    assert.equal(await visible(), 1);
    await search("a-title-that-does-not-exist");
    assert.equal(await visible(), 0);
    assert.equal(await page.locator("#empty-state").isVisible(), true);
    await page.getByRole("button", { name: "清除篩選" }).click();
    await page.waitForTimeout(50);
    assert.equal(await visible(), 6);
    await page.locator('select[name="media"]').selectOption("game");
    assert.equal(await visible(), 1);
    assert.deepEqual(await options("category"), ["", "adventure-game"]);
    assert.equal((await options("tag")).includes("政治學"), false);
    await page
      .locator('select[name="category"]')
      .selectOption("adventure-game");
    assert.equal(await visible(), 1);
    await page.getByRole("button", { name: "清除篩選" }).click();
    await page.waitForTimeout(50);
    await page.locator('select[name="tag"]').selectOption("人工智慧");
    assert.equal(await visible(), 2);
    assert.deepEqual(await options("media"), ["", "animation", "comic"]);
    assert.match(page.url(), /tag=/);
    await page.reload();
    assert.equal(await visible(), 2);
    // popstate must restore values removed from the previous option list.
    await page.evaluate(() => {
      history.pushState(null, "", "?media=game");
      dispatchEvent(new PopStateEvent("popstate"));
    });
    assert.equal(await visible(), 1);
    assert.equal(await page.locator('select[name="media"]').inputValue(), "game");
    await page.goBack();
    assert.equal(await visible(), 2);
    assert.equal(await page.locator('select[name="tag"]').inputValue(), "人工智慧");
    await search("索拉力星");
    assert.equal(await visible(), 1);
    assert.equal(await page.locator('select[name="tag"]').inputValue(), "");
    assert.doesNotMatch(page.url(), /tag=/);
    assert.deepEqual(await options("media"), ["", "novel"]);
    const searchTags = await options("tag");
    assert.equal(searchTags.length, new Set(searchTags).size);
    await page.getByRole("button", { name: "清除篩選" }).click();
    await page.waitForTimeout(50);
    await page.locator('select[name="sort"]').selectOption("year");
    assert.equal(
      await page.locator(".work-row:visible").first().getAttribute("data-id"),
      "outer-wilds",
    );
    await page.goto(home);
    await page.getByRole("button", { name: "切換至深色模式" }).click();
    assert.equal(await page.locator("html").getAttribute("data-theme"), "dark");
    await page.reload();
    assert.equal(await page.locator("html").getAttribute("data-theme"), "dark");
    await page.screenshot({
      path: path.join(root, "preview-dark.png"),
      fullPage: true,
    });
    await page.getByRole("button", { name: "切換至淺色模式" }).click();
    await page.goto(
      pathToFileURL(path.join(sampleSite, "works/solaris/index.html")).href,
    );
    await page
      .getByRole("heading", { name: "內容簡介", exact: true })
      .waitFor();
    assert.match(await page.locator(".work-original").innerText(), /Solaris/);
    await page
      .getByRole("heading", { name: "作品特色", exact: true })
      .waitFor();
    assert.equal(
      await page.getByRole("heading", { name: "為甚麼收藏它" }).count(),
      0,
    );
    assert.match(
      await page.locator(".editions-section").innerText(),
      /Bill Johnston/,
    );
    await page.screenshot({
      path: path.join(root, "preview-detail.png"),
      fullPage: true,
    });
    await page.locator(".prose a").click();
    assert.match(page.url(), /works\/stalker\/index.html/);
    await page.goto(
      pathToFileURL(path.join(sampleSite, "media/game/index.html")).href,
    );
    assert.equal(await visible(), 1);
    await search("Solaris");
    assert.equal(await visible(), 0); // Scoped search stays on this shelf.
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(home);
    assert.equal(await page.locator(".shelf-nav").getAttribute("open"), null);
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
      true,
    );
    await page.screenshot({
      path: path.join(root, "preview-mobile.png"),
      fullPage: true,
    });
    await page.locator(".shelf-nav > summary").click();
    assert.equal(await page.locator(".shelf-nav").getAttribute("open"), "");
    await page.goto(
      pathToFileURL(path.join(sampleSite, "works/solaris/index.html")).href,
    );
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
      true,
    );
    await page.screenshot({
      path: path.join(root, "preview-mobile-detail.png"),
      fullPage: true,
    });
    await page.setViewportSize({ width: 320, height: 700 });
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
      true,
    );
    const noJs = await browser.newContext({ javaScriptEnabled: false });
    const staticPage = await noJs.newPage();
    await staticPage.goto(home);
    assert.equal(await staticPage.locator(".work-row:visible").count(), 6);
    await staticPage
      .getByRole("link", { name: "標籤索引", exact: true })
      .click();
    assert.equal((await staticPage.locator(".tag-index a").count()) > 0, true);
    await noJs.close();

    // Use temporary fictional works; do not invent series relationships for real samples.
    execFileSync("python", ["-c", `
import sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]) / "tests"))
from test_build import BuildTests
from build import build
fixture = BuildTests()
fixture.setUp()
try:
    fixture.entry("first", title="系列第一部", original_title="Part I")
    fixture.entry("third", title="系列第三部", original_title="Part III")
    fixture.entry("standalone", title="獨立作品", media="film", categories=["science-fiction-film"])
    fixture.series()
    build(fixture.source, Path(sys.argv[2]) / "site")
finally:
    fixture.tearDown()
`, root, fixtureRoot], { cwd: root, env: { ...process.env, PYTHONUTF8: "1" }, stdio: "pipe" });
    const seriesHome = pathToFileURL(path.join(fixtureRoot, "site/index.html")).href;
    await page.setViewportSize({ width: 1440, height: 1100 });
    await page.goto(seriesHome);
    await page.locator('select[name="series"]').selectOption("example-cycle");
    assert.equal(await visible(), 2);
    assert.match(page.url(), /series=example-cycle/);
    await page.reload();
    assert.equal(await visible(), 2);
    await search("系列別名");
    assert.equal(await visible(), 2);
    assert.deepEqual(await options("media"), ["", "novel"]);
    await search("");
    await page.locator('select[name="series"]').selectOption("");
    await page.locator('select[name="media"]').selectOption("film");
    assert.equal(await visible(), 1);
    assert.deepEqual(await options("series"), [""]);
    await page.getByRole("button", { name: "清除篩選" }).click();
    await page.waitForTimeout(50);
    assert.equal(await visible(), 3);
    assert.doesNotMatch(page.url(), /series=/);
    await page.locator('.row-title a').filter({ hasText: "系列第一部" }).click();
    const release = page.locator("#series-example-cycle--order-release");
    assert.equal(await release.locator('.series-current').count(), 1);
    assert.match(await release.locator('.series-neighbours').innerText(), /後一部[\s\S]*第二部[\s\S]*尚未收錄/);
    assert.equal(await release.locator('.series-neighbours a').count(), 0);
    const chronology = page.locator("#series-example-cycle--order-chronology");
    assert.match(await chronology.locator('.series-neighbours').innerText(), /前一部[\s\S]*系列第三部/);
    assert.equal(await page.locator('#series-example-cycle--order-members .series-neighbours').count(), 0);
    await page.screenshot({ path: path.join(root, "preview-series-detail.png"), fullPage: true });
    await chronology.locator('.series-neighbours a').click();
    assert.match(page.url(), /works\/third\/index.html/);
    await page.getByRole("link", { name: "完整系列與順序來源 ↗" }).click();
    assert.match(page.url(), /series\/example-cycle\/index.html/);
    assert.equal(await page.locator('#series-example-cycle--order-release li').count(), 3);
    await page.screenshot({ path: path.join(root, "preview-series-desktop.png"), fullPage: true });
    for (const width of [390, 320]) {
      await page.setViewportSize({ width, height: 844 });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
    }
    await page.screenshot({ path: path.join(root, "preview-series-mobile.png"), fullPage: true });
    const seriesNoJs = await browser.newContext({ javaScriptEnabled: false });
    const seriesStatic = await seriesNoJs.newPage();
    await seriesStatic.goto(seriesHome);
    await seriesStatic.getByRole("link", { name: "系列索引", exact: true }).click();
    await seriesStatic.getByRole("link", { name: "範例系列", exact: true }).click();
    await seriesStatic.locator('#series-example-cycle--order-release').getByRole("link", { name: "系列第一部", exact: true }).click();
    assert.match(seriesStatic.url(), /works\/first\/index.html/);
    await seriesNoJs.close();
    assert.deepEqual(errors, []);
    console.log(
      "Browser QA passed: bilingual search, combined filters, URL state, series orders and gaps, previous/next links, themes, mobile, and no-JS navigation.",
    );
  } finally {
    await browser.close();
    const resolved = path.resolve(fixtureRoot);
    if (path.dirname(resolved) !== path.resolve(os.tmpdir()) || !path.basename(resolved).startsWith("wiki-library-series-qa-")) {
      throw new Error("Refusing to remove an unexpected fixture path.");
    }
    fs.rmSync(resolved, { recursive: true, force: true });
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});

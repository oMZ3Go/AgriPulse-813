import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const widths = [1440, 1280, 1024, 768, 390, 360];
async function ready(page: Page) {
  await expect(page.locator('[data-complete="true"]')).toBeVisible();
  await expect(page.locator("#mode-panel")).toBeVisible();
}
async function globeReady(page: Page) { await expect(page.locator('[data-globe-ready="true"]')).toBeVisible({ timeout: 30000 }); }
async function select(page: Page, query: string, name: string) {
  await page.getByRole("combobox", { name: "Find a country" }).fill(query);
  await page.getByRole("option", { name, exact: true }).click();
}
test.beforeEach(async ({ page }) => {
  const errors: string[] = [];
  const external: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("request", (request) => {
    if (/^https?:/.test(request.url()) && new URL(request.url()).hostname !== "127.0.0.1") external.push(request.url());
  });
  page.on("response", (response) => {
    if (response.status() >= 400) errors.push("HTTP " + response.status() + " " + response.url());
  });
  Object.assign(page, { audit: { errors, external } });
});
test.afterEach(async ({ page }, testInfo) => {
  const { errors, external } = (page as Page & { audit: { errors: string[]; external: string[] } }).audit;
  expect(external, "No external runtime requests").toEqual([]);
  const expected404 = testInfo.annotations.some((item) => item.type === "expected-http-error");
  expect(expected404 ? errors.filter((error) => !/HTTP 404|Failed to load resource.*404/.test(error)) : errors, "No unexpected console, runtime or HTTP errors").toEqual([]);
});

test("landing keeps identity, three use cases and immediately usable intro controls", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /From spectral/ })).toBeVisible();
  for (const name of ["Explore Earth", "Verify My Field", "Smart Farm"]) await expect(page.getByRole("button", { name: new RegExp(name) })).toBeEnabled();
  await expect(page.getByRole("link", { name: "Choose an area" })).toBeEnabled();
  await globeReady(page);
  await page.screenshot({ path: "test-results/landing-desktop.png", fullPage: true });
  await page.getByRole("button", { name: /Verify My Field/ }).click();
  await page.getByRole("link", { name: "Choose an area" }).click();
  await expect(page).toHaveURL(/useCase=VERIFY_MY_FIELD/);
  await expect(page.getByRole("button", { name: /Verify My Field/ })).toHaveAttribute("aria-pressed", "true");
});

test("country partial search supports keyboard, Escape and synchronized globe focus", async ({ page }) => {
  await page.goto("/scene");
  await globeReady(page);
  const input = page.getByRole("combobox", { name: "Find a country" });
  await input.fill("Syr");
  await expect(page.getByRole("option")).toHaveCount(1);
  await input.press("ArrowDown");
  await input.press("Enter");
  await expect(input).toHaveValue("Syria");
  await expect(input).toHaveAttribute("aria-expanded", "false");
  await expect(page.locator(".globe-canvas")).toHaveAttribute("data-focused-country", "760");
  await expect(page.locator(".globe-canvas")).toHaveAttribute("data-focus-lat", /3[0-9]/);
  await expect(page.getByRole("heading", { name: "Choose an area to analyse" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Area selection" })).toContainText("Live global EO processing has not yet been executed");
  await expect(page.getByRole("region", { name: "Area selection" })).toContainText("Syria is our target deployment");
  await input.fill("fr");
  await input.press("Escape");
  await expect(input).toHaveValue("Syria");
  await input.fill("zznonexistent");
  await expect(page.getByText("No countries match. Try another name.")).toBeVisible();
  await input.press("Escape");
  await select(page, "Türk", "Turkey");
  await expect(page.locator(".globe-canvas")).toHaveAttribute("data-focused-country", "792");
  await expect(page.getByRole("link", { name: "Open validated demo", exact: true })).toBeVisible();
  await page.screenshot({ path: "test-results/scene-desktop.png", fullPage: true });
  await page.reload();
  await expect(input).toHaveValue("Turkey");
});

test("actual globe polygon picking and regional markers update country search", async ({ page }) => {
  await page.goto("/scene");
  await globeReady(page);
  const canvas = page.locator("canvas");
  const box = await canvas.boundingBox();
  expect(box).not.toBeNull();
  await page.mouse.click(box!.x + box!.width / 2, box!.y + box!.height / 2);
  await expect(page.getByRole("combobox", { name: "Find a country" })).not.toHaveValue("");
  await expect(page.getByRole("region", { name: "Area selection" })).toBeVisible();
  await page.getByRole("button", { name: "Syria: Target deployment", exact: true }).click();
  await expect(page.getByRole("combobox", { name: "Find a country" })).toHaveValue("Syria");
  await expect(page.locator(".globe-canvas")).toHaveAttribute("data-focused-country", "760");
  await page.getByRole("button", { name: "Konya, Turkey: Current validated demo scene", exact: true }).click();
  await expect(page.getByRole("combobox", { name: "Find a country" })).toHaveValue("Turkey");
});

test("non-demo country selection performs no fabricated analysis or data fetch", async ({ page }) => {
  const scientificRequests: string[] = [];
  page.on("request", (request) => { if (request.url().includes("/data/konya/")) scientificRequests.push(request.url()); });
  await page.goto("/scene?useCase=SMART_FARM&mode=EXPERT");
  await globeReady(page);
  await select(page, "Braz", "Brazil");
  const bounds = (await page.locator("canvas").boundingBox())!;
  await page.mouse.move(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2);
  // Raycasting the center after focus verifies the actual camera, not just selected state.
  await expect(page.locator(".globe-canvas")).toHaveAttribute("data-hover-country", "076");
  await page.mouse.click(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2);
  await expect(page.getByRole("combobox", { name: "Find a country" })).toHaveValue("Brazil");
  await expect(page.getByRole("region", { name: "Area selection" })).toContainText("does not mean the country has been analysed");
  await expect(page.locator(".analysis-activity")).toHaveCount(0);
  await expect(page.locator(".assessment-card")).toHaveCount(0);
  await expect(page.getByText("GROUND_VERIFICATION_REQUIRED", { exact: true })).toHaveCount(0);
  await page.getByText("Area selection options · upcoming").click();
  await expect(page.getByText("Drawing and live analysis are not connected yet.", { exact: false })).toBeVisible();
  expect(scientificRequests).toEqual([]);
  await page.getByRole("link", { name: "Open validated Konya demo" }).click();
  await ready(page);
  await expect(page.getByRole("combobox", { name: "Use case" })).toHaveValue("SMART_FARM");
  await expect(page.getByRole("button", { name: "Expert View", exact: true })).toHaveAttribute("aria-pressed", "true");
});

test("real Simple result, truthful availability and completed local activity render", async ({ page }) => {
  await page.goto("/dashboard");
  await ready(page);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Ground verification required");
  for (const text of ["Relative areas of concern are present", "No strong broad moisture decline confirmation", "Automatic intervention: not allowed", "Inspect highlighted areas and collect site-specific ground evidence before intervention."]) await expect(page.getByText(text, { exact: true })).toBeVisible();
  await expect(page.locator("#mode-panel")).not.toContainText(/Spearman|Theil.Sen|\d+%|NDVI ≥/);
  const availability = page.getByRole("region", { name: "Evidence availability" });
  await expect(availability).toContainText("NOT CHECKED");
  await expect(availability).toContainText("Not integrated");
  await expect(availability).toContainText("NOT CONNECTED");
  await expect(availability).toContainText("UNAVAILABLE");
  await page.locator(".analysis-activity summary").click();
  await expect(page.locator('.analysis-activity li[data-state="complete"]')).toHaveCount(9);
  await expect(page.locator(".analysis-activity")).toContainText("No satellite download");
  await page.screenshot({ path: "test-results/simple-desktop.png", fullPage: true });
});

for (const useCase of ["EXPLORE_EARTH", "VERIFY_MY_FIELD", "SMART_FARM"]) {
  test(`Simple and Expert are independent of ${useCase}`, async ({ page }) => {
    await page.goto(`/dashboard?useCase=${useCase}&mode=SIMPLE`);
    await ready(page);
    await expect(page.getByRole("combobox", { name: "Use case" })).toHaveValue(useCase);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Ground verification required");
    await page.getByRole("button", { name: "Expert View", exact: true }).click();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Trace the evidence.");
    await expect(page).toHaveURL(new RegExp("useCase=" + useCase));
    if (useCase === "VERIFY_MY_FIELD") {
      await expect(page.getByRole("region", { name: "Field verification pathway" })).toContainText("Ground Observation unavailable");
      await expect(page.getByRole("region", { name: "Field verification pathway" })).toContainText("not automatically verified ground truth");
    }
    if (useCase === "SMART_FARM") await expect(page.getByRole("region", { name: "Smart Farm pathway" })).toContainText("IoT not connected");
    await page.getByRole("button", { name: "Expert View", exact: true }).press("ArrowLeft");
    await expect(page.getByRole("button", { name: "Simple View", exact: true })).toBeFocused();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Ground verification required");
    await page.getByRole("combobox", { name: "Use case" }).selectOption("SMART_FARM");
    await expect(page.getByRole("button", { name: "Simple View", exact: true })).toHaveAttribute("aria-pressed", "true");
  });
}

test("all real Expert sections and figures render with unchanged scientific truth", async ({ page }) => {
  await page.goto("/dashboard?mode=EXPERT");
  await ready(page);
  await page.screenshot({ path: "test-results/expert-desktop.png", fullPage: true });
  for (const [label, heading] of [["Spatial risk", "Spatial risk"], ["Temporal evidence", "Temporal evidence"], ["Hyperspectral analysis", "Hyperspectral analysis"], ["ML spectral anomaly", "Experimental Spectral Anomaly ML"], ["Decision fusion", "Decision fusion"], ["Data provenance", "Data provenance"], ["Methodology / limitations", "Methodology / limitations"]]) {
    await page.getByRole("navigation", { name: "Expert navigation" }).getByRole("button", { name: label, exact: true }).click();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(heading);
    if (label === "ML spectral anomaly") {
      await expect(page.getByRole("heading", { name: "Spearman ρ ≈ +0.003357" })).toBeVisible();
      await expect(page.locator("#mode-panel")).toContainText("not field-calibrated");
    }
    if (label === "Decision fusion") {
      await expect(page.getByRole("heading", { name: "GROUND_VERIFICATION_REQUIRED", exact: true })).toBeVisible();
      await expect(page.getByText("automation_allowed: false", { exact: true })).toBeVisible();
    }
    if (label === "Temporal evidence") {
      await expect(page.locator(".metric-row")).toContainText("19");
      await expect(page.locator(".metric-row")).toContainText("44");
      await expect(page.locator("#mode-panel")).toContainText("retrospective context only");
    }
    for (const img of await page.locator(".scientific-figure img").all()) {
      await img.scrollIntoViewIfNeeded();
      await expect(img).toHaveJSProperty("complete", true);
      expect(await img.evaluate((element: HTMLImageElement) => element.naturalWidth)).toBeGreaterThan(0);
    }
  }
  await page.reload();
  await ready(page);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Methodology / limitations");
});

test("activity follows real pending reads without premature assessment", async ({ page }) => {
  let release!: () => void;
  const gate = new Promise<void>((resolve) => { release = resolve; });
  await page.route("**/data/konya/temporal.json", async (route) => { await gate; await route.continue(); });
  await page.goto("/dashboard");
  await expect(page.locator('.analysis-activity li[data-state="current"]')).toContainText("Loading temporal evidence");
  await expect(page.locator("#mode-panel")).toHaveCount(0);
  await expect(page.locator('.analysis-activity li[data-state="pending"]')).toHaveCount(4);
  release();
  await ready(page);
});

test("missing package displays an honest error and can retry", async ({ page }) => {
  test.info().annotations.push({ type: "expected-http-error", description: "Deliberate missing package" });
  await page.route("**/data/konya/manifest.json", (route) => route.fulfill({ status: 404, body: "" }));
  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { name: "Evidence package unavailable" })).toBeVisible();
  await expect(page.locator("#mode-panel")).toHaveCount(0);
  await page.unroute("**/data/konya/manifest.json");
  await page.getByRole("button", { name: "Retry local package" }).click();
  await ready(page);
});

test("modified evidence is rejected by export hash validation", async ({ page }) => {
  await page.route("**/data/konya/fusion.json", async (route) => {
    const response = await route.fetch();
    const data = await response.json(); data.decision = "NO_CLEAR_CONCERN";
    await route.fulfill({ response, json: data });
  });
  await page.goto("/dashboard?mode=EXPERT");
  await expect(page.locator(".load-error")).toContainText("differs from its export");
  await expect(page.locator("#mode-panel")).toHaveCount(0);
});

test("reduced motion and unavailable WebGL retain usable country and demo flows", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await globeReady(page);
  await expect(page.locator(".intro-cta")).toHaveCSS("animation-name", "none");
  await expect(page.locator("[data-page-transition]")).toHaveCSS("transform", "none");
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (this: HTMLCanvasElement, ...args: Parameters<typeof original>) {
      if (/webgl/.test(String(args[0]))) return null;
      return original.apply(this, args);
    } as typeof original;
  });
  await page.goto("/scene");
  await expect(page.getByText("Earth view unavailable on this device")).toBeVisible();
  await select(page, "Syr", "Syria");
  await expect(page.getByRole("region", { name: "Area selection" })).toContainText("target deployment");
  await select(page, "Tur", "Turkey");
  await page.getByRole("link", { name: "Open validated demo", exact: true }).click();
  await ready(page);
});

for (const width of widths) test(`layouts stay within the viewport at ${width}px`, async ({ page }) => {
  test.setTimeout(120000);
  await page.setViewportSize({ width, height: width < 700 ? 844 : 1000 });
  for (const route of ["/", "/scene?country=760", "/dashboard", "/dashboard?mode=EXPERT&view=ml&useCase=SMART_FARM"]) {
    await page.goto(route);
    if (route.includes("dashboard")) await ready(page); else await globeReady(page);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    const dimensions = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, viewport: window.innerWidth }));
    expect(dimensions.scroll, route).toBeLessThanOrEqual(dimensions.viewport);
    if (width === 390) await page.screenshot({ path: `test-results/mobile-${route.includes("EXPERT") ? "expert" : route.includes("dashboard") ? "simple" : route.includes("scene") ? "scene" : "landing"}.png`, fullPage: true });
  }
});

test("main routes, open selector and scientific views pass serious/critical accessibility checks", async ({ page }) => {
  test.setTimeout(180000);
  for (const route of ["/", "/scene?country=760", "/dashboard", "/dashboard?mode=EXPERT&view=spatial", "/dashboard?mode=EXPERT&view=ml", "/dashboard?mode=EXPERT&view=provenance", "/dashboard?useCase=VERIFY_MY_FIELD", "/dashboard?useCase=SMART_FARM"]) {
    await page.goto(route);
    if (route.includes("dashboard")) await ready(page); else await globeReady(page);
    if (route.startsWith("/scene")) await page.getByRole("combobox", { name: "Find a country" }).fill("Syr");
    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
    expect(results.violations.filter((item) => ["serious", "critical"].includes(item.impact ?? "")).map(({ id, nodes }) => ({ route, id, nodes: nodes.map(({ target, failureSummary }) => ({ target, failureSummary })) }))).toEqual([]);
  }
});

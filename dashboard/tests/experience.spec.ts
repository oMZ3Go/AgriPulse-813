import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

async function settlePage(page: Page) {
  await expect(page.locator("[data-page-transition]")).toHaveCSS("opacity", "1");
  if (await page.locator("#mode-panel").count()) await expect(page.locator("#mode-panel")).toHaveCSS("opacity", "1");
}

test("globe, scene choice, modes, and all expert navigation work without runtime errors", async ({ page }) => {
  const runtimeErrors: string[] = [];
  const forbiddenRequests: string[] = [];
  page.on("pageerror", (error) => runtimeErrors.push(error.message));
  page.on("console", (message) => { if (message.type() === "error") runtimeErrors.push(message.text()); });
  page.on("request", (request) => { if (/outputs\/|fusion_summary|decision\.json|temporal_summary|stress_summary|spectral_summary/.test(request.url())) forbiddenRequests.push(request.url()); });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /From spectral/ })).toBeVisible();
  await expect(page.locator('[data-globe-ready="true"]')).toBeVisible({ timeout: 30000 });
  await expect(page.locator("canvas")).toBeVisible();
  await settlePage(page);
  await page.screenshot({ path: "test-results/landing-desktop.png", fullPage: true });
  await page.getByRole("link", { name: "Launch Demo" }).click();
  await expect(page).toHaveURL(/\/scene$/);
  await expect(page.locator('[data-globe-ready="true"]')).toBeVisible();
  await page.getByRole("button", { name: /Target deployment Syria and the Arab region/ }).click();
  await expect(page.getByRole("status")).toContainText("no validated AgriPulse analysis");
  await expect(page.getByRole("link", { name: "Open dashboard" })).toHaveCount(0);
  await page.getByRole("button", { name: "Konya, Turkey: Current validated demo scene", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Planet Tanager hyperspectral");
  await expect(page.getByRole("link", { name: "Open dashboard" })).toBeVisible();
  await page.waitForTimeout(900); // Capture the completed 850 ms geographic focus.
  await page.screenshot({ path: "test-results/scene-desktop.png", fullPage: true });
  await page.getByRole("link", { name: "Open dashboard" }).click();
  await expect(page.getByRole("heading", { name: "Your field, in perspective." })).toBeVisible();
  await expect(page.getByText("Automatic action is unavailable")).toBeVisible();
  await expect(page.locator("main")).not.toContainText(/NDMI percentile|Theil.Sen|\d+%/);
  await page.getByRole("button", { name: "Map & hotspots", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Know where to look." })).toBeVisible();
  await page.getByRole("button", { name: "Decision summary", exact: true }).click();
  await expect(page.getByRole("heading", { name: "A considered next step." })).toBeVisible();
  await page.getByRole("button", { name: "Field overview", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Your field, in perspective." })).toBeVisible();
  await settlePage(page);
  await page.screenshot({ path: "test-results/farmer-desktop.png", fullPage: true });
  await page.getByRole("tab", { name: "Expert Mode" }).click();
  await expect(page.getByRole("heading", { name: "Trace the evidence." })).toBeVisible();
  await settlePage(page);
  await page.screenshot({ path: "test-results/expert-desktop.png", fullPage: true });
  for (const [label, heading] of [["Spatial risk", "Spatial risk"], ["Temporal evidence", "Temporal evidence"], ["Decision fusion", "Decision fusion"], ["Hyperspectral value", "Hyperspectral value"], ["Methodology & limitations", "Know the limits of the signal."], ["Data provenance", "Keep the origin in view."]]) {
    await page.getByRole("navigation", { name: "Expert navigation" }).getByRole("button", { name: label, exact: true }).click();
    await expect(page.getByRole("heading", { level: 1, name: heading, exact: true })).toBeVisible();
  }
  await page.reload();
  await expect(page.getByRole("heading", { name: "Keep the origin in view." })).toBeVisible();
  await page.getByRole("tab", { name: "Expert Mode" }).focus();
  await page.keyboard.press("ArrowLeft");
  await expect(page.getByRole("tab", { name: "Farmer Mode" })).toBeFocused();
  await expect(page.getByRole("heading", { name: "Your field, in perspective." })).toBeVisible();
  expect(runtimeErrors).toEqual([]);
  expect(forbiddenRequests).toEqual([]);
});

test("desktop, laptop, tablet, and mobile layouts stay within the viewport", async ({ page }) => {
  test.setTimeout(180000);
  for (const width of [1440, 1280, 1024, 768, 390, 360]) {
    await page.setViewportSize({ width, height: width < 700 ? 844 : 1000 });
    for (const route of ["/", "/scene", "/dashboard", "/dashboard?mode=expert"]) {
      await page.goto(route);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      if (!route.includes("dashboard")) await expect(page.locator('[data-globe-ready="true"]')).toBeVisible();
      await settlePage(page);
      const dimensions = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, viewport: window.innerWidth }));
      expect(dimensions.scroll, `${route} overflows at ${width}px`).toBeLessThanOrEqual(dimensions.viewport);
      if (width === 390) await page.screenshot({ path: `test-results/mobile-${route.includes("expert") ? "expert" : route.includes("dashboard") ? "farmer" : route.includes("scene") ? "scene" : "landing"}.png`, fullPage: true });
    }
  }
});

test("main routes have no serious accessibility violations", async ({ page }) => {
  for (const route of ["/", "/scene", "/dashboard", "/dashboard?mode=expert", "/dashboard?mode=expert&view=provenance"]) {
    await page.goto(route);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    if (!route.includes("dashboard")) await expect(page.locator('[data-globe-ready="true"]')).toBeVisible();
    await settlePage(page);
    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
    expect(results.violations.filter((violation) => ["serious", "critical"].includes(violation.impact ?? "")).map(({ id, nodes }) => ({ route, id, nodes: nodes.map(({ target, failureSummary }) => ({ target, failureSummary })) }))).toEqual([]);
  }
});

test("reduced motion and unavailable WebGL retain a usable scene flow", async ({ page }) => {
  const runtimeErrors: string[] = [];
  page.on("pageerror", (error) => runtimeErrors.push(error.message));
  page.on("console", (message) => { if (message.type() === "error") runtimeErrors.push(message.text()); });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await expect(page.locator('[data-globe-ready="true"]')).toBeVisible();
  await expect(page.getByRole("button", { name: "Resume globe rotation" })).toBeDisabled();
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
  await page.getByRole("button", { name: /Current validated demo scene Konya, Turkey Planet Tanager/ }).click();
  await page.getByRole("link", { name: "Open dashboard" }).click();
  await expect(page.getByRole("heading", { name: "Your field, in perspective." })).toBeVisible();
  expect(runtimeErrors).toEqual([]);
});

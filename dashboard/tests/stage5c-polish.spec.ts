import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { project, unproject } from "../lib/map-projection";
import { countries, countryById } from "../lib/scenes";
import { selectedArea } from "../lib/aoi";

const tilePattern = "https://tile.openstreetmap.org/*/*/*.png";
// Automated interaction must not pan/zoom the public OSM service. These fixtures
// test loading/alignment/failure only, and are never shipped as geographic data.
const tileFixture = '<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256"><rect width="256" height="256" fill="#dedccc"/><path d="M0 70H256M90 0V256" stroke="#fff" stroke-width="8"/></svg>';
async function ready(page: Page) { await expect(page.locator('[data-complete="true"]')).toBeVisible(); }
async function fitBox(page: Page) {
  for (const [name, value] of [["West longitude", "32.48"], ["South latitude", "37.57"], ["East longitude", "32.52"], ["North latitude", "37.61"]]) await page.getByLabel(name, { exact: true }).fill(value);
  await page.getByRole("button", { name: "Fit selected area", exact: true }).click();
  // Tiles intentionally load only while the map itself is visible, not its toolbar.
  await page.locator(".aoi-map").scrollIntoViewIfNeeded();
}
test.beforeEach(async ({ page }) => {
  const errors: string[] = [], external: string[] = [];
  await page.route(tilePattern, (route) => route.fulfill({ contentType: "image/svg+xml", body: tileFixture }));
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
  page.on("request", (request) => { if (/^https?:/.test(request.url()) && !["127.0.0.1", "tile.openstreetmap.org"].includes(new URL(request.url()).hostname)) external.push(request.url()); });
  Object.assign(page, { polishAudit: { errors, external } });
});
test.afterEach(async ({ page }, info) => {
  const { errors, external } = (page as Page & { polishAudit: { errors: string[]; external: string[] } }).polishAudit;
  expect(external).toEqual([]);
  expect(info.annotations.some((a) => a.type === "tile-failure") ? errors.filter((e) => !e.includes("503")) : errors).toEqual([]);
});

test("Web Mercator uses known tile coordinates and round trips both hemispheres", () => {
  expect(project(0, 0)).toEqual([.5, .5]);
  expect(project(180, 0)).toEqual([1, .5]);
  expect(project(-180, 85.0511287798066)[1]).toBeCloseTo(0, 12);
  for (const [lng, lat] of [[32.5, 37.6], [38.5, 35], [-47, -16], [179, -80]]) {
    const actual = unproject(...project(lng, lat));
    expect(actual[0]).toBeCloseTo(lng, 10); expect(actual[1]).toBeCloseTo(lat, 10);
  }
});

test("detail basemap aligns BBOX drawing, pan, zoom, fit and attribution", async ({ page }) => {
  const scientific: string[] = [], tiles: string[] = [];
  page.on("request", (r) => { if (r.url().includes("/data/konya/")) scientific.push(r.url()); if (r.url().startsWith("https://tile.openstreetmap.org/")) tiles.push(r.url()); });
  await page.goto("/scene?country=792");
  const map = page.locator('[data-map-ready="true"]');
  await expect(map).toBeVisible();
  await expect(page.getByRole("link", { name: "Next: define your area" })).toHaveCount(1);
  await expect(page.locator(".earth-topline")).toContainText("03");
  await expect(page.locator(".earth-topline")).toContainText("EARTH / GEOGRAPHIC SELECTION");
  expect(tiles).toEqual([]);
  await fitBox(page);
  await expect(map).toHaveAttribute("data-basemap", "openstreetmap");
  await expect.poll(() => tiles.length).toBeGreaterThan(0);
  await expect.poll(() => page.locator('.context-tile[data-loaded="true"]').count()).toBeGreaterThan(0);
  await expect(page.getByRole("link", { name: "OpenStreetMap contributors" })).toHaveAttribute("href", "https://www.openstreetmap.org/copyright");
  await expect(page.locator(".map-attribution")).toContainText("not EO evidence");
  await map.scrollIntoViewIfNeeded();
  const frame = await map.evaluate((el) => ({ x: Number(el.getAttribute("data-map-x")), y: Number(el.getAttribute("data-map-y")), width: Number(el.getAttribute("data-map-width")), height: Number(el.getAttribute("data-map-height")) }));
  const bounds = (await map.boundingBox())!;
  await page.mouse.move(bounds.x + bounds.width * .3, bounds.y + bounds.height * .3);
  await page.mouse.down();
  await page.mouse.move(bounds.x + bounds.width * .7, bounds.y + bounds.height * .7, { steps: 6 });
  await page.mouse.up();
  const nw = unproject(frame.x + frame.width * .3, frame.y + frame.height * .3);
  const se = unproject(frame.x + frame.width * .7, frame.y + frame.height * .7);
  for (const [name, value] of [["West longitude", nw[0]], ["North latitude", nw[1]], ["East longitude", se[0]], ["South latitude", se[1]]]) expect(Number(await page.getByLabel(String(name), { exact: true }).inputValue())).toBeCloseTo(Number(value), 5);
  const west = await page.getByLabel("West longitude", { exact: true }).inputValue();
  await page.getByRole("button", { name: "Pan map", exact: true }).click();
  await map.press("ArrowRight");
  await expect(map).not.toHaveAttribute("data-map-x", String(frame.x));
  await page.mouse.move(bounds.x + bounds.width * .4, bounds.y + bounds.height * .5);
  await page.mouse.down(); await page.mouse.move(bounds.x + bounds.width * .5, bounds.y + bounds.height * .5, { steps: 4 }); await page.mouse.up();
  await page.getByRole("button", { name: "Zoom in", exact: true }).click();
  await expect(page.getByLabel("West longitude", { exact: true })).toHaveValue(west);
  await expect(page.getByTestId("aoi-rectangle")).toBeVisible();
  const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(result.violations.filter((v) => ["serious", "critical"].includes(v.impact ?? ""))).toEqual([]);
  await page.getByRole("button", { name: "Use this area", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("No EO assessment available for this area");
  expect(scientific).toEqual([]);
});

test("unavailable online tiles preserve manual AOI selection and confirmation", async ({ page }, info) => {
  info.annotations.push({ type: "tile-failure", description: "Deliberate basemap HTTP 503" });
  await page.route(tilePattern, (route) => route.fulfill({ status: 503, body: "Unavailable" }));
  await page.goto("/scene?country=792");
  await expect(page.locator('[data-map-ready="true"]')).toBeVisible();
  await fitBox(page);
  await expect(page.locator(".map-tile-status")).toContainText("Detailed map tiles unavailable");
  await expect(page.getByTestId("aoi-rectangle")).toBeVisible();
  await page.getByRole("button", { name: "Use this area", exact: true }).click();
  await expect(page.locator(".selected-site")).toContainText("AOI selected");
  await page.goto("/scene?country=792");
  await expect(page.locator('[data-map-ready="true"]')).toBeVisible();
  await fitBox(page);
  await expect(page.locator(".map-tile-status")).toContainText("Detailed map tiles unavailable");
  await page.getByRole("button", { name: "Reset map", exact: true }).click();
  await expect(page.locator(".aoi-map")).toHaveAttribute("data-basemap", "local");
  await page.route(tilePattern, (route) => route.fulfill({ contentType: "image/svg+xml", body: tileFixture }));
  await page.getByRole("button", { name: "Fit selected area", exact: true }).click();
  await page.locator(".aoi-map").scrollIntoViewIfNeeded();
  await expect.poll(() => page.locator('.context-tile[data-loaded="true"]').count()).toBeGreaterThan(0);
  await expect(page.locator(".map-tile-status")).toHaveCount(0);
  await page.getByRole("button", { name: "Use this area", exact: true }).click();
  await expect(page.locator(".selected-site")).toContainText("AOI selected");
});

test("globe markers follow the renderer on every moving frame without CSS drift", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator('[data-globe-ready="true"]')).toBeVisible();
  const canvas = (await page.locator("canvas").boundingBox())!;
  await page.evaluate(() => {
    const samples: { drift: number; x: number; scene: string }[] = [];
    Object.assign(window, { markerSamples: samples, sampleMarkers: true });
    const sample = () => {
      for (const anchor of document.querySelectorAll<HTMLElement>(".earth-marker-anchor")) {
        if (!anchor.getClientRects().length) continue;
        const match = anchor.style.transform.match(/translate\(([-\d.]+)px, ([-\d.]+)px\)/);
        if (!match) continue;
        const layer = anchor.parentElement!.getBoundingClientRect(), dot = anchor.querySelector(".marker-dot")!.getBoundingClientRect();
        samples.push({ drift: Math.hypot(dot.x + dot.width / 2 - layer.x - Number(match[1]), dot.y + dot.height / 2 - layer.y - Number(match[2])), x: Number(match[1]), scene: anchor.querySelector<HTMLElement>("button")!.dataset.scene! });
      }
      if ((window as unknown as { sampleMarkers: boolean }).sampleMarkers) requestAnimationFrame(sample);
    };
    requestAnimationFrame(sample);
  });
  await expect(page.locator(".globe-canvas")).toHaveAttribute("data-auto-rotating", "true");
  await expect.poll(() => page.evaluate(() => {
    const samples = (window as unknown as { markerSamples: { x: number; scene: string }[] }).markerSamples.filter((s) => s.scene === "konya");
    return samples.length ? Math.max(...samples.map((s) => s.x)) - Math.min(...samples.map((s) => s.x)) : 0;
  })).toBeGreaterThan(.1);
  await page.mouse.move(canvas.x + canvas.width * .4, canvas.y + canvas.height * .65);
  await page.mouse.down(); await page.mouse.move(canvas.x + canvas.width * .6, canvas.y + canvas.height * .55, { steps: 20 }); await page.mouse.up();
  await page.getByRole("button", { name: "Zoom globe in", exact: true }).click();
  await page.getByRole("button", { name: "Zoom globe out", exact: true }).click();
  await page.locator(".globe-region-controls").getByRole("button", { name: /Syria/ }).click();
  await expect(page.locator(".globe-canvas")).toHaveAttribute("data-focused-country", "760");
  await page.locator(".globe-region-controls").getByRole("button", { name: /Konya/ }).click();
  await expect(page.locator(".globe-canvas")).toHaveAttribute("data-focused-country", "792");
  await page.getByRole("button", { name: "Reset globe view", exact: true }).click();
  await page.setViewportSize({ width: 390, height: 1000 });
  await expect(page.locator(".globe-canvas")).toHaveAttribute("data-altitude", "1.9500");
  await page.setViewportSize({ width: 1440, height: 1000 });
  await expect(page.locator(".globe-canvas")).toHaveAttribute("data-altitude", "1.5000");
  const samples = await page.evaluate(() => { Object.assign(window, { sampleMarkers: false }); return (window as unknown as { markerSamples: { drift: number; x: number; scene: string }[] }).markerSamples; });
  for (const scene of ["konya", "syria"]) {
    const own = samples.filter((s) => s.scene === scene);
    expect(own.length).toBeGreaterThan(10);
    expect(Math.max(...own.map((s) => s.x)) - Math.min(...own.map((s) => s.x))).toBeGreaterThan(15);
    expect(Math.max(...own.map((s) => s.drift))).toBeLessThan(1);
  }
});

test("AOI center is an editable suggestion; capture cannot silently promote it or change science", async ({ page }) => {
  const writes: string[] = [];
  page.on("request", (request) => { if (!["GET", "HEAD"].includes(request.method())) writes.push(request.url()); });
  await page.goto("/dashboard?useCase=VERIFY_MY_FIELD"); await ready(page);
  const assessment = await page.locator("#take-action").innerText();
  await page.getByRole("button", { name: "Expert View", exact: true }).click();
  await expect(page.getByRole("button", { name: "Expert View", exact: true })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "ML spectral anomaly", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Experimental Spectral Anomaly ML");
  const mlEvidence = await page.locator("#mode-panel").innerText();
  await page.getByRole("button", { name: "Simple View", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Ground verification required");
  await expect(page.locator("#ground-longitude")).toHaveValue("");
  await page.getByRole("button", { name: "Use AOI center as starting point", exact: true }).click();
  expect(Number(await page.locator("#ground-longitude").inputValue())).toBeCloseTo(32.574039072555885, 10);
  await page.locator("#ground-crop_type").fill("Wheat");
  for (const [id, value] of [["observer_type", "FARMER"], ["plant_condition", "UNKNOWN"], ["soil_condition", "UNKNOWN"], ["recent_irrigation", "UNKNOWN"]]) await page.locator(`#ground-${id}`).selectOption(value);
  await page.locator("#ground-timestamp").fill("2026-01-09T09:30");
  await page.getByRole("button", { name: "Capture locally", exact: true }).click();
  await expect(page.locator("#ground-error-longitude")).toContainText("actual observation point");
  await expect(page.locator(".observation-summary")).toHaveCount(0);
  await page.getByRole("checkbox", { name: "I checked that these coordinates are the actual observation point." }).check();
  await page.getByRole("button", { name: "Capture locally", exact: true }).click();
  await expect(page.locator(".observation-summary")).toContainText("SELF_REPORTED");
  await expect.poll(() => page.locator("#take-action").innerText()).toBe(assessment);
  await expect(page.locator(".evidence-level")).toHaveText("EO_ENHANCED");
  await expect(page.locator(".availability")).toContainText("UNAVAILABLE");
  await page.getByRole("button", { name: "Edit observation", exact: true }).click();
  await page.locator("#ground-longitude").fill("34");
  await page.getByRole("button", { name: "Capture locally", exact: true }).click();
  await expect(page.locator("#ground-error-longitude")).toContainText("inside the selected area");
  await page.getByRole("button", { name: "Expert View", exact: true }).click();
  await expect(page.getByRole("button", { name: "Expert View", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Experimental Spectral Anomaly ML");
  await expect.poll(() => page.locator("#mode-panel").innerText()).toBe(mlEvidence);
  expect(writes).toEqual([]);
});

test("sticky workspace controls, table alignment and bounded figures fit EN/AR at target widths", async ({ page }) => {
  test.setTimeout(180000);
  await page.emulateMedia({ reducedMotion: "reduce" });
  for (const language of ["en", "ar"]) for (const width of [1440, 1280, 1024, 768, 390, 360]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/dashboard?mode=EXPERT&view=temporal"); await ready(page);
    if (language === "ar" && await page.locator("html").getAttribute("lang") !== "ar") await page.getByRole("button", { name: "العربية", exact: true }).click();
    await page.locator(".workspace-footer").scrollIntoViewIfNeeded();
    const header = (await page.locator(".workspace-header").boundingBox())!, toolbar = (await page.locator(".workspace-toolbar").boundingBox())!;
    expect(toolbar.y).toBeCloseTo(header.height, 0);
    await expect(page.locator("#workspace-use-case")).toBeInViewport();
    await expect(page.locator('.workspace-toolbar .mode-switch button').first()).toBeInViewport();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    const figures = await page.locator(".scientific-figure img").evaluateAll((images) => images.map((el) => ({ width: el.getBoundingClientRect().width, height: el.getBoundingClientRect().height, parent: el.parentElement!.getBoundingClientRect().width })));
    for (const figure of figures) { expect(figure.height).toBeLessThanOrEqual(540); expect(figure.width).toBeLessThanOrEqual(figure.parent); }
    await page.locator(".evidence-table").scrollIntoViewIfNeeded();
    const cells = await page.locator(".evidence-table").evaluate((table) => Array.from(table.querySelectorAll("tr")).map((tr) => Array.from(tr.children).map((td) => ({ x: td.getBoundingClientRect().x, width: td.getBoundingClientRect().width }))));
    for (const row of cells.slice(1)) row.forEach((cell, i) => { expect(cell.x).toBeCloseTo(cells[0][i].x, 1); expect(cell.width).toBeCloseTo(cells[0][i].width, 1); });
    const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
    expect(result.violations.filter((v) => ["serious", "critical"].includes(v.impact ?? "")).map((v) => ({ id: v.id, targets: v.nodes.map((n) => n.target) }))).toEqual([]);
    await page.screenshot({ path: `test-results/polish-${language}-temporal-${width}.png`, fullPage: true });
  }
});

test("landing globe only browses; the single area CTA starts the selected product flow", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/?mode=EXPERT&useCase=VERIFY_MY_FIELD");
  const globe = page.locator('[data-globe-ready="true"]');
  await expect(globe).toBeVisible();
  const bounds = (await page.locator("canvas").boundingBox())!;
  const scroll = await page.evaluate(() => window.scrollY);
  await page.mouse.move(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2);
  await expect(globe).toHaveAttribute("data-hover-country", /\d+/);
  await page.mouse.click(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2);
  await expect(page.locator(".selected-country-next")).toContainText("Browsing country");
  expect(await page.evaluate(() => window.scrollY)).toBe(scroll);
  await expect(page.locator("#area-selection,.workflow-navigation")).toHaveCount(0);
  await page.getByRole("combobox", { name: "Find a country" }).fill("Syria");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/country=760/);
  await expect(page.locator("#area-selection")).toHaveCount(0);
  await expect(page.locator(".product-section").getByRole("link")).toHaveCount(0);
  await expect(page.locator(".header-nav").getByRole("link", { name: "Explore Earth", exact: true })).toHaveAttribute("href", "#country-selection");
  await expect(page.getByRole("link", { name: /Continue/ })).toHaveCount(0);
  const entry = page.getByRole("link", { name: "Choose an area", exact: true });
  await expect(entry).toHaveCount(1);
  await expect(entry.locator("svg")).toHaveCount(1);
  await entry.click();
  await expect(page).toHaveURL(/\/scene\?useCase=VERIFY_MY_FIELD&mode=EXPERT&country=760/);
  await expect(page.locator(".workflow-navigation")).toBeVisible();
  await expect(page.locator("#area-selection")).toBeVisible();
});

test("workflow steps focus their sections, explain prerequisites and share aligned semantic headers", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/scene");
  const nav = page.getByRole("navigation", { name: "Your selection", exact: true });
  await expect(nav.getByRole("button")).toHaveCount(5);
  const blocked = nav.getByRole("button", { name: /04 Choose AOI/ });
  await expect(blocked).toHaveAttribute("aria-disabled", "true");
  await blocked.focus(); await page.keyboard.press("Enter");
  await expect(page.locator("#workflow-step-help")).toHaveText("Choose a country before defining your area.");
  for (const [name, target] of [["01 Choose your purpose", "purpose-selection"], ["02 Choose your view", "view-selection"], ["03 Choose country", "country-selection"]]) {
    const button = nav.getByRole("button", { name: new RegExp(name) });
    await button.focus(); await page.keyboard.press("Enter");
    await expect(page.locator(`#${target}`)).toBeFocused();
    await expect(button).toHaveAttribute("aria-current", "step");
  }
  await expect(nav.locator('[data-step="1"]')).toHaveAttribute("data-done", "true");
  const purpose = (await page.locator('#purpose-selection .step-number').boundingBox())!;
  const country = (await page.locator('#country-selection .step-number').boundingBox())!;
  expect(purpose.y).toBeCloseTo(country.y, 0);
  expect(purpose.height).toBe(country.height);
  await expect(page.locator('#country-selection .workflow-step-heading')).toContainText("03EARTH / GEOGRAPHIC SELECTION");
  await page.getByRole("combobox", { name: "Find a country" }).fill("Syr");
  await page.keyboard.press("ArrowDown"); await page.keyboard.press("Enter");
  await nav.getByRole("button", { name: /04 Choose AOI/ }).click();
  await expect(page.locator("#area-selection")).toBeFocused();
  await nav.getByRole("button", { name: /05 Confirm area/ }).focus(); await page.keyboard.press("Enter");
  await expect(page.locator("#workflow-step-help")).toHaveText("Draw a box or enter four valid coordinates before confirmation.");
  for (const [name, value] of [["West longitude", "36"], ["South latitude", "34"], ["East longitude", "38"], ["North latitude", "36"]]) await page.getByLabel(name, { exact: true }).fill(value);
  await nav.getByRole("button", { name: /05 Confirm area/ }).focus(); await page.keyboard.press("Enter");
  await expect(page.locator("#area-confirmation")).toBeFocused();
  await expect(nav.locator('[data-step="4"]')).toHaveAttribute("data-done", "true");
  const accents = await page.locator(".workflow-step-heading").evaluateAll((els) => els.map((el) => getComputedStyle(el).color));
  expect(new Set(accents).size).toBe(5);
  await expect(page.locator("html")).toHaveCSS("scroll-behavior", "auto");
  const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(result.violations.filter((v) => ["serious", "critical"].includes(v.impact ?? ""))).toEqual([]);
});

test("country 376 cannot be searched, keyboard selected, globe picked or restored as AOI context", async ({ page }) => {
  expect(countries.some((country) => country.id === "376")).toBe(false);
  expect(countryById("376")).toBeNull();
  expect(selectedArea("376", "34,30,36,33")).toBeNull();
  const scientific: string[] = [];
  page.on("request", (r) => { if (r.url().includes("/data/konya/")) scientific.push(r.url()); });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/scene?country=376");
  await expect(page.locator("#area-selection")).toHaveCount(0);
  await expect(page.locator(".selected-country-next")).toHaveCount(0);
  for (const query of ["Israel", "إسرائيل"]) {
    await page.getByRole("combobox", { name: "Find a country" }).fill(query);
    await expect(page.getByRole("option")).toHaveCount(0);
    await page.keyboard.press("ArrowDown"); await page.keyboard.press("Enter");
    await expect(page.locator("#area-selection")).toHaveCount(0);
  }
  await page.goto("/scene?country=760");
  const globe = page.locator('[data-globe-ready="true"]');
  await expect(globe).toHaveAttribute("data-focused-country", "760");
  await expect(globe).toHaveAttribute("data-altitude", "1.5000");
  const canvas = (await page.locator("canvas").boundingBox())!;
  // Project a point inside the untouched Natural Earth polygon onto the focused globe.
  const phi = 31.5 * Math.PI / 180, center = 35.0085 * Math.PI / 180, delta = (34.9 - 38.5234) * Math.PI / 180;
  const depth = 2.5 - (Math.cos(phi) * Math.cos(center) * Math.cos(delta) + Math.sin(phi) * Math.sin(center));
  const scale = Math.min(canvas.width, canvas.height) / (2 * Math.tan(Math.PI / 6));
  const x = canvas.x + canvas.width / 2 + scale * Math.cos(phi) * Math.sin(delta) / depth;
  const y = canvas.y + canvas.height / 2 - scale * (Math.sin(phi) * Math.cos(center) - Math.cos(phi) * Math.cos(delta) * Math.sin(center)) / depth;
  await page.mouse.move(x, y);
  await expect(globe).not.toHaveAttribute("data-hover-country", "376");
  await expect(page.locator(".globe-hover-label")).toHaveCount(0);
  await page.mouse.click(x, y);
  await expect(page).toHaveURL(/country=760/);
  await expect(globe).toHaveAttribute("data-focused-country", "760");
  await page.goto("/dashboard?aoi=custom&country=376&bbox=34,30,36,33");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Invalid area");
  expect(scientific).toEqual([]);
});

test("manual Spain AOI enters Explore Earth in one action and remains truthful across mode and reload", async ({ page }) => {
  const scientific: string[] = [];
  page.on("request", (r) => { if (r.url().includes("/data/konya/")) scientific.push(r.url()); });
  await page.goto("/scene?country=724&useCase=EXPLORE_EARTH");
  await expect(page.getByRole("button", { name: "Apply coordinates", exact: true })).toHaveCount(0);
  for (const [name, value] of [["West longitude", "-4"], ["South latitude", "39"], ["East longitude", "-3"], ["North latitude", "40"]]) await page.getByLabel(name, { exact: true }).fill(value);
  await page.getByRole("button", { name: "Use this area", exact: true }).click();
  await expect(page).toHaveURL(/aoi=custom&country=724&bbox=-4%2C39%2C-3%2C40/);
  await expect(page.locator(".selected-site")).toContainText("AOI selected");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("No EO assessment available for this area");
  await page.getByRole("button", { name: "Expert View", exact: true }).click();
  await expect(page.locator(".workspace")).toHaveAttribute("data-mode", "expert");
  await page.reload();
  await expect(page.locator(".selected-site")).toContainText("-4,39,-3,40");
  await expect(page.locator(".selected-site")).toContainText("Live global EO processing has not yet been executed");
  await expect(page.getByRole("link", { name: "Edit area", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Open validated Konya demo", exact: true })).toBeVisible();
  await expect(page.locator(".assessment-card,.scientific-figure,.analysis-activity")).toHaveCount(0);
  expect(scientific).toEqual([]);
});

test("Expert theme consistently turns technical controls and evidence blue; Simple retains green", async ({ page }) => {
  await page.goto("/dashboard"); await ready(page);
  async function color(selector: string, property: "color" | "backgroundColor") {
    return page.locator(selector).first().evaluate((el, prop) => getComputedStyle(el)[prop].match(/\d+/g)!.slice(0, 3).map(Number), property);
  }
  const simple = await color('.sidebar-nav-item[aria-current="page"]', "backgroundColor");
  expect(simple[1]).toBeGreaterThan(simple[0]); expect(simple[1]).toBeGreaterThan(simple[2]);
  await page.getByRole("button", { name: "Expert View", exact: true }).click();
  await expect(page.locator(".workspace")).toHaveAttribute("data-mode", "expert");
  for (const selector of ['.sidebar-nav-item[aria-current="page"]', '.mode-switch [aria-pressed="true"]', '.expert-overview-grid .evidence-module', '.workspace-toolbar', '.language-switch [aria-pressed="true"]', '.change-scene']) {
    await expect.poll(async () => {
      const [r, g, b] = await color(selector, "backgroundColor");
      return b > g && g > r;
    }).toBe(true);
  }
  await page.getByRole("button", { name: "Temporal evidence", exact: true }).click();
  await expect(page.locator(".evidence-table")).toBeVisible();
  for (const selector of [".evidence-table thead th", ".scientific-figure"]) {
    const blue = await color(selector, "backgroundColor");
    expect(blue[2]).toBeGreaterThan(blue[1]);
  }
  await page.getByRole("button", { name: "Simple View", exact: true }).click();
  await expect(page.locator(".workspace")).toHaveAttribute("data-mode", "simple");
  await expect.poll(() => color('.sidebar-nav-item[aria-current="page"]', "backgroundColor")).toEqual(simple);
});

test("initial globe and Russia Syria Turkey focus stay contained through zoom and resize", async ({ page }) => {
  test.setTimeout(90000);
  await page.emulateMedia({ reducedMotion: "reduce" });
  for (const country of [null, "643", "760", "792"]) {
    await page.goto(country ? `/scene?country=${country}` : "/");
    for (const width of [1440, 768, 390]) {
      await page.setViewportSize({ width, height: 1000 });
      const globe = page.locator('[data-globe-ready="true"]');
      await expect(globe).toBeVisible();
      if (country) await expect(globe).toHaveAttribute("data-focused-country", country);
      for (let i = 0; i < 6; i++) {
        const zoom = page.getByRole("button", { name: "Zoom globe in", exact: true });
        if (await zoom.isEnabled()) await zoom.click();
      }
      await expect(globe).toHaveAttribute("data-altitude", "0.9500");
      await globe.screenshot({ path: `test-results/globe-close-${country ?? "initial"}-${width}.png` });
      await page.getByRole("button", { name: "Zoom globe out", exact: true }).click();
      await page.getByRole("button", { name: "Reset globe view", exact: true }).click();
      const outer = (await globe.boundingBox())!, canvas = (await page.locator("canvas").boundingBox())!, controls = (await page.locator(".globe-tools").boundingBox())!;
      expect(canvas.y - outer.y).toBeGreaterThanOrEqual(15);
      expect(canvas.y + canvas.height).toBeLessThanOrEqual(controls.y);
      expect(canvas.x).toBeGreaterThanOrEqual(outer.x - 1);
      expect(canvas.x + canvas.width).toBeLessThanOrEqual(outer.x + outer.width + 1);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
      await page.mouse.move(canvas.x + canvas.width / 2, canvas.y + canvas.height / 2);
      if (await page.locator(".globe-hover-label").count()) {
        const label = (await page.locator(".globe-hover-label").boundingBox())!;
        expect(label.y).toBeGreaterThanOrEqual(outer.y);
        expect(label.x).toBeGreaterThanOrEqual(outer.x);
        expect(label.x + label.width).toBeLessThanOrEqual(outer.x + outer.width);
      }
      await globe.screenshot({ path: `test-results/globe-fit-${country ?? "initial"}-${width}.png` });
    }
  }
});

test("landing idle rotation pauses for interaction and focus, resumes after rest, and respects reduced motion", async ({ page }) => {
  await page.goto("/");
  const globe = page.locator('[data-globe-ready="true"]');
  await expect(globe).toHaveAttribute("data-auto-rotating", "true");
  const marker = page.locator('.earth-marker-anchor').first();
  const initial = await marker.getAttribute("style");
  await expect.poll(() => marker.getAttribute("style")).not.toBe(initial);
  const canvas = (await page.locator("canvas").boundingBox())!;
  await page.mouse.move(canvas.x + canvas.width / 2, canvas.y + canvas.height / 2);
  await page.mouse.down();
  await expect(globe).toHaveAttribute("data-auto-rotating", "false");
  await page.mouse.move(canvas.x + canvas.width * .6, canvas.y + canvas.height * .4, { steps: 8 });
  await page.mouse.up();
  await expect(globe).toHaveAttribute("data-auto-rotating", "true", { timeout: 9000 });
  await page.locator(".globe-region-controls").getByRole("button", { name: /Syria/ }).click();
  await expect(globe).toHaveAttribute("data-focused-country", "760");
  await expect(globe).toHaveAttribute("data-auto-rotating", "false");
  await expect(page.locator("#area-selection")).toHaveCount(0);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await expect(globe).toHaveAttribute("data-auto-rotating", "false");
  await page.goto("/scene");
  await expect(globe).toHaveAttribute("data-auto-rotating", "false");
});

test("manual coordinates immediately drive overlay metadata and validity with one coherent map toolbar", async ({ page }) => {
  await page.goto("/scene?country=760&mode=EXPERT");
  const toolbar = page.getByRole("group", { name: "Map tools", exact: true });
  await expect(toolbar).toBeVisible();
  const rows = await toolbar.getByRole("button").evaluateAll((buttons) => buttons.map((button) => Math.round(button.getBoundingClientRect().y)));
  expect(new Set(rows).size).toBe(1);
  for (const [name, value] of [["West longitude", "36"], ["South latitude", "34"], ["East longitude", "38"], ["North latitude", "36"]]) await page.getByLabel(name, { exact: true }).fill(value);
  const rectangle = page.getByTestId("aoi-rectangle");
  await expect(rectangle).toBeVisible();
  const width = Number(await rectangle.getAttribute("width"));
  const metadata = await page.locator(".area-metadata").innerText();
  await page.getByLabel("East longitude", { exact: true }).fill("39");
  await expect.poll(async () => Number(await rectangle.getAttribute("width"))).toBeCloseTo(width * 1.5, 10);
  await expect(page.locator(".area-metadata")).not.toHaveText(metadata);
  await expect(page.locator(".area-metadata")).toContainText("35.000000° N, 37.500000° E");
  await page.getByLabel("West longitude", { exact: true }).fill("");
  await expect(page.locator("#bbox-error")).toBeVisible();
  await expect(rectangle).toHaveCount(0);
  await expect(page.locator(".area-metadata")).toHaveCount(0);
  await page.getByRole("button", { name: "Use this area", exact: true }).click();
  await expect(page).toHaveURL(/\/scene\?/);
  await page.getByLabel("West longitude", { exact: true }).fill("36");
  await expect(rectangle).toBeVisible();
  await expect(page.locator("#bbox-error")).toHaveCount(0);
  await toolbar.getByRole("button", { name: "Pan map", exact: true }).click();
  await expect(page.locator(".aoi-map")).toHaveClass(/pan/);
  await toolbar.getByRole("button", { name: "Clear selection", exact: true }).click();
  await expect(rectangle).toHaveCount(0);
  await expect(toolbar.getByRole("button", { name: "Draw a box", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("button", { name: "Use this area", exact: true })).toBeDisabled();
});

test("polished headers and map toolbar fit every target width in EN and AR", async ({ page }) => {
  test.setTimeout(180000);
  await page.emulateMedia({ reducedMotion: "reduce" });
  for (const language of ["en", "ar"]) for (const width of [1440, 1280, 1024, 768, 390, 360]) {
    await page.setViewportSize({ width, height: 1000 });
    for (const url of ["/", "/scene?country=760&mode=EXPERT", "/dashboard?mode=EXPERT"]) {
      await page.goto(url);
      if (await page.locator("html").getAttribute("lang") !== language) await page.getByRole("button", { name: language === "ar" ? "العربية" : "English", exact: true }).click();
      const header = page.locator("header");
      const bounds = (await header.boundingBox())!;
      const controls = await header.locator("a,button").evaluateAll((els) => els.filter((el) => el.getClientRects().length).map((el) => ({ left: el.getBoundingClientRect().left, right: el.getBoundingClientRect().right })));
      for (const control of controls) { expect(control.left).toBeGreaterThanOrEqual(bounds.x - 1); expect(control.right).toBeLessThanOrEqual(bounds.x + bounds.width + 1); }
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
      if (url.startsWith("/scene")) {
        await expect(page.locator(".map-toolbar")).toBeVisible();
        await expect(page.locator(".map-toolbar")).toHaveAttribute("dir", language === "ar" ? "rtl" : "ltr");
        if (language === "ar") {
          await expect(page.locator('.map-toolbar button[aria-label="ارسم مستطيلاً"] span')).toHaveText("ارسم");
          await expect(page.locator(".map-toolbar")).not.toContainText("???");
        }
        if (width >= 768) {
          const rows = await page.locator(".map-toolbar button").evaluateAll((els) => els.map((el) => Math.round(el.getBoundingClientRect().y)));
          expect(new Set(rows).size).toBe(1);
        }
        if ([1440, 360].includes(width)) {
          const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
          expect(result.violations.filter((v) => ["serious", "critical"].includes(v.impact ?? ""))).toEqual([]);
          await page.screenshot({ path: `test-results/final-${language}-scene-${width}.png`, fullPage: true });
        }
      }
    }
  }
});

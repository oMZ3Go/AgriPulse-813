import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { readFile } from "node:fs/promises";
import { utcTimestamp, validateObservation, emptyObservation } from "../lib/observation";

const custom = "/dashboard?aoi=custom&country=760&bbox=36,34,38,36";
const fields = ["West longitude", "South latitude", "East longitude", "North latitude"];
async function coordinates(page: Page, values = ["36", "34", "38", "36"]) {
  for (let i = 0; i < 4; i++) await page.getByLabel(fields[i], { exact: true }).fill(values[i]);
}
async function formValues(page: Page, lng = "37", lat = "35") {
  await page.locator("#ground-crop_type").fill("Wheat");
  await page.locator("#ground-observer_type").selectOption("FARMER");
  await page.locator("#ground-plant_condition").selectOption("MILD_WILTING");
  await page.locator("#ground-soil_condition").selectOption("DRY");
  await page.locator("#ground-recent_irrigation").selectOption("NO");
  await page.locator("#ground-timestamp").fill("2026-01-09T09:30");
  await page.locator("#ground-longitude").fill(lng);
  await page.locator("#ground-latitude").fill(lat);
}
async function ready(page: Page) { await expect(page.locator('[data-complete="true"]')).toBeVisible(); }

test.beforeEach(async ({ page }) => {
  const errors: string[] = [], external: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
  page.on("response", (response) => { if (response.status() >= 400) errors.push(`HTTP ${response.status()} ${response.url()}`); });
  page.on("request", (request) => { if (/^https?:/.test(request.url()) && new URL(request.url()).hostname !== "127.0.0.1") external.push(request.url()); });
  Object.assign(page, { stage5cAudit: { errors, external } });
});
test.afterEach(async ({ page }, info) => {
  const audit = (page as Page & { stage5cAudit: { errors: string[]; external: string[] } }).stage5cAudit;
  expect(audit.external, "No external runtime requests").toEqual([]);
  expect(info.annotations.some((a) => a.type === "expected-http-error") ? audit.errors.filter((e) => !/404/.test(e)) : audit.errors, "No unexpected runtime errors").toEqual([]);
});

test("ordered flow, map drawing, clearing, redrawing and confirmation work", async ({ page }) => {
  await page.goto("/scene");
  await page.getByRole("button", { name: /Verify My Field/ }).click();
  await page.getByRole("button", { name: "Expert View", exact: true }).click();
  await page.getByRole("link", { name: "Next: choose a country" }).click();
  await page.getByRole("combobox", { name: "Find a country" }).fill("Syr");
  await page.getByRole("option", { name: "Syria", exact: true }).click();
  await page.getByRole("link", { name: "Next: define your area" }).last().click();
  const map = page.locator('[data-map-ready="true"]');
  await expect(map).toBeVisible();
  await map.scrollIntoViewIfNeeded();
  const bounds = (await map.boundingBox())!;
  await page.mouse.move(bounds.x + bounds.width * .35, bounds.y + bounds.height * .3);
  await page.mouse.down();
  await page.mouse.move(bounds.x + bounds.width * .6, bounds.y + bounds.height * .65, { steps: 8 });
  await page.mouse.up();
  await expect(page.getByTestId("aoi-rectangle")).toBeVisible();
  const values = await Promise.all(fields.map((name) => page.getByLabel(name, { exact: true }).inputValue()));
  const [west, south, east, north] = values.map(Number);
  expect(west).toBeLessThan(east); expect(south).toBeLessThan(north);
  expect(west).toBeGreaterThanOrEqual(-180); expect(north).toBeLessThanOrEqual(90);
  await page.getByRole("button", { name: "Clear selection", exact: true }).click();
  await expect(page.getByTestId("aoi-rectangle")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Use this area", exact: true })).toBeDisabled();
  await coordinates(page);
  await page.getByRole("button", { name: "Redraw selection", exact: true }).click();
  await expect(page.getByLabel("West longitude", { exact: true })).toHaveValue("");
  await coordinates(page);
  await expect(page.locator('.workflow-progress [aria-current="step"]')).toContainText("Confirm area");
  await page.getByRole("button", { name: "Use this area", exact: true }).click();
  await expect(page).toHaveURL(/useCase=VERIFY_MY_FIELD&mode=EXPERT.*aoi=custom/);
  await expect(page.getByRole("heading", { name: "Ground Observation", exact: true })).toBeVisible();
  await expect(page.locator("#ground-observation")).toContainText("36,34,38,36");
  await expect(page.locator(".assessment-card")).toHaveCount(0);
});

test("invalid manual boxes cannot enter workspace; edits update the pending selection", async ({ page }) => {
  await page.goto("/scene?country=760");
  for (const box of [["", "34", "38", "36"], ["NaN", "34", "38", "36"], ["36", "34", "181", "36"], ["38", "34", "36", "36"], ["36", "36", "38", "36"], ["36", "-91", "38", "36"], ["1e2", "34", "38", "36"]]) {
    await coordinates(page, box);
    await page.getByRole("button", { name: "Use this area", exact: true }).click();
    await expect(page.locator("#bbox-error")).toBeVisible();
    await expect(page).toHaveURL(/\/scene\?/);
    await expect(page.getByTestId("aoi-rectangle")).toHaveCount(0);
  }
  await coordinates(page);
  await expect(page.getByTestId("aoi-rectangle")).toBeVisible();
  await page.getByLabel("West longitude", { exact: true }).fill("39");
  await expect(page.getByTestId("aoi-rectangle")).toHaveCount(0);
  await page.getByRole("button", { name: "Use this area", exact: true }).click();
  await expect(page.locator("#bbox-error")).toBeVisible();
  await page.getByRole("combobox", { name: "Find a country" }).fill("Braz");
  await page.getByRole("option", { name: "Brazil", exact: true }).click();
  await expect(page.getByLabel("West longitude", { exact: true })).toHaveValue("");
  await coordinates(page, ["-48", "-17", "-46", "-15"]);
  await expect(page.locator(".area-metadata")).toContainText("16.000000° S, 47.000000° W");
});

for (const useCase of ["EXPLORE_EARTH", "VERIFY_MY_FIELD", "SMART_FARM"]) test(`custom AOI remains unprocessed in ${useCase} and survives view/reload`, async ({ page }) => {
  const scientificRequests: string[] = [];
  page.on("request", (request) => { if (request.url().includes("/data/konya/")) scientificRequests.push(request.url()); });
  await page.goto(`${custom}&useCase=${useCase}`);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("No EO assessment available for this area");
  await expect(page.locator(".selected-site")).toContainText("Live global EO processing has not yet been executed");
  await page.getByRole("button", { name: "Expert View", exact: true }).click();
  await expect(page).toHaveURL(/bbox=36%2C34%2C38%2C36/);
  await page.reload();
  await expect(page.getByRole("button", { name: "Expert View", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".analysis-activity,.assessment-card,.availability")).toHaveCount(0);
  if (useCase === "SMART_FARM") await expect(page.locator("#site-monitoring")).toContainText("IoT NOT CONNECTED");
  if (useCase === "VERIFY_MY_FIELD") await expect(page.locator("#ground-observation")).toBeVisible();
  expect(scientificRequests).toEqual([]);
});

test("malformed AOI links never silently load the validated package", async ({ page }) => {
  const requests: string[] = [];
  page.on("request", (r) => { if (r.url().includes("/data/konya/")) requests.push(r.url()); });
  for (const query of ["aoi=custom", "aoi=custom&country=760&bbox=1,2,1,4", "aoi=unknown", "aoi=konya&bbox=1,2,3,4", "country=760"]) {
    await page.goto(`/dashboard?${query}`);
    await expect(page.getByRole("heading", { name: "Invalid area", exact: true, level: 1 })).toBeVisible();
  }
  expect(requests).toEqual([]);
});

test("validated package accepts only the exported LF or Windows CRLF transport", async ({ page }) => {
  for (const ending of ["\n", "\r\n"]) {
    await page.route("**/data/konya/*.json", async (route) => {
      const response = await route.fetch();
      const body = (await response.text()).replaceAll("\r\n", "\n").replaceAll("\n", ending);
      await route.fulfill({ response, body });
    });
    await page.goto("/dashboard");
    await ready(page);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Ground verification required");
    await page.unroute("**/data/konya/*.json");
  }
});

test("validated shortcut uses the exact footprint and action panel opens observation", async ({ page }) => {
  await page.goto("/scene?country=792");
  await page.getByRole("link", { name: "Use validated Konya area", exact: true }).click();
  await ready(page);
  await page.locator(".validated-footprint summary").click();
  await expect(page.getByTestId("validated-bbox")).toHaveText("32.44227196464563,37.51375341016496,32.70580618046614,37.69491765950834");
  const action = page.getByRole("region", { name: "Take action", exact: true });
  await expect(action).toContainText("Automatic intervention: not allowed");
  await expect(action).toContainText("does not independently diagnose drought or disease");
  await action.getByRole("link", { name: "Continue to Ground Observation", exact: true }).click();
  await expect(page.locator("#ground-observation")).toBeInViewport();
  await formValues(page, "32.5", "37.6");
  await page.getByRole("button", { name: "Capture locally", exact: true }).click();
  await expect(page.locator(".observation-summary")).toContainText("SELF_REPORTED");
  await expect(page.locator(".availability")).toContainText("UNAVAILABLE");
  await expect(page.locator(".evidence-level")).toHaveText("EO_ENHANCED");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Ground verification required");
});

test("observation validates required fields, point, future time and irrigation order", async ({ page }) => {
  await page.goto(`${custom}&useCase=VERIFY_MY_FIELD`);
  await page.getByRole("button", { name: "Capture locally", exact: true }).click();
  await expect(page.locator("#ground-crop_type")).toBeFocused();
  await expect(page.locator('#ground-observation [aria-invalid="true"]')).toHaveCount(8);
  await formValues(page, "500", "35");
  await page.getByRole("button", { name: "Capture locally", exact: true }).click();
  await expect(page.locator("#ground-error-longitude")).toHaveText("Enter a valid point inside the selected area.");
  await page.locator("#ground-longitude").fill("40");
  await page.getByRole("button", { name: "Capture locally", exact: true }).click();
  await expect(page.locator("#ground-error-longitude")).toBeVisible();
  await page.locator("#ground-longitude").fill("37");
  await page.locator("#ground-timestamp").fill("2099-01-01T12:00");
  await page.getByRole("button", { name: "Capture locally", exact: true }).click();
  await expect(page.locator("#ground-error-timestamp")).toBeVisible();
  await page.locator("#ground-timestamp").fill("2026-01-09T09:30");
  await page.locator("#ground-recent_irrigation").selectOption("YES");
  await page.locator("#ground-recent_irrigation_timestamp").fill("2026-01-10T09:30");
  await page.getByRole("button", { name: "Capture locally", exact: true }).click();
  await expect(page.locator("#ground-error-recent_irrigation_timestamp")).toBeVisible();
  await page.locator("#ground-recent_irrigation_timestamp").fill("2026-01-08T08:00");
  await page.getByRole("button", { name: "Capture locally", exact: true }).click();
  await expect(page.locator(".observation-summary")).toContainText("SELF_REPORTED");
  await expect(page.locator(".observation-summary")).toContainText("Persistent storage / backend integration is not yet enabled");
});

test("local observation exports a truthful Stage 4.7-shaped draft and clears on reload", async ({ page }) => {
  await page.goto(`${custom}&useCase=VERIFY_MY_FIELD`);
  await formValues(page);
  await page.locator("#ground-photo_reference").fill("field-photo.jpg");
  await page.getByRole("button", { name: "Capture locally", exact: true }).click();
  await page.getByRole("button", { name: "Expert View", exact: true }).click();
  await expect(page.locator(".observation-summary")).toContainText("SELF_REPORTED");
  const downloadEvent = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export JSON draft", exact: true }).click();
  const download = await downloadEvent;
  const draft = JSON.parse(await readFile((await download.path())!, "utf8"));
  expect(draft.included_in_saved_assessment).toBe(false);
  expect(draft.observation).toMatchObject({ verification_state: "SELF_REPORTED", is_independent_ground_truth: false, source: "HUMAN_OBSERVATION", timestamp: "2026-01-09T09:30:00.000Z", photo_reference: "field-photo.jpg", location: { type: "Point", longitude: 37, latitude: 35 } });
  expect(draft.selected_aoi.geometry).toMatchObject({ west: 36, south: 34, east: 38, north: 36 });
  await expect(page.locator(".observation-summary")).not.toContainText(/Ground Truth|EXPERT_VERIFIED|SENSOR_SUPPORTED|Saved to cloud|Saved to database/);
  await page.getByRole("button", { name: "Edit observation", exact: true }).click();
  await expect(page.locator("#ground-crop_type")).toHaveValue("Wheat");
  await page.reload();
  await expect(page.locator("#ground-crop_type")).toHaveValue("");
  await expect(page.locator(".observation-summary")).toHaveCount(0);
});

test("calendar parser rejects invalid dates, missing zones in exports and malformed points", async () => {
  for (const value of ["2025-02-29T10:00", "2026-04-31T10:00", "2026-01-01T24:00", "2026-01-01", "invalid"]) expect(utcTimestamp(value)).toBeNull();
  expect(utcTimestamp("2024-02-29T10:00")).toBe("2024-02-29T10:00:00.000Z");
  const input = { ...emptyObservation, crop_type: "Wheat", observer_type: "FARMER", plant_condition: "UNKNOWN", soil_condition: "UNKNOWN", recent_irrigation: "UNKNOWN", timestamp: "2025-01-01T12:00", longitude: "", latitude: "0" };
  const box = { type: "BoundingBox" as const, west: -1, south: -1, east: 1, north: 1 };
  expect(validateObservation(input, box).longitude).toBeTruthy();
  expect(validateObservation({ ...input, longitude: "0" }, box)).toEqual({});
  expect(validateObservation({ ...input, longitude: "0", recent_irrigation_timestamp: "2024-12-30T10:00" }, box).recent_irrigation_timestamp).toBeTruthy();
});

test("sticky sidebar stays accessible and section selection reveals the next heading", async ({ page }) => {
  await page.goto("/dashboard?mode=EXPERT&view=ml");
  await ready(page);
  await page.locator(".workspace-footer").scrollIntoViewIfNeeded();
  const rail = await page.locator(".workspace-sidebar").boundingBox();
  expect(rail!.y).toBeGreaterThanOrEqual(76); expect(rail!.y).toBeLessThanOrEqual(78);
  await page.getByRole("navigation", { name: "Expert navigation" }).getByRole("button", { name: "Temporal evidence", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Temporal evidence" })).toBeInViewport();
  await expect(page.getByRole("button", { name: "Temporal evidence", exact: true })).toHaveAttribute("aria-current", "page");
});

test("globe button and wheel zoom respect bounds, selection and reset", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/scene?country=076");
  const globe = page.locator('[data-globe-ready="true"]');
  await expect(globe).toBeVisible({ timeout: 30000 });
  for (let i = 0; i < 9; i++) { const button = page.getByRole("button", { name: "Zoom globe in", exact: true }); if (await button.isEnabled()) await button.click(); }
  await expect(globe).toHaveAttribute("data-altitude", "0.9500");
  await expect(page.getByRole("button", { name: "Zoom globe in", exact: true })).toBeDisabled();
  const bounds = (await page.locator("canvas").boundingBox())!;
  await page.mouse.move(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2);
  await page.mouse.wheel(0, -10000);
  await expect(globe).toHaveAttribute("data-altitude", "0.9500");
  for (let i = 0; i < 10; i++) { const button = page.getByRole("button", { name: "Zoom globe out", exact: true }); if (await button.isEnabled()) await button.click(); }
  await expect(globe).toHaveAttribute("data-altitude", "3.0000");
  await page.getByRole("button", { name: "Reset globe view", exact: true }).click();
  await expect(globe).toHaveAttribute("data-altitude", "1.5000");
  await page.mouse.move(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2);
  await expect(globe).toHaveAttribute("data-hover-country", "076");
  await page.mouse.click(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2);
  await expect(page.getByRole("combobox", { name: "Find a country" })).toHaveValue("Brazil");
});

for (const width of [1440, 390]) test(`Arabic RTL core flow, persistence and accessibility at ${width}px`, async ({ page }) => {
  test.setTimeout(120000);
  await page.setViewportSize({ width, height: 1000 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/scene");
  await page.getByRole("button", { name: "العربية", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.locator("html")).toHaveAttribute("lang", "ar");
  await expect(page.getByRole("button", { name: /تحقق من حقلي/ })).toBeVisible();
  await page.getByRole("combobox", { name: "ابحث عن دولة" }).fill("سور");
  await page.getByRole("option", { name: "سوريا", exact: true }).click();
  await expect(page.getByRole("heading", { name: "حدد منطقة للتحليل" })).toBeVisible();
  await expect(page.getByRole("button", { name: "استخدم هذه المنطقة", exact: true })).toBeDisabled();
  for (const route of ["/scene?country=760", "/dashboard", "/dashboard?mode=EXPERT&view=ml", `${custom}&useCase=VERIFY_MY_FIELD`, `${custom}&useCase=SMART_FARM`]) {
    await page.goto(route);
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
    if (route.startsWith("/dashboard") && !route.includes("custom")) await ready(page);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
    expect(results.violations.filter((v) => ["serious", "critical"].includes(v.impact ?? "")).map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target) }))).toEqual([]);
    if (route.includes("VERIFY_MY_FIELD")) {
      await expect(page.getByRole("heading", { name: "ملاحظة ميدانية", exact: true })).toBeVisible();
      await page.getByRole("button", { name: "سجّل محلياً", exact: true }).click();
      await expect(page.locator("#ground-observation").getByRole("alert")).toHaveText("يرجى تصحيح الحقول المحددة.");
      await page.screenshot({ path: `test-results/stage5c-ar-ground-${width}.png`, fullPage: true });
    }
  }
  await page.getByRole("button", { name: "English", exact: true }).click();
  await expect(page.locator("html")).toHaveAttribute("dir", "ltr");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
});

test("new local form states pass axe and reduced motion; new layouts fit all target widths", async ({ page }) => {
  test.setTimeout(180000);
  await page.emulateMedia({ reducedMotion: "reduce" });
  for (const width of [1440, 1280, 1024, 768, 390, 360]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto("/scene?country=760");
    await coordinates(page);
    await expect(page.locator("html")).toHaveCSS("scroll-behavior", "auto");
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    if ([1440, 390].includes(width)) await page.screenshot({ path: `test-results/stage5c-aoi-${width}.png`, fullPage: true });
    await page.goto(`${custom}&useCase=VERIFY_MY_FIELD`);
    await page.getByRole("button", { name: "Capture locally", exact: true }).click();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    if ([1440, 390].includes(width)) {
      const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
      expect(result.violations.filter((v) => ["serious", "critical"].includes(v.impact ?? ""))).toEqual([]);
    }
    await formValues(page);
    await page.getByRole("button", { name: "Capture locally", exact: true }).click();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    if ([1440, 390].includes(width)) {
      const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
      expect(result.violations.filter((v) => ["serious", "critical"].includes(v.impact ?? ""))).toEqual([]);
      await page.screenshot({ path: `test-results/stage5c-observation-${width}.png`, fullPage: true });
    }
  }
});

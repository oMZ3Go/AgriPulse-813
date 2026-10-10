// Types come from the Python export; imports are erased from the client bundle.
export type Contract = typeof import("../public/data/konya/contract.json");
export type Manifest = typeof import("../public/data/konya/manifest.json");
export type KonyaData = {
  manifest: Manifest;
  contract: Contract;
  simple: typeof import("../public/data/konya/simple.json");
  spatial: typeof import("../public/data/konya/spatial.json");
  temporal: typeof import("../public/data/konya/temporal.json");
  spectral: typeof import("../public/data/konya/spectral.json");
  ml: typeof import("../public/data/konya/ml.json");
  fusion: typeof import("../public/data/konya/fusion.json");
  provenance: typeof import("../public/data/konya/provenance.json");
};
export const activitySteps = [
  "Area selected: validated Konya scene",
  "Loading validated data package",
  "Reading Stage 4.7 contract",
  "Loading spatial evidence",
  "Loading temporal evidence",
  "Loading hyperspectral evidence",
  "Loading experimental ML evidence",
  "Reading saved decision and provenance",
  "Preparing evidence summary and visualization references",
] as const;
export async function loadKonya(signal: AbortSignal, complete: (count: number) => void): Promise<KonyaData> {
  complete(1);
  const response = await fetch("/data/konya/manifest.json", { signal, cache: "no-cache" });
  if (!response.ok) throw new Error("The local Konya package is unavailable.");
  const manifest: Manifest = await response.json();
  if (manifest.schema_version !== "5B.1" || manifest.scene_id !== "20250608_091605_90_4001") throw new Error("The local package has an incompatible schema or scene.");
  complete(2);
  async function read<K extends keyof Omit<KonyaData, "manifest">>(key: K): Promise<KonyaData[K]> {
    const record = manifest.files?.[key];
    if (!record || record.path !== key + ".json" || !/^[a-f0-9]{64}$/.test(record.sha256)) throw new Error("Invalid local package file reference.");
    const result = await fetch("/data/konya/" + record.path, { signal, cache: "no-cache" });
    if (!result.ok) throw new Error(`Local ${key} evidence is unavailable.`);
    const buffer = await result.arrayBuffer();
    const hash = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", buffer))).map((byte) => byte.toString(16).padStart(2, "0")).join("");
    if (hash !== record.sha256) throw new Error(`Local ${key} evidence differs from its export. Regenerate the package.`);
    return JSON.parse(new TextDecoder().decode(buffer));
  }
  const contract = await read("contract");
  if (contract.schema_version !== "4.7.1" || contract.decision_state !== "GROUND_VERIFICATION_REQUIRED" || contract.automation_allowed !== false || contract.analysis_level !== "EO_ENHANCED" || contract.aoi.aoi_id !== "konya-20250608_091605_90_4001") throw new Error("The Konya contract does not match this validated demo.");
  complete(3);
  const spatial = await read("spatial"); complete(4);
  const temporal = await read("temporal"); complete(5);
  const spectral = await read("spectral"); complete(6);
  const ml = await read("ml"); complete(7);
  const [fusion, provenance] = await Promise.all([read("fusion"), read("provenance")]); complete(8);
  const simple = await read("simple");
  if (fusion.decision !== contract.decision_state || fusion.automation_allowed !== false || ml.score_is_probability !== false || ml.calibrated_agronomic_classifier !== false || simple.projection.status !== contract.decision_state) throw new Error("The evidence package contains inconsistent decision or ML semantics.");
  for (const figures of Object.values(manifest.figures)) for (const figure of figures) {
    if (!/^\/data\/konya\/figures\/[a-z_]+\.png$/.test(figure.src) || figure.width <= 0 || figure.height <= 0) throw new Error("Invalid local figure reference.");
  }
  complete(9);
  return { manifest, contract, simple, spatial, temporal, spectral, ml, fusion, provenance };
}

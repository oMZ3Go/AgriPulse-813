// Geographic labels only. These are regional locator points, not analysis footprints.
// Stage 5A deliberately has no imports from the scientific outputs.
export type SceneId = "konya" | "syria";

export const locations = [
  { id: "konya" as const, name: "Konya, Turkey", lat: 37.87, lng: 32.48, label: "Current validated demo scene" },
  { id: "syria" as const, name: "Syria", lat: 35.0, lng: 38.5, label: "Target deployment" },
];

export const expertSections = [
  { id: "overview", label: "Overview", stage: "Evidence workspace" },
  { id: "spatial", label: "Spatial risk", stage: "Stage 2" },
  { id: "temporal", label: "Temporal evidence", stage: "Stage 3" },
  { id: "fusion", label: "Decision fusion", stage: "Stage 4" },
  { id: "spectral", label: "Hyperspectral value", stage: "Stage 4.5" },
  { id: "methodology", label: "Methodology & limitations", stage: "Scientific context" },
  { id: "provenance", label: "Data provenance", stage: "Source context" },
] as const;

export type ExpertSection = (typeof expertSections)[number]["id"];

import countryData from "./countries.json";
export type Country = (typeof countryData)[number];
export const countries: Country[] = countryData;
export const countryById = (id: string | null) => countries.find((country) => country.id === id) ?? null;
// Regional locators are separate from the validated package's actual AOI.
export const locations = [
  { id: "konya", countryId: "792", name: "Konya, Turkey", lat: 37.6043, lng: 32.5740, label: "Current validated demo scene" },
  { id: "syria", countryId: "760", name: "Syria", lat: 35.0, lng: 38.5, label: "Target deployment" },
];
export const expertSections = [
  { id: "overview", label: "Overview", stage: "Evidence workspace" },
  { id: "spatial", label: "Spatial risk", stage: "Stage 2" },
  { id: "temporal", label: "Temporal evidence", stage: "Stage 3" },
  { id: "spectral", label: "Hyperspectral analysis", stage: "Stage 4.5" },
  { id: "ml", label: "ML spectral anomaly", stage: "Stage 4.6" },
  { id: "fusion", label: "Decision fusion", stage: "Stage 4" },
  { id: "provenance", label: "Data provenance", stage: "Source context" },
  { id: "methodology", label: "Methodology / limitations", stage: "Scientific context" },
] as const;
export type ExpertSection = (typeof expertSections)[number]["id"];

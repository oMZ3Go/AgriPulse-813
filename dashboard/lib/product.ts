export type UseCase = "EXPLORE_EARTH" | "VERIFY_MY_FIELD" | "SMART_FARM";
export type Mode = "SIMPLE" | "EXPERT";
export const useCases = [
  { id: "EXPLORE_EARTH" as const, label: "Explore Earth", description: "Start with the satellite perspective.", detail: "Select an agricultural area and review the Earth-observation evidence available for it." },
  { id: "VERIFY_MY_FIELD" as const, label: "Verify My Field", description: "Connect screening to a field visit.", detail: "Field verification can be added after satellite screening. Ground Observation is a future step." },
  { id: "SMART_FARM" as const, label: "Smart Farm", description: "Prepare for continuous site insight.", detail: "Review satellite evidence today. Calibrated site measurements can be connected in a future stage." },
];
export function parseUseCase(value: string | null): UseCase { return useCases.find((item) => item.id === value)?.id ?? "EXPLORE_EARTH"; }
export function parseMode(value: string | null): Mode { return value?.toUpperCase() === "EXPERT" ? "EXPERT" : "SIMPLE"; }
export function productUrl(route: string, useCase: UseCase, mode: Mode, extra: Record<string, string> = {}) {
  return `${route}?${new URLSearchParams({ useCase, mode, ...extra })}`;
}

"use client";
import { Radio } from "lucide-react";
import type { UseCase } from "@/lib/product";
import { useLanguage } from "./language-provider";

export function ProductFlow({ useCase }: { useCase: UseCase }) {
  const { t } = useLanguage();
  if (useCase !== "SMART_FARM") return null;
  return <section id="site-monitoring" className="product-flow panel" aria-label={t("Smart Farm pathway")}><div className="flow-title"><Radio size={20} /><div><p className="eyebrow">{t("Smart Farm")}</p><h2>{t("A satellite view. A future site connection.")}</h2></div><span className="future-status">{t("IoT not connected")}</span></div>
    <p>{t("No sensors or readings are connected in this demo.")}</p><p>{t("Future site monitoring needs calibrated soil moisture, temperature, humidity and sensor metadata.")}</p><bdi className="mono">IoT NOT CONNECTED</bdi>
  </section>;
}

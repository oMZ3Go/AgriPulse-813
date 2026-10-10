import { MapPin, Radio, ArrowRight } from "lucide-react";
import type { UseCase } from "@/lib/product";
export function ProductFlow({ useCase }: { useCase: UseCase }) {
  if (useCase === "EXPLORE_EARTH") return null;
  const field = useCase === "VERIFY_MY_FIELD";
  return <section className="product-flow panel" aria-label={field ? "Field verification pathway" : "Smart Farm pathway"}><div className="flow-title">{field ? <MapPin size={20} /> : <Radio size={20} />}<div><p className="eyebrow">{field ? "Verify My Field" : "Smart Farm"}</p><h2>{field ? "From screening to a field visit." : "A satellite view. A future site connection."}</h2></div><span className="future-status">{field ? "Ground Observation unavailable" : "IoT not connected"}</span></div>
    <p>{field ? "Field verification can be added after satellite screening. A future Ground Observation will capture crop condition, soil condition, irrigation context, symptoms, notes, location, timestamp and an optional photo. Human input is ground evidence; it is not automatically verified ground truth." : "This flow will combine satellite evidence with continuous site measurements: soil moisture, air temperature, humidity, optional soil temperature and calibrated sensor metadata. No sensors or readings are connected in this demo."}</p>
    <div className="flow-steps"><span>EO screening</span><ArrowRight size={14} /><span>{field ? "Field verification · upcoming" : "Sensor connection · upcoming"}</span><ArrowRight size={14} /><span>{field ? "Ground Observation · upcoming" : "Site monitoring · upcoming"}</span></div>
  </section>;
}

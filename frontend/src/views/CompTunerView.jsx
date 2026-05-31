import React, { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import AddressSearch from "../components/AddressSearch.jsx";
import EstimateCard from "../components/EstimateCard.jsx";
import CompTable from "../components/CompTable.jsx";
import { PriceVsSqftScatter } from "../components/charts.jsx";

const DEFAULTS = { subject_sqft: 2000, beds: 3, baths: 2, year_built: 1992,
  nbhdcd: "", comp_count: 10, size_band: 0.15, months_back: 24 };

export default function CompTunerView() {
  const [f, setF] = useState(DEFAULTS);
  const [seeded, setSeeded] = useState(false);
  const [result, setResult] = useState(null);
  const [err, setErr] = useState("");
  const timer = useRef(null);

  function set(k, v) { setF((p) => ({ ...p, [k]: v })); }

  // debounced re-estimate whenever inputs change (once a neighborhood is set)
  useEffect(() => {
    if (!f.nbhdcd) return;
    clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      setErr("");
      try { setResult(await api.comps(f)); }
      catch (e) { setErr(e.message); }
    }, 300);
    return () => clearTimeout(timer.current);
  }, [f]);

  function onPick(h) {
    setSeeded(true);
    setF((p) => ({ ...p, nbhdcd: h.nbhdcd, subject_sqft: h.sqft || p.subject_sqft,
      beds: h.beds ?? p.beds, baths: h.baths ?? p.baths, year_built: h.year_built ?? p.year_built }));
  }

  return (
    <div>
      <div className="panel">
        <label htmlFor="tuner-seed">Seed from a property (sets neighborhood + attributes)</label>
        <AddressSearch id="tuner-seed" ariaLabel="Seed property address" onPick={onPick} />
      </div>

      {seeded && (
        <div className="panel">
          <div className="row">
            <div><label htmlFor="tuner-sqft">Sqft</label><input id="tuner-sqft" type="number" value={f.subject_sqft} onChange={(e) => set("subject_sqft", Number(e.target.value))} /></div>
            <div><label htmlFor="tuner-beds">Beds</label><input id="tuner-beds" type="number" value={f.beds} onChange={(e) => set("beds", Number(e.target.value))} /></div>
            <div><label htmlFor="tuner-baths">Baths</label><input id="tuner-baths" type="number" value={f.baths} onChange={(e) => set("baths", Number(e.target.value))} /></div>
            <div><label htmlFor="tuner-year">Year built</label><input id="tuner-year" type="number" value={f.year_built} onChange={(e) => set("year_built", Number(e.target.value))} /></div>
          </div>
          <div className="row" style={{ marginTop: 12 }}>
            <div>
              <label htmlFor="tuner-band">Size band ±{Math.round(f.size_band * 100)}%</label>
              <div className="slider-row"><input id="tuner-band" type="range" min="5" max="40" value={f.size_band * 100}
                aria-label={`Size band ±${Math.round(f.size_band * 100)} percent`}
                onChange={(e) => set("size_band", Number(e.target.value) / 100)} /></div>
            </div>
            <div>
              <label htmlFor="tuner-comps">Comps shown: {f.comp_count}</label>
              <div className="slider-row"><input id="tuner-comps" type="range" min="3" max="30" value={f.comp_count}
                aria-label={`Comps shown: ${f.comp_count}`}
                onChange={(e) => set("comp_count", Number(e.target.value))} /></div>
            </div>
            <div>
              <label htmlFor="tuner-window">Window: {f.months_back} mo</label>
              <div className="slider-row"><input id="tuner-window" type="range" min="6" max="60" step="6" value={f.months_back}
                aria-label={`Window: ${f.months_back} months`}
                onChange={(e) => set("months_back", Number(e.target.value))} /></div>
            </div>
          </div>
          <p className="muted" style={{ marginBottom: 0, marginTop: 8 }}>Neighborhood {f.nbhdcd}</p>
        </div>
      )}

      {err && <div className="panel err">{err}</div>}
      {result && (
        <>
          <div className="row">
            <EstimateCard estimate={result.estimate} subject={result.subject} />
            <PriceVsSqftScatter points={result.comps.map((c) => ({ sqft: c.sqft, price: c.price, address: c.address }))}
                                subjectSqft={f.subject_sqft} band={f.size_band} />
          </div>
          <CompTable comps={result.comps} />
        </>
      )}
    </div>
  );
}

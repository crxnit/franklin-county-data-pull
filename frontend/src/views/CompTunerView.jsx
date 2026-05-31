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
      try { setResult(await api.comps({ ...f, subject_sqft: Number(f.subject_sqft) })); }
      catch (e) { setErr(e.message); }
    }, 300);
    return () => clearTimeout(timer.current);
  }, [f]);

  function onPick(h) {
    setSeeded(true);
    setF((p) => ({ ...p, nbhdcd: h.nbhdcd, subject_sqft: h.sqft || p.subject_sqft,
      beds: h.beds ?? p.beds, baths: h.baths ?? p.baths, year_built: h.year_built ?? p.year_built,
      address: h.address }));
  }

  return (
    <div>
      <div className="panel">
        <label>Seed from a property (sets neighborhood + attributes)</label>
        <AddressSearch onPick={onPick} />
      </div>

      {seeded && (
        <div className="panel">
          <div className="row">
            <div><label>Sqft</label><input type="number" value={f.subject_sqft} onChange={(e) => set("subject_sqft", e.target.value)} /></div>
            <div><label>Beds</label><input type="number" value={f.beds} onChange={(e) => set("beds", Number(e.target.value))} /></div>
            <div><label>Baths</label><input type="number" value={f.baths} onChange={(e) => set("baths", Number(e.target.value))} /></div>
            <div><label>Year built</label><input type="number" value={f.year_built} onChange={(e) => set("year_built", Number(e.target.value))} /></div>
          </div>
          <div className="row" style={{ marginTop: 12 }}>
            <div>
              <label>Size band ±{Math.round(f.size_band * 100)}%</label>
              <div className="slider-row"><input type="range" min="5" max="40" value={f.size_band * 100}
                onChange={(e) => set("size_band", Number(e.target.value) / 100)} /></div>
            </div>
            <div>
              <label>Comps shown: {f.comp_count}</label>
              <div className="slider-row"><input type="range" min="3" max="30" value={f.comp_count}
                onChange={(e) => set("comp_count", Number(e.target.value))} /></div>
            </div>
            <div>
              <label>Window: {f.months_back} mo</label>
              <div className="slider-row"><input type="range" min="6" max="60" step="6" value={f.months_back}
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
                                subjectSqft={Number(f.subject_sqft)} band={f.size_band} />
          </div>
          <CompTable comps={result.comps} />
        </>
      )}
    </div>
  );
}

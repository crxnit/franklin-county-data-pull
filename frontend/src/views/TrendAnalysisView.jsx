import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import { TrendChart } from "../components/charts.jsx";

const DIM_LABELS = {
  overall: "Market-wide",
  school: "School district",
  neighborhood: "Neighborhood",
  price_tier: "Price tier",
  sqft_band: "Sqft band",
};

const GRAN_LABELS = {
  sale_biweek: "Bi-weekly",
  sale_month: "Monthly",
  sale_quarter: "Quarterly",
  sale_year: "Yearly",
};

export default function TrendAnalysisView() {
  const [dims, setDims] = useState(null);       // { granularities, dimensions:[{key,groups}] }
  const [dimension, setDimension] = useState("overall");
  const [group, setGroup] = useState("");
  const [granularity, setGranularity] = useState("sale_month");
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");

  // Load the available dimensions/groups/granularities once.
  useEffect(() => {
    api.trendDimensions().then(setDims).catch((e) => setErr(e.message));
  }, []);

  const dimMeta = dims?.dimensions.find((d) => d.key === dimension);
  const groups = dimMeta?.groups || [];
  const groupLabels = dimMeta?.labels || {};        // {groupValue: displayName} (neighborhood only)
  const labelFor = (g) => groupLabels[g] || g;

  // When the dimension changes, default the group to the first available.
  useEffect(() => {
    if (dimension === "overall") { setGroup(""); return; }
    if (groups.length) setGroup((g) => (groups.includes(g) ? g : groups[0]));
  }, [dimension, dims]);

  // Fetch the selected slice.
  useEffect(() => {
    if (!dims) return;
    if (dimension !== "overall" && !group) return;
    setErr("");
    setData(null);
    const params = { dimension, granularity };
    if (dimension !== "overall") params.group = group;
    api.trend(params).then(setData).catch((e) => setErr(e.message));
  }, [dims, dimension, group, granularity]);

  const title = `${DIM_LABELS[dimension]}${dimension !== "overall" && group ? ` · ${labelFor(group)}` : ""}`
    + ` — median $/sqft (${GRAN_LABELS[granularity]})`;

  return (
    <div>
      <div className="panel">
        <div className="row">
          <div>
            <label htmlFor="trend-dim">Breakdown</label>
            <select id="trend-dim" value={dimension} onChange={(e) => setDimension(e.target.value)}>
              {(dims?.dimensions || []).map((d) => (
                <option key={d.key} value={d.key}>{DIM_LABELS[d.key] || d.key}</option>
              ))}
            </select>
          </div>
          {dimension !== "overall" && (
            <div>
              <label htmlFor="trend-group">Group</label>
              <select id="trend-group" value={group} onChange={(e) => setGroup(e.target.value)}>
                {groups.map((g) => <option key={g} value={g}>{labelFor(g)}</option>)}
              </select>
            </div>
          )}
          <div>
            <label htmlFor="trend-gran">Granularity</label>
            <select id="trend-gran" value={granularity} onChange={(e) => setGranularity(e.target.value)}>
              {(dims?.granularities || []).map((g) => (
                <option key={g} value={g}>{GRAN_LABELS[g] || g}</option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {err && <div className="panel err">{err}</div>}
      {data && (data.trend?.length
        ? <TrendChart trend={data.trend} title={title} showPrice />
        : <div className="panel muted">No sales in this slice for the current window.</div>)}
    </div>
  );
}

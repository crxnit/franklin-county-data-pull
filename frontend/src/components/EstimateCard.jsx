import React from "react";
import { usd, ppsf } from "../format.js";

export default function EstimateCard({ estimate, subject }) {
  if (!estimate || estimate.anchor?.value == null)
    return <div className="panel muted">Not enough comparable sales to estimate.</div>;
  const a = estimate.anchor;
  return (
    <div className="panel estimate">
      <div className="muted">Suggested value{subject?.address ? ` — ${subject.address}` : ""}</div>
      <div className="big">{usd(a.value)}</div>
      <div className="range">range {usd(a.low)} – {usd(a.high)}</div>
      <div style={{ marginTop: 12 }}>
        {subject?.sqft && <span className="pill">{subject.sqft.toLocaleString()} sqft</span>}
        {estimate.sanity != null && (
          <span className="pill">sale/assessment {estimate.sanity.toFixed(2)}</span>
        )}
        <span className="pill">±{Math.round(estimate.band * 100)}% size band</span>
      </div>
      <table style={{ marginTop: 14 }}>
        <thead>
          <tr><th>Method</th><th>n</th><th>median $/sqft</th><th>estimate</th></tr>
        </thead>
        <tbody>
          {estimate.views.map((v) => (
            <tr key={v.label}>
              <td>{v.label.replace(/_/g, " ")}</td>
              <td>{v.n}</td>
              <td>{ppsf(v.median_ppsf)}</td>
              <td>{usd(v.estimate)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

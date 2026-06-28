import React from "react";
import { usd, ppsf, num } from "../format.js";

export default function CompTable({ comps, title = "Comparable sales" }) {
  if (!comps || comps.length === 0) return <div className="muted">No comps.</div>;
  return (
    <div className="panel">
      <p className="chart-title">{title} ({comps.length})</p>
      <table>
        <thead>
          <tr>
            <th>Address</th><th>Sold</th><th>Price</th><th>Sqft</th>
            <th>$/sqft</th><th>Bd/Ba</th><th>Built</th><th>Sale:Assess</th>
          </tr>
        </thead>
        <tbody>
          {comps.map((c) => (
            <tr key={c.parcelid}>
              <td data-label="Address">{c.address}</td>
              <td data-label="Sold">{c.sale_date}</td>
              <td data-label="Price">{usd(c.price)}</td>
              <td data-label="Sqft">{num(c.sqft)}</td>
              <td data-label="$/sqft">{ppsf(c.price_per_sqft)}</td>
              <td data-label="Bd/Ba">{c.beds}/{c.baths}</td>
              <td data-label="Built">{c.year_built}</td>
              <td data-label="Sale:Assess">{c.sale_to_assessment ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

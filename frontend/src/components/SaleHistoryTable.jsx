import React from "react";
import { usd } from "../format.js";

// County validity coding is "<num> - <label>"; 0 = valid arms-length sale.
function validity(code) {
  if (!code) return "—";
  const head = code.split("-", 1)[0].trim();
  if (head === "0") return "Valid";
  return code; // surface the county's reason verbatim (e.g. "99 - RMS INVALID")
}

export default function SaleHistoryTable({ history }) {
  if (!history || history.length === 0) return null;
  return (
    <div className="panel">
      <p className="chart-title">Sale history ({history.length} conveyances, county records)</p>
      <table>
        <thead>
          <tr>
            <th>Date</th><th>Price</th><th>Instrument</th><th>Validity</th><th>Flags</th>
          </tr>
        </thead>
        <tbody>
          {history.map((s, i) => (
            <tr key={i}>
              <td data-label="Date">{s.sale_date || "—"}</td>
              <td data-label="Price">{usd(s.price)}</td>
              <td data-label="Instrument">{s.instrument || "—"}</td>
              <td data-label="Validity">{validity(s.valid_code)}</td>
              <td data-label="Flags">{[s.flags, s.condsale].filter(Boolean).join(", ") || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

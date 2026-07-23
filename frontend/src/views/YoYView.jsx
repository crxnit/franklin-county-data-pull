import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import { TrendChart } from "../components/charts.jsx";
import { usd, ppsf } from "../format.js";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// "08-18" -> "Aug 18" (raw echo if it isn't parseable yet).
function dayLabel(mmdd) {
  const m = /^(\d{2})-(\d{2})$/.exec(mmdd);
  return m && MONTHS[m[1] - 1] ? `${MONTHS[m[1] - 1]} ${+m[2]}` : mmdd;
}

const pct = (v) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(1)}%`);

const DEFAULT_WINDOW = { start: "08-18", end: "08-31" };

export default function YoYView() {
  const [start, setStart] = useState(DEFAULT_WINDOW.start);
  const [end, setEnd] = useState(DEFAULT_WINDOW.end);
  const [applied, setApplied] = useState(DEFAULT_WINDOW);
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    setErr("");
    setData(null);
    api.yoyTrend(`${applied.start}:${applied.end}`)
      .then(setData)
      .catch((e) => setErr(e.message));
  }, [applied]);

  const submit = (e) => {
    e.preventDefault();
    setApplied({ start: start.trim(), end: end.trim() });
  };

  const windowLabel = `${dayLabel(applied.start)} – ${dayLabel(applied.end)}`;
  // Chart oldest→newest; table newest first for quick reading.
  const years = data?.years || [];
  const tableRows = [...years].reverse();

  return (
    <div>
      <form className="panel" onSubmit={submit}>
        <div className="row">
          <div>
            <label htmlFor="yoy-start">Window start (MM-DD)</label>
            <input id="yoy-start" value={start} placeholder="08-18"
                   onChange={(e) => setStart(e.target.value)} />
          </div>
          <div>
            <label htmlFor="yoy-end">Window end (MM-DD)</label>
            <input id="yoy-end" value={end} placeholder="08-31"
                   onChange={(e) => setEnd(e.target.value)} />
          </div>
          <div>
            <label>&nbsp;</label>
            <button className="primary" type="submit">Compare years</button>
          </div>
        </div>
        <p className="muted">
          Same calendar window compared across every year of the county's
          conveyance history (back to ~1986). A start after the end (e.g.
          12-20 to 01-05) wraps the year boundary. Years with few sales are
          noisy — check the n column.
        </p>
      </form>

      {err && <div className="panel err">{err}</div>}

      {data && (years.length ? (
        <>
          <TrendChart trend={years} title={`${windowLabel} each year — median $/sqft & price`} showPrice />
          <div className="panel">
            <p className="chart-title">
              {windowLabel}, year over year
              {data.extract_date && data.extract_date !== "local" ? ` · county extract ${data.extract_date}` : ""}
            </p>
            <table>
              <thead>
                <tr>
                  <th>Year</th><th>Sales</th><th>Median price</th><th>YoY</th>
                  <th>Median $/sqft</th><th>YoY</th><th>Excluded</th>
                </tr>
              </thead>
              <tbody>
                {tableRows.map((y) => (
                  <tr key={y.period}>
                    <td data-label="Year">{y.period}</td>
                    <td data-label="Sales">{y.n}</td>
                    <td data-label="Median price">{usd(y.median_price)}</td>
                    <td data-label="Price YoY">{pct(y.yoy_price_pct)}</td>
                    <td data-label="Median $/sqft">{ppsf(y.median_ppsf)}</td>
                    <td data-label="$/sqft YoY">{pct(y.yoy_ppsf_pct)}</td>
                    <td data-label="Excluded">{y.n_excluded || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="muted">
              Excluded = non-market rows kept out of the medians ($0/nominal
              transfers, multi-parcel conveyances, conditional sales,
              county-coded invalid). $/sqft uses current above-grade sqft, so
              it's approximate for houses with later additions.
            </p>
          </div>
        </>
      ) : (
        <div className="panel muted">No sale history for this window — has the bulk sales extract been ingested?</div>
      ))}
    </div>
  );
}

import React, { useState } from "react";
import { api } from "../api.js";
import AddressSearch from "../components/AddressSearch.jsx";
import EstimateCard from "../components/EstimateCard.jsx";
import CompTable from "../components/CompTable.jsx";
import { PriceVsSqftScatter, PpsfHistogram, TrendChart } from "../components/charts.jsx";
import { usd } from "../format.js";

export default function ReportView() {
  const [report, setReport] = useState(null);
  const [nbhd, setNbhd] = useState(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);

  async function load(addr) {
    setErr(""); setLoading(true); setReport(null); setNbhd(null);
    try {
      const r = await api.report(addr);
      setReport(r);
      if (r.subject?.nbhdcd) {
        try { setNbhd(await api.neighborhood(r.subject.nbhdcd)); } catch { /* charts optional */ }
      }
    } catch (e) { setErr(e.message); }
    finally { setLoading(false); }
  }

  return (
    <div>
      <div className="panel">
        <label>Property address</label>
        <AddressSearch onPick={(h) => load(h.address)} />
        <p className="muted" style={{ marginBottom: 0 }}>
          Pick your home to get a comp-based valuation from Franklin County sales.
        </p>
      </div>

      {loading && <div className="panel muted">Loading…</div>}
      {err && <div className="panel err">{err}</div>}

      {report && (
        <>
          <div className="row">
            <EstimateCard estimate={report.estimate} subject={report.subject} />
            <div className="panel">
              <p className="chart-title">Subject</p>
              <div className="kv">
                <span className="k">Address</span><span>{report.subject.address}</span>
                <span className="k">Sqft (above grade)</span><span>{report.subject.sqft?.toLocaleString() || "—"}</span>
                <span className="k">Beds / baths</span><span>{report.subject.beds}/{report.subject.baths}</span>
                <span className="k">Year built</span><span>{report.subject.year_built || "—"}</span>
                <span className="k">Neighborhood</span><span>{report.subject.nbhdcd}</span>
                <span className="k">Assessed</span><span>{usd(report.subject.assessed)}</span>
              </div>
              {report.best_anchor_sale && (
                <p className="muted" style={{ marginTop: 12 }}>
                  Closest comp: <strong>{report.best_anchor_sale.address}</strong> — {usd(report.best_anchor_sale.price)} on {report.best_anchor_sale.sale_date}
                </p>
              )}
              <p className="muted" style={{ marginTop: 6, fontSize: 12 }}>
                Data as of {report.data_as_of?.slice(0, 10)} · validity: {report.valid_basis}
              </p>
            </div>
          </div>

          {nbhd && (
            <div className="row">
              <PriceVsSqftScatter points={nbhd.scatter} subjectSqft={report.subject.sqft} band={report.estimate.band} />
              <PpsfHistogram histogram={nbhd.histogram} median={nbhd.summary.median_ppsf} />
            </div>
          )}
          {nbhd && <TrendChart trend={nbhd.trend} />}

          <CompTable comps={report.comps} title="Most comparable recent sales" />
        </>
      )}
    </div>
  );
}

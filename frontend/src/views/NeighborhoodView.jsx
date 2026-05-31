import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import CompTable from "../components/CompTable.jsx";
import { PpsfHistogram, PriceVsSqftScatter, TrendChart } from "../components/charts.jsx";
import { usd, ppsf } from "../format.js";

export default function NeighborhoodView() {
  const [list, setList] = useState([]);
  const [sel, setSel] = useState("");
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    api.neighborhoods().then((l) => {
      setList(l);
      if (l.length) setSel(l[0].nbhdcd);
    }).catch((e) => setErr(e.message));
  }, []);

  useEffect(() => {
    if (!sel) return;
    setData(null);
    api.neighborhood(sel).then(setData).catch((e) => setErr(e.message));
  }, [sel]);

  return (
    <div>
      <div className="panel">
        <label>Appraiser neighborhood</label>
        <select value={sel} onChange={(e) => setSel(e.target.value)}>
          {list.map((n) => (
            <option key={n.nbhdcd} value={n.nbhdcd}>
              {n.nbhdcd} — {n.n_sales} sales · median {ppsf(n.median_ppsf)}/sqft · {usd(n.median_price)}
            </option>
          ))}
        </select>
      </div>

      {err && <div className="panel err">{err}</div>}
      {data && (
        <>
          <div className="panel">
            <div className="row">
              <div><div className="muted">Median $/sqft</div><div className="big" style={{ fontSize: 26 }}>{ppsf(data.summary.median_ppsf)}</div></div>
              <div><div className="muted">Median price</div><div className="big" style={{ fontSize: 26 }}>{usd(data.summary.median_price)}</div></div>
              <div><div className="muted">Usable comps</div><div className="big" style={{ fontSize: 26 }}>{data.summary.comps_usable}</div></div>
            </div>
          </div>
          <TrendChart trend={data.trend} />
          <div className="row">
            <PpsfHistogram histogram={data.histogram} median={data.summary.median_ppsf} />
            <PriceVsSqftScatter points={data.scatter} />
          </div>
          <CompTable comps={data.recent_sales} title="Recent sales" />
        </>
      )}
    </div>
  );
}

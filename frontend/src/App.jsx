import React, { Suspense, useEffect, useState } from "react";
import { api, setToken, ApiError } from "./api.js";
import ReportView from "./views/ReportView.jsx";
import CompTunerView from "./views/CompTunerView.jsx";
import NeighborhoodView from "./views/NeighborhoodView.jsx";
import TrendAnalysisView from "./views/TrendAnalysisView.jsx";

const VIEWS = {
  report: { label: "Pricing report", Comp: ReportView },
  tuner: { label: "Comp tuner", Comp: CompTunerView },
  neighborhood: { label: "Neighborhoods", Comp: NeighborhoodView },
  trends: { label: "Sales trends", Comp: TrendAnalysisView },
};

export default function App() {
  const [view, setView] = useState("report");
  const [authed, setAuthed] = useState(null); // null=checking, true/false
  const [pw, setPw] = useState("");
  const [meta, setMeta] = useState(null);

  async function check() {
    try {
      setMeta(await api.meta());
      setAuthed(true);
    } catch (e) {
      setAuthed(!(e instanceof ApiError && e.status === 401));
    }
  }
  useEffect(() => { check(); }, []);

  if (authed === null) return <div className="app"><p className="muted">Loading…</p></div>;

  if (authed === false) {
    const submit = () => { setToken(pw); check(); };
    return (
      <div className="app">
        <div className="gate panel">
          <h1>Franklin Housing</h1>
          <p className="muted" id="gate-help">Enter the access password.</p>
          <input type="password" value={pw} aria-label="Access password"
                 aria-describedby="gate-help" autoComplete="current-password"
                 onChange={(e) => setPw(e.target.value)}
                 onKeyDown={(e) => e.key === "Enter" && submit()} />
          <button className="primary" style={{ marginTop: 10 }} onClick={submit}>Enter</button>
        </div>
      </div>
    );
  }

  const ActiveView = VIEWS[view].Comp;
  return (
    <div className="app">
      <header className="top">
        <h1>Franklin Housing</h1>
        <span className="sub">
          Dublin, OH comps{meta?.last_pull ? ` · data ${meta.last_pull.pulled_at.slice(0, 10)} · ${meta.parcels.toLocaleString()} parcels` : ""}
        </span>
        <nav>
          {Object.entries(VIEWS).map(([k, v]) => (
            <button key={k} className={view === k ? "active" : ""} onClick={() => setView(k)}>{v.label}</button>
          ))}
        </nav>
      </header>
      <Suspense fallback={<div className="panel muted">Loading…</div>}>
        <ActiveView />
      </Suspense>
    </div>
  );
}

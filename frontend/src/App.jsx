import React, { useEffect, useState } from "react";
import { api, getToken, setToken, ApiError } from "./api.js";
import ReportView from "./views/ReportView.jsx";
import CompTunerView from "./views/CompTunerView.jsx";
import NeighborhoodView from "./views/NeighborhoodView.jsx";

const VIEWS = {
  report: { label: "Pricing report", el: <ReportView /> },
  tuner: { label: "Comp tuner", el: <CompTunerView /> },
  neighborhood: { label: "Neighborhoods", el: <NeighborhoodView /> },
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
    return (
      <div className="app">
        <div className="gate panel">
          <h1>Franklin Housing</h1>
          <p className="muted">Enter the access password.</p>
          <input type="password" value={pw} onChange={(e) => setPw(e.target.value)}
                 onKeyDown={(e) => e.key === "Enter" && (setToken(pw), check())} />
          <button className="primary" style={{ marginTop: 10 }}
                  onClick={() => { setToken(pw); check(); }}>Enter</button>
        </div>
      </div>
    );
  }

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
      {VIEWS[view].el}
    </div>
  );
}

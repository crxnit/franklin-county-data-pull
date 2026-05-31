import React, { useEffect, useRef, useState } from "react";
import { api } from "../api.js";

export default function AddressSearch({ onPick, placeholder = "Enter a Dublin address…" }) {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState([]);
  const [open, setOpen] = useState(false);
  const timer = useRef(null);

  useEffect(() => {
    if (q.trim().length < 2) { setHits([]); return; }
    clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      try {
        setHits(await api.searchAddress(q.trim()));
        setOpen(true);
      } catch { setHits([]); }
    }, 220);
    return () => clearTimeout(timer.current);
  }, [q]);

  function pick(h) {
    setQ(h.address);
    setOpen(false);
    onPick(h);
  }

  return (
    <div className="autocomplete">
      <input
        value={q}
        placeholder={placeholder}
        onChange={(e) => setQ(e.target.value)}
        onFocus={() => hits.length && setOpen(true)}
      />
      {open && hits.length > 0 && (
        <ul>
          {hits.map((h) => (
            <li key={h.parcelid} onClick={() => pick(h)}>
              {h.address} <span className="muted">· {h.sqft || "?"} sqft · {h.beds}bd/{h.baths}ba · {h.zip}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

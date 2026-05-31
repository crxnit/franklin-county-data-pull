import React, { useEffect, useRef, useState } from "react";
import { api } from "../api.js";

export default function AddressSearch({ onPick, id, ariaLabel = "Property address",
  placeholder = "Enter a Dublin address…" }) {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1); // highlighted option index
  const timer = useRef(null);
  const listId = id ? `${id}-listbox` : "address-listbox";

  useEffect(() => {
    if (q.trim().length < 2) { setHits([]); setActive(-1); return; }
    clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      try {
        setHits(await api.searchAddress(q.trim()));
        setOpen(true);
        setActive(-1);
      } catch { setHits([]); }
    }, 220);
    return () => clearTimeout(timer.current);
  }, [q]);

  function pick(h) {
    setQ(h.address);
    setOpen(false);
    setActive(-1);
    onPick(h);
  }

  function onKeyDown(e) {
    if (!open || hits.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => (i + 1) % hits.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => (i <= 0 ? hits.length - 1 : i - 1));
    } else if (e.key === "Enter" && active >= 0) {
      e.preventDefault();
      pick(hits[active]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  return (
    <div className="autocomplete">
      <input
        id={id}
        value={q}
        placeholder={placeholder}
        role="combobox"
        aria-label={ariaLabel}
        aria-expanded={open && hits.length > 0}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={active >= 0 ? `${listId}-opt-${active}` : undefined}
        onChange={(e) => setQ(e.target.value)}
        onFocus={() => hits.length && setOpen(true)}
        onKeyDown={onKeyDown}
      />
      {open && hits.length > 0 && (
        <ul id={listId} role="listbox">
          {hits.map((h, i) => (
            <li key={h.parcelid} id={`${listId}-opt-${i}`} role="option"
                aria-selected={i === active}
                className={i === active ? "active" : ""}
                onMouseEnter={() => setActive(i)}
                onClick={() => pick(h)}>
              {h.address} <span className="muted">· {h.sqft || "?"} sqft · {h.beds}bd/{h.baths}ba · {h.zip}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

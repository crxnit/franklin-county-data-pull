import React from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ReferenceLine, ReferenceArea,
  ScatterChart, Scatter, LineChart, Line, ResponsiveContainer, CartesianGrid, ZAxis,
} from "recharts";

const AX = { stroke: "#9aa3b2", fontSize: 12 };
const GRID = "#2a2f3a";

export function PpsfHistogram({ histogram, median }) {
  if (!histogram?.length) return null;
  const data = histogram.map((h) => ({ label: `${h.lo}`, count: h.count, lo: h.lo, hi: h.hi }));
  return (
    <div className="panel">
      <p className="chart-title">$/sqft distribution{median ? ` — median $${median.toFixed(0)}` : ""}</p>
      <ResponsiveContainer width="100%" height={240}>
        <BarChart data={data}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="label" tick={AX} />
          <YAxis tick={AX} />
          <Tooltip contentStyle={{ background: "#20242e", border: "1px solid #2a2f3a" }}
                   formatter={(v) => [`${v} sales`, ""]}
                   labelFormatter={(l) => `$${l}+/sqft`} />
          {median && <ReferenceLine x={`${Math.round(median)}`} stroke="#dd8452" />}
          <Bar dataKey="count" fill="#4c8bf5" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function PriceVsSqftScatter({ points, subjectSqft, band = 0.15 }) {
  if (!points?.length) return null;
  const data = points.filter((p) => p.sqft && p.price).map((p) => ({ x: p.sqft, y: p.price, address: p.address }));
  return (
    <div className="panel">
      <p className="chart-title">Price vs sqft{subjectSqft ? ` — subject ${subjectSqft.toLocaleString()} sqft` : ""}</p>
      <ResponsiveContainer width="100%" height={300}>
        <ScatterChart margin={{ left: 10, right: 10, top: 10, bottom: 5 }}>
          <CartesianGrid stroke={GRID} />
          <XAxis type="number" dataKey="x" name="sqft" tick={AX} domain={["dataMin-100", "dataMax+100"]} />
          <YAxis type="number" dataKey="y" name="price" tick={AX}
                 tickFormatter={(v) => `$${Math.round(v / 1000)}k`} />
          <ZAxis range={[40, 40]} />
          <Tooltip contentStyle={{ background: "#20242e", border: "1px solid #2a2f3a" }}
                   formatter={(v, n) => (n === "price" ? `$${v.toLocaleString()}` : v.toLocaleString())} />
          {subjectSqft && (
            <ReferenceArea x1={subjectSqft * (1 - band)} x2={subjectSqft * (1 + band)}
                           fill="#dd8452" fillOpacity={0.12} />
          )}
          {subjectSqft && <ReferenceLine x={subjectSqft} stroke="#dd8452" strokeDasharray="5 4" />}
          <Scatter data={data} fill="#4c8bf5" fillOpacity={0.6} />
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}

export function TrendChart({ trend }) {
  if (!trend?.length) return null;
  return (
    <div className="panel">
      <p className="chart-title">Median $/sqft by month</p>
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={trend}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="period" tick={AX} minTickGap={24} />
          <YAxis tick={AX} domain={["auto", "auto"]} />
          <Tooltip contentStyle={{ background: "#20242e", border: "1px solid #2a2f3a" }} />
          <Line type="monotone" dataKey="median_ppsf" stroke="#4c8bf5" dot={false} strokeWidth={2} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

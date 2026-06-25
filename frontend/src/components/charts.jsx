import React from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ReferenceLine, ReferenceArea,
  ScatterChart, Scatter, LineChart, Line, ResponsiveContainer, CartesianGrid, ZAxis,
} from "recharts";
import { COLORS, TOOLTIP_STYLE } from "../theme.js";

const AX = { stroke: COLORS.muted, fontSize: 12 };
const GRID = COLORS.line;

export function PpsfHistogram({ histogram, median }) {
  if (!histogram?.length) return null;
  const data = histogram.map((h) => ({ label: `${h.lo}`, count: h.count, lo: h.lo, hi: h.hi }));
  const hasMedian = median != null && median > 0;
  return (
    <div className="panel">
      <p className="chart-title">$/sqft distribution{hasMedian ? ` — median $${median.toFixed(0)}` : ""}</p>
      <ResponsiveContainer width="100%" height={240}>
        <BarChart data={data}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="label" tick={AX} />
          <YAxis tick={AX} />
          <Tooltip contentStyle={TOOLTIP_STYLE}
                   formatter={(v) => [`${v} sales`, ""]}
                   labelFormatter={(l) => `$${l}+/sqft`} />
          {hasMedian && <ReferenceLine x={`${Math.round(median)}`} stroke={COLORS.accent2} />}
          <Bar dataKey="count" fill={COLORS.accent} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function PriceVsSqftScatter({ points, subjectSqft, band = 0.15 }) {
  if (!points?.length) return null;
  const data = points.filter((p) => p.sqft && p.price).map((p) => ({ x: p.sqft, y: p.price, address: p.address }));
  const hasSubject = subjectSqft != null && subjectSqft > 0;
  return (
    <div className="panel">
      <p className="chart-title">Price vs sqft{hasSubject ? ` — subject ${subjectSqft.toLocaleString()} sqft` : ""}</p>
      <ResponsiveContainer width="100%" height={300}>
        <ScatterChart margin={{ left: 10, right: 10, top: 10, bottom: 5 }}>
          <CartesianGrid stroke={GRID} />
          <XAxis type="number" dataKey="x" name="sqft" tick={AX} domain={["dataMin-100", "dataMax+100"]} />
          <YAxis type="number" dataKey="y" name="price" tick={AX}
                 tickFormatter={(v) => `$${Math.round(v / 1000)}k`} />
          <ZAxis range={[40, 40]} />
          <Tooltip contentStyle={TOOLTIP_STYLE}
                   formatter={(v, n) => (n === "price" ? `$${v.toLocaleString()}` : v.toLocaleString())} />
          {hasSubject && (
            <ReferenceArea x1={subjectSqft * (1 - band)} x2={subjectSqft * (1 + band)}
                           fill={COLORS.accent2} fillOpacity={0.12} />
          )}
          {hasSubject && <ReferenceLine x={subjectSqft} stroke={COLORS.accent2} strokeDasharray="5 4" />}
          <Scatter data={data} fill={COLORS.accent} fillOpacity={0.6} />
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}

export function TrendChart({ trend, title = "Median $/sqft by month", showPrice = false }) {
  if (!trend?.length) return null;
  return (
    <div className="panel">
      <p className="chart-title">{title}</p>
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={trend}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="period" tick={AX} minTickGap={24} />
          <YAxis yAxisId="ppsf" tick={AX} domain={["auto", "auto"]} />
          {showPrice && (
            <YAxis yAxisId="price" orientation="right" tick={AX} domain={["auto", "auto"]}
                   tickFormatter={(v) => `$${Math.round(v / 1000)}k`} />
          )}
          <Tooltip contentStyle={TOOLTIP_STYLE} />
          <Line yAxisId="ppsf" type="monotone" dataKey="median_ppsf" name="$/sqft"
                stroke={COLORS.accent} dot={false} strokeWidth={2} />
          {showPrice && (
            <Line yAxisId="price" type="monotone" dataKey="median_price" name="price"
                  stroke={COLORS.accent2} dot={false} strokeWidth={2} />
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

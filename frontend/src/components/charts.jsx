// Lazy facade over chartsImpl.jsx. Recharts (~400 kB) is heavy on mobile
// networks and isn't needed for first paint (landing shows only a search box),
// so it's code-split into an async chunk fetched the first time any chart
// renders. Consumers import these names exactly as before; a single <Suspense>
// boundary in App.jsx covers the load. See chartsImpl.jsx for the real charts.
import { lazy } from "react";

const load = (name) => lazy(() => import("./chartsImpl.jsx").then((m) => ({ default: m[name] })));

export const PpsfHistogram = load("PpsfHistogram");
export const PriceVsSqftScatter = load("PriceVsSqftScatter");
export const TrendChart = load("TrendChart");

# 7518 Whigham Ct, Dublin, OH 43016 — Pricing Analysis

*Source: Franklin County Auditor parcel data (canonical GIS layer). Comps = arms-length single-family sales in appraiser neighborhood `00111000`, last 24 months. Generated from the local pipeline.*

## The home
| | |
|---|---|
| Parcel | 273-005856 |
| Above-grade sqft | **1,868** |
| Beds / baths | 3 / 2 |
| Year built | 1992 |
| Assessed value | $417,900 |
| School district | Dublin CSD |
| Appraiser neighborhood | `00111000` (84 usable comps, 24 mo) |

## Suggested list range: **~$510K – $535K** (anchor ~$520K–$525K)

$/sqft falls as homes get larger, so the neighborhood-wide median understates a smaller home like yours. The **size-matched** method is the right lens:

| Method | n | median $/sqft | → est. for 1,868 sqft |
|---|---:|---:|---:|
| All neighborhood comps (24 mo) | 84 | $255 | $477K |
| **Size-matched** (1,588–2,148 sqft) | 8 | **$280** | **$523K** |
| Size-matched, last ~12 mo | 4 | $285 | $532K |
| 2026 sales (all sizes) | 13 | $259 | $484K |

**Sanity check:** $523K ÷ $417,900 assessed = **1.25** — squarely in this neighborhood's normal 1.2–1.4 sale-to-assessment band, so it's not an aggressive number.

## Size-matched comps (1,868 sqft ±15%)

| Sale date | Address | Sqft | Price | $/sqft | Bd/Ba | Sale:Assess |
|---|---|---:|---:|---:|---|---:|
| 2026-04-16 | 5600 Caplestone Ln | 1,868 | $650,000 | **$348** | 2/2 | 1.39 |
| 2026-03-11 | 6498 Wyndburne Dr | 2,022 | $561,750 | $278 | 4/2 | 1.19 |
| 2025-12-31 | 7326 Pueblo Ct | 2,090 | $565,000 | $270 | 4/2 | 1.52 |
| 2025-12-19 | 6287 Worsham Wy | 1,836 | $535,000 | $291 | 4/2 | 1.37 |
| 2025-04-25 | 6279 Wismer Cr | 2,046 | $542,000 | $265 | 4/2 | 1.40 |
| 2024-10-23 | 6570 E Weston Cr | 1,774 | $500,000 | $282 | 3/2 | 1.06 |
| 2024-05-22 | 7415 Wynwright Ct | 2,022 | $535,000 | $265 | 3/2 | 1.33 |
| 2024-05-06 | 7244 Hopewell Ct | 1,772 | $521,000 | $294 | 3/2 | 1.27 |

**Best single anchor — your street:** 7495 Whigham Ct (same year, 4 bd, 2,212 sqft) sold **$600,000 on 2026-04-17** at $271/sqft. Bigger and 4 bd vs. your 3 bd, so a smaller 3 bd landing ~$520K is consistent.

## Distribution

![$/sqft distribution](whigham_ppsf_hist.png)

![Price vs sqft](whigham_price_vs_sqft.png)

In the shaded size band (~1,590–2,150 sqft), sales cluster ~$500K–$565K, with one renovated outlier at $650K (5600 Caplestone, your exact sqft) — the condition premium, made visible.

## What moves the number — your call
- **Condition / updates.** The spread is real: 5600 Caplestone hit **$348/sqft ($650K)**, almost certainly renovated, vs. dated comps near $265. If yours is updated (kitchen/baths/floors), push toward the top of the range or beyond; if original-1992, hold ~$505K–$515K.
- **3 vs 4 bed.** Several size-matched comps are 4 bd; a 3 bd at your size trails slightly — already baked into the conservative anchor.

## Market timing
Dublin $/sqft has been **range-bound for two years** (~$240–260 neighborhood-wide; ~$280 for your size class) — no runaway, no rollover. Pricing here is about condition and comp selection, not timing.

---
*Full neighborhood comp set: `whigham_comps.csv` (84 rows). Hygiene note: `VALID` is unpublished in county GIS data; arms-length status is judged by the sale-to-assessment ratio + price-floor proxy (calibrated against 250 scraped transfers). All comps above passed.*

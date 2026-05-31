"""Whigham-neighborhood (NBHD 00111000) deliverable:
  - data/whigham_comps.csv         cleaned comps in the subject's neighborhood
  - data/whigham_ppsf_hist.png     $/sqft distribution
  - data/whigham_price_vs_sqft.png price vs above-grade sqft scatter

Subject: 7518 Whigham Ct (1,868 sqft, 3bd/2ba, 1992) marked on both plots.
Run:  .venv/bin/python scripts/whigham_report.py
"""

import csv

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from franklin_housing.cache import Cache
from franklin_housing.clean import clean_records
from franklin_housing.config import Config

NBHD = "00111000"
SUBJ_SQFT = 1868
SUBJ_ADDR = "7518 WHIGHAM CT"

cfg = Config()
recs = clean_records(Cache(cfg.db_path).load(), cfg)
nb = [r for r in recs if r["nbhdcd"] == NBHD]
comps = [r for r in nb if r["is_comp"]]

# --- CSV (all neighborhood rows, newest first; includes flags so nothing hidden)
cols = ["sale_date", "address", "price", "sqft", "price_per_sqft", "beds",
        "baths", "year_built", "sale_to_assessment", "is_comp", "flags",
        "parcelid", "zip", "nbhdcd"]
with open("data/whigham_comps.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for r in sorted(nb, key=lambda x: x["sale_date"] or "", reverse=True):
        w.writerow(r)
print(f"wrote data/whigham_comps.csv  ({len(nb)} rows, {len(comps)} usable comps)")

ppsf = [r["price_per_sqft"] for r in comps]
sqft = [r["sqft"] for r in comps]
price = [r["price"] for r in comps]

# --- histogram of $/sqft
fig, ax = plt.subplots(figsize=(7, 4.2))
ax.hist(ppsf, bins=18, color="#4C72B0", edgecolor="white")
med = sorted(ppsf)[len(ppsf) // 2]
ax.axvline(med, color="#C44E52", lw=2, label=f"median ${med:.0f}/sqft")
ax.set_xlabel("$ / above-grade sqft")
ax.set_ylabel("sales")
ax.set_title(f"Whigham area (NBHD {NBHD}) — $/sqft, last 24 mo  (n={len(comps)})")
ax.legend()
fig.tight_layout()
fig.savefig("data/whigham_ppsf_hist.png", dpi=120)
plt.close(fig)
print("wrote data/whigham_ppsf_hist.png")

# --- scatter price vs sqft, subject size marked
fig, ax = plt.subplots(figsize=(7, 4.6))
ax.scatter(sqft, price, s=22, alpha=0.6, color="#4C72B0", label="comps")
# size-matched band shading
ax.axvspan(SUBJ_SQFT * 0.85, SUBJ_SQFT * 1.15, color="#DD8452", alpha=0.12,
           label="size-matched ±15%")
ax.axvline(SUBJ_SQFT, color="#C44E52", lw=1.5, ls="--",
           label=f"subject {SUBJ_SQFT} sqft")
ax.set_xlabel("above-grade sqft")
ax.set_ylabel("sale price ($)")
ax.set_title(f"Whigham area — price vs sqft  ({SUBJ_ADDR})")
ax.ticklabel_format(style="plain", axis="y")
ax.legend(fontsize=8)
fig.tight_layout()
fig.savefig("data/whigham_price_vs_sqft.png", dpi=120)
plt.close(fig)
print("wrote data/whigham_price_vs_sqft.png")

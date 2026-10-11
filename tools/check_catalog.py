"""Shows which earthquake catalogue the game will use and what's in it.

    python tools/check_catalog.py

Put archive.csv (from eq_stats) or a GeoNet quakesearch / FDSN CSV export in
data/catalog/ first. The newest .csv/.txt file in that folder is used.
"""
from __future__ import annotations

import os
import statistics
import sys
import time
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.catalog import load_catalog  # noqa: E402
from game.data import get_data  # noqa: E402
from game.geo import region_of  # noqa: E402
from game.run_builder import score_days  # noqa: E402
from game.tasks import sops_for  # noqa: E402


def main():
    data = get_data()
    t0 = time.time()
    cat = load_catalog(data, progress=print)
    print(f"\nLoaded in {time.time() - t0:.1f}s from: {cat.source}")
    print(cat.summary())
    if not cat.days:
        print("No usable days. Check the file has origin_time, latitude, longitude, magnitude columns.")
        return
    counts = sorted(len(d.events) for d in cat.days)
    q = lambda p: counts[min(len(counts) - 1, int(p * len(counts)))]  # noqa: E731
    print(f"Events per day: median {statistics.median(counts):.0f}, 90th {q(0.9)}, 99th {q(0.99)}, max {counts[-1]}")
    mags = [e[1] for e in cat.events]
    for m in (2.0, 2.7, 3.5, 4.5, 5.5, 6.5):
        k = sum(1 for x in mags if x >= m)
        print(f"  M>={m}: {k:>7,} ({100 * k / len(mags):5.1f}%)")
    regions = Counter(region_of(data, e[2], e[3]) for e in cat.events)
    print("Regions:", ", ".join(f"{k} {v:,}" for k, v in regions.most_common()))
    sop_events = [e for e in cat.events if sops_for(data, e[1], e[4], region_of(data, e[2], e[3]))]
    sops = Counter(s["id"] for e in sop_events for s in sops_for(data, e[1], e[4], region_of(data, e[2], e[3])))
    print(f"Events that would trigger an SOP: {len(sop_events):,}  ({', '.join(f'{k} {v}' for k, v in sops.items())})")
    score_days(data, cat)
    busiest = sorted(cat.days, key=lambda d: -d.score)[:10]
    print("\nBusiest days (these become late-run and final days):")
    for d in busiest:
        print(f"  {d.label}: {len(d.events):>4} events, max M{d.max_mag:.1f}, {d.sop_count} SOP, score {d.score:,.0f}")


if __name__ == "__main__":
    main()

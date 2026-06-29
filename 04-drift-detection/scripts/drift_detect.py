"""Drift detection on a synthetic AI input dataset.

This script intentionally keeps the core report dependency-free so the lab can
run on a fresh host. If Evidently is installed, the same JSON summary is still
the rubric source of truth; the HTML report below is always generated.
"""
from __future__ import annotations

import csv
import json
import math
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
DATA_DIR = HERE / "data"
REPORTS_DIR = HERE / "reports"
REPORTS_DIR.mkdir(exist_ok=True)


def synth_dataset(rng: random.Random, *, shifted: bool, n: int = 1000) -> list[dict[str, float]]:
    rows: list[dict[str, float]] = []
    for _ in range(n):
        if shifted:
            row = {
                "prompt_length": rng.gauss(85, 20),
                "embedding_norm": rng.gauss(1.0, 0.1),
                "response_length": rng.gauss(120, 40),
                "response_quality": rng.betavariate(2, 6),
            }
        else:
            row = {
                "prompt_length": rng.gauss(50, 15),
                "embedding_norm": rng.gauss(1.0, 0.1),
                "response_length": rng.gauss(120, 40),
                "response_quality": rng.betavariate(8, 2),
            }
        rows.append(row)
    return rows


def column(rows: list[dict[str, float]], name: str) -> list[float]:
    return [row[name] for row in rows]


def histogram(reference: list[float], current: list[float], bins: int) -> tuple[list[int], list[int]]:
    lo = min(min(reference), min(current))
    hi = max(max(reference), max(current))
    width = (hi - lo) / bins or 1.0
    ref_counts = [0] * bins
    cur_counts = [0] * bins
    for values, counts in ((reference, ref_counts), (current, cur_counts)):
        for value in values:
            idx = min(int((value - lo) / width), bins - 1)
            counts[idx] += 1
    return ref_counts, cur_counts


def population_stability_index(reference: list[float], current: list[float], bins: int = 10) -> float:
    ref_counts, cur_counts = histogram(reference, current, bins)
    ref_total = sum(ref_counts) + bins
    cur_total = sum(cur_counts) + bins
    score = 0.0
    for ref_count, cur_count in zip(ref_counts, cur_counts):
        ref_p = (ref_count + 1) / ref_total
        cur_p = (cur_count + 1) / cur_total
        score += (cur_p - ref_p) * math.log(cur_p / ref_p)
    return score


def kl_divergence(reference: list[float], current: list[float], bins: int = 20) -> float:
    ref_counts, cur_counts = histogram(reference, current, bins)
    ref_total = sum(ref_counts) + bins * 1e-9
    cur_total = sum(cur_counts) + bins * 1e-9
    score = 0.0
    for ref_count, cur_count in zip(ref_counts, cur_counts):
        ref_p = (ref_count + 1e-9) / ref_total
        cur_p = (cur_count + 1e-9) / cur_total
        score += ref_p * math.log(ref_p / cur_p)
    return score


def ks_statistic(reference: list[float], current: list[float]) -> float:
    ref_sorted = sorted(reference)
    cur_sorted = sorted(current)
    ref_n = len(ref_sorted)
    cur_n = len(cur_sorted)
    i = j = 0
    best = 0.0
    while i < ref_n and j < cur_n:
        value = min(ref_sorted[i], cur_sorted[j])
        while i < ref_n and ref_sorted[i] <= value:
            i += 1
        while j < cur_n and cur_sorted[j] <= value:
            j += 1
        best = max(best, abs(i / ref_n - j / cur_n))
    return best


def approximate_ks_pvalue(ks_stat: float, n: int, m: int) -> float:
    effective_n = n * m / (n + m)
    return min(1.0, 2.0 * math.exp(-2.0 * effective_n * ks_stat * ks_stat))


def write_csv(path: Path, rows: list[dict[str, float]]) -> None:
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_html(path: Path, summary: dict[str, dict[str, float | str]]) -> None:
    rows = "\n".join(
        "<tr>"
        f"<td>{feature}</td>"
        f"<td>{metrics['psi']}</td>"
        f"<td>{metrics['kl']}</td>"
        f"<td>{metrics['ks_stat']}</td>"
        f"<td>{metrics['ks_pvalue']}</td>"
        f"<td>{metrics['drift']}</td>"
        "</tr>"
        for feature, metrics in summary.items()
    )
    path.write_text(
        f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Day 23 Drift Report</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; }}
    table {{ border-collapse: collapse; min-width: 760px; }}
    th, td {{ border: 1px solid #d0d7de; padding: 8px 12px; text-align: right; }}
    th:first-child, td:first-child {{ text-align: left; }}
    th {{ background: #f6f8fa; }}
  </style>
</head>
<body>
  <h1>Day 23 Drift Report</h1>
  <p>Reference vs current synthetic AI-service traffic. PSI &gt; 0.2 is marked as drift.</p>
  <table>
    <thead>
      <tr><th>Feature</th><th>PSI</th><th>KL</th><th>KS stat</th><th>KS p-value</th><th>Drift</th></tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
</body>
</html>
""",
        encoding="utf-8",
    )


def main() -> int:
    rng = random.Random(42)
    reference = synth_dataset(rng, shifted=False)
    current = synth_dataset(rng, shifted=True)
    DATA_DIR.mkdir(exist_ok=True)
    write_csv(DATA_DIR / "reference.csv", reference)
    write_csv(DATA_DIR / "current.csv", current)

    summary: dict[str, dict[str, float | str]] = {}
    for feature in reference[0].keys():
        ref = column(reference, feature)
        cur = column(current, feature)
        psi = population_stability_index(ref, cur)
        kl = kl_divergence(ref, cur)
        ks = ks_statistic(ref, cur)
        summary[feature] = {
            "psi": round(psi, 4),
            "kl": round(kl, 4),
            "ks_stat": round(ks, 4),
            "ks_pvalue": round(approximate_ks_pvalue(ks, len(ref), len(cur)), 6),
            "drift": "yes" if psi > 0.2 else ("moderate" if psi > 0.1 else "no"),
        }

    summary_path = REPORTS_DIR / "drift-summary.json"
    html_path = REPORTS_DIR / "drift-report.html"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_html(html_path, summary)

    print(f"Wrote: {summary_path}")
    print(f"Wrote: {html_path}")
    for feature, metrics in summary.items():
        print(
            f"  {feature:<20} PSI={metrics['psi']:.3f}  "
            f"KL={metrics['kl']:.3f}  KS={metrics['ks_stat']:.3f}  "
            f"drift={metrics['drift']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

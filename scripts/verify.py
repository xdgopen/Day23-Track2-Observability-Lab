"""Rubric gate. Exit 0 only if all submission checkpoints pass.

Run: python3 scripts/verify.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

try:
    import requests
except ImportError:  # keep the rubric gate runnable on a fresh Python install
    requests = None

LAB = Path(__file__).resolve().parent.parent
SUBMISSION = LAB / "submission"


def check(label: str, ok: bool, detail: str = "") -> bool:
    icon = "[PASS]" if ok else "[FAIL]"
    line = f"{icon} {label}"
    if detail:
        line += f"  ({detail})"
    print(line)
    return ok


def http_ok(url: str, timeout: float = 3.0) -> bool:
    if requests is None:
        try:
            with urlopen(url, timeout=timeout) as response:
                return response.status == 200
        except URLError:
            return False
    try:
        return requests.get(url, timeout=timeout).status_code == 200
    except requests.exceptions.RequestException:
        return False


def http_text(url: str, timeout: float = 3.0) -> str:
    if requests is None:
        try:
            with urlopen(url, timeout=timeout) as response:
                return response.read().decode("utf-8", errors="replace")
        except URLError:
            return ""
    try:
        response = requests.get(url, timeout=timeout)
        return response.text if response.status_code == 200 else ""
    except requests.exceptions.RequestException:
        return ""


def http_json(url: str, *, auth: tuple[str, str] | None = None, timeout: float = 3.0):
    if requests is None:
        try:
            request = Request(url)
            if auth:
                import base64

                token = base64.b64encode(f"{auth[0]}:{auth[1]}".encode()).decode()
                request.add_header("Authorization", f"Basic {token}")
            with urlopen(request, timeout=timeout) as response:
                if response.status != 200:
                    return None
                return json.loads(response.read().decode("utf-8"))
        except (URLError, json.JSONDecodeError):
            return None
    try:
        response = requests.get(url, auth=auth, timeout=timeout)
        return response.json() if response.status_code == 200 else None
    except Exception:
        return None


def main() -> int:
    results: list[bool] = []

    # 00-setup
    setup_report = LAB / "00-setup" / "setup-report.json"
    results.append(check(
        "00-setup: setup-report.json committed",
        setup_report.exists(),
        f"path={setup_report}",
    ))

    # 01-instrument-fastapi
    results.append(check(
        "01: app /healthz reachable",
        http_ok("http://localhost:8000/healthz"),
    ))
    results.append(check(
        "01: /metrics exposes inference_requests_total",
        any("inference_requests_total" in line
            for line in http_text("http://localhost:8000/metrics").splitlines())
        if http_ok("http://localhost:8000/metrics") else False,
    ))

    # 02-prometheus-grafana
    results.append(check("02: Prometheus reachable", http_ok("http://localhost:9090/-/healthy")))
    results.append(check("02: Grafana reachable", http_ok("http://localhost:3000/api/health")))
    results.append(check("02: Alertmanager reachable", http_ok("http://localhost:9093/-/healthy")))

    # Verify dashboards loaded (Grafana API)
    dashboards = http_json(
        "http://localhost:3000/api/search?query=Day%2023",
        auth=("admin", "admin"),
    ) or []
    dash_count = len(dashboards)
    results.append(check(
        "02: 3 Day-23 dashboards loaded",
        dash_count >= 3,
        f"found={dash_count}",
    ))

    # 03-tracing-and-logs
    results.append(check("03: Jaeger UI reachable", http_ok("http://localhost:16686/")))
    results.append(check("03: Loki ready", http_ok("http://localhost:3100/ready")))
    results.append(check("03: OTel Collector self-metrics reachable", http_ok("http://localhost:8888/metrics")))

    # 04-drift-detection
    drift_summary = LAB / "04-drift-detection" / "reports" / "drift-summary.json"
    drift_ok = False
    if drift_summary.exists():
        try:
            data = json.loads(drift_summary.read_text())
            drift_ok = any(m.get("drift") == "yes" for m in data.values())
        except json.JSONDecodeError:
            pass
    results.append(check("04: drift-summary.json shows at least one drifted feature", drift_ok))

    # Submission
    reflection = SUBMISSION / "REFLECTION.md"
    results.append(check(
        "submission: REFLECTION.md exists and is non-trivial",
        reflection.exists() and len(reflection.read_text()) > 500,
    ))

    print()
    passed = sum(results)
    total = len(results)
    print(f"Result: {passed}/{total} checks passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())

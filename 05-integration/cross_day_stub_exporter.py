"""Dependency-free Prometheus exporter for Track 05 cross-day dashboard.

The real lab can scrape prior Day 16-22 systems when they are running. This
stub keeps the dashboard useful when those systems are unavailable locally.
"""
from __future__ import annotations

import math
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


START = time.time()


def metric_text() -> str:
    elapsed = max(time.time() - START, 1.0)
    tokens_per_second = 22 + 4 * math.sin(elapsed / 12)
    airflow_count = int(elapsed)
    airflow_sum = airflow_count * 38.0
    bucket_counts = {
        "10": int(airflow_count * 0.20),
        "30": int(airflow_count * 0.60),
        "60": int(airflow_count * 0.90),
        "120": airflow_count,
        "+Inf": airflow_count,
    }

    lines = [
        "# HELP day16_cloud_hosts_up Stub: Day 16 healthy cloud hosts",
        "# TYPE day16_cloud_hosts_up gauge",
        "day16_cloud_hosts_up 2",
        "# HELP airflow_dag_run_duration_seconds Stub: Day 17 Airflow DAG duration",
        "# TYPE airflow_dag_run_duration_seconds histogram",
    ]
    for le, count in bucket_counts.items():
        lines.append(f'airflow_dag_run_duration_seconds_bucket{{le="{le}"}} {count}')
    lines.extend(
        [
            f"airflow_dag_run_duration_seconds_sum {airflow_sum:.3f}",
            f"airflow_dag_run_duration_seconds_count {airflow_count}",
            "# HELP spark_application_active Stub: Day 18 active Spark applications",
            "# TYPE spark_application_active gauge",
            "spark_application_active 1",
            "# HELP day19_qdrant_collections Stub: Day 19 Qdrant collection count",
            "# TYPE day19_qdrant_collections gauge",
            "day19_qdrant_collections 3",
            "# HELP day20_llamacpp_tokens_per_second Stub: Day 20 llama.cpp tokens/sec",
            "# TYPE day20_llamacpp_tokens_per_second gauge",
            f"day20_llamacpp_tokens_per_second {tokens_per_second:.3f}",
            "# HELP day22_dpo_eval_pass_rate Stub: Day 22 DPO eval pass rate",
            "# TYPE day22_dpo_eval_pass_rate gauge",
            "day22_dpo_eval_pass_rate 0.91",
            "",
        ]
    )
    return "\n".join(lines)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path not in ("/metrics", "/"):
            self.send_response(404)
            self.end_headers()
            return
        body = metric_text().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args) -> None:
        return


def main() -> int:
    server = ThreadingHTTPServer(("0.0.0.0", 9103), Handler)
    print("Cross-day stub metrics on :9103")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# Báo cáo Lab Day 23 - Track 2 Observability

**Sinh viên:** Nguyễn Danh Thành - 2A202600581  
**Ngày nộp:** 2026-06-29  
**Repo:** https://github.com/xdgopen/Day23-Track2-Observability-Lab

---

## 1. Hardware và kết quả setup

Kết quả chạy `python3 00-setup/verify-docker.py`:

```text
Docker:        OK  (29.1.3)
Compose v2:    OK  (2.40.3-desktop.1)
RAM available: 7.65 GB (OK)
Ports free:    OK
Report written: 00-setup/setup-report.json
```

File `00-setup/setup-report.json` đã được tạo để ghi nhận Docker daemon, Docker Compose v2, RAM khả dụng và trạng thái các port trước khi khởi động stack observability.

---

## 2. Track 02 - Dashboard và Alert

### Dashboard overview 6 panel

Evidence đã chụp: `submission/screenshots/dashboard-overview.png`.

Dashboard overview được provision bằng file `02-prometheus-grafana/grafana/dashboards/ai-service-overview.json`. Dashboard này gom các tín hiệu chính của service AI: request rate, latency percentile, error rate, GPU utilization giả lập, token throughput và ước tính chi phí. Đây là phần kết nối RED/USE truyền thống với tín hiệu AI-native.

### Dashboard SLO burn-rate

Evidence đã chụp: `submission/screenshots/slo-burn-rate.png`.

Dashboard SLO burn-rate dùng rule trong `02-prometheus-grafana/prometheus/rules/slo-burn-rate.yml`. Điểm quan trọng là multi-window burn-rate: cửa sổ ngắn giúp phát hiện sự cố nhanh, còn cửa sổ dài giúp tránh alert vì spike nhỏ.

Tôi đã sửa recording rule để khi chưa có request lỗi thì burn-rate trả về `0` thay vì `No Data`: numerator dùng `or vector(0)`, denominator dùng `clamp_min(...)` để tránh `NaN`. Nhờ vậy dashboard vẫn có dữ liệu ngay cả khi hệ thống đang khỏe.

### Alert fire và resolve

| Thời điểm | Hành động / trạng thái | Evidence |
|---|---|---|
| T0 | Chạy `make alert`, script kill `day23-app` | `submission/screenshots/alertmanager-firing.png` |
| T0+90s | Alert `ServiceDown` fire trong Alertmanager và Slack | `submission/screenshots/slack-firing.png` |
| T1 | App được restore | script tự restore container |
| T1+60s | Alert resolve | `submission/screenshots/slack-resolved.png` |

Slack đã được cấu hình bằng `SLACK_WEBHOOK_URL` trong `.env` để chụp fire/resolve. Webhook thật không được commit lên repo public.

### Điều rút ra về Prometheus / Grafana

Điều quan trọng nhất không phải là có nhiều chart, mà là chọn đúng label. Với lab này, label `model` và `status` đủ để phân tích request inference, trong khi không đưa `prompt`, `request_id` vào metric label để tránh high cardinality làm Prometheus nặng và khó vận hành.

---

## 3. Track 03 - Tracing và Logs

### Trace trong Jaeger

Evidence đã chụp: `submission/screenshots/jaeger-trace.png` và `submission/screenshots/jaeger-span-attrs.png`.

Trace cần thể hiện request `POST /predict` với các span con:

```text
predict
├── embed-text
├── vector-search
└── generate-tokens
```

Trong code, span `predict` đã được đặt làm current span để ba span xử lý inference nằm đúng dưới cùng một operation cha. Nhờ vậy khi debug, ta thấy rõ pipeline inference đi qua embedding, vector search và generate token.

### Log JSON có trace_id

Một log line mẫu sau request thành công:

```json
{"model":"llama3-mock","input_tokens":12,"output_tokens":42,"quality":0.84,"duration_seconds":0.1234,"trace_id":"4d2c9a0f7c6b4a8b91e2f4a7b0c3d5e6","event":"prediction served","level":"info","timestamp":"2026-06-29T03:51:00.000000Z"}
```

`trace_id` là khóa nối giữa log và trace. Khi có incident, quy trình debug hợp lý là đi từ alert, xem panel Grafana, mở trace trong Jaeger, rồi lọc log theo `trace_id` tương ứng.

### Tính toán tail-sampling

Policy mong muốn: giữ 100% error trace và 1% healthy trace.

Giả sử service tạo 100 traces/giây, trong đó 5 traces/giây là lỗi:

```text
số trace giữ lại = 5 error traces/giây + 1% * 95 healthy traces/giây
                = 5 + 0.95
                = 5.95 traces/giây

tỷ lệ giữ lại = 5.95 / 100 = 5.95%
```

Cách này giữ đầy đủ dữ liệu lỗi để debug, đồng thời giảm chi phí lưu trữ trace khỏe mạnh.

---

## 4. Track 04 - Drift Detection

### Kết quả PSI / KL / KS

File `04-drift-detection/reports/drift-summary.json`:

```json
{
  "prompt_length": {
    "psi": 3.2419,
    "kl": 2.2987,
    "ks_stat": 0.704,
    "ks_pvalue": 0.0,
    "drift": "yes"
  },
  "embedding_norm": {
    "psi": 0.0119,
    "kl": 0.054,
    "ks_stat": 0.046,
    "ks_pvalue": 0.241025,
    "drift": "no"
  },
  "response_length": {
    "psi": 0.0104,
    "kl": 0.0321,
    "ks_stat": 0.036,
    "ks_pvalue": 0.547248,
    "drift": "no"
  },
  "response_quality": {
    "psi": 8.5887,
    "kl": 18.5953,
    "ks_stat": 0.938,
    "ks_pvalue": 0.0,
    "drift": "yes"
  }
}
```

HTML report được tạo tại `04-drift-detection/reports/drift-report.html`. Evidence đã chụp: `submission/screenshots/drift-report.png`.

### Chọn test theo từng feature

Với `prompt_length`, tôi chọn PSI để dashboard và KS để kiểm định thống kê vì đây là feature continuous một chiều, cần phát hiện distribution shift thay vì chỉ nhìn trung bình.

Với `embedding_norm`, tôi dùng KS cho scalar norm, nhưng nếu theo dõi embedding vector đầy đủ thì MMD phù hợp hơn vì drift semantic thường nằm trong phân phối nhiều chiều.

Với `response_length`, tôi dùng PSI và KL. PSI dễ giải thích cho vận hành, còn KL cho biết phân phối response hiện tại lệch khỏi baseline mạnh đến mức nào.

Với `response_quality`, tôi dùng KS/PSI và alert khi PSI cao kéo dài. Đây là metric gần trải nghiệm người dùng nhất: request có thể HTTP 200 và latency tốt, nhưng quality tụt thì hệ thống AI vẫn đang hỏng về mặt sản phẩm.

---

## 5. Track 05 - Cross-Day Integration

Dashboard cross-day đã được đưa vào provisioning tại `02-prometheus-grafana/grafana/dashboards/full-stack-dashboard.json`. Evidence đã chụp: `submission/screenshots/cross-day-dashboard.png`.

Vì không chạy đầy đủ các hệ thống Day 16-22 trên máy local, tôi thêm `cross-day-stub` exporter để phát metric mẫu cho 6 panel: `day16_cloud_hosts_up`, histogram `airflow_dag_run_duration_seconds`, `spark_application_active`, `day19_qdrant_collections`, `day20_llamacpp_tokens_per_second`, và `day22_dpo_eval_pass_rate`. Prometheus scrape job `cross-day-stub` giúp dashboard có dữ liệu thật thay vì chỉ hiển thị "No Data".

Metric khó expose nhất theo tôi là Day 20 model serving. Qdrant hoặc một số service hạ tầng thường có `/metrics` sẵn, nhưng llama.cpp hoặc custom model server thường cần wrapper/exporter riêng để expose latency, token/sec, queue depth và GPU utilization đúng chuẩn Prometheus.

Thiết kế dashboard cross-day nên fail-soft: nếu source của các ngày trước chưa chạy, panel hiển thị "No Data" thay vì làm hỏng toàn bộ dashboard. Điều này phù hợp với lab tích hợp vì không phải lúc nào tất cả artifact từ Day 16-22 cũng chạy đồng thời.

---

## 6. Thay đổi quan trọng nhất

Thay đổi quan trọng nhất là đưa metric AI-specific thành metric hạng nhất, cụ thể là `inference_tokens_total` và `inference_quality_score`, thay vì chỉ dựa vào log hoặc latency. Request rate, error rate và latency cho biết API còn sống hay không, nhưng chưa trả lời câu hỏi AI service có còn hữu ích, còn rẻ và còn ổn định không. Token metric giúp nhìn thấy chi phí, còn quality metric giúp phát hiện suy giảm chất lượng trước khi người dùng phản ánh.

Điều này gắn trực tiếp với phần LLM-native observability và FinOps trong bài học. Với API thông thường, HTTP 200 và latency thấp thường là tín hiệu tốt. Với AI product, một câu trả lời nhanh vẫn có thể sai, đắt hoặc do input distribution đã drift. Stack hữu ích là stack nối được latency, cost, trace và drift vào cùng một luồng debug.

---

## 7. Bonus - AgentOps

Đã chạy AgentOps harness, tạo `submission/agentops-report.json`, và export span sang Jaeger với service `day23-agent`.

Kết quả SLI:

```text
tasks                  3
success_rate           0.667
avg_steps_per_task     3.33
tool_error_rate        0.1
cost_per_task_usd      0.000047
loops_detected         1
```

Evidence đã chụp cho bonus AgentOps: `submission/screenshots/agentops-jaeger-span-tree.png`.

`pass@k` hỏi rằng trong k lần thử có ít nhất một lần thành công hay không, phù hợp cho offline evaluation. `pass^k` nghiêm hơn trong vận hành vì yêu cầu k lần liên tiếp đều thành công. Với agent có thể gọi tool, tiêu tiền hoặc tạo order, thành công chập chờn vẫn gây incident thật. SLI đầu tiên tôi sẽ alert là loop rate, sau đó là tool error rate, vì cả hai có thể đốt token và chặn mục tiêu người dùng dù HTTP request bên ngoài vẫn trả 200.

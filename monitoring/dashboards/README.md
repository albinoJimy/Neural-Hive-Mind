# Monitoring Dashboards

This directory contains Grafana dashboards for monitoring the Neural Hive-Mind system.

## Dashboard Overview

| Dashboard | Description | Tags |
|-----------|-------------|------|
| [ML Feedback & Retraining](#ml-feedback--retraining-dashboard) | Monitors feedback collection and model retraining pipeline | ml-ops, feedback, retraining |
| [Continuous Learning](continuous-learning-dashboard.json) | General continuous learning metrics | specialists, continuous-learning |
| [Approval Monitoring](approval-monitoring.json) | Human approval workflow metrics | approvals, governance |
| [Online Learning](online-learning-overview.json) | Online learning and model updates | online-learning, ml-ops |

---

## ML Feedback & Retraining Dashboard

Dashboard dedicated to monitoring the complete cycle of human feedback and automatic model retraining.

**File:** `ml-feedback-retraining.json`

### Key Metrics

| Metric | Description | Thresholds |
|--------|-------------|------------|
| **Feedback Count vs Threshold** | Progress toward retraining threshold | Green < 70%, Yellow 70-90%, Red > 90% |
| **Retraining Triggers (24h)** | Number of triggers in last 24 hours | Green < 3, Yellow 3-5, Red > 5 |
| **Model Performance (F1)** | Current F1 score of retrained models | Green > 0.75, Yellow 0.72-0.75, Red < 0.72 |
| **Avg Feedback Rating** | Average human rating of model outputs | Green > 0.8, Yellow 0.5-0.8, Red < 0.5 |
| **Retraining Success Rate** | Success rate of retraining triggers | Green > 90%, Yellow 70-90%, Red < 70% |

### Sections

1. **Overview** - High-level gauges and stats for quick assessment
2. **Feedback Collection** - Submission rates, rating distribution, role breakdown
3. **Retraining Triggers** - Threshold progress, trigger status distribution
4. **Retraining Execution** - Duration percentiles, auto-retrain timeline
5. **Model Performance Trends** - Precision/Recall/F1 evolution over time
6. **Dataset Quality** - Dataset sizes and API error rates

### Template Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `$specialist_type` | Filter by specialist type (technical, business, etc) | All |
| `$time_range` | Time window for analysis | 24h |

### Annotations

| Annotation | Color | Description |
|------------|-------|-------------|
| Retraining Triggered | Blue | Manual or threshold-based retraining trigger |
| Auto-Retrain Triggered | Purple | Automatic retraining based on degradation |
| Model Degradation | Red | Model performance dropped below threshold |

### Related Runbooks

- [Feedback Collection Low](docs/runbooks/feedback-collection-low.md) - When feedback rate is below expected
- [Auto-Retrain Failed](docs/runbooks/auto-retrain-failed.md) - When automatic retraining fails
- [Model Degraded](docs/runbooks/model-degraded.md) - When model performance degrades

---

## Import Dashboards

### Using the Import Script

```bash
# Import specific dashboard
./monitoring/dashboards/import-dashboards.sh ml-feedback-retraining

# Import all dashboards
./monitoring/dashboards/import-dashboards.sh --all

# Wait for Grafana to be ready, then import
./monitoring/dashboards/import-dashboards.sh --wait ml-feedback-retraining

# With custom Grafana URL and API key
GRAFANA_URL=https://grafana.neural-hive.io \
GRAFANA_API_KEY=your-api-key \
./monitoring/dashboards/import-dashboards.sh ml-feedback-retraining
```

### Using the Grafana API Directly

```bash
# Import single dashboard
curl -X POST \
  -H "Authorization: Bearer $GRAFANA_API_KEY" \
  -H "Content-Type: application/json" \
  -d @monitoring/dashboards/ml-feedback-retraining.json \
  http://grafana:3000/api/dashboards/db

# Using basic auth
curl -X POST \
  -u "admin:admin" \
  -H "Content-Type: application/json" \
  -d @monitoring/dashboards/ml-feedback-retraining.json \
  http://localhost:3000/api/dashboards/db
```

### Using Makefile Targets

```bash
# Import all dashboards
make import-dashboards

# Deploy complete monitoring stack with dashboards
make deploy-monitoring
```

### Using Kubernetes ConfigMaps

Dashboards can also be deployed as ConfigMaps for automatic provisioning:

```bash
# Apply ConfigMap
kubectl apply -f k8s/monitoring/ml-feedback-dashboard-configmap.yaml

# Verify ConfigMap
kubectl get configmap ml-feedback-retraining-dashboard -n monitoring
```

---

## Troubleshooting

### Metrics Not Appearing

1. Verify specialists are exposing metrics at `/metrics`:
   ```bash
   curl http://specialist-service:8080/metrics | grep neural_hive_feedback
   ```

2. Check Prometheus is scraping the targets:
   ```bash
   kubectl port-forward svc/prometheus 9090:9090 -n monitoring
   # Visit http://localhost:9090/targets
   ```

3. Verify ServiceMonitor configuration:
   ```bash
   kubectl get servicemonitor -n monitoring
   ```

### Threshold Not Updating

1. Check the `RETRAINING_FEEDBACK_THRESHOLD` environment variable in specialist deployments
2. Verify the metric is being updated:
   ```promql
   neural_hive_retraining_feedback_threshold
   ```

### Annotations Not Appearing

1. Ensure Prometheus datasource is configured correctly in Grafana
2. Check annotation queries are valid:
   ```promql
   changes(neural_hive_retraining_triggers_total[1m]) > 0
   ```

### Import Fails

1. Check Grafana is running and accessible:
   ```bash
   curl http://localhost:3000/api/health
   ```

2. Verify authentication credentials:
   ```bash
   curl -u admin:admin http://localhost:3000/api/org
   ```

3. Check JSON syntax:
   ```bash
   jq . monitoring/dashboards/ml-feedback-retraining.json
   ```

---

## Data Flow Diagram

```
+----------------+     +------------+     +---------+     +--------+
|   Specialists  | --> | Prometheus | --> | Grafana | --> |  User  |
|   /metrics     |     |  Scrape    |     | Query   |     |  View  |
+----------------+     +------------+     +---------+     +--------+
        |                    |                 |
        v                    v                 v
+----------------+     +------------+     +---------+
| Metrics:       |     | Time Series|     | Panels: |
| - feedback_*   |     | Storage    |     | - Gauge |
| - retraining_* |     | (15 days)  |     | - Graph |
| - model_*      |     |            |     | - Pie   |
+----------------+     +------------+     +---------+
```

---

## Adding New Dashboards

1. Create the dashboard JSON file in this directory
2. Follow the naming convention: `<feature>-<component>.json`
3. Include required metadata:
   - `title`: Descriptive dashboard title
   - `tags`: Relevant tags for filtering
   - `uid`: Unique identifier for the dashboard
4. Add documentation in this README
5. Update the import script if needed

---

## References

- [Grafana Dashboard JSON Model](https://grafana.com/docs/grafana/latest/dashboards/json-model/)
- [Prometheus Query Language](https://prometheus.io/docs/prometheus/latest/querying/basics/)
- [Neural Hive Metrics Reference](../docs/metrics-reference.md)

#!/usr/bin/env bash
set -euo pipefail

echo "[rollback-worker-agents-to-simulation] Rolling back executors to simulation mode"
echo "Set integration flags to false in Helm values and redeploy."

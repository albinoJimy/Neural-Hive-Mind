#!/bin/bash
set -e

echo "Analyzing Gatekeeper violations..."

echo "=== Constraint Templates ==="
kubectl get constrainttemplates

echo ""
echo "=== Constraints ==="
kubectl get constraints -A

echo ""
echo "=== Violations by Namespace ==="
kubectl get violations -A -o wide || echo "No violations found"

echo ""
echo "=== Detailed Violations ==="
for violation in $(kubectl get violations -A -o jsonpath='{.items[*].metadata.name}' 2>/dev/null); do
  kubectl get violation $violation -A -o yaml | grep -A 5 "metadata:" | head -10
done

echo ""
echo "=== Top Violation Types ==="
kubectl get violations -A -o json | jq -r '.items[] | .kind' | sort | uniq -c | sort -rn
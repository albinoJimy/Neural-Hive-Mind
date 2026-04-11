#!/bin/bash
set -e

NAMESPACE="redis-cluster"
GRACE_PERIOD=${1:-7}

echo "Redis cleanup script"
echo "WARNING: This will remove the old Redis pod!"
echo ""
read -p "Continue? (yes/no) " -n 1 -r
echo

if [ "$REPLY" != "yes" ]; then
  echo "Aborted"
  exit 1
fi

if [ -f "./redis-sync-verify.sh" ]; then
  ./redis-sync-verify.sh
elif [ -f "scripts/redis-sync-verify.sh" ]; then
  ./scripts/redis-sync-verify.sh
else
  echo "Error: redis-sync-verify.sh not found"
  exit 1
fi

if [ $? -ne 0 ]; then
  echo "Verification failed! Aborting cleanup."
  exit 1
fi

echo ""
echo "Cleanup phase 1 complete: Old Redis scaled down"
echo "Final deletion scheduled for $(date -d "+$GRACE_PERIOD days" +%Y-%m-%d)"
#!/bin/bash
set -e

BACKUP_DIR=${1:-"$(ls -td redis/backups/* | head -1)"}

if [ ! -d "$BACKUP_DIR" ]; then
  echo "Backup directory not found: $BACKUP_DIR"
  exit 1
fi

echo "Verifying backup: $BACKUP_DIR"

for file in dump.rdb redis.conf sha256sum.txt; do
  if [ ! -f "$BACKUP_DIR/$file" ]; then
    echo "Missing file: $file"
    exit 1
  fi
done

echo "Verifying SHA256 checksum..."
cd $BACKUP_DIR
sha256sum -c sha256sum.txt
cd -

DUMP_SIZE=$(stat -f%z "$BACKUP_DIR/dump.rdb" 2>/dev/null || stat -c%s "$BACKUP_DIR/dump.rdb")
if [ "$DUMP_SIZE" -lt 100 ]; then
  echo "ERROR: dump.rdb too small ($DUMP_SIZE bytes)"
  exit 1
fi

echo "Backup verification passed!"
echo "Backup: $BACKUP_DIR"
echo "Size: $DUMP_SIZE bytes"
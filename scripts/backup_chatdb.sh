#!/bin/bash
set -e

STAMP=$(date +%Y-%m-%d)
BACKUP_DIR=/root/chatdb-backups
DB_PATH_FILE=/root/.chatdb_path

mkdir -p "$BACKUP_DIR"

# Lan dau chay: tu do tim chat.db that (host hoac trong docker), luu lai duong dan de lan sau dung luon
if [ ! -f "$DB_PATH_FILE" ]; then
  HOST_PATH=$(find / -xdev -name "chat.db" -path "*/data/*" 2>/dev/null | head -1)
  if [ -n "$HOST_PATH" ]; then
    echo "host:$HOST_PATH" > "$DB_PATH_FILE"
  else
    CONTAINER=$(docker ps --format '{{.Names}}' 2>/dev/null | grep -i chatbot | head -1)
    if [ -n "$CONTAINER" ]; then
      CPATH=$(docker exec "$CONTAINER" find / -name "chat.db" -path "*/data/*" 2>/dev/null | head -1)
      echo "docker:$CONTAINER:$CPATH" > "$DB_PATH_FILE"
    else
      echo "KHONG TIM THAY chat.db - vui long kiem tra tay" >&2
      exit 1
    fi
  fi
fi

MODE=$(cut -d: -f1 "$DB_PATH_FILE")

if [ "$MODE" = "host" ]; then
  SRC_PATH=$(cut -d: -f2- "$DB_PATH_FILE")
  sqlite3 "$SRC_PATH" "VACUUM INTO '/tmp/chat_${STAMP}.sqlite'"
else
  CONTAINER=$(cut -d: -f2 "$DB_PATH_FILE")
  CPATH=$(cut -d: -f3- "$DB_PATH_FILE")
  docker exec "$CONTAINER" node -e "
    const { DatabaseSync } = require('node:sqlite');
    const db = new DatabaseSync('$CPATH', { readOnly: true });
    db.exec(\"VACUUM INTO '/tmp/chat_${STAMP}.sqlite'\");
  "
  docker cp "$CONTAINER:/tmp/chat_${STAMP}.sqlite" "/tmp/chat_${STAMP}.sqlite"
fi

gzip -9 "/tmp/chat_${STAMP}.sqlite" -c > "$BACKUP_DIR/chat_${STAMP}.sqlite.gz"
rm -f "/tmp/chat_${STAMP}.sqlite"

# Chi xoa ban backup da qua 365 ngay tuoi, con lai giu nguyen
find "$BACKUP_DIR" -name "chat_*.sqlite.gz" -mtime +365 -delete

echo "Backup xong: $BACKUP_DIR/chat_${STAMP}.sqlite.gz"

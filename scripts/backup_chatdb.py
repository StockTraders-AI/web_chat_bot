#!/usr/bin/env python3
"""Backup service for chat.db.

Runs as a long-lived process (systemd/pm2/docker), not via cron.
On startup it takes a backup immediately, then schedules one every
day at 00:00. Old backups (older than RETENTION_DAYS) are pruned
after each run.
"""
import gzip
import logging
import shutil
import sqlite3
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler

BACKUP_DIR = Path("/root/chatdb-backups")
DB_PATH_FILE = Path("/root/.chatdb_path")
RETENTION_DAYS = 365

BACKUP_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(BACKUP_DIR / "backup.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("backup_chatdb")


def _run(cmd: list[str]) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.strip()


def locate_chat_db() -> tuple[str, str, str | None]:
    """Return (mode, path, container) using the cached location if present."""
    if DB_PATH_FILE.exists():
        parts = DB_PATH_FILE.read_text().strip().split(":", 2)
        if parts[0] == "host":
            return "host", parts[1], None
        return "docker", parts[2], parts[1]

    try:
        out = _run(["find", "/", "-xdev", "-name", "chat.db", "-path", "*/data/*"])
        host_path = out.splitlines()[0] if out else ""
    except subprocess.CalledProcessError:
        host_path = ""

    if host_path:
        DB_PATH_FILE.write_text(f"host:{host_path}\n")
        return "host", host_path, None

    try:
        containers = _run(["docker", "ps", "--format", "{{.Names}}"]).splitlines()
    except (subprocess.CalledProcessError, FileNotFoundError):
        containers = []
    container = next((c for c in containers if "chatbot" in c.lower()), None)
    if not container:
        raise RuntimeError("Khong tim thay chat.db - vui long kiem tra tay")

    out = _run(["docker", "exec", container, "find", "/", "-name", "chat.db", "-path", "*/data/*"])
    container_path = out.splitlines()[0] if out else ""
    if not container_path:
        raise RuntimeError("Khong tim thay chat.db trong container - vui long kiem tra tay")

    DB_PATH_FILE.write_text(f"docker:{container}:{container_path}\n")
    return "docker", container_path, container


def snapshot_to_sqlite(mode: str, path: str, container: str | None, dest: Path) -> None:
    if mode == "host":
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            conn.execute(f"VACUUM INTO '{dest}'")
        finally:
            conn.close()
        return

    tmp_in_container = f"/tmp/{dest.name}"
    node_script = (
        "const { DatabaseSync } = require('node:sqlite');"
        f"const db = new DatabaseSync('{path}', {{ readOnly: true }});"
        f"db.exec(\"VACUUM INTO '{tmp_in_container}'\");"
    )
    _run(["docker", "exec", container, "node", "-e", node_script])
    _run(["docker", "cp", f"{container}:{tmp_in_container}", str(dest)])
    _run(["docker", "exec", container, "rm", "-f", tmp_in_container])


def prune_old_backups() -> None:
    cutoff = datetime.now() - timedelta(days=RETENTION_DAYS)
    for f in BACKUP_DIR.glob("chat_*.sqlite.gz"):
        if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
            f.unlink()
            log.info("Da xoa backup qua han: %s", f.name)


def backup_job() -> None:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d")
    tmp_sqlite = Path(f"/tmp/chat_{stamp}.sqlite")
    final_gz = BACKUP_DIR / f"chat_{stamp}.sqlite.gz"

    try:
        mode, path, container = locate_chat_db()
        snapshot_to_sqlite(mode, path, container, tmp_sqlite)

        with open(tmp_sqlite, "rb") as src, gzip.open(final_gz, "wb", compresslevel=9) as dst:
            shutil.copyfileobj(src, dst)

        prune_old_backups()
        log.info("Backup xong: %s", final_gz)
    except Exception:
        log.exception("Backup that bai")
    finally:
        tmp_sqlite.unlink(missing_ok=True)


def main() -> None:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_job()  # chay ngay 1 lan khi service khoi dong

    scheduler = BlockingScheduler(timezone="Asia/Ho_Chi_Minh")
    scheduler.add_job(backup_job, "cron", hour=0, minute=0)
    log.info("Backup service da khoi dong, lich chay moi ngay 00:00")
    scheduler.start()


if __name__ == "__main__":
    main()

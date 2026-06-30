import aiosqlite
import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta
from settings import (
    SQLITE_PATH,
    HISTORY_TURNS,
    SUPER_ADMIN_USERNAME,
    SUPER_ADMIN_PASSWORD,
    AUTH_SESSION_DAYS,
)


CREATE_SQL = """
CREATE TABLE IF NOT EXISTS chat_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_chat_user_id ON chat_history(user_id, id);

CREATE TABLE IF NOT EXISTS ai_token_usage_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tenant_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  user_key TEXT NOT NULL,
  conversation_id TEXT NOT NULL,
  request_id TEXT NOT NULL,
  route TEXT NOT NULL,
  model TEXT,
  prompt_tokens INTEGER NOT NULL DEFAULT 0,
  completion_tokens INTEGER NOT NULL DEFAULT 0,
  total_tokens INTEGER NOT NULL DEFAULT 0,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_ai_usage_user_key_created
ON ai_token_usage_events(user_key, created_at);
CREATE INDEX IF NOT EXISTS idx_ai_usage_tenant_user_created
ON ai_token_usage_events(tenant_id, user_id, created_at);

CREATE TABLE IF NOT EXISTS semantic_guide_states (
  user_id TEXT PRIMARY KEY,
  state_json TEXT NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  expires_at DATETIME
);
CREATE INDEX IF NOT EXISTS idx_semantic_guide_states_expires
ON semantic_guide_states(expires_at);
CREATE TABLE IF NOT EXISTS sales_discovery_sessions (
  user_id TEXT PRIMARY KEY,
  stage TEXT NOT NULL DEFAULT 'collecting',
  targets_json TEXT NOT NULL,
  summary_json TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  completed_at DATETIME
);

CREATE TABLE IF NOT EXISTS sales_discovery_targets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  target_key TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  suggested_question TEXT NOT NULL DEFAULT '',
  recognizer_key TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'waiting'
    CHECK(status IN ('waiting','supported','confirmed','disabled')),
  active INTEGER NOT NULL DEFAULT 0 CHECK(active IN (0, 1)),
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_by TEXT DEFAULT 'system',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_sales_discovery_targets_status
ON sales_discovery_targets(status, active, sort_order);

CREATE TABLE IF NOT EXISTS case_ideas (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  indicators TEXT NOT NULL DEFAULT '',
  description TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'waiting'
    CHECK(status IN ('waiting','supported')),
  created_by TEXT DEFAULT 'system',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_case_ideas_status
ON case_ideas(status, id);

CREATE TABLE IF NOT EXISTS customer_profiles (
  user_id TEXT PRIMARY KEY,
  gender TEXT,
  birth_year TEXT,
  investment_experience TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sales_demo_users (
  user_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS accounts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT NOT NULL UNIQUE,
  display_name TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('super_admin', 'admin', 'member')),
  status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'locked')),
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  last_login_at DATETIME
);
CREATE INDEX IF NOT EXISTS idx_accounts_role ON accounts(role);
CREATE INDEX IF NOT EXISTS idx_accounts_status ON accounts(status);

CREATE TABLE IF NOT EXISTS account_sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  account_id INTEGER NOT NULL,
  token_hash TEXT NOT NULL UNIQUE,
  expires_at DATETIME NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  revoked_at DATETIME,
  FOREIGN KEY(account_id) REFERENCES accounts(id)
);
CREATE INDEX IF NOT EXISTS idx_account_sessions_account_id ON account_sessions(account_id);
CREATE INDEX IF NOT EXISTS idx_account_sessions_token_hash ON account_sessions(token_hash);

CREATE TABLE IF NOT EXISTS account_audit_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  actor_account_id INTEGER,
  action TEXT NOT NULL,
  target_account_id INTEGER,
  detail_json TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(actor_account_id) REFERENCES accounts(id),
  FOREIGN KEY(target_account_id) REFERENCES accounts(id)
);

CREATE TABLE IF NOT EXISTS permissions (
  key TEXT PRIMARY KEY,
  label TEXT NOT NULL,
  sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS role_permissions (
  role TEXT NOT NULL,
  permission_key TEXT NOT NULL,
  PRIMARY KEY(role, permission_key),
  FOREIGN KEY(permission_key) REFERENCES permissions(key)
);

CREATE TABLE IF NOT EXISTS account_permissions (
  account_id INTEGER NOT NULL,
  permission_key TEXT NOT NULL,
  enabled INTEGER NOT NULL CHECK(enabled IN (0, 1)),
  PRIMARY KEY(account_id, permission_key),
  FOREIGN KEY(account_id) REFERENCES accounts(id),
  FOREIGN KEY(permission_key) REFERENCES permissions(key)
);

CREATE TABLE IF NOT EXISTS condition_types (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  value_key TEXT NOT NULL UNIQUE,
  label TEXT NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_condition_types_value_key
ON condition_types(value_key);

CREATE TABLE IF NOT EXISTS condition_templates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  type TEXT NOT NULL,
  name TEXT NOT NULL,
  condition_logic TEXT DEFAULT '',
  description TEXT NOT NULL,
  status TEXT NOT NULL
    DEFAULT 'waiting'
    CHECK(status IN (
      'waiting',
      'confirmed',
      'need_update'
    )),
  created_by TEXT DEFAULT 'system',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS condition_flows (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  expression TEXT NOT NULL,
  prompt_template TEXT NOT NULL,
  trigger_prompt TEXT NOT NULL DEFAULT '',
  active INTEGER NOT NULL DEFAULT 0 CHECK(active IN (0, 1)),
  status TEXT NOT NULL DEFAULT 'draft'
    CHECK(status IN ('draft','confirmed','running','disabled')),
  created_by TEXT DEFAULT 'system',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_condition_flows_status
ON condition_flows(status);

CREATE INDEX IF NOT EXISTS idx_condition_templates_status
ON condition_templates(status);

CREATE INDEX IF NOT EXISTS idx_condition_templates_type
ON condition_templates(type);
"""

PERMISSIONS = [
    ("chat.use", "Sử dụng chatbot", 10)
]

ROLE_PERMISSION_KEYS = {
    "super_admin":["chat.use"],
    "admin":["chat.use"],
    "member":["chat.use"]
}

DEFAULT_SALES_DISCOVERY_TARGETS = [
    (
        "investment_experience",
        "Thâm niên đầu tư",
        "Biết khách mới tham gia, đầu tư được bao lâu, hoặc đã trải qua vài nhịp thị trường chưa.",
        "Để em tư vấn đúng hơn, anh/chị tham gia thị trường chứng khoán được bao lâu rồi ạ?",
        "investment_experience",
        10,
    ),
    (
        "nav",
        "NAV / quy mô vốn",
        "Biết khoảng vốn khách thường dùng cho chứng khoán, có thể là con số cụ thể hoặc khoảng tương đối.",
        "Hiện anh/chị thường phân bổ khoảng bao nhiêu vốn cho chứng khoán ạ?",
        "money_amount",
        20,
    ),
    (
        "portfolio_cost",
        "Danh mục + giá vốn",
        "Biết các mã chính khách đang nắm và giá vốn nếu khách cung cấp được.",
        "Anh/chị đang nắm những mã nào và giá vốn khoảng bao nhiêu ạ?",
        "ticker_portfolio",
        30,
    ),
    (
        "decision_basis",
        "Cơ sở ra quyết định",
        "Biết khách thường mua bán dựa vào broker, tin tức, tự phân tích, bảng giá, dòng tiền, app, hay cảm tính.",
        "Thường anh/chị quyết định mua bán dựa vào đâu là chính ạ?",
        "decision_basis",
        40,
    ),
]

class MemoryStore:
    def __init__(self, db_path: str = str(SQLITE_PATH)):
        self.db_path = db_path

    async def init(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(CREATE_SQL)
            await self._migrate_condition_templates_type_check(db)

            try:
                await db.execute(
                    "ALTER TABLE condition_templates ADD COLUMN condition_logic TEXT DEFAULT ''"
                )
            except Exception:
                pass

            try:
                await db.execute(
                    "ALTER TABLE condition_flows ADD COLUMN active INTEGER NOT NULL DEFAULT 0 CHECK(active IN (0, 1))"
                )
            except Exception:
                pass

            try:
                await db.execute(
                    "ALTER TABLE condition_flows ADD COLUMN trigger_prompt TEXT NOT NULL DEFAULT ''"
                )
            except Exception:
                pass

            try:
                cur = await db.execute(
                    """
                    SELECT sql
                    FROM sqlite_master
                    WHERE type='table'
                    AND name='condition_flows'
                    """
                )
                row = await cur.fetchone()
                table_sql = row[0] if row else ""

                if "active','inactive" in table_sql or "active', 'inactive" in table_sql:
                    await db.execute("ALTER TABLE condition_flows RENAME TO condition_flows_old")

                    await db.execute(
                        """
                        CREATE TABLE condition_flows (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        expression TEXT NOT NULL,
                        prompt_template TEXT NOT NULL,
                        trigger_prompt TEXT NOT NULL DEFAULT '',
                        active INTEGER NOT NULL DEFAULT 0 CHECK(active IN (0, 1)),
                        status TEXT NOT NULL DEFAULT 'draft'
                            CHECK(status IN ('draft','confirmed','running','disabled')),
                        created_by TEXT DEFAULT 'system',
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                        )
                        """
                    )

                    await db.execute(
                        """
                        INSERT INTO condition_flows(
                            id,
                            name,
                            expression,
                            prompt_template,
                            trigger_prompt,
                            active,
                            status,
                            created_by,
                            created_at,
                            updated_at
                        )
                        SELECT
                            id,
                            name,
                            expression,
                            prompt_template,
                            '',
                            CASE
                                WHEN status='active' THEN 1
                                ELSE 0
                            END,
                            CASE
                                WHEN status='active' THEN 'draft'
                                WHEN status='inactive' THEN 'disabled'
                                ELSE status
                            END,
                            created_by,
                            created_at,
                            updated_at
                        FROM condition_flows_old
                        """
                    )

                    await db.execute("DROP TABLE condition_flows_old")

                    await db.execute(
                        """
                        CREATE INDEX IF NOT EXISTS idx_condition_flows_status
                        ON condition_flows(status)
                        """
                    )
            except Exception:
                pass

            await self._ensure_permissions(db)
            await self._ensure_super_admin(db)
            await self._ensure_sales_discovery_targets(db)
            await db.commit()

    @staticmethod
    def _format_dt(value: datetime) -> str:
        return value.strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _hash_password(password: str) -> str:
        iterations = 260000
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        salt_text = base64.b64encode(salt).decode("ascii")
        digest_text = base64.b64encode(digest).decode("ascii")
        return f"pbkdf2_sha256${iterations}${salt_text}${digest_text}"

    @staticmethod
    def _verify_password(password: str, stored_hash: str) -> bool:
        try:
            algorithm, iterations_text, salt_text, digest_text = stored_hash.split("$", 3)
            if algorithm != "pbkdf2_sha256":
                return False
            iterations = int(iterations_text)
            salt = base64.b64decode(salt_text.encode("ascii"))
            expected = base64.b64decode(digest_text.encode("ascii"))
        except (ValueError, TypeError):
            return False

        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(actual, expected)

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _account_from_row(row):
        if not row:
            return None

        return {
            "id": row[0],
            "username": row[1],
            "display_name": row[2],
            "role": row[3],
            "status": row[4],
            "created_at": row[5],
            "updated_at": row[6],
            "last_login_at": row[7],
        }

    async def _ensure_super_admin(self, db):
        cur = await db.execute(
            "SELECT id FROM accounts WHERE role='super_admin' ORDER BY id ASC LIMIT 1"
        )
        row = await cur.fetchone()
        if row:
            return

        password_hash = self._hash_password(SUPER_ADMIN_PASSWORD)
        await db.execute(
            """
            INSERT INTO accounts(username, display_name, password_hash, role, status)
            VALUES(?, ?, ?, 'super_admin', 'active')
            """,
            (SUPER_ADMIN_USERNAME, "Super Admin", password_hash),
        )

    async def _ensure_permissions(self, db):
        active_keys = [item[0] for item in PERMISSIONS]
        placeholders = ",".join("?" for _ in active_keys)

        for key, label, sort_order in PERMISSIONS:
            await db.execute(
                """
                INSERT INTO permissions(key, label, sort_order)
                VALUES(?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                  label=excluded.label,
                  sort_order=excluded.sort_order
                """,
                (key, label, sort_order),
            )

        await db.execute(
            f"DELETE FROM account_permissions WHERE permission_key NOT IN ({placeholders})",
            active_keys,
        )
        await db.execute("DELETE FROM role_permissions")
        await db.execute(
            f"DELETE FROM permissions WHERE key NOT IN ({placeholders})",
            active_keys,
        )
        for role, keys in ROLE_PERMISSION_KEYS.items():
            for key in keys:
                await db.execute(
                    """
                    INSERT INTO role_permissions(role, permission_key)
                    VALUES(?, ?)
                    """,
                    (role, key),
                )

    async def _ensure_sales_discovery_targets(self, db):
        for target_key, name, description, suggested_question, recognizer_key, sort_order in DEFAULT_SALES_DISCOVERY_TARGETS:
            await db.execute(
                """
                INSERT INTO sales_discovery_targets(
                    target_key,
                    name,
                    description,
                    suggested_question,
                    recognizer_key,
                    status,
                    active,
                    sort_order,
                    created_by
                )
                VALUES(?, ?, ?, ?, ?, 'confirmed', 1, ?, 'system')
                ON CONFLICT(target_key) DO UPDATE SET
                    name=excluded.name,
                    description=excluded.description,
                    suggested_question=excluded.suggested_question,
                    recognizer_key=excluded.recognizer_key,
                    sort_order=excluded.sort_order
                """,
                (
                    target_key,
                    name,
                    description,
                    suggested_question,
                    recognizer_key,
                    sort_order,
                ),
            )

    async def _migrate_condition_templates_type_check(self, db):
        cur = await db.execute(
            """
            SELECT sql
            FROM sqlite_master
            WHERE type='table'
            AND name='condition_templates'
            """
        )

        row = await cur.fetchone()
        table_sql = row[0] if row else ""

        if "CHECK(type IN" not in table_sql:
            return

        await db.execute(
            "ALTER TABLE condition_templates RENAME TO condition_templates_old"
        )

        await db.execute(
            """
            CREATE TABLE condition_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            name TEXT NOT NULL,
            condition_logic TEXT DEFAULT '',
            description TEXT NOT NULL,
            status TEXT NOT NULL
                DEFAULT 'waiting'
                CHECK(status IN (
                'waiting',
                'confirmed',
                'need_update'
                )),
            created_by TEXT DEFAULT 'system',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        await db.execute(
            """
            INSERT INTO condition_templates(
            id,
            type,
            name,
            condition_logic,
            description,
            status,
            created_by,
            created_at,
            updated_at
            )
            SELECT
            id,
            type,
            name,
            condition_logic,
            description,
            status,
            created_by,
            created_at,
            updated_at
            FROM condition_templates_old
            """
        )

        await db.execute("DROP TABLE condition_templates_old")



    async def authenticate_account(self, username: str, password: str):
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """
                SELECT id, username, display_name, password_hash, role, status,
                       created_at, updated_at, last_login_at
                FROM accounts
                WHERE username=?
                """,
                (username.strip(),),
            )
            row = await cur.fetchone()

            if not row or row[5] != "active":
                return None

            if not self._verify_password(password, row[3]):
                return None

            await db.execute(
                "UPDATE accounts SET last_login_at=CURRENT_TIMESTAMP WHERE id=?",
                (row[0],),
            )
            await db.commit()

        return {
            "id": row[0],
            "username": row[1],
            "display_name": row[2],
            "role": row[4],
            "status": row[5],
            "created_at": row[6],
            "updated_at": row[7],
            "last_login_at": row[8],
        }

    async def create_account_session(self, account_id: int):
        token = secrets.token_urlsafe(32)
        token_hash = self._hash_token(token)
        expires_at = self._format_dt(datetime.utcnow() + timedelta(days=AUTH_SESSION_DAYS))

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO account_sessions(account_id, token_hash, expires_at)
                VALUES(?, ?, ?)
                """,
                (account_id, token_hash, expires_at),
            )
            await db.commit()

        return {"token": token, "expires_at": expires_at}

    async def get_account_by_session_token(self, token: str):
        token_hash = self._hash_token(token)
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """
                SELECT a.id, a.username, a.display_name, a.role, a.status,
                       a.created_at, a.updated_at, a.last_login_at
                FROM account_sessions s
                JOIN accounts a ON a.id=s.account_id
                WHERE s.token_hash=?
                  AND s.revoked_at IS NULL
                  AND s.expires_at > CURRENT_TIMESTAMP
                  AND a.status='active'
                """,
                (token_hash,),
            )
            row = await cur.fetchone()

        return self._account_from_row(row)

    async def revoke_account_session(self, token: str):
        token_hash = self._hash_token(token)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE account_sessions
                SET revoked_at=CURRENT_TIMESTAMP
                WHERE token_hash=? AND revoked_at IS NULL
                """,
                (token_hash,),
            )
            await db.commit()

    async def list_accounts(self):
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """
                SELECT id, username, display_name, role, status,
                       created_at, updated_at, last_login_at
                FROM accounts
                ORDER BY id ASC
                """
            )
            rows = await cur.fetchall()

        return [self._account_from_row(row) for row in rows]

    async def list_account_audit_logs(self, limit: int = 10):
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """
                SELECT l.created_at,
                       COALESCE(actor.username, 'system') AS actor_username,
                       l.action,
                       COALESCE(target.username, '') AS target_username,
                       l.detail_json
                FROM account_audit_logs l
                LEFT JOIN accounts actor ON actor.id=l.actor_account_id
                LEFT JOIN accounts target ON target.id=l.target_account_id
                ORDER BY l.id DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = await cur.fetchall()

        return [
            {
                "created_at": row[0],
                "actor_username": row[1],
                "action": row[2],
                "target_username": row[3],
                "detail_json": row[4],
            }
            for row in rows
        ]

    async def get_account(self, account_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """
                SELECT id, username, display_name, role, status,
                       created_at, updated_at, last_login_at
                FROM accounts
                WHERE id=?
                """,
                (account_id,),
            )
            row = await cur.fetchone()

        return self._account_from_row(row)

    async def list_permissions(self):
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """
                SELECT key, label, sort_order
                FROM permissions
                ORDER BY sort_order ASC, key ASC
                """
            )
            rows = await cur.fetchall()

        return [
            {"key": row[0], "label": row[1], "sort_order": row[2]}
            for row in rows
        ]

    async def get_effective_permissions(self, account_id: int):
        account = await self.get_account(account_id)
        if not account:
            return None

        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """
                SELECT p.key, p.label, p.sort_order,
                       CASE
                         WHEN ap.enabled IS NOT NULL THEN ap.enabled
                         WHEN rp.permission_key IS NOT NULL THEN 1
                         ELSE 0
                       END AS enabled
                FROM permissions p
                LEFT JOIN role_permissions rp
                  ON rp.permission_key=p.key AND rp.role=?
                LEFT JOIN account_permissions ap
                  ON ap.permission_key=p.key AND ap.account_id=?
                ORDER BY p.sort_order ASC, p.key ASC
                """,
                (account["role"], account_id),
            )
            rows = await cur.fetchall()

        permissions = [
            {
                "key": row[0],
                "label": row[1],
                "sort_order": row[2],
                "enabled": bool(row[3]),
            }
            for row in rows
        ]

        if account["role"] == "super_admin":
            for permission in permissions:
                permission["enabled"] = True

        return {"account": account, "permissions": permissions}

    async def account_has_permission(self, account_id: int, permission_key: str):
        effective = await self.get_effective_permissions(account_id)
        if not effective:
            return False

        return any(
            item["key"] == permission_key and item["enabled"]
            for item in effective["permissions"]
        )

    async def replace_account_permissions(
        self,
        account_id: int,
        enabled_keys: list[str],
        actor_account_id: int | None = None,
    ):
        account = await self.get_account(account_id)
        if not account:
            return None

        allowed = {item[0] for item in PERMISSIONS}
        clean_keys = sorted(set(enabled_keys) & allowed)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM account_permissions WHERE account_id=?",
                (account_id,),
            )
            for key in allowed:
                await db.execute(
                    """
                    INSERT INTO account_permissions(account_id, permission_key, enabled)
                    VALUES(?, ?, ?)
                    """,
                    (account_id, key, 1 if key in clean_keys else 0),
                )
            await db.execute(
                """
                INSERT INTO account_audit_logs(
                  actor_account_id, action, target_account_id, detail_json
                )
                VALUES(?, 'update_permissions', ?, ?)
                """,
                (
                    actor_account_id,
                    account_id,
                    json.dumps({"permissions": clean_keys}, ensure_ascii=False),
                ),
            )
            await db.commit()

        return await self.get_effective_permissions(account_id)

    async def count_super_admins(self):
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "SELECT COUNT(*) FROM accounts WHERE role='super_admin' AND status='active'"
            )
            row = await cur.fetchone()

        return int(row[0] or 0)

    async def add_account_audit(
        self,
        actor_account_id: int | None,
        action: str,
        target_account_id: int | None = None,
        detail_json: str | None = None,
    ):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO account_audit_logs(
                  actor_account_id, action, target_account_id, detail_json
                )
                VALUES(?, ?, ?, ?)
                """,
                (actor_account_id, action, target_account_id, detail_json),
            )
            await db.commit()

    async def has_assistant_message(self, user_id: str, content: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """
                SELECT 1
                FROM chat_history
                WHERE user_id=? AND role='assistant' AND content=?
                LIMIT 1
                """,
                (user_id, content),
            )
            row = await cur.fetchone()

        return row is not None

    async def create_account(
        self,
        username: str,
        display_name: str,
        password: str,
        role: str,
        actor_account_id: int | None = None,
    ):
        password_hash = self._hash_password(password)

        async with aiosqlite.connect(self.db_path) as db:
            try:
                cur = await db.execute(
                    """
                    INSERT INTO accounts(
                      username, display_name, password_hash, role, status
                    )
                    VALUES(?, ?, ?, ?, 'active')
                    """,
                    (username.strip(), display_name.strip(), password_hash, role),
                )
            except aiosqlite.IntegrityError:
                return None

            account_id = cur.lastrowid
            default_keys = ROLE_PERMISSION_KEYS.get(role, [])
            for permission_key, _, _ in PERMISSIONS:
                await db.execute(
                    """
                    INSERT INTO account_permissions(account_id, permission_key, enabled)
                    VALUES(?, ?, ?)
                    """,
                    (account_id, permission_key, 1 if permission_key in default_keys else 0),
                )
            await db.execute(
                """
                INSERT INTO account_audit_logs(
                  actor_account_id, action, target_account_id, detail_json
                )
                VALUES(?, 'create_account', ?, ?)
                """,
                (
                    actor_account_id,
                    account_id,
                    json.dumps({"username": username.strip(), "role": role}, ensure_ascii=False),
                ),
            )
            await db.commit()

        return await self.get_account(account_id)

    async def update_account(
        self,
        account_id: int,
        display_name: str | None = None,
        role: str | None = None,
        status: str | None = None,
        actor_account_id: int | None = None,
    ):
        existing = await self.get_account(account_id)
        if not existing:
            return None

        next_display_name = display_name.strip() if display_name is not None else existing["display_name"]
        next_role = role if role is not None else existing["role"]
        next_status = status if status is not None else existing["status"]

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE accounts
                SET display_name=?, role=?, status=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (next_display_name, next_role, next_status, account_id),
            )
            await db.execute(
                """
                INSERT INTO account_audit_logs(
                  actor_account_id, action, target_account_id, detail_json
                )
                VALUES(?, 'update_account', ?, ?)
                """,
                (
                    actor_account_id,
                    account_id,
                    json.dumps({"role": next_role, "status": next_status}, ensure_ascii=False),
                ),
            )
            await db.commit()

        return await self.get_account(account_id)

    async def reset_account_password(
        self,
        account_id: int,
        new_password: str,
        actor_account_id: int | None = None,
    ):
        existing = await self.get_account(account_id)
        if not existing:
            return None

        password_hash = self._hash_password(new_password)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE accounts
                SET password_hash=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (password_hash, account_id),
            )
            await db.execute(
                """
                UPDATE account_sessions
                SET revoked_at=CURRENT_TIMESTAMP
                WHERE account_id=? AND revoked_at IS NULL
                """,
                (account_id,),
            )
            await db.execute(
                """
                INSERT INTO account_audit_logs(
                  actor_account_id, action, target_account_id
                )
                VALUES(?, 'reset_password', ?)
                """,
                (actor_account_id, account_id),
            )
            await db.commit()

        return await self.get_account(account_id)

    async def delete_account(self, account_id: int, actor_account_id: int | None = None):
        existing = await self.get_account(account_id)
        if not existing:
            return None

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO account_audit_logs(
                  actor_account_id, action, target_account_id, detail_json
                )
                VALUES(?, 'delete_account', ?, ?)
                """,
                (
                    actor_account_id,
                    account_id,
                    json.dumps(
                        {"username": existing["username"], "role": existing["role"]},
                        ensure_ascii=False,
                    ),
                ),
            )
            await db.execute("DELETE FROM account_sessions WHERE account_id=?", (account_id,))
            await db.execute("DELETE FROM account_permissions WHERE account_id=?", (account_id,))
            await db.execute("DELETE FROM accounts WHERE id=?", (account_id,))
            await db.commit()

        return existing

    async def add(self, user_id: str, role: str, content: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO chat_history(user_id, role, content) VALUES(?,?,?)",
                (user_id, role, content),
            )
            await db.commit()

    async def get_semantic_guide_state(self, user_id: str):
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """
                SELECT state_json, expires_at
                FROM semantic_guide_states
                WHERE user_id=?
                """,
                (user_id,),
            )
            row = await cur.fetchone()

            if not row:
                return None

            expires_at = row[1]
            if expires_at:
                try:
                    expired = datetime.strptime(expires_at, "%Y-%m-%d %H:%M:%S") <= datetime.now()
                except (TypeError, ValueError):
                    expired = False
                if expired:
                    await db.execute(
                        "DELETE FROM semantic_guide_states WHERE user_id=?",
                        (user_id,),
                    )
                    await db.commit()
                    return None

        try:
            value = json.loads(row[0])
        except (TypeError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    async def set_semantic_guide_state(
        self,
        user_id: str,
        state: dict,
        ttl_minutes: int = 60,
    ):
        expires_at = datetime.now() + timedelta(minutes=max(1, ttl_minutes))
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO semantic_guide_states(
                  user_id, state_json, updated_at, expires_at
                )
                VALUES(?, ?, CURRENT_TIMESTAMP, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                  state_json=excluded.state_json,
                  updated_at=CURRENT_TIMESTAMP,
                  expires_at=excluded.expires_at
                """,
                (
                    user_id,
                    json.dumps(state, ensure_ascii=False),
                    self._format_dt(expires_at),
                ),
            )
            await db.commit()

    async def clear_semantic_guide_state(self, user_id: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM semantic_guide_states WHERE user_id=?",
                (user_id,),
            )
            await db.commit()
    async def clear(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM chat_history")
            await db.execute("DELETE FROM semantic_guide_states")
            await db.commit()

    async def recent_messages(self, user_id: str, turns: int | None = None):
        turns = turns or HISTORY_TURNS
        limit = max(2, turns * 2)  # user+assistant
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "SELECT role, content FROM chat_history WHERE user_id=? ORDER BY id DESC LIMIT ?",
                (user_id, limit),
            )
            rows = await cur.fetchall()
        rows.reverse()
        return [{"role": r[0], "content": r[1]} for r in rows]

    async def all_messages(self, user_id: str):
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """
                SELECT role, content
                FROM chat_history
                WHERE user_id=?
                ORDER BY id ASC
                """,
                (user_id,),
            )
            rows = await cur.fetchall()

        return [{"role": r[0], "content": r[1]} for r in rows]

    async def get_sales_discovery(self, user_id: str):
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """
                SELECT user_id, stage, targets_json, summary_json, completed_at
                FROM sales_discovery_sessions
                WHERE user_id=?
                """,
                (user_id,),
            )
            row = await cur.fetchone()

        if not row:
            return None

        return {
            "user_id": row[0],
            "stage": row[1],
            "targets_json": row[2],
            "summary_json": row[3],
            "completed_at": row[4],
        }

    async def upsert_sales_discovery(
        self,
        user_id: str,
        stage: str,
        targets_json: str,
        summary_json: str | None = None,
        completed_at: str | None = None,
    ):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO sales_discovery_sessions(
                  user_id, stage, targets_json, summary_json, updated_at, completed_at
                )
                VALUES(?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                  stage=excluded.stage,
                  targets_json=excluded.targets_json,
                  summary_json=excluded.summary_json,
                  updated_at=CURRENT_TIMESTAMP,
                  completed_at=excluded.completed_at
                """,
                (user_id, stage, targets_json, summary_json, completed_at),
            )
            await db.commit()

    async def list_sales_discovery_targets(
        self,
        active_only: bool = False,
        confirmed_only: bool = False,
    ):
        where = []
        params = []

        if active_only:
            where.append("active=1")

        if confirmed_only:
            where.append("status='confirmed'")

        sql = """
            SELECT
                id,
                target_key,
                name,
                description,
                suggested_question,
                recognizer_key,
                status,
                active,
                sort_order,
                created_by,
                created_at,
                updated_at
            FROM sales_discovery_targets
        """

        if where:
            sql += " WHERE " + " AND ".join(where)

        sql += " ORDER BY sort_order ASC, id ASC"

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(sql, params)
            rows = await cur.fetchall()

        return [dict(row) for row in rows]

    async def create_sales_discovery_target(
        self,
        target_key: str,
        name: str,
        description: str,
        suggested_question: str = "",
        recognizer_key: str = "",
        status: str = "waiting",
        active: bool = False,
        created_by: str | None = None,
    ):
        targets = await self.list_sales_discovery_targets()
        next_sort = (max([int(item["sort_order"] or 0) for item in targets]) + 10) if targets else 10

        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """
                INSERT INTO sales_discovery_targets(
                    target_key,
                    name,
                    description,
                    suggested_question,
                    recognizer_key,
                    status,
                    active,
                    sort_order,
                    created_by
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    target_key,
                    name,
                    description,
                    suggested_question,
                    recognizer_key,
                    status,
                    1 if active else 0,
                    next_sort,
                    created_by,
                ),
            )
            await db.commit()
            return cur.lastrowid

    async def update_sales_discovery_target(
        self,
        target_id: int,
        name: str,
        description: str,
        suggested_question: str,
        recognizer_key: str,
        status: str,
        active: bool,
    ):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE sales_discovery_targets
                SET
                    name=?,
                    description=?,
                    suggested_question=?,
                    recognizer_key=?,
                    status=?,
                    active=?,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (
                    name,
                    description,
                    suggested_question,
                    recognizer_key,
                    status,
                    1 if active else 0,
                    target_id,
                ),
            )
            await db.commit()

    async def delete_sales_discovery_target(self, target_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM sales_discovery_targets WHERE id=?",
                (target_id,),
            )
            await db.commit()

    async def reorder_sales_discovery_target(self, target_id: int, direction: str):
        targets = await self.list_sales_discovery_targets()
        index = next((i for i, item in enumerate(targets) if int(item["id"]) == int(target_id)), -1)

        if index < 0:
            return False

        swap_index = index - 1 if direction == "up" else index + 1

        if swap_index < 0 or swap_index >= len(targets):
            return True

        current = targets[index]
        other = targets[swap_index]

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE sales_discovery_targets SET sort_order=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (other["sort_order"], current["id"]),
            )
            await db.execute(
                "UPDATE sales_discovery_targets SET sort_order=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (current["sort_order"], other["id"]),
            )
            await db.commit()

        return True

    async def list_case_ideas(self):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT
                    id,
                    name,
                    indicators,
                    description,
                    status,
                    created_by,
                    created_at,
                    updated_at
                FROM case_ideas
                ORDER BY id ASC
                """
            )
            rows = await cur.fetchall()

        return [dict(row) for row in rows]

    async def get_case_idea(self, case_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT
                    id,
                    name,
                    indicators,
                    description,
                    status,
                    created_by,
                    created_at,
                    updated_at
                FROM case_ideas
                WHERE id=?
                """,
                (case_id,),
            )
            row = await cur.fetchone()

        return dict(row) if row else None

    async def create_case_idea(
        self,
        name: str,
        indicators: str,
        description: str,
        created_by: str | None = None,
    ):
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """
                INSERT INTO case_ideas(
                    name,
                    indicators,
                    description,
                    status,
                    created_by
                )
                VALUES(?, ?, ?, 'waiting', ?)
                """,
                (name, indicators, description, created_by),
            )
            await db.commit()
            return cur.lastrowid

    async def update_case_idea(
        self,
        case_id: int,
        name: str,
        indicators: str,
        description: str,
    ):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE case_ideas
                SET
                    name=?,
                    indicators=?,
                    description=?,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (name, indicators, description, case_id),
            )
            await db.commit()

    async def set_case_idea_supported(self, case_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE case_ideas
                SET status='supported', updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (case_id,),
            )
            await db.commit()

    async def delete_case_idea(self, case_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM case_ideas WHERE id=?",
                (case_id,),
            )
            await db.commit()

    async def record_ai_token_usage(
        self,
        tenant_id: str,
        user_id: str,
        user_key: str,
        conversation_id: str,
        request_id: str,
        route: str,
        model: str | None,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        created_at: datetime | None = None,
    ):
        created_at_text = self._format_dt(created_at or datetime.utcnow())
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO ai_token_usage_events(
                    tenant_id,
                    user_id,
                    user_key,
                    conversation_id,
                    request_id,
                    route,
                    model,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    created_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tenant_id,
                    user_id,
                    user_key,
                    conversation_id,
                    request_id,
                    route,
                    model,
                    int(prompt_tokens or 0),
                    int(completion_tokens or 0),
                    int(total_tokens or 0),
                    created_at_text,
                ),
            )
            await db.commit()

    async def list_ai_token_usage_events(
        self,
        since: datetime,
        tenant_id: str | None = None,
        user_id: str | None = None,
    ):
        query = """
            SELECT
                tenant_id,
                user_id,
                user_key,
                conversation_id,
                request_id,
                route,
                model,
                prompt_tokens,
                completion_tokens,
                total_tokens,
                created_at
            FROM ai_token_usage_events
            WHERE created_at >= ?
        """
        params = [self._format_dt(since)]

        if tenant_id is not None:
            query += " AND tenant_id=?"
            params.append(tenant_id)
        if user_id is not None:
            query += " AND user_id=?"
            params.append(user_id)

        query += " ORDER BY created_at ASC, id ASC"

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(query, params)
            rows = await cur.fetchall()

        return [dict(row) for row in rows]

    async def list_ai_usage_subjects(self, since: datetime):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                """
                SELECT
                    tenant_id,
                    user_id,
                    user_key,
                    COUNT(*) AS request_count,
                    COALESCE(SUM(total_tokens), 0) AS total_tokens,
                    MAX(created_at) AS last_used_at
                FROM ai_token_usage_events
                WHERE created_at >= ?
                GROUP BY tenant_id, user_id, user_key
                ORDER BY total_tokens DESC, last_used_at DESC
                """,
                (self._format_dt(since),),
            )
            rows = await cur.fetchall()

        return [dict(row) for row in rows]

    async def delete_user_data(self, user_id: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM chat_history WHERE user_id=?", (user_id,))
            await db.execute("DELETE FROM sales_discovery_sessions WHERE user_id=?", (user_id,))
            await db.execute("DELETE FROM semantic_guide_states WHERE user_id=?", (user_id,))
            await db.execute("DELETE FROM customer_profiles WHERE user_id=?", (user_id,))
            await db.execute("DELETE FROM sales_demo_users WHERE user_id=?", (user_id,))
            await db.commit()

    async def list_sales_demo_users(self):
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """
                SELECT user_id, name, created_at
                FROM sales_demo_users
                UNION
                SELECT user_id, 'Khách demo ' || substr(user_id, 2), MIN(created_at)
                FROM (
                  SELECT user_id, created_at FROM chat_history
                  UNION ALL
                  SELECT user_id, created_at FROM sales_discovery_sessions
                  UNION ALL
                  SELECT user_id, created_at FROM customer_profiles
                )
                WHERE user_id NOT IN (SELECT user_id FROM sales_demo_users)
                GROUP BY user_id
                ORDER BY created_at ASC, user_id ASC
                """
            )
            rows = await cur.fetchall()

        return [
            {
                "id": row[0],
                "name": row[1],
                "created_at": row[2],
            }
            for row in rows
        ]

    async def create_sales_demo_user(self):
        users = await self.list_sales_demo_users()
        next_number = 1
        used_numbers = []

        for user in users:
            user_id = user["id"] or ""
            if user_id.startswith("u") and user_id[1:].isdigit():
                used_numbers.append(int(user_id[1:]))

        if used_numbers:
            next_number = max(used_numbers) + 1

        user_id = f"u{next_number}"
        name = f"Khách demo {next_number}"

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO sales_demo_users(user_id, name, updated_at)
                VALUES(?, ?, CURRENT_TIMESTAMP)
                """,
                (user_id, name),
            )
            await db.commit()

        return {"id": user_id, "name": name}

    async def get_customer_profile(self, user_id: str):
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """
                SELECT user_id, gender, birth_year, investment_experience
                FROM customer_profiles
                WHERE user_id=?
                """,
                (user_id,),
            )
            row = await cur.fetchone()

        if not row:
            return None

        return {
            "user_id": row[0],
            "gender": row[1],
            "birth_year": row[2],
            "investment_experience": row[3],
        }

    async def upsert_customer_profile(
        self,
        user_id: str,
        gender: str,
        birth_year: str,
        investment_experience: str,
    ):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO customer_profiles(
                  user_id, gender, birth_year, investment_experience, updated_at
                )
                VALUES(?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET
                  gender=excluded.gender,
                  birth_year=excluded.birth_year,
                  investment_experience=excluded.investment_experience,
                  updated_at=CURRENT_TIMESTAMP
                """,
                (user_id, gender, birth_year, investment_experience),
            )
            await db.commit()

    async def create_condition_template(
        self,
        type: str,
        name: str,
        condition_logic: str,
        description: str,
        created_by: str | None = None
    ):
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """
                INSERT INTO condition_templates(
                    type,
                    name,
                    condition_logic,
                    description,
                    created_by
                )
                VALUES(?,?,?,?,?)
                """,
                (
                    type,
                    name,
                    condition_logic,
                    description,
                    created_by
                )
            )

            await db.commit()
            return cur.lastrowid

    async def update_condition_template(
        self,
        template_id: int,
        type: str,
        name: str,
        condition_logic: str,
        description: str,
    ):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE condition_templates
                SET
                    type=?,
                    name=?,
                    condition_logic=?,
                    description=?,
                    status='waiting',
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (
                    type,
                    name,
                    condition_logic,
                    description,
                    template_id,
                )
            )

            await db.commit()

    async def list_condition_templates(self):
        async with aiosqlite.connect(self.db_path) as db:

            db.row_factory = aiosqlite.Row

            cur = await db.execute(
                """
                SELECT
                    id,
                    type,
                    name,
                    condition_logic,
                    description,
                    status,
                    created_by,
                    created_at,
                    updated_at
                FROM condition_templates
                ORDER BY id ASC
                """
            )

            rows = await cur.fetchall()

            return [
                {
                    "id": r["id"],
                    "type": r["type"],
                    "name": r["name"],
                    "condition_logic": r["condition_logic"],
                    "description": r["description"],
                    "status": r["status"],
                    "created_by": r["created_by"],
                    "created_at": r["created_at"],
                    "updated_at": r["updated_at"],
                }
                for r in rows
            ]

    async def list_condition_types(self):
        async with aiosqlite.connect(self.db_path) as db:

            db.row_factory = aiosqlite.Row

            cur = await db.execute(
                """
                SELECT
                    id,
                    value_key,
                    label,
                    created_at,
                    updated_at
                FROM condition_types
                ORDER BY id ASC
                """
            )

            rows = await cur.fetchall()

            return [dict(r) for r in rows]

    async def create_condition_type(
        self,
        label: str
    ):
        value_key = (
            label.strip()
            .lower()
            .replace(" ", "_")
        )

        async with aiosqlite.connect(self.db_path) as db:

            try:
                cur = await db.execute(
                    """
                    INSERT INTO condition_types(
                        value_key,
                        label
                    )
                    VALUES(?, ?)
                    """,
                    (
                        value_key,
                        label.strip()
                    )
                )

                await db.commit()

                return cur.lastrowid

            except aiosqlite.IntegrityError:
                return None

    async def get_condition_template(
        self,
        template_id:int
    ):
        async with aiosqlite.connect(self.db_path) as db:

            db.row_factory=aiosqlite.Row

            cur=await db.execute(
                """
                SELECT
                    id,
                    type,
                    name,
                    condition_logic,
                    description,
                    status
                FROM condition_templates
                WHERE id=?
                """,
                (template_id,)
            )

            row=await cur.fetchone()

            if not row:
                return None

            return dict(row)

    async def delete_condition_template(
        self,
        template_id:int
    ):

        async with aiosqlite.connect(self.db_path) as db:

            await db.execute(
                """
                DELETE FROM condition_templates
                WHERE id=?
                """,
                (template_id,)
            )

            await db.commit()


    async def confirm_condition_template(
        self,
        template_id:int
    ):

        async with aiosqlite.connect(self.db_path) as db:

            await db.execute(
                """
                UPDATE condition_templates
                SET
                    status='confirmed',
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (template_id,)
            )

            await db.commit()

    async def create_condition_flow(
        self,
        name: str,
        expression: str,
        prompt_template: str,
        trigger_prompt: str = "",
        created_by: str | None = None,
    ):
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """
                INSERT INTO condition_flows(
                    name,
                    expression,
                    prompt_template,
                    trigger_prompt,
                    active,
                    status,
                    created_by
                )
                VALUES(?, ?, ?, ?, 0, 'draft', ?)
                """,
                (
                    name,
                    expression,
                    prompt_template,
                    trigger_prompt,
                    created_by,
                )
            )

            await db.commit()
            return cur.lastrowid


    async def list_condition_flows(self):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            cur = await db.execute(
                """
                SELECT
                    id,
                    name,
                    expression,
                    prompt_template,
                    trigger_prompt,
                    active,
                    status,
                    created_by,
                    created_at,
                    updated_at
                FROM condition_flows
                ORDER BY id DESC
                """
            )

            rows = await cur.fetchall()
            return [dict(r) for r in rows]

    async def get_condition_flow(
        self,
        flow_id: int,
    ):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            cur = await db.execute(
                """
                SELECT
                    id,
                    name,
                    expression,
                    prompt_template,
                    trigger_prompt,
                    active,
                    status,
                    created_by,
                    created_at,
                    updated_at
                FROM condition_flows
                WHERE id=?
                """,
                (flow_id,),
            )

            row = await cur.fetchone()

        if not row:
            return None

        return dict(row)


    async def update_condition_flow(
        self,
        flow_id: int,
        name: str,
        expression: str,
        prompt_template: str,
        trigger_prompt: str | None = None,
        status: str = "draft",
    ):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE condition_flows
                SET
                    name=?,
                    expression=?,
                    prompt_template=?,
                    trigger_prompt=COALESCE(?, trigger_prompt),
                    status=?,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (
                    name,
                    expression,
                    prompt_template,
                    trigger_prompt,
                    status,
                    flow_id,
                )
            )

            await db.commit()

    async def update_condition_flow_trigger_prompt(
        self,
        flow_id: int,
        trigger_prompt: str,
    ):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE condition_flows
                SET
                    trigger_prompt=?,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (
                    trigger_prompt,
                    flow_id,
                )
            )

            await db.commit()

    async def set_condition_flow_active(
        self,
        flow_id: int,
        active: bool,
    ):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE condition_flows
                SET
                    active=?,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (
                    1 if active else 0,
                    flow_id,
                ),
            )

            await db.commit()


    async def delete_condition_flow(
        self,
        flow_id: int,
    ):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                DELETE FROM condition_flows
                WHERE id=?
                """,
                (flow_id,)
            )

            await db.commit()

    async def confirm_condition_flow(
            self,
            flow_id: int,
        ):
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    """
                    UPDATE condition_flows
                    SET
                        status='confirmed',
                        updated_at=CURRENT_TIMESTAMP
                    WHERE id=?
                    """,
                    (flow_id,)
                )

                await db.commit()

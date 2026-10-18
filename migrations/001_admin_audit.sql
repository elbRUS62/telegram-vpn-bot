-- Аудит действий админов из Mini App
CREATE TABLE IF NOT EXISTS admin_audit (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id   INTEGER NOT NULL,
    action     TEXT    NOT NULL,
    target_id  INTEGER,
    meta       TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_admin_audit_admin  ON admin_audit(admin_id, created_at);
CREATE INDEX IF NOT EXISTS idx_admin_audit_target ON admin_audit(target_id);

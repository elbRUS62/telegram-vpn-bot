import logging
import secrets
from datetime import datetime, timedelta

import aiosqlite

from config import DB_PATH, SUBSCRIPTION_DAYS

logger = logging.getLogger(__name__)

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                xui_email TEXT UNIQUE,
                sub_id TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                notified_3d INTEGER DEFAULT 0,
                notified_0d INTEGER DEFAULT 0,
                invited_by INTEGER,
                invites_count INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS invite_links (
                token TEXT PRIMARY KEY,
                created_by INTEGER NOT NULL,
                friend_user_id INTEGER,
                friend_username TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                used_at TIMESTAMP,
                is_used INTEGER DEFAULT 0,
                xui_email TEXT,
                sub_id TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS invites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                inviter_id INTEGER NOT NULL,
                invited_user_id INTEGER,
                invited_username TEXT,
                invited_first_name TEXT,
                type TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS donations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                amount REAL NOT NULL,
                currency TEXT DEFAULT 'RUB',
                message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS waitlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                first_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS support_tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                username TEXT,
                first_name TEXT,
                subject TEXT NOT NULL,
                category TEXT DEFAULT 'other',
                status TEXT DEFAULT 'open',
                unread_admin INTEGER DEFAULT 1,
                unread_user INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                closed_at TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_support_tickets_user
            ON support_tickets(telegram_id, updated_at DESC)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_support_tickets_status
            ON support_tickets(status, updated_at DESC)
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS support_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL,
                sender TEXT NOT NULL,
                admin_id INTEGER,
                text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_support_messages_ticket
            ON support_messages(ticket_id, id)
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS monitor_state (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS monitor_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                panel_id TEXT NOT NULL,
                ts INTEGER NOT NULL,
                cpu_percent REAL,
                mem_percent REAL,
                disk_percent REAL,
                online_count INTEGER,
                traffic_total INTEGER
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_monitor_metrics_panel_ts
            ON monitor_metrics(panel_id, ts)
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                telegram_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                role TEXT NOT NULL DEFAULT 'admin',
                is_active INTEGER NOT NULL DEFAULT 1,
                added_by INTEGER,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS admin_login_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token_hash TEXT UNIQUE NOT NULL,
                admin_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                used_at TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS diagnostic_stats (
                bucket TEXT NOT NULL,
                timezone TEXT NOT NULL DEFAULT 'unknown',
                stage TEXT NOT NULL,
                ok INTEGER NOT NULL,
                latency_bucket TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (bucket, timezone, stage, ok, latency_bucket)
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_diagnostic_stats_bucket
            ON diagnostic_stats(bucket)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_admin_login_tokens_expires
            ON admin_login_tokens(expires_at)
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS admin_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                target_id INTEGER,
                meta TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Миграция: добавляем поле renew_count, если его нет
        async with db.execute("PRAGMA table_info(users)") as cur:
            columns = [row[1] for row in await cur.fetchall()]

        if "renew_count" not in columns:
            await db.execute("ALTER TABLE users ADD COLUMN renew_count INTEGER DEFAULT 0")
            logger.info("🔧 Добавлено поле renew_count в таблицу users")
        # Миграция: добавляем поля в invite_links для веб-привязки
        async with db.execute("PRAGMA table_info(invite_links)") as cur:
            il_columns = [row[1] for row in await cur.fetchall()]

        if "counted" not in il_columns:
            await db.execute("ALTER TABLE invite_links ADD COLUMN counted INTEGER DEFAULT 0")
            logger.info("🔧 Добавлено поле counted в invite_links")

        if "bound_to_tg_id" not in il_columns:
            await db.execute("ALTER TABLE invite_links ADD COLUMN bound_to_tg_id INTEGER DEFAULT NULL")
            logger.info("🔧 Добавлено поле bound_to_tg_id в invite_links")

        if "bound_at" not in il_columns:
            await db.execute("ALTER TABLE invite_links ADD COLUMN bound_at TIMESTAMP DEFAULT NULL")
            logger.info("🔧 Добавлено поле bound_at в invite_links")
            
        await db.commit()

    # После создания таблиц переносим старых админов из ADMIN_ID.
    from permissions import seed_admins

    seed_admins()

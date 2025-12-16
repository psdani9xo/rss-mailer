import os
import time
import json
import smtplib
import ssl
import sqlite3
from email.mime.text import MIMEText
from datetime import datetime
import feedparser


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def db_connect(db_path: str):
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            feed_url TEXT,
            keywords TEXT,
            check_interval INTEGER,
            email_from TEXT,
            email_to TEXT,
            smtp_server TEXT,
            smtp_port INTEGER,
            smtp_username TEXT,
            smtp_password TEXT,
            enabled INTEGER
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS hits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT,
            title TEXT,
            link TEXT,
            matched_keyword TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            last_checked TEXT,
            last_hit TEXT,
            running INTEGER
        )
    """)
    conn.execute("INSERT OR IGNORE INTO settings (id, enabled, check_interval, smtp_port) VALUES (1, 1, 600, 587)")
    conn.execute("INSERT OR IGNORE INTO state (id, running) VALUES (1, 0)")
    conn.commit()
    return conn


def log_line(log_path: str, msg: str):
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"[{now_str()}] {msg}\n")


def load_settings(conn: sqlite3.Connection):
    row = conn.execute("SELECT feed_url, keywords, check_interval, email_from, email_to, smtp_server, smtp_port, smtp_username, smtp_password, enabled FROM settings WHERE id=1").fetchone()
    if not row:
        return None
    keys = [k.strip() for k in (row[1] or "").splitlines() if k.strip()]
    return {
        "feed_url": row[0] or "",
        "keywords": keys,
        "check_interval": int(row[2] or 600),
        "email_from": row[3] or "",
        "email_to": row[4] or "",
        "smtp_server": row[5] or "smtp.gmail.com",
        "smtp_port": int(row[6] or 587),
        "smtp_username": row[7] or "",
        "smtp_password": row[8] or "",
        "enabled": int(row[9] or 0),
    }


def already_hit(conn: sqlite3.Connection, title: str) -> bool:
    r = conn.execute("SELECT 1 FROM hits WHERE title = ? LIMIT 1", (title,)).fetchone()
    return r is not None


def send_email(s, subject: str, body: str, log_path: str):
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = s["email_from"]
    msg["To"] = s["email_to"]

    context = ssl.create_default_context()
    with smtplib.SMTP(s["smtp_server"], s["smtp_port"], timeout=30) as server:
        server.ehlo()
        server.starttls(context=context)
        server.login(s["smtp_username"], s["smtp_password"])
        server.sendmail(s["email_from"], [s["email_to"]], msg.as_string())

    log_line(log_path, f"Email enviado: {subject}")


def check_once(conn: sqlite3.Connection, log_path: str):
    s = load_settings(conn)
    if not s or not s["enabled"]:
        return

    if not s["feed_url"]:
        log_line(log_path, "No hay FEED_URL configurado.")
        return

    if not s["keywords"]:
        log_line(log_path, "No hay KEYWORDS configuradas.")
        return

    try:
        feed = feedparser.parse(s["feed_url"])
    except Exception as e:
        log_line(log_path, f"Error parseando feed: {e}")
        return

    conn.execute("UPDATE state SET last_checked=? WHERE id=1", (now_str(),))
    conn.commit()

    if not getattr(feed, "entries", None):
        log_line(log_path, "Feed sin entries.")
        return

    for entry in feed.entries:
        title = (getattr(entry, "title", "") or "").strip()
        link = (getattr(entry, "link", "") or "").strip()

        if not title:
            continue

        matched = None
        for kw in s["keywords"]:
            if kw in title:
                matched = kw
                break

        if not matched:
            continue

        if already_hit(conn, title):
            continue

        # Guardar hit
        conn.execute(
            "INSERT INTO hits (ts, title, link, matched_keyword) VALUES (?, ?, ?, ?)",
            (now_str(), title, link, matched)
        )
        conn.execute("UPDATE state SET last_hit=? WHERE id=1", (now_str(),))
        conn.commit()

        # Email
        subject = f"RSS match: {matched}"
        body = f"Titulo: {title}\nKeyword: {matched}\nLink: {link}\nFecha: {now_str()}\n"
        try:
            send_email(s, subject, body, log_path)
        except Exception as e:
            log_line(log_path, f"Fallo enviando email: {e}")

        log_line(log_path, f"HIT: [{matched}] {title} {link}")


class WatcherController:
    def __init__(self, db_path: str, log_path: str):
        self.db_path = db_path
        self.log_path = log_path
        self.conn = db_connect(db_path)

    def set_running(self, v: int):
        self.conn.execute("UPDATE state SET running=? WHERE id=1", (int(v),))
        self.conn.commit()

    def is_running(self) -> bool:
        r = self.conn.execute("SELECT running FROM state WHERE id=1").fetchone()
        return bool(r and int(r[0]) == 1)

    def tick(self):
        # Se llama periodicamente por APScheduler
        if not self.is_running():
            return
        check_once(self.conn, self.log_path)

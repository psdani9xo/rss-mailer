import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, flash
from apscheduler.schedulers.background import BackgroundScheduler
from watcher import db_connect, WatcherController

DATA_DIR = os.getenv("DATA_DIR", "/data")
DB_PATH = os.path.join(DATA_DIR, "app.db")
LOG_PATH = os.path.join(DATA_DIR, "log.txt")

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-me")

conn = db_connect(DB_PATH)
controller = WatcherController(DB_PATH, LOG_PATH)

scheduler = BackgroundScheduler(daemon=True)
scheduler.start()

# Job fijo cada 10s, el watcher internamente mira el intervalo en settings?
# Aqui simplifico: corremos tick cada 10s y el feedparser ya decide por dedupe.
# Si quieres respetar intervalo exacto, lo hacemos por scheduler reschedule (te lo ajusto).
scheduler.add_job(controller.tick, "interval", seconds=10, id="watcher_tick", replace_existing=True)


def get_settings():
    row = conn.execute("SELECT feed_url, keywords, check_interval, email_from, email_to, smtp_server, smtp_port, smtp_username, smtp_password, enabled FROM settings WHERE id=1").fetchone()
    return {
        "feed_url": row[0] or "",
        "keywords": row[1] or "",
        "check_interval": int(row[2] or 600),
        "email_from": row[3] or "",
        "email_to": row[4] or "",
        "smtp_server": row[5] or "smtp.gmail.com",
        "smtp_port": int(row[6] or 587),
        "smtp_username": row[7] or "",
        "smtp_password": row[8] or "",
        "enabled": int(row[9] or 0),
    }


def get_state():
    row = conn.execute("SELECT last_checked, last_hit, running FROM state WHERE id=1").fetchone()
    return {
        "last_checked": (row[0] or ""),
        "last_hit": (row[1] or ""),
        "running": int(row[2] or 0),
    }


@app.get("/")
def dashboard():
    return render_template("dashboard.html", settings=get_settings(), state=get_state())


@app.post("/start")
def start():
    controller.set_running(1)
    flash("Watcher arrancado.")
    return redirect(url_for("dashboard"))


@app.post("/stop")
def stop():
    controller.set_running(0)
    flash("Watcher parado.")
    return redirect(url_for("dashboard"))


@app.get("/settings")
def settings():
    return render_template("settings.html", settings=get_settings(), state=get_state())


@app.post("/settings")
def save_settings():
    form = request.form
    conn.execute("""
        UPDATE settings SET
            feed_url=?,
            keywords=?,
            check_interval=?,
            email_from=?,
            email_to=?,
            smtp_server=?,
            smtp_port=?,
            smtp_username=?,
            smtp_password=?,
            enabled=?
        WHERE id=1
    """, (
        form.get("feed_url", "").strip(),
        form.get("keywords", "").strip(),
        int(form.get("check_interval", "600")),
        form.get("email_from", "").strip(),
        form.get("email_to", "").strip(),
        form.get("smtp_server", "smtp.gmail.com").strip(),
        int(form.get("smtp_port", "587")),
        form.get("smtp_username", "").strip(),
        form.get("smtp_password", "").strip(),
        1 if form.get("enabled") == "on" else 0
    ))
    conn.commit()
    flash("Configuracion guardada.")
    return redirect(url_for("settings"))


@app.get("/history")
def history():
    rows = conn.execute("SELECT ts, title, link, matched_keyword FROM hits ORDER BY id DESC LIMIT 500").fetchall()
    return render_template("history.html", rows=rows, state=get_state())


@app.get("/logs")
def logs():
    txt = ""
    try:
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            # tail simple: ultimas 300 lineas
            lines = f.readlines()[-300:]
            txt = "".join(lines)
    except FileNotFoundError:
        txt = "(sin log aun)"
    return render_template("logs.html", text=txt, state=get_state())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=1235)

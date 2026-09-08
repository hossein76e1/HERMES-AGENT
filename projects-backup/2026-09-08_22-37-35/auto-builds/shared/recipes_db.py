#!/usr/bin/env python3
"""
🗄 recipes_db.py — لایه دادهٔ ربات آشپزی
SQLite: دستور پخت‌ها، کاربران، علاقه‌مندی‌ها، لیست خرید، برنامه غذایی، امتیازها
"""
import sqlite3
import json
import os
from datetime import datetime, timedelta

DB_PATH = os.environ.get("COOK_DB_PATH", "cooking_bot.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_conn()
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS recipes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        category TEXT NOT NULL,
        ingredients TEXT NOT NULL,        -- JSON list
        steps TEXT NOT NULL,              -- JSON list
        time_min INTEGER DEFAULT 30,
        servings INTEGER DEFAULT 2,
        calories INTEGER DEFAULT 0,
        protein REAL DEFAULT 0,
        carbs REAL DEFAULT 0,
        fat REAL DEFAULT 0,
        photo_url TEXT,
        video_url TEXT,
        tags TEXT DEFAULT '',             -- diet tags: لاغری,دیابت,گیاهی,...
        created_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        lang TEXT DEFAULT 'fa',
        daily_hour INTEGER DEFAULT 9,     -- ساعت ارسال دستور روز
        daily_enabled INTEGER DEFAULT 1,
        diet TEXT DEFAULT '',             -- رژیم: لاغری/دیابت/عادی
        points INTEGER DEFAULT 0,
        level INTEGER DEFAULT 1,
        joined_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS favorites (
        user_id INTEGER NOT NULL,
        recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
        added_at TEXT DEFAULT (datetime('now')),
        PRIMARY KEY (user_id, recipe_id)
    );
    CREATE TABLE IF NOT EXISTS ratings (
        user_id INTEGER NOT NULL,
        recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
        stars INTEGER CHECK(stars BETWEEN 1 AND 5),
        PRIMARY KEY (user_id, recipe_id)
    );
    CREATE TABLE IF NOT EXISTS shopping_list (
        user_id INTEGER NOT NULL,
        item TEXT NOT NULL,
        done INTEGER DEFAULT 0,
        added_at TEXT DEFAULT (datetime('now'))
    );
    CREATE TABLE IF NOT EXISTS meal_plan (
        user_id INTEGER NOT NULL,
        day TEXT NOT NULL,                -- شنبه..جمعه
        recipe_id INTEGER REFERENCES recipes(id),
        PRIMARY KEY (user_id, day)
    );
    CREATE TABLE IF NOT EXISTS timers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        label TEXT,
        fire_at TEXT NOT NULL,
        notified INTEGER DEFAULT 0
    );
    ''')
    conn.commit()
    conn.close()


# ─── Recipes ────────────────────────────────────────────────────────────────
def add_recipe(title, category, ingredients, steps, time_min=30, servings=2,
               calories=0, protein=0, carbs=0, fat=0, photo_url=None, video_url=None, tags=""):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO recipes (title, category, ingredients, steps, time_min, servings, calories, protein, carbs, fat, photo_url, video_url, tags) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (title, category, json.dumps(ingredients, ensure_ascii=False), json.dumps(steps, ensure_ascii=False),
         time_min, servings, calories, protein, carbs, fat, photo_url, video_url, tags))
    rid = cur.lastrowid
    conn.commit(); conn.close()
    return rid


def get_recipe(rid):
    conn = get_conn()
    r = conn.execute("SELECT * FROM recipes WHERE id=?", (rid,)).fetchone()
    conn.close()
    return dict(r) if r else None


def random_recipe(diet=None):
    conn = get_conn()
    if diet and diet != "عادی":
        r = conn.execute("SELECT * FROM recipes WHERE tags LIKE ? ORDER BY RANDOM() LIMIT 1", (f"%{diet}%",)).fetchone()
        if not r:
            r = conn.execute("SELECT * FROM recipes ORDER BY RANDOM() LIMIT 1").fetchone()
    else:
        r = conn.execute("SELECT * FROM recipes ORDER BY RANDOM() LIMIT 1").fetchone()
    conn.close()
    return dict(r) if r else None


def search_recipes(q, by="name", limit=8):
    """by: name | ingredient | category"""
    conn = get_conn()
    if by == "name":
        rows = conn.execute("SELECT * FROM recipes WHERE title LIKE ? LIMIT ?", (f"%{q}%", limit)).fetchall()
    elif by == "category":
        rows = conn.execute("SELECT * FROM recipes WHERE category LIKE ? LIMIT ?", (f"%{q}%", limit)).fetchall()
    else:  # ingredient — each ingredient is matched
        rows = conn.execute("SELECT * FROM recipes WHERE ingredients LIKE ? LIMIT ?", (f"%{q}%", limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def all_categories():
    conn = get_conn()
    rows = conn.execute("SELECT DISTINCT category FROM recipes ORDER BY category").fetchall()
    conn.close()
    return [r["category"] for r in rows]


def recipes_by_category(cat, limit=10):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM recipes WHERE category=? ORDER BY title LIMIT ?", (cat, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def suggest_by_diet(diet, max_cal=None, limit=5):
    conn = get_conn()
    q = "SELECT * FROM recipes WHERE tags LIKE ?"
    args = [f"%{diet}%"]
    if max_cal:
        q += " AND calories <= ?"
        args.append(max_cal)
    q += " ORDER BY RANDOM() LIMIT ?"
    args.append(limit)
    rows = conn.execute(q, args).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── Users ──────────────────────────────────────────────────────────────────
def upsert_user(user_id):
    conn = get_conn()
    conn.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit(); conn.close()


def get_user(user_id):
    conn = get_conn()
    r = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return dict(r) if r else None


def set_user_field(user_id, field, value):
    assert field in ("lang", "daily_hour", "daily_enabled", "diet")
    conn = get_conn()
    conn.execute(f"UPDATE users SET {field}=? WHERE user_id=?", (value, user_id))
    conn.commit(); conn.close()


def add_points(user_id, pts):
    conn = get_conn()
    conn.execute("UPDATE users SET points = points + ? WHERE user_id=?", (pts, user_id))
    conn.execute("UPDATE users SET level = MAX(1, points / 100 + 1) WHERE user_id=?", (user_id,))
    conn.commit(); conn.close()


def all_daily_users():
    conn = get_conn()
    rows = conn.execute("SELECT user_id, daily_hour, diet FROM users WHERE daily_enabled=1").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def stats():
    conn = get_conn()
    users = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
    recipes = conn.execute("SELECT COUNT(*) c FROM recipes").fetchone()["c"]
    favs = conn.execute("SELECT COUNT(*) c FROM favorites").fetchone()["c"]
    conn.close()
    return {"users": users, "recipes": recipes, "favorites": favs}


# ─── Favorites ──────────────────────────────────────────────────────────────
def toggle_fav(user_id, rid):
    conn = get_conn()
    if conn.execute("SELECT 1 FROM favorites WHERE user_id=? AND recipe_id=?", (user_id, rid)).fetchone():
        conn.execute("DELETE FROM favorites WHERE user_id=? AND recipe_id=?", (user_id, rid))
        conn.commit(); conn.close()
        return False
    conn.execute("INSERT INTO favorites (user_id, recipe_id) VALUES (?,?)", (user_id, rid))
    conn.commit(); conn.close()
    return True


def user_favorites(user_id, limit=15):
    conn = get_conn()
    rows = conn.execute(
        "SELECT r.* FROM favorites f JOIN recipes r ON r.id=f.recipe_id WHERE f.user_id=? ORDER BY f.added_at DESC LIMIT ?",
        (user_id, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── Ratings ────────────────────────────────────────────────────────────────
def rate_recipe(user_id, rid, stars):
    conn = get_conn()
    conn.execute("INSERT OR REPLACE INTO ratings (user_id, recipe_id, stars) VALUES (?,?,?)", (user_id, rid, stars))
    conn.commit(); conn.close()


def avg_rating(rid):
    conn = get_conn()
    r = conn.execute("SELECT AVG(stars) a, COUNT(*) c FROM ratings WHERE recipe_id=?", (rid,)).fetchone()
    conn.close()
    return (r["a"] or 0, r["c"])


# ─── Shopping list ──────────────────────────────────────────────────────────
def add_to_list(user_id, items):
    conn = get_conn()
    for it in items:
        if not conn.execute("SELECT 1 FROM shopping_list WHERE user_id=? AND item=? AND done=0", (user_id, it)).fetchone():
            conn.execute("INSERT INTO shopping_list (user_id, item) VALUES (?,?)", (user_id, it))
    conn.commit(); conn.close()


def get_list(user_id):
    conn = get_conn()
    rows = conn.execute("SELECT id, item, done FROM shopping_list WHERE user_id=? ORDER BY done, added_at", (user_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def toggle_list_item(user_id, item_id):
    conn = get_conn()
    r = conn.execute("SELECT done FROM shopping_list WHERE id=? AND user_id=?", (item_id, user_id)).fetchone()
    if r:
        conn.execute("UPDATE shopping_list SET done=? WHERE id=?", (0 if r["done"] else 1, item_id))
        conn.commit()
    conn.close()


def clear_list(user_id):
    conn = get_conn()
    conn.execute("DELETE FROM shopping_list WHERE user_id=?", (user_id,))
    conn.commit(); conn.close()


def recipe_to_list(recipe):
    """Add all ingredients of a recipe to the shopping list."""
    ings = json.loads(recipe["ingredients"])
    return [i.strip() for i in ings if i.strip()]


# ─── Meal plan ──────────────────────────────────────────────────────────────
DAYS = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"]


def set_plan_day(user_id, day, recipe_id):
    conn = get_conn()
    conn.execute("INSERT OR REPLACE INTO meal_plan (user_id, day, recipe_id) VALUES (?,?,?)", (user_id, day, recipe_id))
    conn.commit(); conn.close()


def get_plan(user_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT p.day, r.title, p.recipe_id FROM meal_plan p LEFT JOIN recipes r ON r.id=p.recipe_id WHERE p.user_id=?",
        (user_id,)).fetchall()
    conn.close()
    return {r["day"]: (r["title"], r["recipe_id"]) for r in rows}


def auto_fill_plan(user_id, diet=None):
    """Fill empty days with random recipes."""
    plan = get_plan(user_id)
    for day in DAYS:
        if day not in plan:
            r = random_recipe(diet)
            if r:
                set_plan_day(user_id, day, r["id"])


# ─── Timers ─────────────────────────────────────────────────────────────────
def add_timer(user_id, label, minutes):
    conn = get_conn()
    fire_at = (datetime.now() + timedelta(minutes=minutes)).isoformat()
    conn.execute("INSERT INTO timers (user_id, label, fire_at) VALUES (?,?,?)", (user_id, label, fire_at))
    conn.commit(); conn.close()


def due_timers():
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, user_id, label FROM timers WHERE notified=0 AND fire_at <= ?", (datetime.now().isoformat(),)).fetchall()
    if rows:
        conn.execute("UPDATE timers SET notified=1 WHERE notified=0 AND fire_at <= ?", (datetime.now().isoformat(),))
        conn.commit()
    conn.close()
    return [dict(r) for r in rows]


# ─── Unit converter ─────────────────────────────────────────────────────────
UNITS = {
    "فنجان": 180, "لیوان": 240, "قاشق غذاخوری": 15, "قاشق چای‌خوری": 5,
    "پیمانه": 240, "میلی‌لیتر": 1, "گرم": 1, "کیلوگرم": 1000,
}


def convert(amount, unit, target):
    if unit not in UNITS or target not in UNITS:
        return None
    ml = amount * UNITS[unit]
    return round(ml / UNITS[target], 1)


init_db()

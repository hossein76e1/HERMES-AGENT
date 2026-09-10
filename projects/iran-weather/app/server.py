#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""هواشناسی ایران — بک‌اند (FastAPI + Open-Meteo + کش فایل)"""

import asyncio
import json
import math
import time
from pathlib import Path

import httpx
import uvicorn
import jdatetime
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

BASE = Path(__file__).parent.parent          # iran-weather/
DATA_DIR = BASE / "data"
STATIC_DIR = BASE / "static"
CACHE_DIR = DATA_DIR / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

CITIES = json.loads((DATA_DIR / "cities.json").read_text(encoding="utf-8"))
for _i, _c in enumerate(CITIES):
    _c["id"] = _i


def _norm(s: str) -> str:
    return (s.replace("ي", "ی").replace("ك", "ک")
             .replace("\u200c", " ").replace("ـ", "")
             .replace("آ", "ا").replace("أ", "ا").replace("إ", "ا")
             .replace("ة", "ه").replace("ٔ", "")
             .lower().strip())


_index = {}
for i, c in enumerate(CITIES):
    words = set()
    for nm in (c["fa"], c["en"]):
        for w in _norm(nm).split():
            if len(w) >= 2:
                words.add(w)
    words.add(_norm(c["fa"]))
    for w in words:
        _index.setdefault(w, []).append(i)


def search_cities(q, limit=12):
    nq = _norm(q)
    if not nq:
        return []
    seen = set()
    ranked = []
    exact = list(_index.get(nq, []))
    prefix = []
    contains = []
    for w, idxs in _index.items():
        if w != nq and w.startswith(nq):
            prefix.extend(idxs)
        elif nq in w and not w.startswith(nq):
            contains.extend(idxs)
    for tier, group in ((0, exact), (1, prefix), (2, contains)):
        for i in group:
            if i not in seen:
                seen.add(i)
                ranked.append((tier, -CITIES[i]["pop"], i))
    ranked.sort()
    return [CITIES[i] for _, _, i in ranked[:limit]]


WMO = {
    0: ("آسمان صاف", "clear"),
    1: ("عمدتاً صاف", "clear"),
    2: ("نیمه ابری", "partly"),
    3: ("ابری", "cloudy"),
    45: ("مه", "fog"),
    48: ("مه یخ‌زده", "fog"),
    51: ("رگبار خفیف", "rain"),
    53: ("رگبار متوسط", "rain"),
    55: ("رگبار شدید", "rain"),
    56: ("نمنم یخ‌زده", "sleet"),
    57: ("نمنم یخ‌زده شدید", "sleet"),
    61: ("باران خفیف", "rain"),
    63: ("باران متوسط", "rain"),
    65: ("باران شدید", "rain"),
    66: ("باران یخ‌زده", "sleet"),
    67: ("باران یخ‌زده شدید", "sleet"),
    71: ("بارش برف خفیف", "snow"),
    73: ("بارش برف متوسط", "snow"),
    75: ("بارش برف سنگین", "snow"),
    77: ("دانه‌های برف", "snow"),
    80: ("رگبار پراکنده", "rain"),
    81: ("رگبار متوسط", "rain"),
    82: ("رگبار شدید", "rain"),
    85: ("رگبار برف خفیف", "snow"),
    86: ("رگبار برف سنگین", "snow"),
    95: ("رعد و برق", "storm"),
    96: ("رعد و برق با تگرگ", "storm"),
    99: ("رعد و برق با تگرگ شدید", "storm"),
}


def wmo_info(code):
    if code is None:
        return ("—", "clear")
    return WMO.get(code, ("نامشخص", "cloudy"))


def beaufort_label(kmh):
    if kmh is None:
        return "—"
    k = float(kmh)
    if k < 1:
        return "آرام"
    if k < 6:
        return "نسیم ملایم"
    if k < 12:
        return "نسیم سبک"
    if k < 20:
        return "نسیم معتدل"
    if k < 29:
        return "باد تازه"
    if k < 39:
        return "باد قوی"
    if k < 50:
        return "باد شدید"
    if k < 62:
        return "توفان"
    if k < 75:
        return "توفان شدید"
    return "توفان ویرانگر"


def uv_label(uv):
    if uv is None:
        return "—"
    u = float(uv)
    if u < 3:
        return "کم"
    if u < 6:
        return "متوسط"
    if u < 8:
        return "زیاد"
    if u < 11:
        return "خیلی زیاد"
    return "خطرناک"


J_MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
            "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]

_WIND_DIRS = ["شمالی", "شمال‌شرقی", "شرقی", "جنوب‌شرقی", "جنوبی", "جنوب‌غربی", "غربی", "شمال‌غربی"]


def wind_dir_fa(deg):
    if deg is None:
        return "—"
    return _WIND_DIRS[int(((deg % 360) + 22.5) // 45) % 8]


def moon_phase_fa(date_str):
    import datetime
    try:
        d = datetime.date.fromisoformat(date_str)
    except Exception:
        return "—"
    days = (d - datetime.date(2000, 1, 6)).days % 29.530588853
    if days < 1.85 or days > 27.68:
        return "ماه نو"
    if days < 6.4:
        return "هلال نو"
    if days < 8.4:
        return "ربع اول"
    if days < 13.7:
        return "احدب اول"
    if days < 15.8:
        return "ماه کامل"
    if days < 21.1:
        return "احدب دوم"
    if days < 23.1:
        return "ربع آخر"
    return "هلال آخر"


def jalali_str(date_str):
    """'2026-09-09' -> {'j':'1405-06-18','label':'۱۸ شهریور','wd':'چهارشنبه'}"""
    if not date_str:
        return None
    try:
        y, m, d = (int(x) for x in date_str[:10].split("-"))
        j = jdatetime.date.fromgregorian(day=d, month=m, year=y)
    except Exception:
        return {"j": date_str, "label": "", "wd": ""}
    wday = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"][j.weekday()]
    return {"j": f"{j.year}-{j.month:02d}-{j.day:02d}",
            "label": f"{j.day} {J_MONTHS[j.month - 1]}", "wd": wday}


def dew_point(t, rh):
    if t is None or rh is None:
        return None
    rh = max(1.0, min(100.0, float(rh)))
    t = float(t)
    a, b = 17.62, 243.12
    gamma = (a * t) / (b + t) + math.log(rh / 100.0)
    if a - gamma == 0:
        return None
    return round((b * gamma) / (a - gamma), 1)


def heat_note(t):
    if t is None:
        return ""
    if t >= 40:
        return "گرمای طاقت‌فرسا"
    if t >= 35:
        return "گرمای خطرناک"
    if t >= 30:
        return "هوای گرم"
    if t <= -10:
        return "سرمای شدید"
    if t <= -5:
        return "هوای خیلی سرد"
    if t <= 0:
        return "هوای سرد"
    return ""


OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
HOURLY_VARS = [
    "temperature_2m", "apparent_temperature", "relative_humidity_2m",
    "dew_point_2m", "precipitation_probability", "precipitation",
    "weather_code", "pressure_msl", "cloud_cover", "visibility",
    "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m",
    "uv_index", "is_day", "cape",
]
CURRENT_VARS = [
    "temperature_2m", "apparent_temperature", "relative_humidity_2m",
    "is_day", "precipitation", "weather_code", "cloud_cover",
    "pressure_msl", "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m",
]
DAILY_VARS = [
    "weather_code", "temperature_2m_max", "temperature_2m_min",
    "apparent_temperature_max", "apparent_temperature_min",
    "sunrise", "sunset", "uv_index_max", "precipitation_sum",
    "precipitation_probability_max", "precipitation_hours",
    "wind_speed_10m_max", "wind_gusts_10m_max",
]

CACHE_TTL = 900
_client = httpx.AsyncClient(timeout=30)


def _cache_path(city):
    key = f"{city['lat']}_{city['lng']}".replace(".", "_").replace("-", "m")
    return CACHE_DIR / f"{key}.json"


def _read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def transform(city, raw):
    cur = raw.get("current", {})
    h = raw.get("hourly", {})
    d = raw.get("daily", {})
    times = h.get("time", [])
    now_local = cur.get("time")

    start_i = 0
    for i, t in enumerate(times):
        if t >= now_local:
            start_i = i
            break

    cape = h.get("cape", [])
    hourly = []
    for i in range(start_i, len(times)):
        code = h["weather_code"][i]
        desc, kind = wmo_info(code)
        hourly.append({
            "time": times[i],
            "temp": h["temperature_2m"][i],
            "feels": h["apparent_temperature"][i],
            "humidity": h["relative_humidity_2m"][i],
            "dew": h["dew_point_2m"][i],
            "pop": h["precipitation_probability"][i],
            "precip": h["precipitation"][i],
            "code": code,
            "desc": desc,
            "kind": kind,
            "pressure": h["pressure_msl"][i],
            "cloud": h["cloud_cover"][i],
            "vis": h["visibility"][i],
            "wind": h["wind_speed_10m"][i],
            "wdir": h["wind_direction_10m"][i],
            "gust": h["wind_gusts_10m"][i],
            "uv": h["uv_index"][i],
            "is_day": h["is_day"][i],
            "cape": cape[i] if i < len(cape) else None,
        "jal": jalali_str(times[i]),
        })

    daily = []
    for j, day in enumerate(d.get("time", [])):
        code = d["weather_code"][j]
        desc, kind = wmo_info(code)
        daily.append({
            "date": day,
            "code": code,
            "desc": desc,
            "kind": kind,
            "tmax": d["temperature_2m_max"][j],
            "tmin": d["temperature_2m_min"][j],
            "feels_max": d["apparent_temperature_max"][j],
            "feels_min": d["apparent_temperature_min"][j],
            "sunrise": d["sunrise"][j],
            "sunset": d["sunset"][j],
            "uvmax": d["uv_index_max"][j],
            "precip_sum": d["precipitation_sum"][j],
            "pop_max": d["precipitation_probability_max"][j],
            "precip_hours": d["precipitation_hours"][j],
            "wind_max": d["wind_speed_10m_max"][j],
            "gust_max": d["wind_gusts_10m_max"][j],
            "moon": moon_phase_fa(day),
            "jal": jalali_str(day),
        })

    desc, kind = wmo_info(cur.get("weather_code"))
    wd = cur.get("wind_direction_10m")
    t_now = cur.get("temperature_2m")
    rh_now = cur.get("relative_humidity_2m")
    sunrise0 = d["sunrise"][0] if d.get("sunrise") else None
    sunset0 = d["sunset"][0] if d.get("sunset") else None
    uvmax0 = d["uv_index_max"][0] if d.get("uv_index_max") else None

    return {
        "city": {
            "fa": city["fa"], "en": city["en"], "prov": city["prov"],
            "lat": city["lat"], "lng": city["lng"],
        },
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M", time.localtime()),
        "current": {
            "time": now_local,
            "temp": t_now,
            "feels": cur.get("apparent_temperature"),
            "humidity": rh_now,
            "is_day": cur.get("is_day", 1),
            "precip": cur.get("precipitation"),
            "code": cur.get("weather_code"),
            "desc": desc,
            "kind": kind,
            "cloud": cur.get("cloud_cover"),
            "pressure": cur.get("pressure_msl"),
            "wind": cur.get("wind_speed_10m"),
            "wind_label": beaufort_label(cur.get("wind_speed_10m")),
            "wdir": wd,
            "wdir_fa": wind_dir_fa(wd),
            "gust": cur.get("wind_gusts_10m"),
            "dew": dew_point(t_now, rh_now),
            "heat_note": heat_note(t_now),
            "sunrise": sunrise0,
            "sunset": sunset0,
            "uv_note": uv_label(uvmax0),
        },
        "hourly": hourly,
        "daily": daily,
        "elevation": raw.get("elevation"),
        "utc_offset": raw.get("utc_offset_seconds"),
    }


app = FastAPI(title="هواشناسی ایران")


@app.get("/api/cities/search")
async def api_search(q: str = "", limit: int = 12):
    return {"results": search_cities(q, min(limit, 30))}


@app.get("/api/weather/{city_id}")
async def api_weather(city_id: int, refresh: bool = False):
    if city_id < 0 or city_id >= len(CITIES):
        raise HTTPException(404, "city not found")
    city = CITIES[city_id]
    cf = _cache_path(city)
    now = time.time()
    if not refresh and cf.exists() and now - cf.stat().st_mtime < CACHE_TTL:
        data = _read_json(cf)
        if data:
            data["cached"] = True
            return data
    try:
        params = {
            "latitude": city["lat"], "longitude": city["lng"],
            "current": ",".join(CURRENT_VARS),
            "hourly": ",".join(HOURLY_VARS),
            "daily": ",".join(DAILY_VARS),
            "timezone": "Asia/Tehran",
            "forecast_days": 7,
            "wind_speed_unit": "kmh",
        }
        r = await _client.get(OPEN_METEO, params=params)
        r.raise_for_status()
        data = transform(city, r.json())
        tmp = cf.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(cf)
        data["cached"] = False
        return data
    except Exception as e:
        stale = _read_json(cf) if cf.exists() else None
        if stale is not None:
            stale["cached"] = True
            stale["stale"] = True
            return stale
        raise HTTPException(502, f"سرویس هواشناسی در دسترس نیست: {e}")


@app.get("/api/home")
async def api_home(keep: int = 30, refresh: bool = False):
    """وضعیت لحظه‌ای پرجمعیت‌ترین شهرها برای صفحه‌ی اصلی (از کش، بدون فراخوانی همزمان)."""
    keep = min(keep, 40)
    cells = []
    missing = []
    for idx, city in enumerate(CITIES[:keep]):
        cf = _cache_path(city)
        data = _read_json(cf) if cf.exists() else None
        fresh = data and (time.time() - cf.stat().st_mtime < CACHE_TTL * 4)
        if fresh:
            c = data.get("current", {})
            cells.append({
                "id": idx, "fa": city["fa"], "en": city["en"], "prov": city["prov"],
                "temp": c.get("temp"), "code": c.get("code"), "desc": c.get("desc"),
                "kind": c.get("kind"), "is_day": c.get("is_day", 1), "wind": c.get("wind"),
                "humidity": c.get("humidity"), "feels": c.get("feels"),
            })
        else:
            missing.append(idx)
    # warm-up in background-safe batches
    if missing:
        try:
            sem = asyncio.Semaphore(6)
            async def one(i):
                async with sem:
                    await api_weather(i, refresh=refresh)
            await asyncio.gather(*(one(i) for i in missing), return_exceptions=True)
        except Exception:
            pass
        for idx in missing:
            cf = _cache_path(CITIES[idx])
            data = _read_json(cf) if cf.exists() else None
            if data:
                c = data.get("current", {})
                cells.append({
                    "id": idx, "fa": CITIES[idx]["fa"], "en": CITIES[idx]["en"],
                    "prov": CITIES[idx]["prov"],
                    "temp": c.get("temp"), "code": c.get("code"), "desc": c.get("desc"),
                    "kind": c.get("kind"), "is_day": c.get("is_day", 1),
                    "wind": c.get("wind"), "humidity": c.get("humidity"), "feels": c.get("feels"),
                })
    cells.sort(key=lambda x: x["id"])
    return {"cells": cells, "count": len(cells)}


@app.get("/api/provinces")
async def api_provinces():
    provs = []
    seen = set()
    for c in CITIES:  # cities.json is pop-sorted, so order is sensible
        if c["prov"] not in seen:
            seen.add(c["prov"])
            provs.append(c["prov"])
    return {"provinces": provs}


@app.get("/api/cities")
async def api_cities(prov: str = "", q: str = "", limit: int = 400):
    if prov:
        items = [c for c in CITIES if c["prov"] == prov]
        items.sort(key=lambda x: -x["pop"])
    elif q:
        return {"cities": search_cities(q, min(limit, 30))}
    else:
        items = sorted(CITIES, key=lambda x: -x["pop"])
    return {"cities": items[: min(limit, 400)]}


@app.get("/api/health")
async def health():
    return {"ok": True, "cities": len(CITIES), "ts": time.time()}


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")

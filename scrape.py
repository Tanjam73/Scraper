#!/usr/bin/env python3
"""
Mumbai monsoon rail data collector.

Runs on a schedule (GitHub Actions) and appends two raw logs:
  data/rainfall.csv    -- one row per location per run (a rainfall time series)
  data/disruptions.csv -- one row per NEW disruption news item (deduped by link)

You join these two later: "ward X crossed Y mm  ->  section Z failed T min after".
That join is the analysis step. This file only CAPTURES. Capture now, derive later.

No API keys. No paid services. Two free, stable sources:
  - Open-Meteo  (rainfall / precipitation, no key)
  - Google News RSS (disruption events, no key)

If one source is down, the other still logs. A failing run never crashes the job.
"""

import csv
import os
import sys
import time
import datetime as dt
from urllib.parse import quote_plus

import requests
import feedparser

# --------------------------------------------------------------------------- #
# Config -- edit these freely.
# --------------------------------------------------------------------------- #

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

# Points along WR / CR / Harbour + known flood hotspots.
# NOTE: Open-Meteo's precipitation grid is ~11 km, so nearby points may report
# the same value. That's fine to start. For TRUE ward-level rain, swap in BMC's
# AWS portal later -- the CSV schema stays identical.
LOCATIONS = [
    ("Churchgate",   18.935, 72.827, "WR"),
    ("Dadar",        19.018, 72.844, "WR/CR"),
    ("Andheri",      19.119, 72.846, "WR"),
    ("Borivali",     19.231, 72.857, "WR"),
    ("Virar",        19.455, 72.811, "WR"),
    ("CSMT",         18.940, 72.835, "CR"),
    ("Sion",         19.043, 72.862, "CR-hotspot"),
    ("Kurla",        19.065, 72.879, "CR-hotspot"),
    ("Thane",        19.186, 72.975, "CR"),
    ("Kalyan",       19.243, 73.130, "CR"),
    ("Chunnabhatti", 19.046, 72.875, "Harbour-hotspot"),
    ("Matunga",      19.027, 72.852, "CR-hotspot"),
]

# Searches that surface Mumbai local-train disruption events.
NEWS_QUERIES = [
    "mumbai local train waterlogging",
    "mumbai local train suspended rain",
    "western railway local delayed rain",
    "central railway mumbai local disrupted",
    "harbour line train waterlogging",
]

# Keywords that mark an item as an actual disruption (used only to tag rows).
DISRUPTION_WORDS = [
    "waterlog", "suspend", "delay", "disrupt", "flood", "halt",
    "cancel", "stranded", "submerg", "block", "late",
]

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
RAIN_CSV = os.path.join(DATA_DIR, "rainfall.csv")
DISR_CSV = os.path.join(DATA_DIR, "disruptions.csv")

RAIN_HEADER = ["run_ts_ist", "location", "lat", "lon", "line",
               "obs_time", "precip_mm", "rain_mm", "source"]
DISR_HEADER = ["run_ts_ist", "published", "headline", "matched", "link", "source"]

OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
GNEWS_RSS = "https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"

HEADERS = {"User-Agent": "mumbai-rail-collector/1.0 (research data collection)"}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def now_ist():
    return dt.datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")


def ensure_csv(path, header):
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(header)


def append_rows(path, rows):
    with open(path, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)


def existing_links(path):
    """Links already logged, so we don't re-log the same news every 30 min."""
    seen = set()
    if os.path.exists(path):
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                seen.add(row.get("link", ""))
    return seen


# --------------------------------------------------------------------------- #
# Source 1: rainfall (always log a row per location -- it's a time series)
# --------------------------------------------------------------------------- #

def fetch_rainfall():
    rows, ts = [], now_ist()
    for name, lat, lon, line in LOCATIONS:
        try:
            r = requests.get(
                OPEN_METEO,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "precipitation,rain",
                    "timezone": "Asia/Kolkata",
                },
                headers=HEADERS,
                timeout=20,
            )
            r.raise_for_status()
            cur = r.json().get("current", {})
            rows.append([ts, name, lat, lon, line,
                         cur.get("time", ""),
                         cur.get("precipitation", ""),
                         cur.get("rain", ""),
                         "open-meteo"])
        except Exception as e:                       # one bad point != lost run
            print(f"  rainfall {name}: {e}", file=sys.stderr)
            rows.append([ts, name, lat, lon, line, "", "", "", "open-meteo-ERR"])
        time.sleep(0.4)                              # be polite
    return rows


# --------------------------------------------------------------------------- #
# Source 2: disruption news (log only NEW items)
# --------------------------------------------------------------------------- #

def fetch_disruptions(seen):
    out, ts = [], now_ist()
    for q in NEWS_QUERIES:
        url = GNEWS_RSS.format(q=quote_plus(q))
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)
        except Exception as e:
            print(f"  news '{q}': {e}", file=sys.stderr)
            continue
        for entry in feed.entries:
            link = entry.get("link", "")
            if not link or link in seen:
                continue
            title = entry.get("title", "")
            matched = [w for w in DISRUPTION_WORDS if w in title.lower()]
            if not matched:                          # skip unrelated headlines
                continue
            seen.add(link)
            out.append([ts,
                        entry.get("published", ""),
                        title,
                        "|".join(matched),
                        link,
                        entry.get("source", {}).get("title", "google-news")])
        time.sleep(0.4)
    return out


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main():
    ensure_csv(RAIN_CSV, RAIN_HEADER)
    ensure_csv(DISR_CSV, DISR_HEADER)

    try:
        rain = fetch_rainfall()
        append_rows(RAIN_CSV, rain)
        print(f"rainfall: +{len(rain)} rows")
    except Exception as e:
        print(f"rainfall block failed: {e}", file=sys.stderr)

    try:
        seen = existing_links(DISR_CSV)
        disr = fetch_disruptions(seen)
        if disr:
            append_rows(DISR_CSV, disr)
        print(f"disruptions: +{len(disr)} new items")
    except Exception as e:
        print(f"disruption block failed: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Publishes the NOTAMs in force at each airport, for the airport NOTAM lists in the page.

The NOTAMs come from the private extract that the Raspberry Pi pushes every 15 minutes
from the Signal bot's NOTAM copy (see the Pi's /root/avwx-airspace-export/export.py);
nothing here asks the FAA. Only airports in the weather station list are kept, since
those are the ones the page can show.

Each airport's list is compressed and scrambled the same way as the airspace NOTAM texts
(see notam_text_entry in update_airspace.py), keyed by its ICAO code, and filed in one of
256 small files in data/airport_notams/. A page looking up EDDK fetches only the one
file that holds EDDK. data/airport_notams/status.json says how fresh the data is.

NOTAMs at other locations (FIRs and US centers, country-wide and GPS NOTAMs, airfields
without a weather station) are filed the same way under their own location, for the
regional NOTAM PDFs; data/airport_notams/areas.json lists them, with each airport's FIR.

This deters casual copying only; anyone reading index.html can unscramble an airport.
"""
import base64
import gzip
import hashlib
import json
import math
import os
import re
import sys
import zlib
from collections import Counter
from datetime import datetime, timezone

EXTRACT_PATH = os.environ.get("NOTAM_AIRPORTS_PATH", "")
STATIONS_PATH = "data/stations.cache.xml.gz"
OUT_DIR = "data/airport_notams"
SALT = "avwx-airport-notams-v1"
MAX_AGE_HOURS = 6        # an extract older than this is not shown at all


def entry(icao, notams):
    """(file, locator, scrambled data) for one airport's list. index.html
    (readAirportNotams) reverses this."""
    key = hashlib.sha256(f"{SALT}|{icao}".encode()).digest()
    locator = hashlib.sha256(b"loc|" + key).hexdigest()[:24]
    packed = zlib.compress(json.dumps(notams, separators=(",", ":"), ensure_ascii=False).encode("utf-8"), 9)
    stream = b"".join(hashlib.sha256(key + counter.to_bytes(4, "big")).digest()
                      for counter in range(len(packed) // 32 + 1))
    scrambled = bytes(a ^ b for a, b in zip(packed, stream))
    return locator[:2], locator, base64.b64encode(scrambled).decode()


def station_ids():
    with gzip.open(STATIONS_PATH, "rt", encoding="utf-8", errors="replace") as f:
        return set(re.findall(r"<station_id>\s*([A-Z0-9]{3,4})\s*</station_id>", f.read()))


def station_info():
    """{station: (country, state, latitude, longitude)} from the station list."""
    with gzip.open(STATIONS_PATH, "rt", encoding="utf-8", errors="replace") as f:
        text = f.read()
    info = {}
    for block in re.findall(r"<Station>(.*?)</Station>", text, re.S):
        tag = lambda name: (re.search(rf"<{name}>\s*([^<]*?)\s*</{name}>", block) or [None, ""])[1]
        try:
            lat, lon = float(tag("latitude")), float(tag("longitude"))
        except ValueError:
            lat = lon = None
        if tag("station_id"):
            info[tag("station_id")] = (tag("country"), tag("state"), lat, lon)
    return info


def position_of(text):
    """(latitude, longitude) from a Q-line position such as "4937N00612E", or None."""
    m = re.fullmatch(r"(\d{2})(\d{2})([NS])(\d{3})(\d{2})([EW])", (text or "").strip().upper())
    if not m:
        return None
    lat = (int(m[1]) + int(m[2]) / 60) * (1 if m[3] == "N" else -1)
    lon = (int(m[4]) + int(m[5]) / 60) * (1 if m[6] == "E" else -1)
    return round(lat, 3), round(lon, 3)


def airport_of(notam, stations, by_last_three):
    """The airport a NOTAM belongs to. US domestic NOTAMs often carry only the FAA's own
    three-letter id (JFK); that is matched to the station list (KJFK, or PANC in Alaska)."""
    icao = notam.get("l") or ""
    if icao in stations:
        return icao
    domestic = notam.get("d") or ""
    if not icao and len(domestic) == 3 and domestic.isalpha():
        if "K" + domestic in stations:
            return "K" + domestic
        return by_last_three.get(domestic)
    return None


def write(files, status):
    os.makedirs(OUT_DIR, exist_ok=True)
    for index in range(256):
        name = f"{index:02x}"
        path = os.path.join(OUT_DIR, name + ".json")
        body = json.dumps(files.get(name, {}), separators=(",", ":"), sort_keys=True)
        if not os.path.exists(path) or open(path).read() != body:
            with open(path, "w") as f:
                f.write(body)
    with open(os.path.join(OUT_DIR, "status.json"), "w") as f:
        json.dump(status, f, separators=(",", ":"))


def main():
    if not EXTRACT_PATH or not os.path.exists(EXTRACT_PATH):
        print("No airport NOTAM extract, nothing changed.")
        return
    with open(EXTRACT_PATH, encoding="utf-8") as f:
        extract = json.load(f)
    as_of = extract.get("bot_data_as_of", "")
    try:
        age_hours = (datetime.now(timezone.utc) - datetime.strptime(as_of[:16], "%Y-%m-%dT%H:%M")
                     .replace(tzinfo=timezone.utc)).total_seconds() / 3600
    except ValueError:
        age_hours = 999
    if age_hours > MAX_AGE_HOURS:
        # Better no list than an old one: a reopened runway would still show as closed
        write({}, {"ok": False, "as_of": as_of, "reason": "the NOTAM copy is out of date"})
        with open(os.path.join(OUT_DIR, "areas.json"), "w") as f:
            json.dump({"airport_fir": {}, "areas": []}, f)
        print(f"Extract too old ({as_of}); airport NOTAMs withdrawn.")
        return

    stations = station_ids()
    by_last_three = {}
    for station in sorted(stations):
        if len(station) == 4 and station[0] == "P":
            by_last_three.setdefault(station[1:], station)

    notams = extract.get("notams", [])
    # A US center or FIR given by its FAA id ("ZMA") is filed under its ICAO one ("KZMA")
    icao_of = {n["d"]: n["l"] for n in notams if n.get("d") and n.get("l") and n["d"] != n["l"]}

    def fir_of(notam):
        fir = (notam.get("fir") or "").strip().upper()
        if len(fir) == 3:
            fir = icao_of.get(fir) or ("K" + fir if fir.startswith("Z") else fir)
        return fir if re.fullmatch(r"[A-Z0-9]{4}", fir) else ""

    per_airport, per_area, firs, positions, all_firs = {}, {}, {}, {}, set()
    for notam in notams:
        if not notam.get("t"):
            continue
        # [number, start, end, issued, classification, text, schedule, Q-code]; the schedule is item D,
        # the days and hours within the period when it applies ("MON-FRI 2200-0400"), or ""; the
        # Q-code ("QMRLC": runway closed) is the subject the issuing office gave it, or ""
        row = [notam.get("n", ""), notam.get("s", ""), notam.get("e", ""), notam.get("i", ""), notam.get("c", ""),
               notam["t"].replace("\r\n", "\n").strip(), (notam.get("sch") or "").strip(), (notam.get("q") or "").strip()]
        if fir_of(notam):
            all_firs.add(fir_of(notam))
        airport = airport_of(notam, stations, by_last_three)
        if airport:
            per_airport.setdefault(airport, []).append(row)
            if fir_of(notam):
                firs.setdefault(airport, Counter())[fir_of(notam)] += 1
            continue
        # Not at a weather station: a FIR or US center, a country-wide or GPS NOTAM, or a
        # small airfield; filed under its own location for the regional NOTAM PDFs
        area = (notam.get("l") or notam.get("d") or "").strip().upper()
        if not re.fullmatch(r"[A-Z0-9]{3,4}", area):
            continue
        per_area.setdefault(area, []).append(row)
        position = position_of(notam.get("pos"))
        if position:
            positions.setdefault(area, []).append(position)

    files = {}
    for key, rows in list(per_airport.items()) + list(per_area.items()):
        rows.sort(key=lambda n: (n[1], n[0]))
        name, locator, data = entry(key, rows)
        files.setdefault(name, {})[locator] = data

    # Which FIR or center each airport lies in (the one its NOTAMs name most), and for each
    # area: its country (from the stations sharing its ICAO prefix), US state (that of the
    # nearest station, for small US airfields), position, NOTAM count and kind
    info = station_info()
    airport_fir = {airport: counts.most_common(1)[0][0] for airport, counts in firs.items()}
    fir_set = set(airport_fir.values()) | all_firs
    prefix_country = {}
    for prefix_len in (2, 1):
        counts = {}
        for station, (country, _, _, _) in info.items():
            if len(station) == 4 and country:
                counts.setdefault(station[:prefix_len], Counter())[country] += 1
        prefix_country[prefix_len] = {p: c.most_common(1)[0][0] for p, c in counts.items()}
    located = [(s, v) for s, v in info.items() if v[0] == "US" and v[1] and v[2] is not None]
    areas = []
    for area, rows in sorted(per_area.items()):
        domestic_only = all(r[4] in ("DOM", "DOMESTIC", "FDC") for r in rows) and len(area) == 3
        country = "US" if domestic_only else (prefix_country[2].get(area[:2]) or prefix_country[1].get(area[:1]) or "")
        lat = lon = None
        if area in positions:
            lats, lons = sorted(p[0] for p in positions[area]), sorted(p[1] for p in positions[area])
            lat, lon = lats[len(lats) // 2], lons[len(lons) // 2]
        kind = "gps" if area == "KGPS" else ("fir" if area in fir_set else "other")
        state = ""
        if country == "US" and kind == "other" and lat is not None and located:
            nearest, (_, near_state, near_lat, near_lon) = min(
                located, key=lambda s: (s[1][2] - lat) ** 2 + ((s[1][3] - lon) * math.cos(math.radians(lat))) ** 2)
            if math.hypot(near_lat - lat, (near_lon - lon) * math.cos(math.radians(lat))) < 1.0:
                state = near_state
        areas.append([area, kind, country, state, lat, lon, len(rows)])
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "areas.json"), "w") as f:
        json.dump({"airport_fir": airport_fir, "areas": areas}, f, separators=(",", ":"), sort_keys=True)

    write(files, {"ok": True, "as_of": as_of, "airports": len(per_airport),
                  "notams": sum(len(n) for n in per_airport.values()),
                  "areas": len(per_area), "area_notams": sum(len(n) for n in per_area.values())})
    print(f"Airport NOTAMs: {sum(len(n) for n in per_airport.values())} at {len(per_airport)} airports, "
          f"{sum(len(n) for n in per_area.values())} more at {len(per_area)} other locations, "
          f"data as of {as_of}.")


if __name__ == "__main__":
    sys.exit(main())

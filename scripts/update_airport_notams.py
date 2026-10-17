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

This deters casual copying only; anyone reading index.html can unscramble an airport.
"""
import base64
import gzip
import hashlib
import json
import os
import re
import sys
import zlib
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
        print(f"Extract too old ({as_of}); airport NOTAMs withdrawn.")
        return

    stations = station_ids()
    by_last_three = {}
    for station in sorted(stations):
        if len(station) == 4 and station[0] == "P":
            by_last_three.setdefault(station[1:], station)

    per_airport = {}
    for notam in extract.get("notams", []):
        airport = airport_of(notam, stations, by_last_three)
        if not airport or not notam.get("t"):
            continue
        # [number, start, end, issued, classification, text]
        per_airport.setdefault(airport, []).append(
            [notam.get("n", ""), notam.get("s", ""), notam.get("e", ""), notam.get("i", ""), notam.get("c", ""),
             notam["t"].replace("\r\n", "\n").strip()])

    files = {}
    for airport, notams in per_airport.items():
        notams.sort(key=lambda n: (n[1], n[0]))
        name, locator, data = entry(airport, notams)
        files.setdefault(name, {})[locator] = data
    write(files, {"ok": True, "as_of": as_of, "airports": len(per_airport),
                  "notams": sum(len(n) for n in per_airport.values())})
    print(f"Airport NOTAMs: {sum(len(n) for n in per_airport.values())} at {len(per_airport)} airports, "
          f"data as of {as_of}.")


if __name__ == "__main__":
    sys.exit(main())

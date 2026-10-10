#!/usr/bin/env python3
"""Writes data/satellite_times.json: the newest GeoColor image times on CIRA's SLIDER.

The map's satellite layer needs to know which images exist, but SLIDER does not let web
pages read its list of times, so this job fetches it and republishes it alongside the
weather data. For each satellite the three newest times are kept (the page uses the
second as a backup while the newest is still being published). A satellite whose list
cannot be fetched keeps its previous entry.
"""
import json
import os
import urllib.request

SATELLITES = ["goes-19", "goes-18", "himawari", "meteosat-9"]
SOURCE_URL = "https://slider.cira.colostate.edu/data/json/{}/full_disk/geocolor/latest_times.json"
OUT_PATH = "data/satellite_times.json"


def main():
    times = {}
    if os.path.exists(OUT_PATH):
        try:
            with open(OUT_PATH) as f:
                times = json.load(f)
        except ValueError:
            times = {}

    for satellite in SATELLITES:
        try:
            with urllib.request.urlopen(SOURCE_URL.format(satellite), timeout=20) as response:
                stamps = [str(t) for t in json.load(response)["timestamps_int"]]
            if not stamps or not all(len(s) == 14 and s.isdigit() for s in stamps[:3]):
                raise ValueError("unexpected list of times")
            times[satellite] = sorted(stamps, reverse=True)[:3]
            print(f"{satellite}: newest {times[satellite][0]}")
        except Exception as error:
            print(f"{satellite}: kept previous times ({error})")

    with open(OUT_PATH, "w") as f:
        json.dump(times, f, separators=(",", ":"))


if __name__ == "__main__":
    main()

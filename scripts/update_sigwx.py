#!/usr/bin/env python3
"""Gathers the high-level significant weather forecast for the map's SIG WX layer.

The World Area Forecast System's forecast (thunderstorm cloud, icing, turbulence, jet
streams, tropopause heights, tropical cyclones, volcanoes) is published by
aviationweather.gov as eight small files per forecast time. Browsers are not allowed
to read those from another site, so this copies the newest forecast run into one
compact file, data/sigwx.json, which the page reads.

A new run appears every six hours. Most times this is called there is nothing new, and
it stops after a couple of quick checks.
"""
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.request

SOURCE_URL = "https://aviationweather.gov/data/products/autosigwx/{day}/{day}_{hour}_F{ahead:02d}_sigwx_hi_{kind}.geojson"
OUT_PATH = "data/sigwx.json"
KINDS = ["CB", "ICING", "TURB", "JET", "TROP", "TC", "VOLC", "RAD"]
HOURS_AHEAD = list(range(6, 49, 3))
USER_AGENT = "AvWx-Web data job (github.com/Unpiloted0852/AvWx-Web)"


def source_url(run, ahead, kind):
    return SOURCE_URL.format(day=run.strftime("%Y%m%d"), hour=run.strftime("%H"), ahead=ahead, kind=kind)


def open_url(url, method="GET"):
    """The source is slow to answer now and then, so each request gets three tries.
    A plain "not there" is passed straight on."""
    request = urllib.request.Request(url, method=method, headers={"User-Agent": USER_AGENT})
    for attempt in range(3):
        try:
            return urllib.request.urlopen(request, timeout=30)
        except urllib.error.HTTPError as error:
            if error.code == 404 or attempt == 2:
                raise
        except (urllib.error.URLError, OSError):
            if attempt == 2:
                raise
        time.sleep(2 + 3 * attempt)


def exists(url):
    try:
        with open_url(url, "HEAD") as response:
            return response.status == 200
    except (urllib.error.URLError, OSError):
        return False


def fetch_features(url):
    with open_url(url) as response:
        return json.load(response).get("features") or []


def flat_points(coordinates):
    """[[lon, lat], ...] as [lat, lon, lat, lon, ...], rounded to about a kilometre"""
    flat = []
    for lon, lat in coordinates:
        flat += [round(lat, 2), round(lon, 2)]
    return flat


def level(value):
    """A flight level as a number, or None where the forecast gives none ("XXX")"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def outline(feature):
    geometry = feature.get("geometry") or {}
    if geometry.get("type") == "Polygon":
        return geometry["coordinates"][0]
    if geometry.get("type") == "LineString":
        return geometry["coordinates"]
    return None


def areas(features, label_key):
    out = []
    for feature in features:
        points = outline(feature)
        if not points or len(points) < 3:
            continue
        properties = feature.get("properties") or {}
        out.append({"k": str(properties.get(label_key) or ""), "top": level(properties.get("top")),
                    "base": level(properties.get("base")), "p": flat_points(points)})
    return out


def lines(features):
    out = []
    for feature in features:
        points = outline(feature)
        if not points or len(points) < 2:
            continue
        properties = feature.get("properties") or {}
        line = {"p": flat_points(points)}
        if "height" in properties:
            line["h"] = level(properties.get("height"))
        if "fleche" in properties:
            # Points along a jet stream where its speed (knots) and flight level are given
            line["f"] = [[round(f["lat"], 2), round(f["lon"], 2), f.get("speed"), f.get("height")]
                         for f in properties["fleche"] if "lat" in f and "lon" in f]
        out.append(line)
    return out


def points(features):
    out = []
    for feature in features:
        geometry = feature.get("geometry") or {}
        if geometry.get("type") != "Point":
            continue
        lon, lat = geometry["coordinates"][:2]
        out.append({"n": str((feature.get("properties") or {}).get("name") or ""), "p": [round(lat, 2), round(lon, 2)]})
    return out


def forecast_time(run, ahead):
    features = {kind: fetch_features(source_url(run, ahead, kind)) for kind in KINDS}
    valid = run + datetime.timedelta(hours=ahead)
    return {
        "valid": valid.strftime("%Y-%m-%dT%HZ"),
        "cb": areas(features["CB"], "extent"),
        "icing": areas(features["ICING"], "severity"),
        "turb": areas(features["TURB"], "severity"),
        "jet": lines(features["JET"]),
        "trop": lines(features["TROP"]),
        "tc": points(features["TC"]),
        "volc": points(features["VOLC"]),
        "rad": points(features["RAD"]),
    }


def main():
    have, have_times = None, 0
    try:
        with open(OUT_PATH) as f:
            old = json.load(f)
        have, have_times = old.get("run"), len(old.get("times") or [])
    except (OSError, ValueError):
        pass

    now = datetime.datetime.now(datetime.timezone.utc)
    newest = now.replace(hour=now.hour - now.hour % 6, minute=0, second=0, microsecond=0)
    for back in range(5):
        run = newest - datetime.timedelta(hours=6 * back)
        name = run.strftime("%Y-%m-%dT%HZ")
        # A run already in hand is left alone. One that could only be read in part is
        # tried again, but only a couple of times an hour, as this runs every few minutes.
        if name == have and (have_times == len(HOURS_AHEAD) or now.minute % 30 >= 10):
            print(f"Already have the newest run ({have}).")
            return
        # A run is taken once its first and last files are both there
        if exists(source_url(run, HOURS_AHEAD[0], KINDS[0])) and exists(source_url(run, HOURS_AHEAD[-1], KINDS[-1])):
            break
    else:
        print("No forecast run found.")
        return

    times = []
    for ahead in HOURS_AHEAD:
        try:
            times.append(forecast_time(run, ahead))
        except (urllib.error.URLError, OSError, ValueError, KeyError, TypeError) as error:
            print(f"Skipping +{ahead} h: {error}", file=sys.stderr)
    # A run that could only be read in part is tried again next time, and only replaces
    # what is there if it is an improvement
    if len(times) < len(HOURS_AHEAD) // 2 or (name == have and len(times) <= have_times):
        print(f"Read {len(times)} of {len(HOURS_AHEAD)} forecast times; keeping what is there.", file=sys.stderr)
        return

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH + ".tmp", "w") as f:
        json.dump({"run": name, "source": "WAFS high-level SIGWX via aviationweather.gov", "times": times},
                  f, separators=(",", ":"))
    os.replace(OUT_PATH + ".tmp", OUT_PATH)
    print(f"Wrote run {name}: {len(times)} forecast times.")


if __name__ == "__main__":
    main()

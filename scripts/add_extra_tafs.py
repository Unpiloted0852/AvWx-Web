#!/usr/bin/env python3
"""Adds TAFs that aviationweather.gov's cache is missing to data/tafs.cache.xml.gz.

Each station in STATIONS is fetched from the NWS text server and appended as a <TAF>
entry carrying the fields the page reads (raw_text, station_id, issue_time,
valid_time_from, valid_time_to). A station is skipped if the cache already has it, if
its TAF has expired, or if anything about it fails to download or parse, so the cache
file is never left worse than it was downloaded.
"""
import gzip
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

STATIONS = ["ETNG"]
SOURCE_URL = "https://tgftp.nws.noaa.gov/data/forecasts/taf/stations/{}.TXT"
CACHE_PATH = "data/tafs.cache.xml.gz"

HEADER = re.compile(r"^TAF (?:(?:AMD|COR) )?(\w{4}) (\d{2})(\d{2})(\d{2})Z (\d{2})(\d{2})/(\d{2})(\d{2})\b")


def nearest(ref, day, hour, minute=0):
    """The date with this day-of-month and time that lies closest to ref."""
    extra_day = hour == 24  # TAFs write midnight at the end of a day as hour 24
    if extra_day:
        hour = 0
    candidates = []
    for month_offset in (-1, 0, 1):
        month_index = ref.year * 12 + ref.month - 1 + month_offset
        try:
            candidate = datetime(month_index // 12, month_index % 12 + 1, day, hour, minute, tzinfo=timezone.utc)
        except ValueError:  # that month has no such day
            continue
        candidates.append(candidate + timedelta(days=1) if extra_day else candidate)
    return min(candidates, key=lambda c: abs(c - ref))


def build_entry(station, text, now):
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    ref = now
    if lines and re.fullmatch(r"\d{4}/\d{2}/\d{2} \d{2}:\d{2}", lines[0]):
        ref = datetime.strptime(lines.pop(0), "%Y/%m/%d %H:%M").replace(tzinfo=timezone.utc)
    raw = " ".join(" ".join(lines).split())
    if not raw.startswith("TAF "):
        raw = "TAF " + raw
    match = HEADER.match(raw)
    if not match or match.group(1) != station:
        raise ValueError("unrecognised TAF: " + raw[:60])
    if not re.fullmatch(r"[A-Z0-9 /+\-=.$]+", raw):
        raise ValueError("unexpected characters in TAF")
    _, i_day, i_hour, i_min, f_day, f_hour, t_day, t_hour = match.groups()
    issue = nearest(ref, int(i_day), int(i_hour), int(i_min))
    valid_from = nearest(issue, int(f_day), int(f_hour))
    valid_to = nearest(valid_from, int(t_day), int(t_hour))
    if valid_to <= now:
        raise ValueError("TAF expired at " + valid_to.isoformat())
    stamp = lambda d: d.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return (
        f"<TAF><raw_text><![CDATA[{raw}]]></raw_text><station_id>{station}</station_id>"
        f"<issue_time>{stamp(issue)}</issue_time><bulletin_time>{stamp(issue)}</bulletin_time>"
        f"<valid_time_from>{stamp(valid_from)}</valid_time_from>"
        f"<valid_time_to>{stamp(valid_to)}</valid_time_to></TAF>"
    )


def main():
    with gzip.open(CACHE_PATH, "rt", encoding="utf-8") as f:
        xml = f.read()
    end = xml.rfind("</data>")
    if end == -1:
        sys.exit("no </data> in " + CACHE_PATH)

    now = datetime.now(timezone.utc)
    entries = []
    for station in STATIONS:
        if f"<station_id>{station}</station_id>" in xml:
            print(f"{station}: already in the cache, skipped")
            continue
        try:
            with urllib.request.urlopen(SOURCE_URL.format(station), timeout=20) as response:
                text = response.read().decode("ascii")
            entries.append(build_entry(station, text, now))
            print(f"{station}: added")
        except Exception as error:
            print(f"{station}: skipped ({error})")
    if not entries:
        return

    xml = xml[:end] + "".join(entries) + xml[end:]
    xml = re.sub(
        r'(<data num_results=")(\d+)(")',
        lambda m: m.group(1) + str(int(m.group(2)) + len(entries)) + m.group(3),
        xml,
        count=1,
    )
    with gzip.open(CACHE_PATH, "wt", encoding="utf-8") as f:
        f.write(xml)


if __name__ == "__main__":
    main()

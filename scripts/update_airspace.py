#!/usr/bin/env python3
"""Writes data/airspace.json: special use airspace that is active now or due to be soon.

Sources, each read independently so that one failing does not lose the others:
  FAA   The SUA website's schedule (restricted, warning, alert, prohibited, MOA and
        other areas, plus TFRs) with times in UTC. Area shapes come with the schedule;
        TFR shapes come from the FAA's TFR map service.
  DFS   Germany's web AUP: activation times and shapes for German restricted areas.
  EAUP  The European airspace use plan and its updates (EUROCONTROL's EAUP/EUUP), read
        through the community service at eaup.vatsim.pt. The plan names areas without
        giving their shapes, so shapes are looked up by name in openAIP's airspace data
        (needs the OPENAIP_API_KEY environment variable; licence CC BY-NC) and kept in
        data/airspace_shapes_eu.json so each is only fetched once in a while. Areas
        whose shape cannot be found are left out.

  NOTAM Airspace activations from the rest of the world, taken from NOTAMs. These come
        from a private extract (see NOTAM_EXTRACT_PATH) that a separate machine prepares
        from its own NOTAM copy; this job makes no NOTAM requests itself. Only outlines,
        times and the NOTAM number are passed on, never the NOTAM text. Outlines are read
        from coordinate lists and circles in the text, or looked up in openAIP when the
        NOTAM names an area. This source is skipped when no extract is supplied.

        The full text of each NOTAM that is drawn is also published, so the map can show
        it when its area is tapped. Texts are split across the small files in
        data/notam_text/ and each is scrambled with a key made from its own NOTAM number,
        so they are not readable or searchable as files and cannot be fetched as one list.
        This is a deterrent to casual copying, not protection: anyone who knows a NOTAM's
        number and location can unscramble it, which is exactly what the map does.

If a source cannot be read, the areas it gave last time are kept until they expire.

The result is for situational awareness only. NOTAMs and the official publications
remain the authority.
"""
import base64
import hashlib
import html
import json
import math
import os
import re
import urllib.parse
import urllib.request
import zlib
from datetime import datetime, timedelta, timezone

OUT_PATH = "data/airspace.json"
LOOK_AHEAD_HOURS = 24
USER_AGENT = "Mozilla/5.0 (compatible; AvWx-Web data job)"

FAA_SCHEDULE_URL = "https://sua.faa.gov/sua/schedule.json?limit=2000"
FAA_TFR_SHAPES_URL = ("https://tfr.faa.gov/geoserver/TFR/ows?service=WFS&version=1.1.0&request=GetFeature"
                      "&typeName=TFR:V_TFR_LOC&outputFormat=application/json&srsname=EPSG:4326")
FAA_SUA_SHAPES_URL = ("https://services6.arcgis.com/ssFJjBXIUyZDrSYZ/arcgis/rest/services/Special_Use_Airspace"
                      "/FeatureServer/0/query")
DFS_AUP_URL = "https://ais.dfs.de/pilotservice/briefing/aup/ajax/aup_briefing.jsp"
EAUP_URL = "https://eaup.vatsim.pt/api/v4/areas/"
OPENAIP_URL = "https://api.core.openaip.net/api/airspaces"
SHAPES_PATH = "data/airspace_shapes_eu.json"
SHAPE_MAX_AGE_DAYS = 28      # look a known shape up again after this long
SHAPE_RETRY_DAYS = 3         # look a missing shape up again after this long

# How often each source is asked, in minutes. In between, its last answer is reused.
SOURCE_INTERVAL = {"FAA": 5, "DFS": 15, "EAUP": 15, "NOTAM": 10}

NOTAM_EXTRACT_PATH = os.environ.get("NOTAM_EXTRACT_PATH", "")
NOTAM_TEXT_DIR = "data/notam_text"
NOTAM_TEXT_SALT = "avwx-notam-text-v1"
NOTAM_MAX_AGE_HOURS = 6      # an extract older than this is not shown at all

# First two letters of a European area designator -> country code used by openAIP
EAUP_COUNTRIES = {
    "BI": "IS", "EB": "BE", "ED": "DE", "EE": "EE", "EF": "FI", "EG": "GB", "EH": "NL", "EI": "IE",
    "EK": "DK", "EL": "LU", "EN": "NO", "EP": "PL", "ES": "SE", "ET": "DE", "EV": "LV", "EY": "LT",
    "GC": "ES", "LA": "AL", "LB": "BG", "LC": "CY", "LD": "HR", "LE": "ES", "LF": "FR", "LG": "GR",
    "LH": "HU", "LI": "IT", "LJ": "SI", "LK": "CZ", "LM": "MT", "LO": "AT", "LP": "PT", "LQ": "BA",
    "LR": "RO", "LS": "CH", "LT": "TR", "LU": "MD", "LW": "MK", "LY": "RS", "LZ": "SK", "UG": "GE",
    "UK": "UA",
}
# The same for the rest of the world, used for areas named in NOTAMs
WORLD_COUNTRIES = dict(EAUP_COUNTRIES, **{
    "CY": "CA", "CZ": "CA", "MM": "MX", "SB": "BR", "SA": "AR", "SC": "CL", "SK": "CO", "SP": "PE",
    "YB": "AU", "YM": "AU", "YS": "AU", "YP": "AU", "NZ": "NZ", "RJ": "JP", "RO": "JP", "RK": "KR",
    "RC": "TW", "RP": "PH", "VT": "TH", "WS": "SG", "WM": "MY", "WI": "ID", "WA": "ID", "VH": "HK",
    "VI": "IN", "VA": "IN", "VO": "IN", "VE": "IN", "OP": "PK", "OE": "SA", "OM": "AE", "OO": "OM",
    "OB": "BH", "OK": "KW", "OJ": "JO", "OL": "LB", "LL": "IL", "HE": "EG", "DT": "TN", "GM": "MA",
    "DA": "DZ", "FA": "ZA", "HK": "KE", "UA": "KZ", "UB": "AZ", "UD": "AM", "UM": "BY", "UT": "UZ",
    "UU": "RU", "UW": "RU", "UH": "RU", "UL": "RU", "UR": "RU", "UI": "RU", "UE": "RU", "UN": "RU",
    "US": "RU", "UO": "RU",
})

FAA_TYPES = {"R": "Restricted", "W": "Warning", "A": "Alert", "P": "Prohibited", "M": "MOA", "O": "Other"}
FAA_TFR_TYPES = {"SEC": "Security", "HAZ": "Hazards", "EVT": "Special event", "UASPG": "UAS public gathering",
                 "VIP": "VIP", "SPC": "Space operations"}


def fetch(url, data=None, timeout=40):
    request = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def iso(moment):
    return moment.strftime("%Y-%m-%dT%H:%MZ")


MAX_RING_POINTS = 240


def ring(points, places=4):
    """[(lat, lon), ...] -> flat [lat, lon, lat, lon, ...] rounded to about 10 m.

    Some shapes arrive with thousands of points (circles drawn point by point); those
    are thinned evenly, which is plenty for a map overlay.
    """
    points = list(points)
    if len(points) > MAX_RING_POINTS:
        step = len(points) / MAX_RING_POINTS
        points = [points[int(i * step)] for i in range(MAX_RING_POINTS)]
    flat = []
    for lat, lon in points:
        flat += [round(lat, places), round(lon, places)]
    return flat


def keep_window(start, end, now):
    return end > now and start < now + timedelta(hours=LOOK_AHEAD_HOURS)


# ── Outline checks ───────────────────────────────────────────────────────────

def self_crosses(points):
    """True when an outline [(lat, lon), ...] crosses itself (drawn, it would look like a
    bow tie or have a fold in it)."""
    pts = list(points)
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    n = len(pts)
    if n < 4:
        return False

    def side(p, q, r):
        value = (q[1] - p[1]) * (r[0] - p[0]) - (q[0] - p[0]) * (r[1] - p[1])
        return (value > 1e-12) - (value < -1e-12)

    edges = [(pts[i], pts[(i + 1) % n]) for i in range(n)]
    for i in range(n):
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue
            (a, b), (c, d) = edges[i], edges[j]
            if side(a, b, c) * side(a, b, d) < 0 and side(c, d, a) * side(c, d, b) < 0:
                return True
    return False


def untangle(points):
    """Some notices draw a bow tie: a small area's corners listed out of order, or one stray
    corner in an otherwise good list. A single corner whose removal leaves a clean outline
    is dropped; failing that, up to eight corners are put in order around their middle if
    that gives a clean outline. Anything else is left exactly as published."""
    import math
    pts = list(points)
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    if not self_crosses(pts):
        return points
    if 5 <= len(pts) <= 80:
        for i in range(len(pts)):
            trimmed = pts[:i] + pts[i + 1:]
            if not self_crosses(trimmed):
                return trimmed
    if len(pts) > 8:
        return points
    lat0 = sum(p[0] for p in pts) / len(pts)
    lon0 = sum(p[1] for p in pts) / len(pts)
    scale = math.cos(math.radians(lat0))
    ordered = sorted(pts, key=lambda p: math.atan2(p[0] - lat0, (p[1] - lon0) * scale))
    return ordered if not self_crosses(ordered) else points


def corridor(line, half_width_km, round_start=False, round_end=False):
    """The area within half_width_km either side of a line through [(lat, lon), ...], as one
    outline: down one side and back up the other, with the ends squared off (or rounded,
    where a piece of a longer band meets the next piece). On the outside of each bend the
    edge follows a curve around the corner point (every spot there is exactly that far
    from it); on the inside the two edges meet where they cross."""
    line = [p for i, p in enumerate(line) if i == 0 or p != line[i - 1]]
    if len(line) < 2:
        return []
    lat0 = sum(p[0] for p in line) / len(line)
    kx = 111.32 * math.cos(math.radians(lat0))   # km per degree of longitude here
    ky = 110.57                                  # km per degree of latitude
    xy = [(p[1] * kx, p[0] * ky) for p in line]
    w = half_width_km

    def unit(a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy) or 1.0
        return dx / length, dy / length

    def side(sign):
        """The edge on one side: sign +1 is the left of the direction of travel."""
        out = []
        for i, (x, y) in enumerate(xy):
            d_in = unit(xy[i - 1], xy[i]) if i > 0 else None
            d_out = unit(xy[i], xy[i + 1]) if i < len(xy) - 1 else None
            if d_in is None or d_out is None:
                d = d_in or d_out
                out.append((x - sign * d[1] * w, y + sign * d[0] * w))
                continue
            n_in = (-sign * d_in[1], sign * d_in[0])
            n_out = (-sign * d_out[1], sign * d_out[0])
            turn = d_in[0] * d_out[1] - d_in[1] * d_out[0]   # > 0: the line bends left
            if abs(turn) < 1e-9 and d_in[0] * d_out[0] + d_in[1] * d_out[1] > 0:
                out.append((x + n_in[0] * w, y + n_in[1] * w))   # straight on
            elif turn * sign > 0:
                # Inside of the bend: where the two offset edges cross, kept within reach
                # so a very sharp bend does not throw the point far away
                mx, my = n_in[0] + n_out[0], n_in[1] + n_out[1]
                m = math.hypot(mx, my) or 1.0
                cos_half = max(0.25, (mx * n_in[0] + my * n_in[1]) / m)
                out.append((x + mx / m * w / cos_half, y + my / m * w / cos_half))
            else:
                # Outside of the bend: a curve around the corner point
                a1, a2 = math.atan2(n_in[1], n_in[0]), math.atan2(n_out[1], n_out[0])
                sweep = (a2 - a1 + math.pi) % (2 * math.pi) - math.pi
                steps = max(1, int(abs(sweep) / math.radians(10)))
                for k in range(steps + 1):
                    a = a1 + sweep * k / steps
                    out.append((x + math.cos(a) * w, y + math.sin(a) * w))
        return out

    def cap(i, d):
        """A half circle around point i, from the left edge round the front to the right
        edge, where d is the direction the front faces."""
        x, y = xy[i]
        a = math.atan2(d[0], -d[1])     # angle of the left edge
        return [(x + math.cos(a - math.pi * k / 12) * w, y + math.sin(a - math.pi * k / 12) * w) for k in range(1, 12)]

    left, right = side(1), side(-1)
    end_cap = cap(-1, unit(xy[-2], xy[-1])) if round_end else []
    start_cap = cap(0, unit(xy[1], xy[0])) if round_start else []
    outline = left + end_cap + right[::-1] + start_cap
    return [(y / ky, x / kx) for x, y in outline]


def corridor_pieces(line, half_width_km):
    """A band along a line, as one outline, or as several pieces where one outline would
    cross itself (a route that loops back across its own path). Drawn as one shape, the
    part where the band overlaps itself would show as a hole; as pieces it shows darker.
    Pieces meet at a turning point and have rounded ends there, so together they cover
    exactly the band."""
    line = [p for i, p in enumerate(line) if i == 0 or p != line[i - 1]]
    if len(line) < 2:
        return []
    pieces, current = [], line[:2]
    for point in line[2:]:
        if self_crosses(corridor(current + [point], half_width_km)):
            pieces.append(current)
            current = [current[-1], point]
        else:
            current = current + [point]
    pieces.append(current)
    last = len(pieces) - 1
    return [corridor(piece, half_width_km, round_start=i > 0, round_end=i < last) for i, piece in enumerate(pieces)]


# ── FAA ──────────────────────────────────────────────────────────────────────

def faa_limit(hundreds, above_ground):
    hundreds = int(hundreds)
    if hundreds == 0:
        return "SFC"
    if above_ground:
        return f"{hundreds * 100:,} ft AGL"
    if hundreds >= 180:
        return "UNL" if hundreds >= 990 else f"FL{hundreds:03d}"
    return f"{hundreds * 100:,} ft"


def faa_points(text):
    """38°38'19.000"N 104°52'2.000"W, ... -> [(lat, lon), ...]

    Single-digit minutes sometimes come with a space after the degree sign
    (110° 0'2.000"W); the spaces are allowed so those corners are not lost.
    """
    points = []
    for d1, m1, s1, ns, d2, m2, s2, ew in re.findall(
            r"(\d+)°\s*(\d+)'\s*([\d.]+)\"\s*([NS])\s+(\d+)°\s*(\d+)'\s*([\d.]+)\"\s*([EW])", text):
        lat = (int(d1) + int(m1) / 60 + float(s1) / 3600) * (1 if ns == "N" else -1)
        lon = (int(d2) + int(m2) / 60 + float(s2) / 3600) * (1 if ew == "E" else -1)
        points.append((lat, lon))
    return points


def geojson_rings(geometry):
    """Outer rings of a GeoJSON Polygon or MultiPolygon as [(lat, lon), ...] lists."""
    if not geometry:
        return []
    polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry.get("coordinates", [])
    return [[(lat, lon) for lon, lat in polygon[0]] for polygon in polygons if polygon]


def faa_charted_shape(name):
    """Looks a charted area up by name when the schedule came without its shape."""
    query = urllib.parse.urlencode({
        "where": "NAME LIKE '{}%'".format(name.replace("'", "''")),
        "outFields": "NAME", "f": "geojson", "outSR": 4326, "resultRecordCount": 5})
    features = json.loads(fetch(f"{FAA_SUA_SHAPES_URL}?{query}")).get("features", [])
    rings = []
    for feature in features:
        rings += geojson_rings(feature.get("geometry"))
    return rings


def faa_areas(now):
    schedule = json.loads(fetch(FAA_SCHEDULE_URL).decode("latin-1"))["schedule"]

    tfr_shapes = {}
    try:
        for feature in json.loads(fetch(FAA_TFR_SHAPES_URL))["features"]:
            notam = feature["properties"].get("NOTAM_KEY", "").split("-")[0]
            entry = tfr_shapes.setdefault(notam, {"rings": [], "title": feature["properties"].get("TITLE", "")})
            entry["rings"] += geojson_rings(feature.get("geometry"))
    except Exception as error:
        print(f"FAA: TFR shapes unavailable ({error})")

    areas = {}
    skipped = 0
    for row in schedule:
        try:
            start = datetime.strptime(row["start_time"], "%m/%d/%Y %H:%M").replace(tzinfo=timezone.utc)
            end = datetime.strptime(row["end_time"], "%m/%d/%Y %H:%M").replace(tzinfo=timezone.utc)
        except (KeyError, ValueError):
            skipped += 1
            continue
        if not keep_window(start, end, now):
            continue

        code = row.get("type", "")
        raw_name = row.get("airspace_name", "").strip()
        note = ""
        if row.get("type_class") == "TFR":
            name = f"TFR {raw_name}"
            kind = "TFR"
            shape = tfr_shapes.get(raw_name, {})
            rings = shape.get("rings", [])
            note = FAA_TFR_TYPES.get(code, code)
            if shape.get("title"):
                note += ": " + shape["title"].split(",")[0].strip() if "," in shape["title"] else ""
        else:
            name = f"{code}-{raw_name}" if code in "RWAP" and code else raw_name
            kind = FAA_TYPES.get(code, "Other")
            points = faa_points(html.unescape(row.get("tfr_short") or ""))
            if row.get("type_class") == "MTR / AR":
                # Military training routes and refuelling tracks mostly come as a closed
                # outline. A few come as a line whose ends lie far apart and which wanders
                # back across itself (the route's centre line); those are drawn as a band
                # 2 NM either side of the line, since the real width is not given. Anything
                # else is treated like any other outline.
                kind = "Route"
                ends_apart_nm = (math.hypot(points[0][0] - points[-1][0],
                                            (points[0][1] - points[-1][1]) * math.cos(math.radians(points[0][0]))) * 60
                                 if len(points) >= 2 else 0)
                if ends_apart_nm > 20 and self_crosses(points):
                    rings = corridor_pieces(points, 2 * 1.852)
                    note = "Route centre line, drawn 2 NM either side; actual width varies, see the chart"
                else:
                    rings = [untangle(points)] if len(points) >= 3 else []
            else:
                rings = [points] if len(points) >= 3 else []
                if rings and self_crosses(points):
                    # The schedule's outline is tangled: the charted shape is used instead
                    # when there is one, else small outlines are put in order
                    try:
                        charted = [r for r in faa_charted_shape(name) if not self_crosses(r)]
                    except Exception:
                        charted = []
                    rings = charted or [untangle(points)]

        key = name
        if key not in areas:
            if not rings and kind != "TFR":
                try:
                    rings = faa_charted_shape(name)
                except Exception:
                    rings = []
            if not rings:
                skipped += 1
                continue
            areas[key] = {"name": name, "kind": kind, "region": "US", "source": "FAA",
                          "state": row.get("state", ""), "note": note,
                          "rings": [ring(r) for r in rings], "windows": []}
        upper = faa_limit(row.get("max_alt", 0), str(row.get("max_alt_agl", "0")) == "1")
        if str(row.get("up_to_not_incl_fl_flag", "0")) == "1" and upper not in ("SFC", "UNL"):
            upper = "below " + upper
        areas[key]["windows"].append([iso(start), iso(end),
                                      faa_limit(row.get("min_alt", 0), str(row.get("agl", "0")) == "1"), upper])
    print(f"FAA: {len(areas)} areas, {skipped} entries skipped (no shape or unreadable times)")
    return list(areas.values())


# ── DFS (Germany) ────────────────────────────────────────────────────────────

def dfs_limit(token):
    token = token.upper()
    if token in ("GND", "SFC", "MSL"):
        return "SFC"
    if token == "UNL":
        return "UNL"
    if token.startswith("F") and token[1:].isdigit():
        return f"FL{int(token[1:]):03d}"
    if token.startswith("A") and token[1:].isdigit():
        return f"{int(token[1:]) * 100:,} ft"
    return token


def dfs_points(text):
    """514530N0084100E-515300N0084100E-... -> [(lat, lon), ...]"""
    points = []
    for la, ns, lo, ew in re.findall(r"(\d{6})([NS])(\d{7})([EW])", text):
        lat = (int(la[:2]) + int(la[2:4]) / 60 + int(la[4:]) / 3600) * (1 if ns == "N" else -1)
        lon = (int(lo[:3]) + int(lo[3:5]) / 60 + int(lo[5:]) / 3600) * (1 if ew == "E" else -1)
        points.append((lat, lon))
    return points


def dfs_areas(now):
    form = urllib.parse.urlencode({
        "DATE_BEGIN": now.strftime("%Y-%m-%d"), "TIME_BEGIN": now.strftime("%H:%M"),
        "DATE_END": (now + timedelta(hours=LOOK_AHEAD_HOURS)).strftime("%Y-%m-%d"),
        "TIME_END": (now + timedelta(hours=LOOK_AHEAD_HOURS)).strftime("%H:%M"),
        "LOWER": "GND", "UPPER": "UNL", "MAP": "OSM", "RADIOFAKEMAP": "on", "leaflet-base-layers_109": "on",
    }).encode()
    page = fetch(DFS_AUP_URL, data=form).decode("utf-8", "replace")
    if "data-polygon" not in page and "not available" in page:
        raise RuntimeError("briefing not available")

    areas = []
    for table in re.findall(r'<table class="airspace".*?</table>', page, flags=re.S):
        name = re.search(r'data-part="([^"]+)"', table)
        polygon = re.search(r'data-polygon="([^"]*)"', table)
        points = dfs_points(polygon.group(1)) if polygon else []
        if not name or len(points) < 3:
            continue
        windows = []
        for row in re.findall(r'<tr class="validity">.*?</tr>', table, flags=re.S):
            times = re.findall(r'<time datetime="([^"]+)"', row)
            limits = re.search(r"Lower Limit\s+(\S+)\s+to\s+Upper Limit\s+(\S+)", re.sub(r"<[^>]+>", " ", row))
            if len(times) < 2 or not limits:
                continue
            start = datetime.strptime(times[0], "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)
            end = datetime.strptime(times[1], "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)
            if keep_window(start, end, now):
                windows.append([iso(start), iso(end), dfs_limit(limits.group(1)), dfs_limit(limits.group(2))])
        if windows:
            kind = "Danger" if name.group(1).upper().startswith("ED-D") else "Restricted"
            areas.append({"name": name.group(1), "kind": kind, "region": "DE", "source": "DFS",
                          "state": "", "note": "", "rings": [ring(points)], "windows": windows})
    print(f"DFS: {len(areas)} areas")
    return areas


# ── EAUP (Europe) ────────────────────────────────────────────────────────────

def plain(text):
    return re.sub(r"[^A-Z0-9]", "", text.upper())


def eaup_kind(designator):
    code = designator[2:]
    for prefix, kind in (("TSA", "Temporary segregated"), ("TRA", "Temporary reserved"), ("TR", "Temporary reserved"),
                         ("D", "Danger"), ("R", "Restricted"), ("P", "Prohibited")):
        if code.startswith(prefix):
            return kind
    return "Reserved"


def eaup_base_name(designator):
    """EPD24Z, EGD013Z1 -> EPD24, EGD013: the area a flight-planning buffer zone belongs to."""
    return re.sub(r"(?<=[0-9A-Z])Z\d*$", "", designator) if re.search(r"\dZ\d*$|\d[A-Z]Z\d*$", designator) else designator


def openaip_country(country, api_key):
    items, page = [], 1
    while page:
        query = urllib.parse.urlencode({"country": country, "page": page, "limit": 1000})
        request = urllib.request.Request(f"{OPENAIP_URL}?{query}",
                                         headers={"x-openaip-api-key": api_key, "User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=90) as response:
            data = json.load(response)
        items += data.get("items", [])
        page = data.get("nextPage")
    return items


def openaip_index(items):
    """Ways an openAIP area may be referred to -> its rings.

    openAIP names vary by country: "EPD21", "D017 PORTLAND", "LF-R45A BOURGOGNE",
    "EY-D 10", "LI TRA 413 - TREBISACCE", "LI-R64-CUNEO". The name is split at spaces
    and hyphens, and the first one, two, three and four pieces joined are each taken
    as a possible designator.
    """
    index = {}
    for item in items:
        rings = geojson_rings(item.get("geometry"))
        pieces = [p for p in re.split(r"[\s\-]+", item.get("name", "").upper()) if p]
        if not rings or not pieces:
            continue
        for count in range(1, min(4, len(pieces)) + 1):
            candidate = plain("".join(pieces[:count]))
            if len(candidate) >= 3:
                index.setdefault(candidate, []).extend(r for r in rings if r not in index.get(candidate, []))
    return index


def openaip_lookup(index, name):
    """Rings for a plan designator: as written, without its country prefix, or, when the
    plan names a whole area that openAIP holds in lettered parts, all of those parts."""
    for wanted in (name, name[2:]):
        if len(wanted) >= 3 and wanted in index:
            return index[wanted]
    for wanted in (name, name[2:]):
        parts = [rings for key, rings in index.items()
                 if len(wanted) >= 4 and len(key) == len(wanted) + 1 and key.startswith(wanted) and key[-1].isalpha()]
        if parts:
            return [r for rings in parts for r in rings][:12]
    return None


def named_shapes(names, now, countries=EAUP_COUNTRIES):
    """Rings for each designator that can be found, using and updating the shapes file."""
    cache = {}
    if os.path.exists(SHAPES_PATH):
        try:
            with open(SHAPES_PATH) as f:
                cache = json.load(f)
        except ValueError:
            cache = {}
    today = now.strftime("%Y-%m-%d")

    def age(entry):
        return (now - datetime.strptime(entry["d"], "%Y-%m-%d").replace(tzinfo=timezone.utc)).days

    wanted = {}
    for name in names:
        entry = cache.get(name)
        if entry is None or age(entry) > (SHAPE_MAX_AGE_DAYS if entry.get("r") else SHAPE_RETRY_DAYS):
            country = countries.get(name[:2])
            if country:
                wanted.setdefault(country, []).append(name)

    api_key = os.environ.get("OPENAIP_API_KEY", "").strip()
    if wanted and not api_key:
        print("no OPENAIP_API_KEY, so new shapes cannot be looked up")
    changed = False
    for country, country_names in (wanted.items() if api_key else []):
        try:
            index = openaip_index(openaip_country(country, api_key))
        except Exception as error:
            print(f"openAIP {country} unavailable ({error})")
            continue
        for name in country_names:
            rings = openaip_lookup(index, name)
            previous = cache.get(name)
            if rings:
                cache[name] = {"d": today, "r": [ring(r) for r in rings]}
            elif previous and previous.get("r"):
                previous["d"] = today  # still plotted from the shape found before
            else:
                cache[name] = {"d": today}
            changed = True
    if changed:
        with open(SHAPES_PATH, "w") as f:
            json.dump(cache, f, separators=(",", ":"), sort_keys=True)
    return {name: cache[name]["r"] for name in names if cache.get(name, {}).get("r")}


def eaup_areas(now):
    plan = json.loads(fetch(EAUP_URL))
    notice = plan.get("notice_info", {})
    valid_from = datetime.fromisoformat(notice["valid_wef"]).replace(tzinfo=timezone.utc)
    valid_until = datetime.fromisoformat(notice["valid_til"]).replace(tzinfo=timezone.utc)

    def limit(level):
        level = int(level)
        return "SFC" if level <= 0 else "UNL" if level >= 660 else f"FL{level:03d}"

    def clock(text, not_before):
        """A time of day inside the plan's validity, as the first such moment at or after not_before."""
        hours, minutes = int(text[0:2]), int(text[3:5])
        moment = not_before.replace(hour=hours, minute=minutes, second=0, microsecond=0)
        return moment if moment >= not_before else moment + timedelta(days=1)

    listed = {row["name"] for row in plan.get("areas", [])}
    windows = {}
    for row in plan.get("areas", []):
        name = row["name"]
        if "NPZ" in name:
            continue  # no-planning zones are flight-planning constructs, not reserved airspace
        base = eaup_base_name(name)
        if base != name and base in listed:
            continue  # a buffer zone around an area that is itself in the plan
        start = clock(row["start_time"], valid_from.replace(hour=0, minute=0))
        if start < valid_from:
            start += timedelta(days=1) if start + timedelta(days=1) < valid_until else timedelta(0)
            start = max(start, valid_from)
        end = clock(row["end_time"], start + timedelta(minutes=1))
        end = min(end, valid_until) if end > valid_until else end
        if row["end_time"][:5] == "23:59":
            end += timedelta(minutes=1)
        if keep_window(start, end, now):
            windows.setdefault(base, []).append(
                [iso(start), iso(end), limit(row["minimum_fl"]), limit(row["maximum_fl"])])

    shapes = named_shapes(sorted(windows), now)
    kind_of_plan = notice.get("type", "EAUP")
    areas = []
    for name, area_windows in windows.items():
        if name not in shapes:
            continue
        areas.append({"name": name, "kind": eaup_kind(name), "region": EAUP_COUNTRIES.get(name[:2], "EU"),
                      "source": f"{kind_of_plan}, shape openAIP", "state": "", "note": "",
                      "rings": shapes[name], "windows": area_windows})
    STATUS_NOTES["EAUP"] = {"plan": kind_of_plan, "valid_until": iso(valid_until), "unplotted": len(windows) - len(areas)}
    print(f"EAUP: {len(areas)} of {len(windows)} areas have a shape ({kind_of_plan} valid from {iso(valid_from)})")
    return areas


# ── NOTAMs (rest of the world) ───────────────────────────────────────────────

NOTAM_KINDS = {"T": "Temporary restricted", "D": "Danger", "R": "Restricted", "P": "Prohibited",
               "A": "Airspace reservation", "M": "Military operating area", "O": "Overflying restriction"}
# Only NOTAMs announcing that an area is or will be in use: activated, will take place, established
NOTAM_STATES = ("CA", "LW", "CS")
NOTAM_COORD = re.compile(r"(\d{2})(\d{2})(\d{2}(?:\.\d+)?)?\s?([NS])\s{0,2}(\d{3})(\d{2})(\d{2}(?:\.\d+)?)?\s?([EW])")
NOTAM_RADIUS = re.compile(r"(?:RADIUS|RADII|RAD)\s*(?:OF\s*)?(\d+(?:[.,]\d+)?)\s*(NM|KM|M)\b"
                          r"|(\d+(?:[.,]\d+)?)\s*(NM|KM|M)\s*(?:RADIUS|RAD\b)")


def notam_point(match):
    d1, m1, s1, ns, d2, m2, s2, ew = match.groups()
    lat = (int(d1) + int(m1) / 60 + float(s1 or 0) / 3600) * (1 if ns == "N" else -1)
    lon = (int(d2) + int(m2) / 60 + float(s2 or 0) / 3600) * (1 if ew == "E" else -1)
    return (lat, lon) if abs(lat) <= 90 and abs(lon) <= 180 else None


def circle(centre, radius_km, steps=18):
    import math
    lat, lon = centre
    points = []
    for i in range(steps):
        angle = 2 * math.pi * i / steps
        d_lat = radius_km / 111.2 * math.cos(angle)
        d_lon = radius_km / (111.2 * max(0.05, math.cos(math.radians(lat)))) * math.sin(angle)
        points.append((lat + d_lat, lon + d_lon))
    return points


_C = NOTAM_COORD.pattern
_DIR = r"(?:COUNTER ?-?CLOCKWISE|ANTI ?-?CLOCKWISE|CLOCKWISE|CCW|CW)"
_RAD = r"(?P<r>\d+(?:[.,]\d+)?) ?(?P<u>NM|KM|M)\b"
_CENTRED = r"(?:CENTRED|CENTERED|CENTRE|CENTER)(?: ON| AT)?"
# Ways notices describe a boundary running along an arc to the next point:
#   ... FROM THIS POINT FOLLOWING AN ARC OF 5,9NM RADIUS CENTRED ON <centre> COUNTER CLOCKWISE UP TO <point>
#   ... THEN CLOCKWISE ALONG ARC RADIUS 28 KM CENTRE (<centre>) TO <point>
NOTAM_ARC = re.compile(
    r"(?:FROM THIS POINT )?(?:THEN )?(?:(?P<d1>" + _DIR + r") )?(?:FOLLOWING|ALONG) (?:AN? |THE )?(?:(?P<d2>" + _DIR
    + r") )?ARC (?:OF (?:A )?(?:CIRCLE )?)?(?:(?P<d3>" + _DIR + r") )?(?:WITH (?:A )?)?(?:RADIUS (?:OF )?" + _RAD
    + r"|" + _RAD.replace("<r>", "<r2>").replace("<u>", "<u2>") + r" RADIUS)(?: ?,)? ?" + _CENTRED + r" ?\(?(?P<c>" + _C
    + r")\)? ?(?:(?P<d4>" + _DIR + r") )?(?:UP )?TO\b")
#   ... - A CLOCKWISE 3NM ARC CENTERED ON <centre> - <point>
NOTAM_ARC_SHORT = re.compile(
    r"\bAN? (?P<d1>" + _DIR + r") " + _RAD + r" ARC " + _CENTRED + r" ?\(?(?P<c>" + _C + r")\)?")
#   THE LINE CONNECTING <a> TO <b> IS THE MINOR ARC WITH A RADIUS OF 50NM FM <centre>
NOTAM_ARC_LINE = re.compile(
    r"THE LINE CONNECTING (?P<a>" + _C + r") TO (?P<b>" + _C + r") IS THE (?P<k>MINOR|MAJOR) ARC (?:WITH )?(?:A )?RADIUS (?:OF )?"
    + _RAD + r" (?:FM|FROM|" + _CENTRED + r") (?P<c>" + _C + r")")


def arc_points(start, end, centre, clockwise=None, major=False):
    """Points along an arc around centre from start to end, not including either end, about
    every 5 degrees. The radius runs smoothly from the start's distance to the end's, so the
    arc meets both points exactly. With no direction given the shorter way round is taken
    (or the longer, for a major arc). Start and end the same: the full circle."""
    kx = 111.32 * math.cos(math.radians(centre[0]))
    ky = 110.57

    def polar(point):
        dx, dy = (point[1] - centre[1]) * kx, (point[0] - centre[0]) * ky
        return math.atan2(dx, dy), math.hypot(dx, dy)   # bearing (clockwise from north), km

    b1, r1 = polar(start)
    b2, r2 = polar(end)
    if r1 < 0.01 or r2 < 0.01:
        return []
    sweep = (b2 - b1) % (2 * math.pi)            # the clockwise way round
    if sweep < 1e-9:
        sweep = 2 * math.pi
    if clockwise is None:
        clockwise = (sweep <= math.pi) != major
    turn = sweep if clockwise else -(2 * math.pi - sweep)
    steps = max(2, int(abs(turn) / math.radians(5)))
    points = []
    for i in range(1, steps):
        f = i / steps
        b, r = b1 + turn * f, r1 + (r2 - r1) * f
        points.append((centre[0] + r * math.cos(b) / ky, centre[1] + r * math.sin(b) / kx))
    return points


def arc_direction(match):
    words = [match.groupdict().get(k) for k in ("d1", "d2", "d3", "d4")]
    word = next((w for w in words if w), None)
    if not word:
        return None
    return not re.match(r"COUNTER|ANTI|CCW", word)


def follow_arc_line(points, a, b, centre, major):
    """Where an outline has the edge a-b (either way round), that edge becomes the arc."""
    near = lambda p, q: abs(p[0] - q[0]) < 1e-4 and abs(p[1] - q[1]) < 1e-4
    n = len(points)
    for i in range(n):
        p, q = points[i], points[(i + 1) % n]
        if (near(p, a) and near(q, b)) or (near(p, b) and near(q, a)):
            return points[:i + 1] + arc_points(p, q, centre, None, major) + points[i + 1:]
    return points


# ── Following a border ───────────────────────────────────────────────────────
# Some notices run a boundary "along the state border" between two points. The country
# borders in data/boundaries.json (Natural Earth 1:50m, which the map also draws) are
# followed between them. Where borders stop at a coast, short hops across the water join
# them up, as a sea border would.

BOUNDARIES_PATH = "data/boundaries.json"
BORDER_HOP_KM = 150          # longest hop across water between two border lines
BORDER_REACH_KM = 15         # how near a border a notice's point must be
_border_graph = None


def border_graph():
    """Border vertices and their links: {vertex: [(neighbour, km), ...]}, plus the vertices."""
    global _border_graph
    if _border_graph is not None:
        return _border_graph
    links, vertices = {}, []
    try:
        with open(BOUNDARIES_PATH) as f:
            data = json.load(f)
    except (OSError, ValueError):
        _border_graph = ({}, [])
        return _border_graph
    scale = data.get("scale", 100)

    def link(a, b, km):
        links.setdefault(a, []).append((b, km))
        links.setdefault(b, []).append((a, km))

    ends = []
    for flat in data.get("countries", []):
        lon = lat = 0
        line = []
        for i in range(0, len(flat) - 1, 2):
            lon += flat[i]
            lat += flat[i + 1]
            line.append((lat / scale, lon / scale))
        for a, b in zip(line, line[1:]):
            if a != b:
                link(a, b, distance_km(a, b))
        if line:
            ends += [line[0], line[-1]]
    vertices = list(links)
    # Hops across water between the ends of border lines, made a little dearer than
    # following a border so a land border is always preferred
    for i, a in enumerate(ends):
        for b in ends[i + 1:]:
            if a != b and abs(a[0] - b[0]) < 1.5:
                km = distance_km(a, b)
                if km <= BORDER_HOP_KM:
                    link(a, b, km * 1.5)
    _border_graph = (links, vertices)
    return _border_graph


def distance_km(a, b):
    kx = 111.32 * math.cos(math.radians((a[0] + b[0]) / 2))
    return math.hypot((a[1] - b[1]) * kx, (a[0] - b[0]) * 110.57)


def border_path(start, end):
    """Points along the borders from near start to near end, or [] when no believable
    path is found (the caller then joins the two points with a straight edge)."""
    import heapq
    links, vertices = border_graph()
    if not vertices:
        return []
    nearest = lambda p: min(vertices, key=lambda v: (v[0] - p[0]) ** 2 + ((v[1] - p[1]) * math.cos(math.radians(p[0]))) ** 2)
    a, b = nearest(start), nearest(end)
    if distance_km(a, start) > BORDER_REACH_KM or distance_km(b, end) > BORDER_REACH_KM or a == b:
        return []
    straight = distance_km(start, end)
    best, previous, queue = {a: 0.0}, {}, [(0.0, a)]
    while queue:
        cost, v = heapq.heappop(queue)
        if v == b:
            break
        if cost > best.get(v, 1e18) or cost > 4 * straight + 50:
            continue
        for w, km in links.get(v, ()):
            if cost + km < best.get(w, 1e18):
                best[w] = cost + km
                previous[w] = v
                heapq.heappush(queue, (cost + km, w))
    if b not in previous:
        return []
    path = [b]
    while path[-1] != a:
        path.append(previous[path[-1]])
    return path[::-1]


NOTAM_BORDER = re.compile(r"(?:\bTHEN )?(?:\bALONG )?(?:THE )?(?:\b[A-Z]+ )?\bBORDER(?: LINE)?(?: TO\b)?")


NOTAM_CORRIDOR = re.compile(r"(\d+(?:[.,]\d+)?)\s*(NM|KM)\s+(?:EACH|EITHER|BOTH)\s+SIDES?\s+OF")


def notam_rings(text):
    """Outlines described in a NOTAM's text: runs of coordinates are polygons, and a lone
    coordinate with a radius beside it is a circle. A notice describing an area "5NM
    either side of a line" through its coordinates gets that band instead."""
    # Notices are wrapped at a fixed width, which can split a coordinate across two lines
    # (34341 / 7N1271700E). Where joining such breaks finds more coordinates, the joined
    # text is read; runs of spaces and line breaks are then treated as one space.
    joined = re.sub(r"(?<=[0-9NSEW])[ \t]*\n[ \t]*(?=[0-9NSEW])", "", text)
    if len(NOTAM_COORD.findall(joined)) > len(NOTAM_COORD.findall(text)):
        text = joined
    text = re.sub(r"\s+", " ", text)

    # Arcs. Each arc phrase is swapped for a marker, so its centre is not read as a corner
    # (or as the middle of a circle) and the boundary joins the points on either side of it
    # along the arc instead of a straight line.
    arcs = []

    def take_arc(match):
        centre = notam_point(NOTAM_COORD.match(match.group("c")))
        arcs.append((centre, arc_direction(match)))
        return f" ~ARC{len(arcs) - 1}~ "

    text = NOTAM_ARC.sub(take_arc, text)
    text = NOTAM_ARC_SHORT.sub(take_arc, text)
    arc_lines = []

    def take_arc_line(match):
        a, b, c = (notam_point(NOTAM_COORD.match(match.group(k))) for k in ("a", "b", "c"))
        if a and b and c:
            arc_lines.append((a, b, c, match.group("k") == "MAJOR"))
        return " "

    text = NOTAM_ARC_LINE.sub(take_arc_line, text)
    width = NOTAM_CORRIDOR.search(text)
    half_width_km = None
    if width:
        half_width_km = float(width.group(1).replace(",", ".")) * {"NM": 1.852, "KM": 1.0}[width.group(2)]
        if not 0.05 <= half_width_km <= 100:
            half_width_km = None
    matches = [(m, notam_point(m)) for m in NOTAM_COORD.finditer(text)]
    matches = [(m, p) for m, p in matches if p]
    runs, run = [], []
    arc_into = {}   # where a point is reached along an arc: its position -> the arc
    border_into = set()   # where a point is reached along a border: its position
    for match, point in matches:
        # Coordinates belong to the same outline when only separators (or an arc) lie between them
        gap = text[run[-1][0].end():match.start()] if run else ""
        markers = re.findall(r"~ARC(\d+)~", gap)
        # "THEN ALONG STATE BORDER TO", "-UKRAINIAN BORDER-": the edge to the next point
        # follows the border (see border_path)
        along_border = bool(NOTAM_BORDER.search(gap))
        gap_plain = NOTAM_BORDER.sub("", re.sub(r"~ARC\d+~", "", gap))
        if run and len(markers) <= 1 and re.fullmatch(r"[\s\-–,;.()]{0,24}", gap_plain):
            if markers and arcs[int(markers[0])][0]:
                arc_into[match.start()] = arcs[int(markers[0])]
            elif along_border:
                border_into.add(match.start())
            run.append((match, point))
        else:
            if run:
                runs.append(run)
            run = [(match, point)]
    if run:
        runs.append(run)

    rings = []
    for run in runs:
        points = [p for _, p in run]
        if half_width_km and len(points) >= 2 and run[0][0].start() > width.start():
            lats, lons = [p[0] for p in points], [p[1] for p in points]
            if max(lats) - min(lats) < 15 and max(lons) - min(lons) < 25:
                rings += corridor_pieces(points, half_width_km)
            continue
        if any(m.start() in arc_into or m.start() in border_into for m, _ in run):
            points = [run[0][1]]
            for match, point in run[1:]:
                if match.start() in arc_into:
                    centre, clockwise = arc_into[match.start()]
                    points += arc_points(points[-1], point, centre, clockwise)
                elif match.start() in border_into:
                    points += border_path(points[-1], point)
                points.append(point)
        if len(points) >= 3:
            if points[0] == points[-1]:
                points = points[:-1]
            for a, b, centre, major in arc_lines:
                points = follow_arc_line(points, a, b, centre, major)
            lats, lons = [p[0] for p in points], [p[1] for p in points]
            # A real area is not continent-sized; anything larger is a misread
            if len(points) >= 3 and max(lats) - min(lats) < 15 and max(lons) - min(lons) < 25:
                rings.append(untangle(points))
        elif len(points) == 1:
            start, end = run[0][0].span()
            nearby = NOTAM_RADIUS.search(text[max(0, start - 90):end + 70])
            if nearby:
                amount = float((nearby.group(1) or nearby.group(3)).replace(",", "."))
                unit = nearby.group(2) or nearby.group(4)
                radius_km = amount * {"NM": 1.852, "KM": 1.0, "M": 0.001}[unit]
                if 0.05 <= radius_km <= 400:
                    rings.append(circle(points[0], radius_km))
    return rings[:12]


def notam_limits(text):
    """Lower and upper limits where the text states them unmistakably, else two empty
    strings. Guessing is worse than saying nothing, so only three plain forms count."""
    explicit = re.search(r"\bF\)\s*(\S[^\n]{0,18}?)\s+G\)\s*(\S[^\n]{0,18})", text)
    if explicit:
        return explicit.group(1).strip(), explicit.group(2).strip()
    patterns = (
        r"\b(SFC|GND)\s?(?:-|–|/|TO|UP TO)\s?(FL\s?\d{2,3}|\d{3,5}\s?(?:FT|M)\s?(?:AMSL|AGL|MSL)|UNL)\b",
        r"\b(FL\s?\d{2,3})\s?(?:-|–|/|TO)\s?(FL\s?\d{2,3}|UNL)\b",
        r"\b(\d{2,5}\s?M\s?AMSL)\s?(?:-|–|/|TO)\s?(\d{2,5}\s?M\s?AMSL)\b",
        r"\b(\d{3,5}\s?FT\s?(?:AMSL|AGL))\s?(?:-|–|/|TO)\s?(\d{3,5}\s?FT\s?(?:AMSL|AGL))\b",
    )
    for pattern in patterns:
        found = re.findall(pattern, text)
        # Several different limits in one NOTAM (one per sub-area) cannot be shown as one
        if found and len(set(found)) == 1:
            return tuple(re.sub(r"\s+", " ", part) for part in found[0])
    return "", ""


def notam_named(text, location):
    """Designators of charted areas the NOTAM names, e.g. LI TSA626 or UR-R525, for the
    country the NOTAM comes from."""
    prefix = re.escape(location[:2])
    found = re.findall(rf"\b{prefix}[\s\-]?((?:TSA|TRA|TS|TR|R|D|P)[\s\-]?\d{{1,4}}[A-Z]?)\b", text)
    return list(dict.fromkeys(location[:2] + plain(code) for code in found))[:6]


def notam_text_entry(number, location, text):
    """Where a NOTAM's text is filed and its scrambled form: (file, locator, data).

    The key is a hash of the NOTAM's number and location; the locator is a hash of the
    key. The text is compressed, then combined with a stream of hashes of the key and a
    counter. index.html (readAirspaceNotam) reverses this.
    """
    key = hashlib.sha256(f"{NOTAM_TEXT_SALT}|{number}|{location}".encode()).digest()
    locator = hashlib.sha256(b"loc|" + key).hexdigest()[:24]
    packed = zlib.compress(text.encode("utf-8"), 9)
    stream = b"".join(hashlib.sha256(key + counter.to_bytes(4, "big")).digest()
                      for counter in range(len(packed) // 32 + 1))
    scrambled = bytes(a ^ b for a, b in zip(packed, stream))
    return locator[:2], locator, base64.b64encode(scrambled).decode()


def write_notam_texts(texts):
    """Files the texts of the NOTAMs on the map, 256 small files by locator."""
    files = {}
    for (number, location), text in texts.items():
        name, locator, data = notam_text_entry(number, location, text)
        files.setdefault(name, {})[locator] = data
    os.makedirs(NOTAM_TEXT_DIR, exist_ok=True)
    for index in range(256):
        name = f"{index:02x}"
        path = os.path.join(NOTAM_TEXT_DIR, name + ".json")
        body = json.dumps(files.get(name, {}), separators=(",", ":"), sort_keys=True)
        if not os.path.exists(path) or open(path).read() != body:
            with open(path, "w") as f:
                f.write(body)


def notam_areas(now):
    with open(NOTAM_EXTRACT_PATH) as f:
        extract = json.load(f)
    as_of = datetime.strptime(extract["bot_data_as_of"][:16], "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)
    if now - as_of > timedelta(hours=NOTAM_MAX_AGE_HOURS):
        raise RuntimeError(f"extract is stale (NOTAM copy as of {iso(as_of)})")

    drawn, named, undrawable = [], {}, 0
    texts = {}  # (number, location) -> text, for every NOTAM that ends up on the map
    for notam in extract.get("notams", []):
        code = notam.get("q", "")
        if len(code) != 5 or code[3:] not in NOTAM_STATES:
            continue
        try:
            start = datetime.strptime(notam["s"], "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)
            end = (now + timedelta(days=3650) if notam["e"].startswith("PERM")
                   else datetime.strptime(notam["e"], "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc))
        except (KeyError, ValueError):
            continue
        if not keep_window(start, end, now):
            continue
        text, location = notam.get("t", ""), notam.get("l", "")
        lower, upper = notam_limits(text)
        area = {"name": f"NOTAM {notam['n']}", "kind": NOTAM_KINDS.get(code[2], "Restricted"),
                "region": WORLD_COUNTRIES.get(location[:2], location[:2]), "source": "NOTAM",
                "state": location, "note": "", "notams": [[notam["n"], location]], "_text": text,
                "windows": [[iso(start), iso(end), lower, upper]]}
        rings = notam_rings(text)
        if rings:
            area["rings"] = [ring(r, 3) for r in rings]  # about 100 m: ample, and keeps the file small
            texts[(notam["n"], location)] = area.pop("_text")
            drawn.append(area)
            continue
        designators = notam_named(text, location)
        if designators:
            for designator in designators:
                named.setdefault(designator, []).append(dict(area, name=designator, note=f"NOTAM {notam['n']}"))
        else:
            undrawable += 1

    shapes = named_shapes(sorted(named), now, WORLD_COUNTRIES) if named else {}
    for designator, entries in named.items():
        if designator not in shapes:
            undrawable += len(entries)
            continue
        merged = dict(entries[0], rings=shapes[designator], windows=[w for e in entries for w in e["windows"]],
                      notams=[e["notams"][0] for e in entries][:5])
        for entry in entries[:5]:
            texts[tuple(entry["notams"][0])] = entry["_text"]
        merged.pop("_text", None)
        drawn.append(merged)

    for area in drawn:
        area.pop("_text", None)
    write_notam_texts(texts)

    STATUS_NOTES["NOTAM"] = {"as_of": iso(as_of), "unplotted": undrawable}
    print(f"NOTAM: {len(drawn)} areas drawn, {undrawable} could not be ({len(shapes)} of {len(named)} named areas found)")
    return drawn


# ── Putting it together ──────────────────────────────────────────────────────

SOURCES = {"FAA": faa_areas, "DFS": dfs_areas, "EAUP": eaup_areas}
if NOTAM_EXTRACT_PATH and os.path.exists(NOTAM_EXTRACT_PATH):
    SOURCES["NOTAM"] = notam_areas
STATUS_NOTES = {}  # extra facts a source wants shown with its status


def merge_windows(windows):
    """Joins windows that touch or overlap and share the same limits."""
    merged = []
    for window in sorted(windows):
        last = merged[-1] if merged else None
        if last and last[2:] == window[2:] and window[0] <= last[1]:
            last[1] = max(last[1], window[1])
        else:
            merged.append(list(window))
    return merged


def main():
    now = datetime.now(timezone.utc)
    previous, previous_status = {}, {}
    if os.path.exists(OUT_PATH):
        try:
            with open(OUT_PATH) as f:
                last_file = json.load(f)
            previous_status = last_file.get("sources", {})
            for area in last_file.get("areas", []):
                previous.setdefault(area.get("origin"), []).append(area)
        except ValueError:
            previous, previous_status = {}, {}

    areas, status = [], {}
    for source, read in SOURCES.items():
        last = previous_status.get(source, {})
        fresh_until = None
        if last.get("ok") and last.get("updated"):
            fresh_until = (datetime.strptime(last["updated"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)
                           + timedelta(minutes=SOURCE_INTERVAL.get(source, 5) - 1))
        if fresh_until and now < fresh_until:
            found = previous.get(source, [])
            status[source] = last
        else:
            try:
                found = read(now)
                status[source] = dict({"ok": True, "updated": iso(now)}, **STATUS_NOTES.get(source, {}))
            except Exception as error:
                print(f"{source}: kept previous areas ({error})")
                found = previous.get(source, [])
                status[source] = {"ok": False}
        for area in found:
            area["origin"] = source
            area["windows"] = merge_windows(w for w in area["windows"] if w[1] > iso(now))
            if area["windows"]:
                areas.append(area)

    # Germany's own plan is the better source for German areas that the European plan also lists
    national = {plain(a["name"]) for a in areas if a["origin"] == "DFS"}
    areas = [a for a in areas if not (a["origin"] == "EAUP" and plain(a["name"]) in national)]
    # Likewise an area named in a NOTAM that a plan already lists
    planned = {plain(a["name"]) for a in areas if a["origin"] in ("DFS", "EAUP")}
    areas = [a for a in areas if not (a["origin"] == "NOTAM" and plain(a["name"]) in planned)]

    areas.sort(key=lambda a: (a["region"], a["name"]))
    with open(OUT_PATH, "w") as f:
        json.dump({"generated": iso(now), "sources": status, "areas": areas}, f, separators=(",", ":"))
    print(f"wrote {len(areas)} areas")


if __name__ == "__main__":
    main()

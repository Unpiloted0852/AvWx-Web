"""Adds the surface wind map layer: colours for wind speed and moving streaks for direction,
estimated from current METARs. Works on any copy of the page."""
import re, sys
path = sys.argv[1]
page = open(path, encoding='utf-8').read()
if 'L.SurfaceWindLayer' in page: sys.exit('already applied')
def sub(old, new):
    # Indentation is ignored, as the Android app's copy of the page is laid out differently
    global page
    parts = [re.escape(l.strip()) for l in old.rstrip('\n').split('\n')]
    pattern = r'[ \t]*\r?\n[ \t]*'.join(parts)
    if old[0] in ' \t': pattern = r'[ \t]*' + pattern
    if old.endswith('\n'): pattern += r'[ \t]*\r?\n'
    found = list(re.finditer(pattern, page))
    if len(found) != 1: sys.exit(f'{len(found)} matches for {old[:70]!r}')
    page = page[:found[0].start()] + new + page[found[0].end():]
def before(anchor, new): sub(anchor, new + anchor)
def after(anchor, new): sub(anchor, anchor + new)

# --- Styles ---
before("  /* ── WAFS grids: turbulence, icing and wind by altitude ── */\n", """  /* ── Surface wind estimated from METARs ── */
  html .layer-btn.wind-active { background-color: #0f766e !important; border-color: #115e59 !important; color: #fff !important; box-shadow: 0 2px 10px rgba(15,118,110,.4) !important; }
  #windBar {
    position: absolute; bottom: 2rem; left: 50%; transform: translateX(-50%);
    z-index: 1000; display: none; flex-direction: column; align-items: stretch; gap: 4px;
    width: min(340px, calc(100% - 5.5rem)); padding: 7px 10px;
    background: rgba(255,255,255,.92); border: 1px solid rgba(0,0,0,.08);
    border-radius: 10px; -webkit-backdrop-filter: blur(8px); backdrop-filter: blur(8px); color: #1f2937;
    font: 600 0.7rem 'Public Sans', sans-serif;
  }
  html.dark #windBar { background: rgba(15,25,41,.92); border-color: rgba(255,255,255,.08); color: #e5e7eb; }
  #windBar .wind-row { display: flex; gap: 6px; }
  #windBar button {
    flex: 1; min-height: 30px; border-radius: 7px; border: 1px solid rgba(127,127,127,.35);
    background: transparent; color: inherit; font: inherit; cursor: pointer;
  }
  #windBar button.wind-on { background: #0f766e; border-color: #115e59; color: #fff; }
  #windLegendTitle { text-align: center; font-size: 0.62rem; }
  #windLegendBar { height: 10px; border-radius: 3px; border: 1px solid rgba(127,127,127,.5); }
  #windLegendTicks { position: relative; height: 13px; font: 600 0.56rem 'IBM Plex Mono', monospace; opacity: .85; }
  #windLegendTicks span { position: absolute; transform: translateX(-50%); white-space: nowrap; }
  #windLegendTicks span:first-child { transform: none; }
  #windLegendTicks span:last-child { transform: translateX(-100%); }
  #windBar small { text-align: center; font-size: 0.6rem; font-weight: 500; opacity: .75; }
""")

# --- Legend bar ---
before("                <!-- Unified Map Warning (Tiny Bottom Right) -->\n", """                <!-- Surface wind: what the colours show, and how far to trust them -->
                <div id="windBar">
                    <div class="wind-row">
                        <button id="windShow-speed" onclick="setWindShow('speed')">Steady wind</button>
                        <button id="windShow-peak" onclick="setWindShow('peak')">With gusts</button>
                    </div>
                    <b id="windLegendTitle"></b>
                    <div id="windLegendBar"></div>
                    <div id="windLegendTicks"></div>
                    <small id="windNote">Estimate from airport reports, not a forecast model.</small>
                </div>

""")

# --- Layer button ---
before("""        <button id="dayNightBtn" onclick="toggleDayNight()\"""", """        <button id="windBtn" onclick="toggleWind()" class="layer-btn bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center justify-center">
            <span class="font-black tracking-tighter leading-none" style="font-size:0.6rem">SFC<br>WIND</span>
        </button>

""")

# --- Layer state, remembered between visits (off unless switched on) ---
after("    const hasWafs = !!wafsLayer;\n", "    const hasWind = !!windLayer;\n")
sub("hasSigwx || hasWafs || hasPirep", "hasSigwx || hasWafs || hasWind || hasPirep")
after("        wafs: !!wafsLayer,\n", "        wind: !!windLayer,\n")
after("            wafs: false,\n", "            wind: false,\n")
after("""    const fieldMapOn = fieldMapLayer ? fieldMapLayer.mode : null;
    if (wantFieldMap !== fieldMapOn) toggleFieldMap(wantFieldMap || fieldMapOn);
""", """
    // Apply Surface Wind
    if (!!settings.wind !== !!windLayer) toggleWind();
""")
sub("if (hasFreezing || hasHeatmap || fieldMapLayer) {", "if (hasFreezing || hasHeatmap || fieldMapLayer || windLayer) {")

# --- Only one whole-map colouring at a time ---
after("            if (flightCatLayer) toggleFlightCat();\n", "            if (windLayer) toggleWind();\n")
after("        if (fieldMapLayer) toggleFieldMap(fieldMapLayer.mode);\n", "        if (windLayer) toggleWind();\n")

# --- Each station's number replaces its dot while it is on, as with the temperature map ---
sub("if (!fieldMapLayer) markerLayerGroup.addLayer(visualMarker);", "if (!fieldMapLayer && !windLayer) markerLayerGroup.addLayer(visualMarker);")
after("""        document.getElementById('stationsBtn').classList.toggle('runway-active', showStationsOnMap);\n""",
      "        if (windLayer) windLayer._drawNumbers();\n")

# --- Gusts from the station data ---
after("""            const windSpeed = parseInt(node.querySelector("wind_speed_kt")?.textContent);\n""",
      """            const windGust = parseInt(node.querySelector("wind_gust_kt")?.textContent);\n""")
after("                windSpeed: isNaN(windSpeed) ? null : windSpeed,\n", "                windGust: isNaN(windGust) ? null : windGust,\n")

# --- The layer ---
before("    // --- Taps where several areas overlap ---\n", r"""    // --- SURFACE WIND ---
    // An estimate from airport reports, not a forecast model. The reports are spread onto a
    // world grid, nearer airports counting for more. Away from airports the layer fades out
    // and stops altogether, so nothing is shown over open ocean or other empty areas.
    // Variable winds add their speed to the colour but no direction; calm reports add zero to
    // both. Where reports disagree, the averaged direction weakens and the streaks slow down.
    const WIND_CELLS_PER_DEG = 2;
    const WIND_MAX_LAT = 85;
    const WIND_W = 360 * WIND_CELLS_PER_DEG;      // columns wrap around at the antimeridian
    const WIND_H = 2 * WIND_MAX_LAT * WIND_CELLS_PER_DEG + 1;
    const WIND_KM_PER_DEG = 111.2;
    const WIND_REACH_KM = 300;      // nothing is shown further than this from a report
    const WIND_SOLID_KM = 100;      // the fade starts this far from the nearest report
    const WIND_SOFTEN_KM = 30;      // stops the nearest airport from swamping its neighbours
    const WIND_MAX_AGE_MIN = 180;   // older reports are not current
    const WIND_MAX_KT = 150;        // anything above this is treated as a bad report
    const WIND_FIELD_STEP = 8;      // screen pixels per colour sample
    const WIND_FRAME_MS = 33;       // about 30 streak updates a second
    const WIND_PX_PER_KT = 5;       // streak speed in screen pixels a second, at any zoom
    const WIND_STOPS = [            // kt, red, green, blue
        [0, 58, 76, 122], [5, 44, 128, 160], [10, 46, 164, 120], [15, 132, 186, 76], [20, 226, 196, 62],
        [25, 236, 146, 50], [30, 222, 88, 58], [40, 186, 44, 96], [55, 128, 44, 148], [70, 74, 28, 112]
    ];
    const WIND_TICKS = [0, 10, 20, 30, 40, 55, 70];
    const WIND_RGB = (function() {  // colour for every quarter knot
        const table = new Uint8Array((70 * 4 + 1) * 3);
        for (let i = 0, s = 0; i <= 70 * 4; i++) {
            const kt = i / 4;
            while (s < WIND_STOPS.length - 2 && kt > WIND_STOPS[s + 1][0]) s++;
            const a = WIND_STOPS[s], b = WIND_STOPS[s + 1], t = (kt - a[0]) / (b[0] - a[0]);
            for (let c = 0; c < 3; c++) table[i * 3 + c] = a[c + 1] + (b[c + 1] - a[c + 1]) * t;
        }
        return table;
    })();

    let windLayer = null;
    let windShow = 'speed';     // 'speed' or 'peak', what the colours show
    try { if (localStorage.getItem('windShow') === 'peak') windShow = 'peak'; } catch (e) {}

    // A report's wind if it is current and believable
    function usableWind(m) {
        return !!m && m.windSpeed != null && m.windSpeed <= WIND_MAX_KT && !(m.age != null && m.age > WIND_MAX_AGE_MIN);
    }

    function buildWindGrid(stations) {
        const size = WIND_W * WIND_H;
        const grid = { east: new Float32Array(size), north: new Float32Array(size), speed: new Float32Array(size),
            peak: new Float32Array(size), cover: new Float32Array(size), used: 0 };
        const weights = new Float32Array(size);
        const reachDeg = WIND_REACH_KM / WIND_KM_PER_DEG;
        const reach2 = WIND_REACH_KM * WIND_REACH_KM, soft2 = WIND_SOFTEN_KM * WIND_SOFTEN_KM;

        for (const s of stations) {
            const m = s.metar;
            if (!usableWind(m) || s.latitude == null || s.longitude == null) continue;
            grid.used++;
            // Winds are reported as where they blow from; these are where they blow to
            const from = (m.windDir == null ? 0 : m.windDir) * Math.PI / 180;
            const blowing = m.windDir == null ? 0 : m.windSpeed;
            const east = -Math.sin(from) * blowing, north = -Math.cos(from) * blowing;
            const peak = Math.max(m.windSpeed, m.windGust || 0);

            const firstRow = Math.max(0, Math.ceil((WIND_MAX_LAT - s.latitude - reachDeg) * WIND_CELLS_PER_DEG));
            const lastRow = Math.min(WIND_H - 1, Math.floor((WIND_MAX_LAT - s.latitude + reachDeg) * WIND_CELLS_PER_DEG));
            for (let row = firstRow; row <= lastRow; row++) {
                const lat = WIND_MAX_LAT - row / WIND_CELLS_PER_DEG;
                const dy = (lat - s.latitude) * WIND_KM_PER_DEG;
                const width2 = reach2 - dy * dy;
                if (width2 <= 0) continue;
                const kmPerDegLng = WIND_KM_PER_DEG * Math.max(0.02, Math.cos(lat * Math.PI / 180));
                const span = Math.min(Math.ceil(Math.sqrt(width2) / kmPerDegLng * WIND_CELLS_PER_DEG), WIND_W / 2 - 1);
                const centre = Math.round((s.longitude + 180) * WIND_CELLS_PER_DEG);
                for (let col = centre - span; col <= centre + span; col++) {
                    const dx = (col / WIND_CELLS_PER_DEG - 180 - s.longitude) * kmPerDegLng;
                    const d2 = dx * dx + dy * dy;
                    if (d2 >= reach2) continue;
                    const d = Math.sqrt(d2);
                    const i = row * WIND_W + ((col % WIND_W) + WIND_W) % WIND_W;
                    const edge = 1 - d / WIND_REACH_KM;
                    const w = edge * edge / (d2 + soft2);
                    weights[i] += w;
                    grid.east[i] += w * east;
                    grid.north[i] += w * north;
                    grid.speed[i] += w * m.windSpeed;
                    grid.peak[i] += w * peak;
                    const fade = Math.min(1, (WIND_REACH_KM - d) / (WIND_REACH_KM - WIND_SOLID_KM));
                    const cover = fade * fade * (3 - 2 * fade);
                    if (cover > grid.cover[i]) grid.cover[i] = cover;
                }
            }
        }
        for (let i = 0; i < size; i++) {
            const w = weights[i];
            if (!w) continue;
            grid.east[i] /= w; grid.north[i] /= w; grid.speed[i] /= w; grid.peak[i] /= w;
        }
        return grid;
    }

    // The wind at a spot, from the four grid cells around it. Cells with no reports nearby are
    // left out of the blend, so the colours do not slide towards calm at the edge of the data.
    // Fills in and returns "out"; out.cover is 0 where there is nothing to show.
    function sampleWind(grid, lat, lng, out) {
        out.cover = 0;
        if (lat > WIND_MAX_LAT || lat < -WIND_MAX_LAT) return out;
        const fy = (WIND_MAX_LAT - lat) * WIND_CELLS_PER_DEG;
        const fx = (lng + 180) * WIND_CELLS_PER_DEG;
        const row = Math.min(Math.floor(fy), WIND_H - 2), col = Math.floor(fx);
        const ty = fy - row, tx = fx - col;
        const left = ((col % WIND_W) + WIND_W) % WIND_W, right = left + 1 === WIND_W ? 0 : left + 1;
        const a = row * WIND_W + left, b = row * WIND_W + right, c = a + WIND_W, d = b + WIND_W;
        const wa = (1 - tx) * (1 - ty), wb = tx * (1 - ty), wc = (1 - tx) * ty, wd = tx * ty;
        const cover = grid.cover;
        out.cover = cover[a] * wa + cover[b] * wb + cover[c] * wc + cover[d] * wd;
        if (out.cover <= 0) return out;
        const ua = cover[a] ? wa : 0, ub = cover[b] ? wb : 0, uc = cover[c] ? wc : 0, ud = cover[d] ? wd : 0;
        const total = ua + ub + uc + ud;
        const blend = v => (v[a] * ua + v[b] * ub + v[c] * uc + v[d] * ud) / total;
        out.east = blend(grid.east); out.north = blend(grid.north);
        out.speed = blend(grid.speed); out.peak = blend(grid.peak);
        return out;
    }

    if (typeof L.SurfaceWindLayer === 'undefined') {
        L.SurfaceWindLayer = L.Layer.extend({
            onAdd: function(map) {
                this._map = map;
                // The colours lie under the radar and the streaks above it; taps pass through both
                const addPane = (name, zIndex) => {
                    const pane = map.getPane(name) || map.createPane(name);
                    pane.style.zIndex = zIndex;
                    pane.style.pointerEvents = 'none';
                    return pane;
                };
                this._field = L.DomUtil.create('canvas', '', addPane('windFieldPane', 235));
                this._streaks = L.DomUtil.create('canvas', '', addPane('windStreakPane', 260));
                this._numbers = L.DomUtil.create('canvas', '', addPane('windNumberPane', 270));
                this._numbers.style.cssText = 'position:absolute;top:0;left:0;pointer-events:none';
                this._samples = document.createElement('canvas');
                this._field.style.cssText = this._streaks.style.cssText = 'position:absolute;top:0;left:0;pointer-events:none';
                this._ratio = Math.min(window.devicePixelRatio || 1, 1.5);
                this._reduceMotion = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
                this._particles = [];
                this._particleLimit = Infinity;
                this._at = {};
                this._stopFollowingZoom = followMapZoom(this, map, [this._field, this._numbers]);
                map.on('zoomstart', this._zoomStarted, this);
                map.on('zoomend', this._zoomEnded, this);
                map.on('move', this._moved, this);
                map.on('moveend', this._moveEnded, this);
                map.on('resize', this._resized, this);
                this._resized();
                this._frame = requestAnimationFrame(t => this._tick(t));
            },

            onRemove: function(map) {
                cancelAnimationFrame(this._frame);
                this._frame = null;
                this._stopFollowingZoom();
                map.off('zoomstart', this._zoomStarted, this);
                map.off('zoomend', this._zoomEnded, this);
                map.off('move', this._moved, this);
                map.off('moveend', this._moveEnded, this);
                map.off('resize', this._resized, this);
                this._field.remove();
                this._streaks.remove();
                this._numbers.remove();
                this._grid = this._samples = this._particles = null;
            },

            // Called whenever the view is settled at a new size or zoom
            _resized: function() {
                const size = this._map.getSize();
                this._size = size;
                this._field.width = size.x;
                this._field.height = size.y;
                this._streaks.width = Math.round(size.x * this._ratio);
                this._streaks.height = Math.round(size.y * this._ratio);
                this._numbers.width = this._streaks.width;
                this._numbers.height = this._streaks.height;
                this._numbers.style.width = size.x + 'px';
                this._numbers.style.height = size.y + 'px';
                this._field.style.width = this._streaks.style.width = size.x + 'px';
                this._field.style.height = this._streaks.style.height = size.y + 'px';
                this._restart();
            },

            _zoomStarted: function() {
                this._zooming = true;
                this._clearStreaks();
            },

            _zoomEnded: function() {
                this._zooming = false;
                this._restart();
            },

            // Follows a drag: the canvases stay over the view, with the new part of the map coloured in
            _moved: function() {
                if (this._zooming || !this._grid || !this._origin) return;
                const was = this._origin;
                this._readView();
                const dx = was.x - this._origin.x, dy = was.y - this._origin.y;
                this._place();
                this._drawField();
                const particles = this._particles;
                for (let i = 0; i < particles.length; i++) { particles[i].x += dx; particles[i].y += dy; }
                const ctx = this._streaks.getContext('2d');
                ctx.save();
                ctx.globalCompositeOperation = 'copy';
                ctx.setTransform(1, 0, 0, 1, 0, 0);
                ctx.drawImage(this._streaks, dx * this._ratio, dy * this._ratio);
                ctx.restore();
            },

            _moveEnded: function() {
                if (this._zooming) return;
                this._moved();
                this._drawNumbers();
            },

            _readView: function() {
                const map = this._map;
                this._origin = map.containerPointToLayerPoint([0, 0]).add(map.getPixelOrigin());
                this._worldPx = map.options.crs.scale(map.getZoom());
            },

            _place: function() {
                const topLeft = this._map.containerPointToLayerPoint([0, 0]);
                L.DomUtil.setPosition(this._field, topLeft);
                L.DomUtil.setPosition(this._streaks, topLeft);
                markDrawnView(this, this._map);
            },

            _restart: function() {
                if (this._zooming || !this._size.x || !this._size.y) return;
                this._refreshGrid();
                this._readView();
                this._place();
                this._drawField();
                this._drawNumbers();
                this._clearStreaks();
                this._seed();
            },

            // Rebuilds the grid when new reports have arrived
            _refreshGrid: function() {
                if (this._gridFrom === allStationsData) return false;
                this._gridFrom = allStationsData;
                this._grid = buildWindGrid(allStationsData);
                updateWindBar();
                return true;
            },

            // Screen position to map position, using the same maths as the map's own projection
            _latAt: function(y) {
                return (2 * Math.atan(Math.exp(Math.PI * (1 - 2 * (this._origin.y + y) / this._worldPx))) - Math.PI / 2) * 180 / Math.PI;
            },
            _lngAt: function(x) {
                return (this._origin.x + x) / this._worldPx * 360 - 180;
            },

            _drawField: function() {
                const grid = this._grid, size = this._size;
                const ctx = this._field.getContext('2d');
                ctx.clearRect(0, 0, size.x, size.y);
                if (!grid || !grid.used) return;
                const cols = Math.ceil(size.x / WIND_FIELD_STEP) + 1, rows = Math.ceil(size.y / WIND_FIELD_STEP) + 1;
                const samples = this._samples;
                if (samples.width !== cols || samples.height !== rows) {
                    samples.width = cols;
                    samples.height = rows;
                    this._sampleImage = samples.getContext('2d').createImageData(cols, rows);
                }
                const data = this._sampleImage.data, at = this._at;
                const strength = (document.documentElement.classList.contains('dark') ? 0.55 : 0.62) * 255;
                const useSpeed = windShow !== 'peak';
                for (let r = 0, p = 0; r < rows; r++) {
                    const lat = this._latAt((r + 0.5) * WIND_FIELD_STEP);
                    for (let c = 0; c < cols; c++, p += 4) {
                        sampleWind(grid, lat, this._lngAt((c + 0.5) * WIND_FIELD_STEP), at);
                        if (at.cover <= 0) { data[p + 3] = 0; continue; }
                        const kt = useSpeed ? at.speed : at.peak;
                        const i = Math.min(70 * 4, Math.round(kt * 4)) * 3;
                        data[p] = WIND_RGB[i]; data[p + 1] = WIND_RGB[i + 1]; data[p + 2] = WIND_RGB[i + 2];
                        data[p + 3] = at.cover * strength;
                    }
                }
                samples.getContext('2d').putImageData(this._sampleImage, 0, 0);
                ctx.imageSmoothingEnabled = true;
                ctx.drawImage(samples, 0, 0, cols * WIND_FIELD_STEP, rows * WIND_FIELD_STEP);
            },

            // The wind reported at each station, in place of its dot. They ride along with the
            // map during a drag and are redrawn when it stops.
            _drawNumbers: function() {
                const map = this._map, size = this._size;
                L.DomUtil.setPosition(this._numbers, map.containerPointToLayerPoint([0, 0]));
                const ctx = this._numbers.getContext('2d');
                ctx.setTransform(this._ratio, 0, 0, this._ratio, 0, 0);
                ctx.clearRect(0, 0, size.x, size.y);
                if (!showStationsOnMap) return;
                ctx.font = 'bold 13px sans-serif';
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.lineJoin = 'round';
                ctx.lineWidth = 3.5;
                ctx.strokeStyle = 'rgba(255,255,255,0.95)';
                ctx.fillStyle = '#000';
                const read = m => !usableWind(m) ? null : windShow === 'peak' ? Math.max(m.windSpeed, m.windGust || 0) : m.windSpeed;
                // Numbers that would overlap one already drawn are left out until the map is zoomed in
                const CELL_W = 34, CELL_H = 18;
                const taken = new Set();
                collectFieldPoints(map, read, Math.round).points.forEach(p => {
                    if (p.x < 0 || p.y < 0 || p.x > size.x || p.y > size.y) return;
                    const cx = Math.round(p.x / (CELL_W / 2)), cy = Math.round(p.y / (CELL_H / 2));
                    for (let i = -1; i <= 1; i++) {
                        for (let j = -1; j <= 1; j++) {
                            if (taken.has((cx + i) + ':' + (cy + j))) return;
                        }
                    }
                    taken.add(cx + ':' + cy);
                    ctx.strokeText(p.label, p.x, p.y);
                    ctx.fillText(p.label, p.x, p.y);
                });
            },

            _clearStreaks: function() {
                this._streaks.getContext('2d').clearRect(0, 0, this._streaks.width, this._streaks.height);
            },

            _seed: function() {
                const area = this._size.x * this._size.y;
                const count = Math.min(this._particleLimit, Math.max(120, Math.min(1600, Math.round(area / 900))));
                this._particles = [];
                for (let i = 0; i < count; i++) {
                    const p = { x: 0, y: 0, life: 0 };
                    this._respawn(p);
                    this._particles.push(p);
                }
                // With reduced motion asked for, show still streaks instead of moving ones
                if (this._reduceMotion) for (let i = 0; i < 25; i++) this._step(WIND_FRAME_MS / 1000);
            },

            _respawn: function(p) {
                p.x = Math.random() * this._size.x;
                p.y = Math.random() * this._size.y;
                p.life = 1.5 + Math.random() * 3;
            },

            // Moves every streak one step and draws what it covered
            _step: function(seconds) {
                const grid = this._grid, size = this._size, at = this._at, particles = this._particles;
                if (!grid) return;
                const ctx = this._streaks.getContext('2d');
                const dark = document.documentElement.classList.contains('dark');
                ctx.setTransform(this._ratio, 0, 0, this._ratio, 0, 0);
                // Older parts of the trails fade away
                ctx.globalCompositeOperation = 'destination-in';
                ctx.fillStyle = 'rgba(0,0,0,0.94)';
                ctx.fillRect(0, 0, size.x, size.y);
                ctx.globalCompositeOperation = 'source-over';
                ctx.strokeStyle = dark ? 'rgba(255,255,255,0.8)' : 'rgba(255,255,255,0.92)';
                ctx.lineWidth = 1.2;
                ctx.beginPath();
                for (let i = 0; i < particles.length; i++) {
                    const p = particles[i];
                    p.life -= seconds;
                    if (p.life <= 0 || p.x < 0 || p.y < 0 || p.x > size.x || p.y > size.y) { this._respawn(p); continue; }
                    sampleWind(grid, this._latAt(p.y), this._lngAt(p.x), at);
                    // No streaks at the faded edge, or where the wind is calm or has no direction
                    if (at.cover < 0.25 || at.east * at.east + at.north * at.north < 0.25) { this._respawn(p); continue; }
                    const nx = p.x + at.east * WIND_PX_PER_KT * seconds;
                    const ny = p.y - at.north * WIND_PX_PER_KT * seconds;
                    ctx.moveTo(p.x, p.y);
                    ctx.lineTo(nx, ny);
                    p.x = nx;
                    p.y = ny;
                }
                ctx.stroke();
            },

            _tick: function(now) {
                this._frame = requestAnimationFrame(t => this._tick(t));
                const elapsed = now - (this._lastStep || 0);
                if (elapsed < WIND_FRAME_MS - 4) return;
                this._lastStep = now;
                // Nothing to do while zooming, or while another tab of the page is showing
                if (this._zooming || !this._map._container.offsetWidth || !this._grid) {
                    if (!this._zooming && !this._grid && allStationsData.length) this._restart();
                    return;
                }
                if (this._refreshGrid()) { this._restart(); return; }
                if (this._reduceMotion) return;
                this._step(WIND_FRAME_MS / 1000);
                // On a device that cannot keep up, use fewer streaks rather than stutter
                if (elapsed < 500) {
                    this._slowness = (this._slowness || WIND_FRAME_MS) * 0.95 + elapsed * 0.05;
                    if (this._slowness > 55 && this._particles.length > 120) {
                        this._particleLimit = Math.max(120, Math.round(this._particles.length * 0.8));
                        this._particles.length = this._particleLimit;
                        this._slowness = WIND_FRAME_MS;
                    }
                }
            }
        });
    }

    function updateWindBar() {
        const note = windLayer && windLayer._grid ? windLayer._grid.used : 0;
        ['speed', 'peak'].forEach(show => document.getElementById('windShow-' + show).classList.toggle('wind-on', show === windShow));
        document.getElementById('windLegendTitle').textContent = windShow === 'peak' ? 'Surface wind including gusts (kt)' : 'Surface wind speed (kt)';
        const top = WIND_STOPS[WIND_STOPS.length - 1][0];
        document.getElementById('windLegendBar').style.background = 'linear-gradient(to right, ' +
            WIND_STOPS.map(s => `rgb(${s[1]},${s[2]},${s[3]}) ${(s[0] / top * 100).toFixed(1)}%`).join(', ') + ')';
        document.getElementById('windLegendTicks').innerHTML = WIND_TICKS.map(kt =>
            `<span style="left:${(kt / top * 100).toFixed(1)}%">${kt}</span>`).join('');
        document.getElementById('windNote').textContent = 'Estimate from ' + (note ? note.toLocaleString() + ' ' : '') +
            'airport reports, not a forecast model. Blank areas have no reports nearby.';
    }

    function setWindShow(show) {
        windShow = show;
        try { localStorage.setItem('windShow', show); } catch (e) {}
        updateWindBar();
        if (windLayer) { windLayer._drawField(); windLayer._drawNumbers(); }
    }

    // Sits above whichever other bars at the bottom of the map are showing
    function positionWindBar() {
        const bar = document.getElementById('windBar');
        if (!bar || bar.style.display === 'none' || !bar.style.display) return;
        const map = document.getElementById('weatherMap').getBoundingClientRect();
        let lift = 32;
        ['sigwxBar', 'wafsBar', 'heatmapLegend'].forEach(id => {
            const other = document.getElementById(id);
            if (!other || getComputedStyle(other).display === 'none') return;
            lift = Math.max(lift, map.bottom - other.getBoundingClientRect().top + 8);
        });
        bar.style.bottom = lift + 'px';
    }
    (function() {
        ['sigwxBar', 'wafsBar', 'heatmapLegend'].forEach(id => {
            const other = document.getElementById(id);
            if (other) new MutationObserver(positionWindBar).observe(other, { attributes: true, attributeFilter: ['style', 'class'] });
        });
    })();

    function toggleWind() {
        const btn = document.getElementById('windBtn');
        const bar = document.getElementById('windBar');
        if (!mapInstance) return;
        if (windLayer) {
            mapInstance.removeLayer(windLayer);
            windLayer = null;
            btn.classList.remove('wind-active');
            bar.style.display = 'none';
        } else {
            // Only one whole-map colouring at a time
            if (fieldMapLayer) toggleFieldMap(fieldMapLayer.mode);
            if (flightCatLayer) toggleFlightCat();
            windLayer = new L.SurfaceWindLayer();
            mapInstance.addLayer(windLayer);
            btn.classList.add('wind-active');
            bar.style.display = 'flex';
            updateWindBar();
            positionWindBar();
        }
        // Station dots are left out while this is on, so redraw the markers
        if (currentStationsData.length > 0) renderMap(currentStationsData);
        updateLayerActiveState();
    }

""")
open(path, 'w', encoding='utf-8').write(page)

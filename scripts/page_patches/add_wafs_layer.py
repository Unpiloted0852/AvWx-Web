"""Adds the WAFS grids layer (turbulence, icing, wind by altitude). Works on either copy of the page."""
import sys
path = sys.argv[1]
lines = open(path, encoding='utf-8').read().split('\n')
if any('toggleWafs' in l for l in lines): sys.exit('already applied')
def find(t, start=0, startswith=False):
    hits = [i for i, l in enumerate(lines) if i >= start and (l.strip().startswith(t) if startswith else l.strip() == t)]
    if not hits or (len(hits) != 1 and not start): sys.exit(f'{len(hits)} matches for {t!r}')
    return hits[0]

CSS = '''  /* ── WAFS grids: turbulence, icing and wind by altitude ── */
  html .layer-btn.wafs-active { background-color: #4f46e5 !important; border-color: #4338ca !important; color: #fff !important; box-shadow: 0 2px 10px rgba(79,70,229,.4) !important; }
  #wafsBar {
    position: absolute; bottom: 2rem; left: 50%; transform: translateX(-50%);
    z-index: 1000; display: none; flex-direction: column; align-items: stretch; gap: 5px;
    width: min(340px, calc(100% - 5.5rem)); padding: 7px 10px;
    background: rgba(255,255,255,.92); border: 1px solid rgba(0,0,0,.08);
    border-radius: 10px; backdrop-filter: blur(8px); color: #1f2937;
    font: 600 0.7rem 'Public Sans', sans-serif;
  }
  html.dark #wafsBar { background: rgba(15,25,41,.92); border-color: rgba(255,255,255,.08); color: #e5e7eb; }
  #wafsBar .wafs-row { display: flex; align-items: center; gap: 6px; }
  #wafsBar button {
    flex: 1; height: 30px; border-radius: 6px; cursor: pointer; font: 700 0.72rem 'Public Sans', sans-serif;
    background: rgba(127,127,127,.18); border: 1px solid rgba(127,127,127,.3); color: inherit;
  }
  #wafsBar button.wafs-step { flex: none; width: 38px; font-size: 0.85rem; }
  #wafsBar button.wafs-on { background: #4f46e5; border-color: #4338ca; color: #fff; }
  #wafsBar button:disabled { opacity: .35; cursor: default; }
  #wafsBar .wafs-value { flex: 1; text-align: center; font: 700 0.74rem 'IBM Plex Mono', monospace; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  #wafsBar small { text-align: center; font-size: 0.6rem; font-weight: 500; opacity: .7; }'''.split('\n')

BUTTON = '''
        <button id="wafsBtn" onclick="toggleWafs()" class="layer-btn bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center justify-center">
            <span class="font-black tracking-tighter leading-none" style="font-size:0.6rem">WAFS</span>
        </button>'''.split('\n')

BAR = '''
                <!-- WAFS grids: what to show, at which altitude, for which time -->
                <div id="wafsBar">
                    <div class="wafs-row">
                        <button id="wafsKind-edr" onclick="setWafs({ kind: 'edr' })">Turbulence</button>
                        <button id="wafsKind-icsev" onclick="setWafs({ kind: 'icsev' })">Icing</button>
                        <button id="wafsKind-wind" onclick="setWafs({ kind: 'wind' })">Wind</button>
                    </div>
                    <div class="wafs-row">
                        <button id="wafsLower" class="wafs-step" onclick="stepWafs('level', -1)" aria-label="Lower altitude">▼</button>
                        <div id="wafsLevel" class="wafs-value">FL300</div>
                        <button id="wafsHigher" class="wafs-step" onclick="stepWafs('level', 1)" aria-label="Higher altitude">▲</button>
                    </div>
                    <div class="wafs-row">
                        <button id="wafsEarlier" class="wafs-step" onclick="stepWafs('time', -1)" aria-label="Earlier forecast time">◀</button>
                        <div id="wafsTime" class="wafs-value">loading…</div>
                        <button id="wafsLater" class="wafs-step" onclick="stepWafs('time', 1)" aria-label="Later forecast time">▶</button>
                    </div>
                    <small>WAFS forecast picture from aviationweather.gov. For planning only.</small>
                </div>'''.split('\n')

JS = '''
    // --- WAFS grids: turbulence, icing and wind at a chosen altitude ---
    // aviationweather.gov publishes the World Area Forecast System's gridded forecasts as
    // ready-made pictures of the world, one per altitude and forecast time. The picture for
    // the chosen kind, altitude and time is laid over the map. The forecast run and its
    // times are read from the SIG WX file, which comes from the same run.
    const WAFS_PICTURES = 'https://aviationweather.gov/data/products/wafs';
    const WAFS_BOUNDS = [[-75.940536, -179.983902], [75.940536, 179.983902]];
    // Flight level and the pressure (mb) its pictures are filed under
    const WAFS_LEVELS = {
        edr: [[100, 697], [140, 595], [180, 506], [240, 393], [270, 344], [300, 301], [340, 250], [390, 197], [450, 148]],
        icsev: [[60, 812], [100, 697], [140, 595], [180, 506], [240, 393], [300, 301]],
        wind: [[100, 697], [140, 595], [180, 506], [240, 393], [270, 344], [300, 301], [340, 250], [390, 197], [450, 148]]
    };
    const WAFS_NAMES = { edr: 'Turbulence', icsev: 'Icing', wind: 'Wind speed' };
    let wafsLayer = null;
    let wafsRun = null;             // { run, times } from the SIG WX file
    let wafsChoice = { kind: 'edr', level: 300, valid: null };   // valid null follows the clock
    let wafsRefreshInterval = null;
    try { Object.assign(wafsChoice, JSON.parse(localStorage.getItem('wafsChoice')) || {}, { valid: null }); } catch (e) {}

    function wafsTimes() {
        if (!wafsRun || !Array.isArray(wafsRun.times)) return [];
        const now = _nowAccurate();
        const all = wafsRun.times.map(t => sigwxTime(t.valid));
        const current = all.filter(t => t > now - 3 * 3600000);
        return current.length ? current : all;
    }

    function drawWafs() {
        if (!wafsLayer) return;
        const levels = WAFS_LEVELS[wafsChoice.kind] || WAFS_LEVELS.edr;
        // The nearest altitude this kind of forecast has to the one last chosen
        const level = levels.reduce((best, l) => Math.abs(l[0] - wafsChoice.level) < Math.abs(best[0] - wafsChoice.level) ? l : best);
        const at = levels.indexOf(level);
        ['edr', 'icsev', 'wind'].forEach(kind => document.getElementById('wafsKind-' + kind).classList.toggle('wafs-on', kind === wafsChoice.kind));
        document.getElementById('wafsLevel').textContent = `FL${String(level[0]).padStart(3, '0')} · ${at + 1} of ${levels.length}`;
        document.getElementById('wafsLower').disabled = at === 0;
        document.getElementById('wafsHigher').disabled = at === levels.length - 1;

        const times = wafsTimes();
        const label = document.getElementById('wafsTime');
        if (times.length === 0) {
            label.textContent = wafsRun ? 'Not available right now' : 'loading…';
            document.getElementById('wafsEarlier').disabled = document.getElementById('wafsLater').disabled = true;
            return;
        }
        const now = _nowAccurate();
        let index = times.indexOf(wafsChoice.valid);
        if (index < 0) {
            wafsChoice.valid = null;
            index = times.reduce((best, t, i) => Math.abs(t - now) < Math.abs(times[best] - now) ? i : best, 0);
        }
        const valid = times[index], d = new Date(valid);
        const hours = Math.round((valid - now) / 3600000);
        label.textContent = `${['Sun','Mon','Tue','Wed','Thu','Fri','Sat'][d.getUTCDay()]} ${String(d.getUTCDate()).padStart(2, '0')}/${String(d.getUTCHours()).padStart(2, '0')}Z · ${hours === 0 ? 'now' : (hours > 0 ? `in ${hours} h` : `${-hours} h ago`)}`;
        document.getElementById('wafsEarlier').disabled = index === 0;
        document.getElementById('wafsLater').disabled = index === times.length - 1;

        const run = new Date(sigwxTime(wafsRun.run));
        const day = `${run.getUTCFullYear()}${String(run.getUTCMonth() + 1).padStart(2, '0')}${String(run.getUTCDate()).padStart(2, '0')}`;
        const hour = String(run.getUTCHours()).padStart(2, '0');
        const ahead = String(Math.round((valid - run.getTime()) / 3600000)).padStart(2, '0');
        const url = `${WAFS_PICTURES}/${day}/${hour}/${day}_${hour}_F${ahead}_wafs_${level[1]}_${wafsChoice.kind}_m.png`;
        if (wafsLayer._url !== url) wafsLayer.setUrl(url);
        wafsLayer._wafsState = { index: index, at: at, times: times, levels: levels };
    }

    // The buttons: a change of kind, or a step in altitude or time
    function setWafs(change) {
        Object.assign(wafsChoice, change);
        try { localStorage.setItem('wafsChoice', JSON.stringify({ kind: wafsChoice.kind, level: wafsChoice.level })); } catch (e) {}
        drawWafs();
    }
    function stepWafs(what, by) {
        const state = wafsLayer && wafsLayer._wafsState;
        if (!state) return;
        if (what === 'level') {
            const next = state.levels[state.at + by];
            if (next) setWafs({ level: next[0] });
        } else {
            const next = state.times[state.index + by];
            if (next) setWafs({ valid: next });
        }
    }

    async function refreshWafs() {
        try {
            const res = await fetch(`${SIGWX_URL}?cb=${Date.now()}`, { cache: 'no-store' });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            wafsRun = { run: data.run, times: (data.times || []).map(t => ({ valid: t.valid })) };
        } catch (e) {
            console.warn('WAFS forecast times unavailable', e);
            if (!wafsRun) wafsRun = { times: [] };
        }
        drawWafs();
    }

    // Sits above the SIG WX time bar when both are showing
    function positionWafsBar() {
        const bar = document.getElementById('wafsBar'), other = document.getElementById('sigwxBar');
        if (!bar || !other) return;
        const lift = getComputedStyle(other).display !== 'none' ? other.offsetHeight + 8 : 0;
        bar.style.bottom = `calc(${other.style.bottom || '2rem'} + ${lift}px)`;
    }
    (function() {
        const other = document.getElementById('sigwxBar');
        if (other) new MutationObserver(positionWafsBar).observe(other, { attributes: true, attributeFilter: ['style'] });
    })();

    function toggleWafs() {
        const btn = document.getElementById('wafsBtn');
        const bar = document.getElementById('wafsBar');
        if (!mapInstance) return;
        if (wafsLayer) {
            mapInstance.removeLayer(wafsLayer);
            wafsLayer = null;
            clearInterval(wafsRefreshInterval);
            wafsRefreshInterval = null;
            wafsChoice.valid = null;
            btn.classList.remove('wafs-active');
            bar.style.display = 'none';
        } else {
            // Under the airport dots and every tappable area; taps pass straight through it
            const pane = mapInstance.getPane('wafsPane') || mapInstance.createPane('wafsPane');
            pane.style.zIndex = 350;
            pane.style.pointerEvents = 'none';
            const blank = 'data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==';
            wafsLayer = L.imageOverlay(blank, WAFS_BOUNDS, { pane: 'wafsPane', opacity: 0.75, interactive: false }).addTo(mapInstance);
            wafsLayer.on('error', () => { document.getElementById('wafsTime').textContent = 'No picture for this choice'; });
            btn.classList.add('wafs-active');
            bar.style.display = 'flex';
            positionWafsBar();
            drawWafs();
            refreshWafs();
            wafsRefreshInterval = setInterval(refreshWafs, 10 * 60 * 1000);
        }
    }'''.split('\n')

i = find('html .layer-btn.sigwx-active {', startswith=True); lines[i - 1:i - 1] = CSS
i = find('<button id="sigwxBtn"', startswith=True); i = find('</button>', i); lines[i + 1:i + 1] = BUTTON
i = find('<div id="sigwxBar">'); i = find('<div id="sigwxKey">', i)
depth = 0
while True:  # the end of the SIG WX bar
    i += 1
    if lines[i].strip() == '</div>':
        if depth == 0: break
    if lines[i].strip() == '</div>' and depth: depth -= 1
i = find('</div>', i + 1); lines[i + 1:i + 1] = BAR
i = find('// --- Taps where several areas overlap ---')
while lines[i - 1].strip() == '': i -= 1
lines[i:i] = JS
open(path, 'w', encoding='utf-8').write('\n'.join(lines))
print('patched', path)

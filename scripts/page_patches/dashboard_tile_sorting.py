"""Adds a "Sort tiles" choice to the dashboard: own order, distance from home, worst weather,
strongest wind, or name. Works on either copy of the page."""
import sys
path = sys.argv[1]
lines = open(path, encoding='utf-8').read().split('\n')
if any('dashSortedStations' in l for l in lines): sys.exit('already applied')
def find(t, start=0, startswith=False):
    hits = [i for i, l in enumerate(lines) if i >= start and (l.strip().startswith(t) if startswith else l.strip() == t)]
    if not hits or (len(hits) != 1 and not start): sys.exit(f'{len(hits)} matches for {t!r}')
    return hits[0]
def indent(i): return lines[i][:len(lines[i]) - len(lines[i].lstrip())]

# The choice itself, under the "Add nearby airports" button
i = find('<button onclick="openDashSearchModal()"', startswith=True); i = find('</button>', i); d = indent(i)
lines[i + 1:i + 1] = [d + l if l else '' for l in '''
<!-- Row 3: the order the tiles are shown in -->
<label class="flex items-center gap-2 text-xs font-bold text-gray-600 dark:text-gray-300">
    Sort tiles
    <select id="dashSortSelect" onchange="setDashSort(this.value)" class="flex-1 sm:flex-none min-w-0 px-2 py-2 rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 text-gray-800 dark:text-gray-100 font-bold text-xs">
        <option value="manual">My own order (drag to arrange)</option>
        <option value="distance">Nearest to home first</option>
        <option value="weather">Worst weather first</option>
        <option value="wind">Strongest wind first</option>
        <option value="name">By code, A to Z</option>
    </select>
</label>'''.split('\n')]

# Dragging a tile while a sort is in force keeps what is on screen and goes back to own order
i = find('const item = dashboardState.stations.splice(evt.oldIndex, 1)[0];'); d = indent(i)
lines[i:i] = [d + "// The tiles were dragged from the order shown, which a sort may have set: that order",
              d + "// becomes the user's own, and the sort is switched off",
              d + "if (dashboardState.sort && dashboardState.sort !== 'manual') {",
              d + "    dashboardState.stations = dashSortedStations();",
              d + "    dashboardState.sort = 'manual';",
              d + "    const select = document.getElementById('dashSortSelect');",
              d + "    if (select) select.value = 'manual';",
              d + "}"]

# Tiles are laid out in the sorted order
i = find('dashboardState.stations.forEach(icao => {'); d = indent(i)
lines[i] = d + 'dashSortedStations(stationLookup).forEach(icao => {'
lines[i:i] = [d + "const sortSelect = document.getElementById('dashSortSelect');",
              d + "if (sortSelect) sortSelect.value = dashboardState.sort || 'manual';"]

# The sorting
i = find('function removeDashboardStation(icao) {'); d = indent(i)
lines[i:i] = [d + l if l else '' for l in r'''// --- Order of the tiles ---
// The user's own order is always kept as it is; a sort only changes the order the tiles
// are shown in, and is worked out afresh each time they are drawn, so "worst weather
// first" follows the time slider and each data refresh.
function setDashSort(mode) {
    dashboardState.sort = mode;
    saveDashboardState();
    if (mode === 'distance' && !dashHomeStation()) showDashAddStatus('Set a home airport on the main page to sort by distance.', true);
    renderDashboard();
}

function dashHomeStation(lookup) {
    let home = null;
    try { home = localStorage.getItem('homeIcao'); } catch (e) {}
    if (!home) return null;
    const station = (lookup || new Map(allStationsData.map(s => [s.id, s]))).get(home.toUpperCase());
    return station && station.latitude != null && station.longitude != null ? station : null;
}

// What a tile shows at the time on the slider, boiled down for sorting
function dashTileSummary(station) {
    let category = 'NODATA', text = '';
    if (dashboardTimeOffset === 0) {
        if (station.metar) { category = station.metar.category; text = station.metar.rawText || ''; }
    } else if (station.taf) {
        const target = new Date(Date.now() + dashboardTimeOffset * 3600000);
        if (target.getUTCMinutes() >= 30) target.setUTCHours(target.getUTCHours() + 1);
        target.setUTCMinutes(0, 0, 0);
        if (!(station.taf.validTo && target > station.taf.validTo)) {
            const condition = getConditionsAtTime(station.taf.rawText, target);
            category = condition.category;
            text = condition.rawText || '';
        }
    }
    const wind = text.match(/(\d{3}|VRB)(\d{2,3})(?:G(\d{2,3}))?KT/);
    return { category: category, wind: wind ? parseInt(wind[3] || wind[2], 10) : -1 };
}

function dashSortedStations(lookup) {
    const own = dashboardState.stations.slice();
    const mode = dashboardState.sort || 'manual';
    if (mode === 'manual') return own;
    lookup = lookup || new Map(allStationsData.map(s => [s.id, s]));
    let key;   // smaller sorts first
    if (mode === 'name') {
        return own.sort();
    } else if (mode === 'distance') {
        const home = dashHomeStation(lookup);
        if (!home) return own;
        key = icao => {
            const s = lookup.get(icao);
            return s && s.latitude != null && s.longitude != null ? haversineDistance(home.latitude, home.longitude, s.latitude, s.longitude) : Infinity;
        };
    } else if (mode === 'weather') {
        const rank = { LIFR: 0, IFR: 1, MVFR: 2, VFR: 3 };
        key = icao => { const r = rank[dashTileSummary(lookup.get(icao) || {}).category]; return r === undefined ? 9 : r; };
    } else if (mode === 'wind') {
        key = icao => -dashTileSummary(lookup.get(icao) || {}).wind;
    } else {
        return own;
    }
    // Tiles that tie stay in the user's own order
    return own.map((icao, at) => ({ icao: icao, key: key(icao), at: at }))
        .sort((a, b) => (a.key - b.key) || (a.at - b.at)).map(entry => entry.icao);
}
'''.split('\n')]
open(path, 'w', encoding='utf-8').write('\n'.join(lines))
print('patched', path)

"""Adds the WAFS colour legend, remembers the WAFS layer between visits, and swaps the RWY
button for one that shows or hides the station circles (runways then always show).
Apply after add_wafs_layer.py. Works on either copy of the page."""
import sys
path = sys.argv[1]
lines = open(path, encoding='utf-8').read().split('\n')
if any('toggleStationDots' in l for l in lines): sys.exit('already applied')
def find(t, start=0, startswith=False):
    hits = [i for i, l in enumerate(lines) if i >= start and (l.strip().startswith(t) if startswith else l.strip() == t)]
    if not hits or (len(hits) != 1 and not start): sys.exit(f'{len(hits)} matches for {t!r}')
    return hits[0]
def indent(i): return lines[i][:len(lines[i]) - len(lines[i].lstrip())]
def after(t, new, startswith=False):
    i = find(t, startswith=startswith); d = indent(i)
    lines[i + 1:i + 1] = [d + n if n else '' for n in new]

# --- WAFS legend ---
i = find('#wafsBar small {', startswith=True); d = indent(i)
lines[i + 1:i + 1] = [d + l for l in '''#wafsLegend { display: flex; flex-direction: column; gap: 2px; }
#wafsLegend b { text-align: center; font-size: 0.62rem; }
#wafsLegend .wafs-strip { display: flex; height: 9px; border-radius: 3px; overflow: hidden; border: 1px solid rgba(127,127,127,.5); }
#wafsLegend .wafs-strip i { flex: 1; }
#wafsLegend .wafs-ticks { display: flex; font: 600 0.56rem 'IBM Plex Mono', monospace; opacity: .85; }
#wafsLegend .wafs-ticks span { flex: 1; text-align: center; }
#wafsLegend .wafs-ticks.wafs-spread { justify-content: space-between; }
#wafsLegend .wafs-ticks.wafs-spread span { flex: none; }'''.split('\n')]
i = find('<small>WAFS forecast picture from aviationweather.gov. For planning only.</small>')
lines[i:i] = [indent(i) + '<div id="wafsLegend"></div>']
after("const WAFS_NAMES = { edr: 'Turbulence', icsev: 'Icing', wind: 'Wind speed' };", '''// The colours used in the pictures, as given in aviationweather.gov's own legends
const WAFS_LEGENDS = {
    edr: { title: 'Turbulence (EDR × 100): higher is rougher', spread: true, labels: ['10', '20', '40', '60', '80', '100'],
        colours: ['#ccff00', '#ffcc00', '#ff9900', '#ff6600', '#ff0000', '#cc0000', '#990000', '#660000', '#4d0000'] },
    icsev: { title: 'Icing severity', labels: ['Trace', 'Light', 'Mod', 'Heavy'], colours: ['#ccffff', '#99ccff', '#6699ff', '#3333ff'] },
    wind: { title: 'Wind speed (kt)', labels: ['60', '70', '80', '90', '100', '110', '120', '130', '140', '150'],
        colours: ['#00ffff', '#00f2e5', '#00e5cc', '#00d8a5', '#00cc7f', '#00bf3f', '#00b200', '#5ebf00', '#7fcc00', '#a5d800'] }
};'''.split('\n'))
after("['edr', 'icsev', 'wind'].forEach(kind => document.getElementById('wafsKind-' + kind)", '''const legend = WAFS_LEGENDS[wafsChoice.kind] || WAFS_LEGENDS.edr;
document.getElementById('wafsLegend').innerHTML = `<b>${legend.title}</b>
    <div class="wafs-strip">${legend.colours.map(c => `<i style="background:${c}"></i>`).join('')}</div>
    <div class="wafs-ticks${legend.spread ? ' wafs-spread' : ''}">${legend.labels.map(l => `<span>${l}</span>`).join('')}</div>`;'''.split('\n'), startswith=True)

# --- WAFS layer remembered between visits, and counted by the menu's dot ---
i = find('function toggleWafs() {'); i = find('wafsRefreshInterval = setInterval(refreshWafs, 10 * 60 * 1000);', i); i = find('}', i)
lines[i + 1:i + 1] = [indent(i) + 'updateLayerActiveState();']
after('const hasSigwx = !!sigwxLayer;', ['const hasWafs = !!wafsLayer;'])
i = find('if (hasRadar || hasFreezing', startswith=True); assert 'hasSigwx ||' in lines[i]
lines[i] = lines[i].replace('hasSigwx ||', 'hasSigwx || hasWafs ||')
after('sigwx: !!sigwxLayer,', ['wafs: !!wafsLayer,', 'stations: showStationsOnMap,'])
after('sigwx: false,', ['wafs: false,', 'stations: true,'])
after('if (!!settings.sigwx !== !!sigwxLayer) toggleSigwx();', ['', '// Apply WAFS grids', 'if (!!settings.wafs !== !!wafsLayer) toggleWafs();',
      '', '// Apply station circles (on unless switched off)', 'if ((settings.stations !== false) !== showStationsOnMap) toggleStationDots();'])
after('if (sigwxRefreshInterval) refreshSigwx();', ['if (wafsRefreshInterval) refreshWafs();'])

# --- Station circles button in place of RWY; runways always show ---
i = find('<button id="runwayMapBtn"', startswith=True); d = indent(i)
assert 'RWY' in lines[i + 1] and lines[i + 2].strip() == '</button>'
lines[i] = d + '<button id="stationsBtn" onclick="toggleStationDots()" class="layer-btn runway-active bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center justify-center">'
lines[i + 1] = lines[i + 1].replace('RWY', 'STN')
i = find('if (settings.runways !== showRunwaysOnMap) toggleRunwayOnMap();')
assert lines[i - 1].strip() == '// Apply Runways'
lines[i - 1:i + 1] = [indent(i) + '// Runways are always shown now; their button became the station circles button']
i = find('const hasRunways = showRunwaysOnMap;'); lines[i] = indent(i) + 'const hasRunways = false; // always on now, so they no longer count as a layer switched on'
i = find('// --- MODE B: STANDARD DOTS ---'); assert lines[i - 1].strip() == '} else {'
lines[i - 1] = indent(i - 1) + '} else if (showStationsOnMap) {'
i = find('// --- WAFS grids: turbulence, icing and wind at a chosen altitude ---'); d = indent(i)
lines[i:i] = [d + l if l else '' for l in '''// --- Station circles on or off ---
// For a clear view of the weather layers. Runways, drawn in the circles' place when the
// map is zoomed in on an airport, are not affected.
let showStationsOnMap = true;
function toggleStationDots() {
    showStationsOnMap = !showStationsOnMap;
    document.getElementById('stationsBtn').classList.toggle('runway-active', showStationsOnMap);
    if (currentStationsData.length > 0) renderMap(currentStationsData);
    updateLayerActiveState();
}
'''.split('\n')]
open(path, 'w', encoding='utf-8').write('\n'.join(lines))
print('patched', path)

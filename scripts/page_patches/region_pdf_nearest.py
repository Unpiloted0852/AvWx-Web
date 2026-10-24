"""The country / state / Europe / USA NOTAM PDFs list their airports nearest first, measured
from the airport whose card the button was tapped on (that airport itself first). Airports
without a known position come last, A-Z. Works on either copy of the page."""
import sys
path = sys.argv[1]
lines = open(path, encoding='utf-8').read().split('\n')
if any('async function makeRegionNotamPdf(button, country, state, from) {' in l for l in lines): sys.exit('already applied')
def find(t, start=0):
    hits = [i for i, l in enumerate(lines) if i >= start and l.strip() == t]
    if not hits or (len(hits) != 1 and not start): sys.exit(f'{len(hits)} matches for {t!r}')
    return hits[0]
def indent(i):
    return lines[i][:len(lines[i]) - len(lines[i].lstrip())]
def replace(old, new):
    i = find(old)
    lines[i] = indent(i) + new

replace('''onclick="makeRegionNotamPdf(this, '${esc(country)}', '${esc(state)}')">PDF of all airport NOTAMs in ${esc(label)}</button>`;''',
        '''onclick="makeRegionNotamPdf(this, '${esc(country)}', '${esc(state)}', '${esc(icao)}')">PDF of all airport NOTAMs in ${esc(label)}</button>`;''')
replace('async function makeRegionNotamPdf(button, country, state) {',
        'async function makeRegionNotamPdf(button, country, state, from) {')
i = find(".map(([id]) => id).sort();")
pad = indent(i)
lines[i:i + 1] = [pad + '.map(([id]) => id).sort();'] + [pad[:-4] + l for l in '''// Nearest first, from the airport whose card the button is on; those without a position last
const home = cachedStationMap.get(from);
const away = icao => {
    const s = cachedStationMap.get(icao);
    if (!home || home.latitude == null || !s || s.latitude == null) return Infinity;
    const rad = Math.PI / 180, dLat = (s.latitude - home.latitude) * rad, dLon = (s.longitude - home.longitude) * rad;
    const h = Math.sin(dLat / 2) ** 2 + Math.cos(home.latitude * rad) * Math.cos(s.latitude * rad) * Math.sin(dLon / 2) ** 2;
    return Math.asin(Math.min(1, Math.sqrt(h)));
};
const distance = new Map(airports.map(icao => [icao, away(icao)]));
airports.sort((a, b) => (distance.get(a) - distance.get(b)) || (a < b ? -1 : 1));'''.split('\n')]

open(path, 'w', encoding='utf-8').write('\n'.join(lines))
print('applied')

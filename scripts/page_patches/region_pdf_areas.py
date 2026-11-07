"""The country / state / Europe / USA NOTAM PDFs end with the NOTAMs not filed under a weather
station airport: the FIRs and US centers the region's airports lie in, the region's
country-wide NOTAMs and airfields without a weather station (nearest first), the US national
FDC NOTAMs for US PDFs, and the GPS satellite NOTAMs. Uses data/airport_notams/areas.json from
update_airport_notams.py. Needs region_pdf_nearest.py first. Works on either copy of the page."""
import sys
path = sys.argv[1]
lines = open(path, encoding='utf-8').read().split('\n')
if any('function airportNotamAreaTitle(' in l for l in lines): sys.exit('already applied')
if not any('async function makeRegionNotamPdf(button, country, state, from) {' in l for l in lines): sys.exit('apply region_pdf_nearest.py first')
def find(t, start=0):
    hits = [i for i, l in enumerate(lines) if i >= start and l.strip() == t]
    if not hits or (len(hits) != 1 and not start): sys.exit(f'{len(hits)} matches for {t!r}')
    return hits[0]
def indent(i):
    return lines[i][:len(lines[i]) - len(lines[i].lstrip())]

# The heading of an area's NOTAMs in the PDF
i = find('async function makeRegionNotamPdf(button, country, state, from) {')
lines[i:i] = '''// The PDF heading for NOTAMs filed under a location other than a weather station airport
function airportNotamAreaTitle(key, kind) {
    if (kind === 'gps') return 'GPS NOTAMs (satellite status)';
    if (kind === 'fir') return `${key}: FIR / center NOTAMs`;
    if (key === 'KFDC') return 'KFDC: US national (FDC) NOTAMs';
    return `${key} NOTAMs`;
}
'''.split('\n')

# Which areas, after the airports have been put in order
i = find('airports.sort((a, b) => (distance.get(a) - distance.get(b)) || (a < b ? -1 : 1));')
pad = indent(i)
lines[i + 1:i + 1] = [pad + l if l else l for l in '''// Then, for the end of the PDF, the NOTAMs not at a weather station airport (areas.json):
// the FIRs and US centers the region's airports lie in, the region's other locations
// (country-wide NOTAMs, airfields without a weather station) nearest first, the US national
// FDC NOTAMs for US PDFs, and GPS. Without the list, the PDF has the airports only.
const areaKind = new Map();
try {
    const index = await fetch(`${AIRPORT_NOTAMS_URL}/areas.json?cb=${Date.now()}`, { cache: 'no-store' }).then(r => r.ok ? r.json() : null);
    if (index && Array.isArray(index.areas)) {
        const firs = new Set(airports.map(icao => (index.airport_fir || {})[icao]).filter(Boolean));
        const usPdf = scope === 'US' || country === 'US';
        const picked = index.areas.filter(([key, kind, inCountry, inState]) => kind === 'gps' || firs.has(key)
            || (key === 'KFDC' && usPdf)
            // The whole USA: its centers (ids starting Z) only, not every small airfield
            || (scope === 'US' ? inCountry === 'US' && /^(K|P[AGH])Z/.test(key)
                : scope === 'EUROPE' ? EUROPE_COUNTRIES.has(inCountry) : inCountry === country && (!state || inState === state)));
        const rank = { fir: 0, other: 1, gps: 2 };
        const areaAway = ([, , , , lat, lon]) => {
            if (!home || home.latitude == null || lat == null) return Infinity;
            const rad = Math.PI / 180, dLat = (lat - home.latitude) * rad, dLon = (lon - home.longitude) * rad;
            return Math.asin(Math.min(1, Math.sqrt(Math.sin(dLat / 2) ** 2 + Math.cos(home.latitude * rad) * Math.cos(lat * rad) * Math.sin(dLon / 2) ** 2)));
        };
        picked.sort((a, b) => (rank[a[1]] ?? 1) - (rank[b[1]] ?? 1) || (areaAway(a) - areaAway(b)) || (a[0] < b[0] ? -1 : 1));
        for (const [key, kind] of picked) if (!airports.includes(key)) areaKind.set(key, kind);
    }
} catch (e) { console.warn('Area NOTAM list not loaded', e); }'''.split('\n')]

replace_at = find('const wanted = airports.map(icao => {')
lines[replace_at] = indent(replace_at) + 'const wanted = [...airports, ...areaKind.keys()].map(icao => {'

i = find('if (notams.length) { found.push({ icao, notams }); total += notams.length; }')
lines[i] = indent(i) + 'if (notams.length) { found.push(areaKind.has(icao) ? { icao, notams, title: airportNotamAreaTitle(icao, areaKind.get(icao)) } : { icao, notams }); total += notams.length; }'

# The PDF: a section heading before the first area, and the area's own heading
i = find('for (const airport of pdfNotams.airports) {')
lines[i:i] = [indent(i) + 'let areasStarted = false;']
i = find('yield;   // one step per airport (see makeRegionNotamPdf)', i)
pad = indent(i)
lines[i + 1:i + 1] = [pad + l for l in '''if (airport.title && !areasStarted) {
    areasStarted = true;
    room(24);
    y += 4;
    doc.setFont("helvetica", "bold"); doc.setFontSize(13); doc.setTextColor(0, 0, 0);
    doc.text("Area NOTAMs", PAGE_MARGIN, y); y += 5;
    doc.setFont("helvetica", "normal"); doc.setFontSize(8); doc.setTextColor(90, 90, 90);
    doc.text("FIRs and centers, country-wide NOTAMs, airfields without a weather station, and GPS.", PAGE_MARGIN, y); y += 7;
}'''.split('\n')]
hits = [k for k, l in enumerate(lines) if l.strip() == 'doc.text(`${airport.icao} NOTAMs${count}`, PAGE_MARGIN, y); y += 6;']
if len(hits) != 1: sys.exit(f'{len(hits)} matches for the airport heading')
lines[hits[0]] = indent(hits[0]) + 'doc.text(`${airport.title || airport.icao + \' NOTAMs\'}${count}`, PAGE_MARGIN, y); y += 6;'

open(path, 'w', encoding='utf-8').write('\n'.join(lines))
print('applied')

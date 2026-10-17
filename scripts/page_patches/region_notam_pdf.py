"""Adds a "PDF of all airport NOTAMs in <country or US state>" button to each airport's NOTAM
section. Apply after airport_notams.py and airport_notams_refresh.py. Works on either copy
of the page (matches stripped lines)."""
import sys

path = sys.argv[1]
lines = open(path, encoding='utf-8').read().split('\n')
if any('makeRegionNotamPdf' in l for l in lines):
    sys.exit('already applied')


def find(text, start=0, startswith=False):
    hits = [i for i, l in enumerate(lines) if i >= start and (l.strip().startswith(text) if startswith else l.strip() == text)]
    if not hits or (len(hits) != 1 and not start):
        sys.exit(f'{len(hits)} matches for {text!r}')
    return hits[0]


def indent(i):
    return lines[i][:len(lines[i]) - len(lines[i].lstrip())]


# 1. Each station keeps its country and state
i = find('map.set(id, { name: label, latitude: isNaN(lat) ? null : lat, longitude: isNaN(lon) ? null : lon, elevationFt: elevFt });')
lines[i] = lines[i].replace('elevationFt: elevFt });', "elevationFt: elevFt, country: country || '', state: state || '' });")

# 2. The button, under each airport's list
for old in ("content.innerHTML = `<p class=\"text-xs opacity-60\">No NOTAMs on file for ${esc(icao)}.</p>` + footer;",
            "content.innerHTML = toggle + rows + footer;"):
    i = find(old)
    lines[i] = lines[i].replace('+ footer;', '+ airportNotamRegionButton(icao) + footer;')

# 3. The PDF title can name the region
i = find('function drawPdfNotams(doc, pdfNotams) {')
lines[i] = lines[i].replace('(doc, pdfNotams)', '(doc, pdfNotams, title)')
i = find('doc.text("NOTAMs", PAGE_MARGIN, y); y += 6;', i)
lines[i] = lines[i].replace('doc.text("NOTAMs", PAGE_MARGIN, y)', 'doc.text(title || "NOTAMs", PAGE_MARGIN, y)')

# 4. Making the regional PDF
i = find('// The NOTAMs of the report\'s airports that were chosen for the PDF: [{icao, notams}], in')
d = indent(i)
block = r'''// ── NOTAMs for a whole country, or a US state, as one PDF ──────
// Every airport the page knows in that country (or state) is looked up, using each of the
// published NOTAM files only once. Limited so the PDF stays within reason: about 300 pages.
const REGION_NOTAM_LIMIT = 3500;
const US_STATE_NAMES = { AL: 'Alabama', AK: 'Alaska', AZ: 'Arizona', AR: 'Arkansas', CA: 'California', CO: 'Colorado',
    CT: 'Connecticut', DE: 'Delaware', DC: 'District of Columbia', FL: 'Florida', GA: 'Georgia', HI: 'Hawaii', ID: 'Idaho',
    IL: 'Illinois', IN: 'Indiana', IA: 'Iowa', KS: 'Kansas', KY: 'Kentucky', LA: 'Louisiana', ME: 'Maine', MD: 'Maryland',
    MA: 'Massachusetts', MI: 'Michigan', MN: 'Minnesota', MS: 'Mississippi', MO: 'Missouri', MT: 'Montana', NE: 'Nebraska',
    NV: 'Nevada', NH: 'New Hampshire', NJ: 'New Jersey', NM: 'New Mexico', NY: 'New York', NC: 'North Carolina',
    ND: 'North Dakota', OH: 'Ohio', OK: 'Oklahoma', OR: 'Oregon', PA: 'Pennsylvania', RI: 'Rhode Island',
    SC: 'South Carolina', SD: 'South Dakota', TN: 'Tennessee', TX: 'Texas', UT: 'Utah', VT: 'Vermont', VA: 'Virginia',
    WA: 'Washington', WV: 'West Virginia', WI: 'Wisconsin', WY: 'Wyoming', PR: 'Puerto Rico' };

// The region an airport belongs to: its US state, or its country
function airportRegion(icao) {
    const station = cachedStationMap && cachedStationMap.get(icao);
    if (!station || !station.country) return null;
    if (station.country === 'US') {
        return station.state ? { country: 'US', state: station.state, name: US_STATE_NAMES[station.state] || station.state } : null;
    }
    let name = station.country;
    try { name = new Intl.DisplayNames(['en'], { type: 'region' }).of(station.country) || name; } catch (e) {}
    return { country: station.country, state: null, name: name };
}

function airportNotamRegionButton(icao) {
    const region = airportRegion(icao);
    if (!region) return '';
    const esc = text => String(text).replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
    return `<button type="button" class="mt-3 w-full text-xs font-bold py-2 px-3 rounded-lg bg-black/30 hover:bg-black/40"
        onclick="makeRegionNotamPdf(this, '${esc(region.country)}', '${esc(region.state || '')}')">PDF of all airport NOTAMs in ${esc(region.name)}</button>`;
}

async function makeRegionNotamPdf(button, country, state) {
    const original = button.textContent;
    const say = text => { button.textContent = text; };
    button.disabled = true;
    try {
        let region = state ? (US_STATE_NAMES[state] || state) : country;
        if (!state) { try { region = new Intl.DisplayNames(['en'], { type: 'region' }).of(country) || country; } catch (e) {} }
        const airports = [...cachedStationMap.entries()]
            .filter(([, s]) => s.country === country && (!state || s.state === state)).map(([id]) => id).sort();
        say(`Loading NOTAMs for ${airports.length} airports…`);
        // Which file holds each airport, and each file fetched once
        const join = (a, b) => { const out = new Uint8Array(a.length + b.length); out.set(a); out.set(b, a.length); return out; };
        const wanted = airports.map(icao => {
            const key = sha256Bytes(new TextEncoder().encode(`${AIRPORT_NOTAMS_SALT}|${icao}`));
            const locator = Array.from(sha256Bytes(join(new TextEncoder().encode('loc|'), key)).slice(0, 12),
                byte => byte.toString(16).padStart(2, '0')).join('');
            return { icao, key, locator };
        });
        const stamp = Date.now();
        const status = await fetch(`${AIRPORT_NOTAMS_URL}/status.json?cb=${stamp}`, { cache: 'no-store' }).then(r => r.ok ? r.json() : null);
        if (!status || !status.ok) throw new Error('out of date');
        _airportNotamsStatus = status;
        const files = {};
        await Promise.all([...new Set(wanted.map(w => w.locator.slice(0, 2)))].map(async name => {
            const r = await fetch(`${AIRPORT_NOTAMS_URL}/${name}.json?cb=${stamp}`, { cache: 'no-store' });
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            files[name] = await r.json();
        }));
        const found = [];
        let total = 0;
        for (const { icao, key, locator } of wanted) {
            const entry = files[locator.slice(0, 2)][locator];
            if (!entry) continue;
            const scrambled = Uint8Array.from(atob(entry), ch => ch.charCodeAt(0));
            const packed = new Uint8Array(scrambled.length);
            for (let block = 0; block * 32 < scrambled.length; block++) {
                const counter = new Uint8Array([block >>> 24, block >>> 16, block >>> 8, block]);
                const stream = sha256Bytes(join(key, counter));
                for (let i = block * 32; i < Math.min(scrambled.length, block * 32 + 32); i++) packed[i] = scrambled[i] ^ stream[i - block * 32];
            }
            const notams = sortAirportNotams(currentAirportNotams(JSON.parse(pako.inflate(packed, { to: 'string' }))));
            if (notams.length) { found.push({ icao, notams }); total += notams.length; }
        }
        if (total > REGION_NOTAM_LIMIT) {
            say(`Too many for one PDF: ${total.toLocaleString()} NOTAMs in ${region} (limit ${REGION_NOTAM_LIMIT.toLocaleString()})`);
            setTimeout(() => { say(original); button.disabled = false; }, 6000);
            return;
        }
        if (total === 0) {
            say(`No airport NOTAMs on file in ${region}`);
            setTimeout(() => { say(original); button.disabled = false; }, 4000);
            return;
        }
        say(`Making a PDF of ${total.toLocaleString()} NOTAMs at ${found.length} airports…`);
        await new Promise(r => setTimeout(r, 30));   // let the message show before the heavy work
        const { jsPDF } = window.jspdf;
        const doc = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' });
        drawPdfNotams(doc, { airports: found, status: status }, `NOTAMs: ${region}`);
        const file = region.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
        showPdfPreview(doc, `notams-${file}.pdf`);
        say(original);
        button.disabled = false;
    } catch (e) {
        console.warn('Regional NOTAM PDF failed', e);
        say('Could not make the PDF right now. Please try again.');
        setTimeout(() => { say(original); button.disabled = false; }, 5000);
    }
}

'''.split('\n')
lines[i:i] = [(d + l) if l else '' for l in block]
open(path, 'w', encoding='utf-8').write('\n'.join(lines))
print('patched', path)

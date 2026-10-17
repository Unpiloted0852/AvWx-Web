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
// published NOTAM files only once. Limited so the PDF stays within reason: about 300 pages
// for a country or state. Europe as a whole (about 400 pages) and the whole USA (about
// 2,000 pages, offered with a warning) have their own limits.
const REGION_NOTAM_LIMITS = { region: 3500, EUROPE: 15000, US: 50000 };
// Europe for this purpose: the European countries, with the UK, Turkey, Ukraine and the
// Caucasus; Russia, which reaches far into Asia, is left to its own country PDF
const EUROPE_COUNTRIES = new Set(('AL AD AM AT AZ BY BE BA BG HR CY CZ DK EE FI FR GE DE GI GR HU IS IE IT XK LV LI LT ' +
    'LU MT MD MC ME NL MK NO PL PT RO SM RS SK SI ES SE CH TR UA GB FO GL IM JE GG AX SJ VA').split(' '));
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
    const button = (country, state, label) => `<button type="button" class="mt-2 w-full text-xs font-bold py-2 px-3 rounded-lg bg-black/30 hover:bg-black/40"
        onclick="makeRegionNotamPdf(this, '${esc(country)}', '${esc(state)}')">PDF of all airport NOTAMs in ${esc(label)}</button>`;
    let html = '<div class="mt-2">' + button(region.country, region.state || '', region.name);
    if (region.country === 'US') html += button('US', '', 'the whole USA');
    else if (EUROPE_COUNTRIES.has(region.country)) html += button('EUROPE', '', 'Europe');
    return html + '</div>';
}

async function makeRegionNotamPdf(button, country, state) {
    const original = button.dataset.label || button.textContent;
    button.dataset.label = original;
    const say = text => { button.textContent = text; };
    // The whole USA makes a very large PDF: the first tap only says so, a second tap goes ahead
    if (country === 'US' && !state && button.dataset.confirmed !== 'yes') {
        button.dataset.confirmed = 'yes';
        say('About 2,000 pages: slow, and may fail on a phone. Tap again to make it.');
        setTimeout(() => { if (!button.disabled) { delete button.dataset.confirmed; say(original); } }, 8000);
        return;
    }
    delete button.dataset.confirmed;
    button.disabled = true;
    try {
        const scope = country === 'EUROPE' ? 'EUROPE' : (country === 'US' && !state ? 'US' : 'region');
        let region = state ? (US_STATE_NAMES[state] || state) : country;
        if (scope === 'EUROPE') region = 'Europe';
        else if (scope === 'US') region = 'the USA';
        else { try { region = new Intl.DisplayNames(['en'], { type: 'region' }).of(country) || country; } catch (e) {} }
        const airports = [...cachedStationMap.entries()]
            .filter(([, s]) => scope === 'EUROPE' ? EUROPE_COUNTRIES.has(s.country) : (s.country === country && (!state || s.state === state)))
            .map(([id]) => id).sort();
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
        const limit = REGION_NOTAM_LIMITS[scope];
        if (total > limit) {
            say(`Too many for one PDF: ${total.toLocaleString()} NOTAMs in ${region} (limit ${limit.toLocaleString()})`);
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
        // Drawn an airport at a time with pauses, so the page stays responsive and shows progress
        const steps = drawPdfNotamsSteps(doc, { airports: found, status: status }, `NOTAMs: ${region.replace(/^the /, '')}`);
        let done = 0, lastPause = performance.now();
        while (!steps.next().done) {
            done++;
            if (performance.now() - lastPause > 120) {
                say(`Making the PDF… ${Math.round(done / found.length * 100)}% (${doc.getNumberOfPages()} pages)`);
                await new Promise(r => setTimeout(r, 0));
                lastPause = performance.now();
            }
        }
        say('Opening the PDF…');
        await new Promise(r => setTimeout(r, 30));
        const file = region.replace(/^the /, '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
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

# 5. drawPdfNotams in steps, one airport at a time
i = find('function drawPdfNotams(doc, pdfNotams, title) {')
d = indent(i)
lines[i] = d + 'function* drawPdfNotamsSteps(doc, pdfNotams, title) {'
j = find('for (const airport of pdfNotams.airports) {', i)
lines[j + 1:j + 1] = [indent(j) + '    yield;   // one step per airport (see makeRegionNotamPdf)']
k = j
while lines[k] != d + '}':
    k += 1
lines[k + 1:k + 1] = ['', d + '// All the steps at once, for the PDF report',
                      d + 'function drawPdfNotams(doc, pdfNotams, title) {',
                      d + '    const steps = drawPdfNotamsSteps(doc, pdfNotams, title);',
                      d + '    let step;',
                      d + '    do { step = steps.next(); } while (!step.done);',
                      d + '    return step.value;',
                      d + '}']
open(path, 'w', encoding='utf-8').write('\n'.join(lines))
print('patched', path)

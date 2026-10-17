"""Adds a NOTAMs section to the airport detail view (opened from the dashboard and from the
map). Works on either copy of the page (matches stripped lines)."""
import sys

path = sys.argv[1]
lines = open(path, encoding='utf-8').read().split('\n')
if any('fetchAirportNotams' in l for l in lines):
    sys.exit('already applied')


def find(text, start=0, startswith=False):
    hits = [i for i, l in enumerate(lines) if i >= start and (l.strip().startswith(text) if startswith else l.strip() == text)]
    if not hits or (len(hits) != 1 and not start):
        sys.exit(f'{len(hits)} matches for {text!r}')
    return hits[0]


def indent(i):
    return lines[i][:len(lines[i]) - len(lines[i].lstrip())]


# 1. The section, after the TAF card in the detail view
i = find('<h3 class="text-[10px] font-black uppercase tracking-widest opacity-60 mb-2">TAF (Time Synced)</h3>')
j = find('</div>', i)            # end of the TAF text block
j = find('</div>', j + 1)        # end of the TAF card
d = indent(j)
lines[j + 1:j + 1] = [d + l for l in '''<div id="airportNotamsSection" class="bg-black/20 p-4 rounded-xl">
    <h3 class="text-[10px] font-black uppercase tracking-widest opacity-60 mb-2">NOTAMs</h3>
    <div id="airportNotamsContent"><p class="italic opacity-40 text-xs">Loading…</p></div>
</div>'''.split('\n')]

# 2. Loaded when the view opens, beside the D-ATIS
i = find('fetchDatis(icao);')
lines[i + 1:i + 1] = [indent(i) + 'fetchAirportNotams(icao);']

# 3. The loading and drawing
i = find('// ── WIND ROSE ──────────────────────────────────────────────────', startswith=True)
d = indent(i)
block = r'''// ── AIRPORT NOTAMs ─────────────────────────────────────────────
// The NOTAMs in force at an airport now or starting within three days. They come from the
// FAA NOTAM system by way of the Signal bot's copy on the project's Raspberry Pi; this
// project's data job files each airport's list, compressed and scrambled, in one of 256
// small files (see scripts/update_airport_notams.py), so only one small file is fetched
// per airport. The scrambling only deters casual copying.
let AIRPORT_NOTAMS_URL = `${BASE_URL}/data/airport_notams`;
const AIRPORT_NOTAMS_SALT = 'avwx-airport-notams-v1';
let _airportNotamsStatus = null;

async function readAirportNotams(icao) {
    const join = (a, b) => { const out = new Uint8Array(a.length + b.length); out.set(a); out.set(b, a.length); return out; };
    const key = sha256Bytes(new TextEncoder().encode(`${AIRPORT_NOTAMS_SALT}|${icao}`));
    const locator = Array.from(sha256Bytes(join(new TextEncoder().encode('loc|'), key)).slice(0, 12),
        byte => byte.toString(16).padStart(2, '0')).join('');
    const [status, file] = await Promise.all([
        fetch(`${AIRPORT_NOTAMS_URL}/status.json?cb=${Date.now()}`, { cache: 'no-store' }).then(r => r.ok ? r.json() : null),
        fetch(`${AIRPORT_NOTAMS_URL}/${locator.slice(0, 2)}.json?cb=${Date.now()}`, { cache: 'no-store' }).then(r => {
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            return r.json();
        })
    ]);
    _airportNotamsStatus = status;
    const entry = file[locator];
    if (!entry) return [];
    const scrambled = Uint8Array.from(atob(entry), ch => ch.charCodeAt(0));
    const packed = new Uint8Array(scrambled.length);
    for (let block = 0; block * 32 < scrambled.length; block++) {
        const counter = new Uint8Array([block >>> 24, block >>> 16, block >>> 8, block]);
        const stream = sha256Bytes(join(key, counter));
        for (let i = block * 32; i < Math.min(scrambled.length, block * 32 + 32); i++) packed[i] = scrambled[i] ^ stream[i - block * 32];
    }
    // [number, start, end, issued, classification, text]
    return JSON.parse(pako.inflate(packed, { to: 'string' }));
}

function airportNotamTime(text) {
    // "2026-10-16T13:32" (UTC) -> milliseconds
    return text && text !== 'PERM' ? Date.parse(text + ':00Z') : NaN;
}

// In force first, then those still to start, each in order of their start
function sortAirportNotams(notams) {
    const now = _nowAccurate();
    return notams.slice().sort((a, b) => {
        const sa = airportNotamTime(a[1]), sb = airportNotamTime(b[1]);
        const fa = !(sa > now), fb = !(sb > now);
        if (fa !== fb) return fa ? -1 : 1;
        return (sa || 0) - (sb || 0) || a[0].localeCompare(b[0]);
    });
}

// "In force until 23 Oct 2026", "Starts Sun 21:00Z, until ...", for screen and PDF
function airportNotamWhen(start, end) {
    const s = airportNotamTime(start), e = airportNotamTime(end), now = _nowAccurate();
    const until = end === 'PERM' ? 'permanent' : (isNaN(e) ? '' : `until ${airspaceClock(e)}`);
    if (!isNaN(s) && s > now) return { soon: true, text: `Starts ${airspaceClock(s)}${until ? ', ' + until : ''}` };
    return { soon: false, text: `In force${until ? (end === 'PERM' ? ', ' : ' ') + until : ''}` };
}

// The airports whose NOTAMs go into the PDF report, remembered on this device
function pdfNotamAirports() {
    try { return new Set(JSON.parse(localStorage.getItem('pdfNotamAirports') || '[]')); } catch (e) { return new Set(); }
}
function setPdfNotamAirport(icao, wanted) {
    const chosen = pdfNotamAirports();
    if (wanted) chosen.add(icao); else chosen.delete(icao);
    try { localStorage.setItem('pdfNotamAirports', JSON.stringify([...chosen])); } catch (e) {}
}

async function fetchAirportNotams(icao) {
    const content = document.getElementById('airportNotamsContent');
    if (!content) return;
    const esc = text => String(text).replace(/[&<>"]/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]));
    let notams;
    try {
        notams = await readAirportNotams(icao);
    } catch (e) {
        content.innerHTML = '<p class="text-xs opacity-60">NOTAMs could not be loaded right now. Check official sources before flight.</p>';
        return;
    }
    if (document.getElementById('airportNotamsContent') !== content) return;   // another airport opened meanwhile
    const status = _airportNotamsStatus || {};
    if (!status.ok) {
        content.innerHTML = '<p class="text-xs opacity-60">NOTAMs are not available right now (the NOTAM copy is out of date). Check official sources before flight.</p>';
        return;
    }
    const asOf = airportNotamTime((status.as_of || '').slice(0, 16));
    const asOfText = isNaN(asOf) ? '' : `as of ${airspaceClock(asOf)}`;
    const header = document.querySelector('#airportNotamsSection h3');
    if (header) header.innerHTML = `NOTAMs${notams.length ? ` (${notams.length})` : ''} <span class="font-normal normal-case tracking-normal opacity-40 text-[9px]">${asOfText}</span>`;
    const footer = `<p class="mt-3 text-[10px] opacity-50">In force now or starting within three days, from the FAA NOTAM system. May be incomplete: check official sources before flight.</p>`;
    if (notams.length === 0) {
        content.innerHTML = `<p class="text-xs opacity-60">No NOTAMs on file for ${esc(icao)}.</p>` + footer;
        return;
    }
    const included = pdfNotamAirports().has(icao);
    const toggle = `<label class="flex items-center gap-2 mb-2 text-xs font-bold cursor-pointer select-none">
        <input type="checkbox" class="w-4 h-4 accent-indigo-500" ${included ? 'checked' : ''}
               onchange="setPdfNotamAirport('${esc(icao)}', this.checked)">
        Include these NOTAMs in the PDF report
    </label>`;
    const rows = sortAirportNotams(notams).map(([number, start, end, issued, classification, text]) => {
        const when = airportNotamWhen(start, end);
        return `<div class="py-2 border-t border-white/10">
            <div class="flex flex-wrap items-baseline gap-x-2 text-[10px] uppercase tracking-wider"><span class="font-black">${esc(number)}</span><span class="normal-case tracking-normal font-bold ${when.soon ? 'bg-black/30 rounded px-1.5' : 'opacity-90'}">${esc(when.text)}</span></div>
            <div class="mt-1 font-mono text-[13px] font-semibold leading-relaxed whitespace-pre-wrap break-words rounded-lg px-2.5 py-2" style="background:rgba(0,0,0,.72);color:#fff">${esc(text)}</div>
        </div>`;
    }).join('');
    content.innerHTML = toggle + rows + footer;
}

// The NOTAMs of the report's airports that were chosen for the PDF: [{icao, notams}], in
// the report's order, plus how fresh they are. Airports that fail to load are listed
// with notams null, so the PDF can say so rather than leave them out silently.
async function loadPdfNotams(stationsData) {
    const chosen = pdfNotamAirports();
    const wanted = (stationsData || []).map(d => d.station && d.station.id || d.id).filter(id => id && chosen.has(id));
    const airports = [];
    for (const icao of [...new Set(wanted)]) {
        try { airports.push({ icao: icao, notams: sortAirportNotams(await readAirportNotams(icao)) }); }
        catch (e) { airports.push({ icao: icao, notams: null }); }
    }
    return { airports: airports, status: _airportNotamsStatus || {} };
}

// Draws the chosen airports' NOTAMs from the top of the current (first) page of the PDF
// report; says whether there were any, so the weather can start on a fresh page after them
function drawPdfNotams(doc, pdfNotams) {
    if (!pdfNotams || !pdfNotams.airports.length) return false;
    let y = PAGE_MARGIN;
    const room = needed => { if (y + needed > PAGE_HEIGHT - PAGE_MARGIN) { doc.addPage(); y = PAGE_MARGIN; } };
    const asOf = airportNotamTime((pdfNotams.status.as_of || '').slice(0, 16));
    doc.setFont("helvetica", "bold"); doc.setFontSize(14); doc.setTextColor(0, 0, 0);
    doc.text("NOTAMs", PAGE_MARGIN, y); y += 6;
    doc.setFont("helvetica", "normal"); doc.setFontSize(8); doc.setTextColor(90, 90, 90);
    doc.splitTextToSize(`In force now or starting within three days, from the FAA NOTAM system${isNaN(asOf) ? '' : ', as of ' + new Date(asOf).toISOString().slice(0, 16).replace('T', ' ') + 'Z'}. May be incomplete: check official sources before flight.`, USABLE_WIDTH)
        .forEach(line => { doc.text(line, PAGE_MARGIN, y); y += 3.6; });
    y += 3;
    for (const airport of pdfNotams.airports) {
        room(14);
        doc.setFont("helvetica", "bold"); doc.setFontSize(12); doc.setTextColor(0, 0, 0);
        const count = airport.notams ? ` (${airport.notams.length})` : '';
        doc.text(`${airport.icao} NOTAMs${count}`, PAGE_MARGIN, y); y += 6;
        if (!pdfNotams.status.ok || !airport.notams) {
            doc.setFont("helvetica", "italic"); doc.setFontSize(9); doc.setTextColor(150, 0, 0);
            doc.text("NOTAMs could not be loaded for this airport. Check official sources.", PAGE_MARGIN + 2, y); y += 7;
            continue;
        }
        if (airport.notams.length === 0) {
            doc.setFont("helvetica", "italic"); doc.setFontSize(9); doc.setTextColor(80, 80, 80);
            doc.text("No NOTAMs on file.", PAGE_MARGIN + 2, y); y += 7;
            continue;
        }
        for (const [number, start, end, issued, classification, text] of airport.notams) {
            const when = airportNotamWhen(start, end);
            doc.setFont("courier", "normal"); doc.setFontSize(8);
            const lines = text.split('\n').flatMap(part => doc.splitTextToSize(part || ' ', USABLE_WIDTH - 4));
            room(5 + Math.min(lines.length, 6) * 3.4);
            doc.setFont("helvetica", "bold"); doc.setFontSize(8.5); doc.setTextColor(0, 0, 0);
            doc.text(number, PAGE_MARGIN + 2, y);
            doc.setFont("helvetica", "normal");
            if (when.soon) doc.setTextColor(180, 110, 0); else doc.setTextColor(180, 0, 0);
            doc.text(when.text, PAGE_MARGIN + 2 + doc.getTextWidth(number) + 3, y);
            y += 4;
            doc.setFont("courier", "normal"); doc.setFontSize(8); doc.setTextColor(30, 30, 30);
            for (const line of lines) { room(3.4); doc.text(line, PAGE_MARGIN + 4, y); y += 3.4; }
            y += 2.2;
        }
        y += 3;
    }
    return true;
}

'''.split('\n')
lines[i:i] = [(d + l) if l else '' for l in block]

# 4. The PDF: the chosen airports' NOTAMs are loaded before it is drawn, and drawn last
i = find('generatePDF(currentReportData.stationsData, currentReportData.refName, currentReportData.routeAnalysisResult);')
d = indent(i)
lines[i:i + 1] = [d + 'const pdfNotams = await loadPdfNotams(currentReportData.stationsData);',
                  d + 'generatePDF(currentReportData.stationsData, currentReportData.refName, currentReportData.routeAnalysisResult, pdfNotams);']
i = find('function generatePDF(stationsData, refName, routeAnalysisResult) {')
lines[i] = lines[i].replace('routeAnalysisResult) {', 'routeAnalysisResult, pdfNotams) {')
# The NOTAM pages come first, before the route analysis and the weather
i = find('let cursorY = PAGE_MARGIN;', i)
lines[i + 1:i + 1] = ['', indent(i) + '// The chosen airports\' NOTAMs come first', indent(i) + 'if (drawPdfNotams(doc, pdfNotams)) doc.addPage();']
open(path, 'w', encoding='utf-8').write('\n'.join(lines))
print('patched', path)

"""Keeps an open airport's NOTAM list current: reloads it every 5 minutes and when the page
comes back into view, hides NOTAMs whose end time has passed (also in the PDF), and turns
"Starts ..." into "In force" on time. Apply after airport_notams.py. Works on either copy
of the page (matches stripped lines)."""
import sys

path = sys.argv[1]
lines = open(path, encoding='utf-8').read().split('\n')
if any('renderAirportNotams' in l for l in lines):
    sys.exit('already applied')


def find(text, start=0, startswith=False):
    hits = [i for i, l in enumerate(lines) if i >= start and (l.strip().startswith(text) if startswith else l.strip() == text)]
    if not hits or (len(hits) != 1 and not start):
        sys.exit(f'{len(hits)} matches for {text!r}')
    return hits[0]


i = find('async function fetchAirportNotams(icao) {')
j = find("// The NOTAMs of the report's airports that were chosen for the PDF: [{icao, notams}], in", i)
d = lines[i][:len(lines[i]) - len(lines[i].lstrip())]
block = r'''// Only NOTAMs that have not yet ended: the published list is up to about 20 minutes old,
// and an open view or a saved choice can be older still
function currentAirportNotams(notams) {
    const now = _nowAccurate();
    return notams.filter(n => !(airportNotamTime(n[2]) <= now));
}

// The airport whose NOTAMs are on screen, and its timers
let _airportNotamsView = null;

// Still showing: this is the latest airport opened, and its view has not been closed
// (closing hides the view rather than removing it)
function airportNotamsViewOpen(view) {
    if (!view || _airportNotamsView !== view || !document.body.contains(view.content)) return false;
    const modal = view.content.closest('#tileModal');
    return !(modal && modal.classList.contains('hidden'));
}

async function fetchAirportNotams(icao) {
    const content = document.getElementById('airportNotamsContent');
    if (!content) return;
    if (_airportNotamsView) { clearInterval(_airportNotamsView.tick); clearInterval(_airportNotamsView.reload); }
    const view = { icao: icao, content: content, notams: null, loadedAt: 0 };
    _airportNotamsView = view;
    const stillOpen = () => airportNotamsViewOpen(view);
    const load = async () => {
        try {
            const notams = await readAirportNotams(icao);
            if (!stillOpen()) return;
            view.notams = notams;
            view.loadedAt = Date.now();
            renderAirportNotams(view);
        } catch (e) {
            if (!stillOpen()) return;
            // Keep a list already on screen; say so only when there is nothing to show
            if (!view.notams) content.innerHTML = '<p class="text-xs opacity-60">NOTAMs could not be loaded right now. Check official sources before flight.</p>';
        }
    };
    view.load = load;
    await load();
    // Every minute: drop NOTAMs that have ended, update "Starts ..." labels. Every five
    // minutes: fetch the list again. Both stop once the airport view is closed.
    view.tick = setInterval(() => { if (stillOpen()) { if (view.notams) renderAirportNotams(view); } else clearInterval(view.tick); }, 60 * 1000);
    view.reload = setInterval(() => { if (stillOpen()) load(); else clearInterval(view.reload); }, 5 * 60 * 1000);
}

// Back from the background (a phone screen turned on, another tab): fetch at once if the
// list is more than a minute old, since timers may not have run in the meantime
document.addEventListener('visibilitychange', () => {
    const view = _airportNotamsView;
    if (document.visibilityState !== 'visible' || !airportNotamsViewOpen(view)) return;
    if (Date.now() - view.loadedAt > 60 * 1000) view.load();
});

// Draws the list, keeping the reader's place in it
function renderAirportNotams(view) {
    const { icao, content } = view;
    const esc = text => String(text).replace(/[&<>"]/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]));
    let scroller = content.parentElement;
    while (scroller && scroller !== document.body && !(scroller.scrollHeight > scroller.clientHeight && /auto|scroll/.test(getComputedStyle(scroller).overflowY))) scroller = scroller.parentElement;
    const scrollTop = scroller ? scroller.scrollTop : 0;
    const status = _airportNotamsStatus || {};
    if (!status.ok) {
        content.innerHTML = '<p class="text-xs opacity-60">NOTAMs are not available right now (the NOTAM copy is out of date). Check official sources before flight.</p>';
        return;
    }
    const notams = currentAirportNotams(view.notams);
    const asOf = airportNotamTime((status.as_of || '').slice(0, 16));
    const asOfText = isNaN(asOf) ? '' : `as of ${airspaceClock(asOf)}`;
    const header = document.querySelector('#airportNotamsSection h3');
    if (header) header.innerHTML = `NOTAMs${notams.length ? ` (${notams.length})` : ''} <span class="font-normal normal-case tracking-normal opacity-40 text-[9px]">${asOfText}</span>`;
    const footer = `<p class="mt-3 text-[10px] opacity-50">In force now or starting within three days, from the FAA NOTAM system. Updates every few minutes while open. May be incomplete: check official sources before flight.</p>`;
    if (notams.length === 0) {
        content.innerHTML = `<p class="text-xs opacity-60">No NOTAMs on file for ${esc(icao)}.</p>` + footer;
    } else {
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
    if (scroller) scroller.scrollTop = scrollTop;
}

'''.split('\n')
lines[i:j] = [(d + l) if l else '' for l in block]

# The PDF leaves out NOTAMs that have ended, too
i = find('try { airports.push({ icao: icao, notams: sortAirportNotams(await readAirportNotams(icao)) }); }')
lines[i] = lines[i].replace('sortAirportNotams(await readAirportNotams(icao))', 'sortAirportNotams(currentAirportNotams(await readAirportNotams(icao)))')
open(path, 'w', encoding='utf-8').write('\n'.join(lines))
print('patched', path)

"""Sorts an airport's NOTAM list into folding groups (Runways, Taxiways & aprons, ...), all
folded when an airport opens, with an "Open all" / "Fold all" button. The group comes from the
NOTAM's own Q-code (the subject its issuing office gave it) or, for US NOTAMs without one, from
the FAA keyword it must start with; anything else goes under Other, nothing is guessed from the
wording. Needs notam_schedule.py first. Works on either copy of the page."""
import sys
path = sys.argv[1]
lines = open(path, encoding='utf-8').read().split('\n')
if any('function airportNotamGroup(' in l for l in lines): sys.exit('already applied')
if not any('function airportNotamWhen(start, end, schedule) {' in l for l in lines): sys.exit('apply notam_schedule.py first')
def find(t, start=0):
    hits = [i for i, l in enumerate(lines) if i >= start and l.strip() == t]
    if not hits or (len(hits) != 1 and not start): sys.exit(f'{len(hits)} matches for {t!r}')
    return hits[0]
def indent(i):
    return lines[i][:len(lines[i]) - len(lines[i].lstrip())]

i = find("// Draws the list, keeping the reader's place in it")
pad = indent(i)
lines[i:i] = [pad + l if l else l for l in '''// The groups an airport's NOTAMs are filed under, in the order shown
const AIRPORT_NOTAM_GROUPS = ['Runways', 'Taxiways & aprons', 'Lighting', 'Approaches & procedures', 'Navaids & GPS',
    'Obstacles', 'Airspace & warnings', 'ATC & radio', 'Airport & services', 'Other'];

// A NOTAM's group, from its Q-code ("QMRLC": MR runway, LC closed), which the issuing office
// chose, or else from the keyword FAA rules make a US NOTAM start with ("RWY", "OBST", ...)
function airportNotamGroup(code, text) {
    const q = /^Q[A-Z]{4}$/.test(code || '') ? code.slice(1, 3) : '';
    if (q && q !== 'XX') {
        if (q[0] === 'M') return 'BCDHRSTUW'.includes(q[1]) ? 'Runways' : 'Taxiways & aprons';
        if (q[0] === 'O') return q === 'OB' || q === 'OL' ? 'Obstacles' : 'Other';
        const byLetter = { L: 'Lighting', P: 'Approaches & procedures', I: 'Navaids & GPS', G: 'Navaids & GPS',
            N: 'Navaids & GPS', A: 'Airspace & warnings', R: 'Airspace & warnings', W: 'Airspace & warnings',
            S: 'ATC & radio', C: 'ATC & radio', F: 'Airport & services' };
        if (byLetter[q[0]]) return byLetter[q[0]];
    }
    const upper = String(text || '').trim().toUpperCase();
    if (upper.startsWith('[US DOD PROCEDURAL NOTAM]')) return 'Approaches & procedures';
    const byKeyword = { RWY: 'Runways', TWY: 'Taxiways & aprons', APRON: 'Taxiways & aprons', RAMP: 'Taxiways & aprons',
        OBST: 'Obstacles', NAV: 'Navaids & GPS', COM: 'ATC & radio', SVC: 'Airport & services', AD: 'Airport & services',
        AERODROME: 'Airport & services', AIRSPACE: 'Airspace & warnings', SECURITY: 'Airspace & warnings',
        IAP: 'Approaches & procedures', ODP: 'Approaches & procedures', SID: 'Approaches & procedures',
        STAR: 'Approaches & procedures', CHART: 'Approaches & procedures', DATA: 'Approaches & procedures',
        VFP: 'Approaches & procedures' };
    return byKeyword[upper.split(/[\\s,.]/)[0]] || 'Other';
}

// Open or fold one group, or all of them, in the list on screen
function toggleAirportNotamGroup(group) {
    const view = _airportNotamsView;
    if (!view || !view.open) return;
    if (view.open.has(group)) view.open.delete(group); else view.open.add(group);
    renderAirportNotams(view);
}
function toggleAllAirportNotamGroups() {
    const view = _airportNotamsView;
    if (!view || !view.groups) return;
    const allOpen = view.groups.every(group => view.open.has(group));
    view.open = new Set(allOpen ? [] : view.groups);
    renderAirportNotams(view);
}
'''.split('\n')]

i = find('const rows = sortAirportNotams(notams).map(([number, start, end, issued, classification, text, schedule]) => {')
lines[i] = indent(i) + 'const row = ([number, start, end, issued, classification, text, schedule]) => {'
j = find("}).join('');", i)
pad = indent(j)
lines[j:j + 1] = [pad + l if l else l for l in '''};
// In groups, all folded when an airport opens; the reader's choice lasts while it stays open
if (!view.open) view.open = new Set();
const grouped = new Map(AIRPORT_NOTAM_GROUPS.map(group => [group, []]));
for (const notam of sortAirportNotams(notams)) grouped.get(airportNotamGroup(notam[7], notam[5])).push(notam);
const shown = [...grouped].filter(([, list]) => list.length);
view.groups = shown.map(([group]) => group);
const allOpen = view.groups.every(group => view.open.has(group));
const chevron = open => `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0;transition:transform .15s;transform:rotate(${open ? 180 : 0}deg)"><path d="M6 9l6 6 6-6"/></svg>`;
const openAll = shown.length > 1 ? `<button type="button" onclick="toggleAllAirportNotamGroups()" class="shrink-0 mb-2 flex items-center gap-1 rounded-full bg-black/30 hover:bg-black/40 px-3 py-1 text-[10px] font-black uppercase tracking-wider">${allOpen ? 'Fold all' : 'Open all'}${chevron(allOpen)}</button>` : '';
const rows = shown.map(([group, list]) => {
    const open = view.open.has(group);
    const later = list.filter(([, start]) => airportNotamTime(start) > _nowAccurate()).length;
    return `<div class="border-t border-white/10">
        <button type="button" onclick="toggleAirportNotamGroup(this.dataset.group)" data-group="${esc(group)}" aria-expanded="${open}" class="w-full flex items-center gap-2 py-2.5 text-left">
            <span class="text-[11px] font-black uppercase tracking-wider">${esc(group)}</span>
            <span class="rounded-full bg-black/30 px-2 text-[10px] font-bold">${list.length}</span>
            ${later ? `<span class="text-[10px] font-bold opacity-70">${later} starting later</span>` : ''}
            <span class="ml-auto">${chevron(open)}</span>
        </button>
        ${open ? `<div class="pb-2">${list.map(row).join('')}</div>` : ''}
    </div>`;
}).join('');'''.split('\n')]

i = find("content.innerHTML = toggle + rows + airportNotamRegionButton(icao) + footer;")
lines[i] = indent(i) + 'content.innerHTML = `<div class="flex items-center justify-between gap-2">${toggle}${openAll}</div>` + rows + airportNotamRegionButton(icao) + footer;'

open(path, 'w', encoding='utf-8').write('\n'.join(lines))
print('applied')

"""Shows a NOTAM's schedule (item D, "MON-FRI 2200-0400") in the airport NOTAM list and the
PDFs, so a runway closed only at night does not look closed all day. Works on either copy of
the page."""
import sys
path = sys.argv[1]
lines = open(path, encoding='utf-8').read().split('\n')
if any('function airportNotamWhen(start, end, schedule)' in l for l in lines): sys.exit('already applied')
def find(t, start=0):
    hits = [i for i, l in enumerate(lines) if i >= start and l.strip() == t]
    if not hits or (len(hits) != 1 and not start): sys.exit(f'{len(hits)} matches for {t!r}')
    return hits[0]
def indent(i):
    return lines[i][:len(lines[i]) - len(lines[i].lstrip())]
def replace(old, new):
    i = find(old)
    lines[i] = indent(i) + new

replace('// [number, start, end, issued, classification, text]',
        '// [number, start, end, issued, classification, text, schedule]')

i = find('// "In force until 23 Oct 2026", "Starts Sun 21:00Z, until ...", for screen and PDF')
j = find('function airportNotamWhen(start, end) {', i)
k = find('}', j)
pad = indent(j)
lines[i:k + 1] = [pad + l if l else l for l in '''// "In force until 23 Oct 2026", "Starts Sun 21:00Z, until ...", for screen and PDF. A NOTAM
// with a schedule (item D, "MON-FRI 2200-0400") applies only at those times within its
// period, so it is not called "in force" and the schedule is shown beside it
function airportNotamWhen(start, end, schedule) {
    const s = airportNotamTime(start), e = airportNotamTime(end), now = _nowAccurate();
    const until = end === 'PERM' ? 'permanent' : (isNaN(e) ? '' : `until ${airspaceClock(e)}`);
    const only = schedule ? `Only ${schedule} (times UTC)` : '';
    if (!isNaN(s) && s > now) return { soon: true, only: only, text: `Starts ${airspaceClock(s)}${until ? ', ' + until : ''}` };
    if (schedule) return { soon: false, only: only, text: `At set times${until ? (end === 'PERM' ? ', ' : ' ') + until : ''}` };
    return { soon: false, only: '', text: `In force${until ? (end === 'PERM' ? ', ' : ' ') + until : ''}` };
}'''.split('\n')]

# The list on screen
replace('const rows = sortAirportNotams(notams).map(([number, start, end, issued, classification, text]) => {',
        'const rows = sortAirportNotams(notams).map(([number, start, end, issued, classification, text, schedule]) => {')
i = find('const when = airportNotamWhen(start, end);', find('const rows = sortAirportNotams(notams).map(([number, start, end, issued, classification, text, schedule]) => {'))
lines[i] = indent(i) + 'const when = airportNotamWhen(start, end, schedule);'
i = find('<div class="flex flex-wrap items-baseline gap-x-2 text-[10px] uppercase tracking-wider"><span class="font-black">${esc(number)}</span><span class="normal-case tracking-normal font-bold ${when.soon ? \'bg-black/30 rounded px-1.5\' : \'opacity-90\'}">${esc(when.text)}</span></div>', i)
lines.insert(i + 1, indent(i) + '${when.only ? `<div class="mt-1"><span class="inline-block rounded px-1.5 py-0.5 text-[12px] font-black" style="background:#fde047;color:#000">${esc(when.only)}</span></div>` : \'\'}')

# The PDFs
replace('for (const [number, start, end, issued, classification, text] of airport.notams) {',
        'for (const [number, start, end, issued, classification, text, schedule] of airport.notams) {')
i = find('const when = airportNotamWhen(start, end);')
lines[i] = indent(i) + 'const when = airportNotamWhen(start, end, schedule);'
i = find('room(5 + Math.min(lines.length, 6) * 3.4);', i)
lines[i] = indent(i) + 'room(5 + (when.only ? 4 : 0) + Math.min(lines.length, 6) * 3.4);'
i = find('doc.text(when.text, PAGE_MARGIN + 2 + doc.getTextWidth(number) + 3, y);', i)
if lines[i + 1].strip() != 'y += 4;': sys.exit('PDF layout not as expected')
pad = indent(i)
lines[i + 2:i + 2] = [pad + l for l in [
    'if (when.only) {',
    '    doc.setFont("helvetica", "bold"); doc.setTextColor(0, 0, 0);',
    '    doc.text(when.only, PAGE_MARGIN + 2, y); y += 4;',
    '}']]

open(path, 'w', encoding='utf-8').write('\n'.join(lines))
print('applied')

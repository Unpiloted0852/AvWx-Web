"""In the NOTAM PDFs, a NOTAM that applies only at set times shows its schedule on a yellow
band and its text in ICAO form (B) start, C) end, D) schedule, E) text), so it cannot be
read as applying all day. Needs notam_schedule.py first. Works on either copy of the page."""
import sys
path = sys.argv[1]
lines = open(path, encoding='utf-8').read().split('\n')
if any('function airportNotamIcaoText(' in l for l in lines): sys.exit('already applied')
if not any('function airportNotamWhen(start, end, schedule) {' in l for l in lines): sys.exit('apply notam_schedule.py first')
def find(t, start=0):
    hits = [i for i, l in enumerate(lines) if i >= start and l.strip() == t]
    if not hits or (len(hits) != 1 and not start): sys.exit(f'{len(hits)} matches for {t!r}')
    return hits[0]
def indent(i):
    return lines[i][:len(lines[i]) - len(lines[i].lstrip())]

# A helper after airportNotamWhen
i = find('function airportNotamWhen(start, end, schedule) {')
k = find('}', i)
pad = indent(i)
lines[k + 1:k + 1] = [pad + l if l else l for l in '''
// A scheduled NOTAM's text in ICAO form for the PDFs: "B) 2610192200 C) 2610240400",
// "D) MON-FRI 2200-0400", "E) RWY 06/24 CLOSED", start and end in UTC
function airportNotamIcaoText(start, end, schedule, text) {
    const stamp = value => value === 'PERM' ? 'PERM' : String(value || '').replace(/\\D/g, '').slice(2, 12);
    return `B) ${stamp(start)} C) ${stamp(end)}\\nD) ${schedule}\\nE) ${text}`;
}'''.split('\n')]

# The PDFs
i = find('for (const [number, start, end, issued, classification, text, schedule] of airport.notams) {')
j = find("const lines = text.split('\\n').flatMap(part => doc.splitTextToSize(part || ' ', USABLE_WIDTH - 4));", i)
lines[j] = indent(j) + "const lines = (schedule ? airportNotamIcaoText(start, end, schedule, text) : text).split('\\n').flatMap(part => doc.splitTextToSize(part || ' ', USABLE_WIDTH - 4));"
j = find('doc.text(when.only, PAGE_MARGIN + 2, y); y += 4;', j)
pad = indent(j)
lines[j:j + 1] = [pad + l for l in [
    'doc.setFillColor(253, 224, 71);',
    'doc.rect(PAGE_MARGIN + 1, y - 3.1, doc.getTextWidth(when.only) + 2, 4.2, "F");',
    'doc.text(when.only, PAGE_MARGIN + 2, y); y += 4.6;']]
j = find('room(5 + (when.only ? 4 : 0) + Math.min(lines.length, 6) * 3.4);', i)
lines[j] = indent(j) + 'room(5 + (when.only ? 4.6 : 0) + Math.min(lines.length, 6) * 3.4);'

open(path, 'w', encoding='utf-8').write('\n'.join(lines))
print('applied')

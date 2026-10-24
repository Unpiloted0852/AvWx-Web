"""In the NOTAM PDFs, every NOTAM's text is shown in ICAO form (A) airport, B) start, C) end,
D) schedule when it has one, E) text), not only the scheduled ones. The coloured "In force" /
"Starts" note and the yellow schedule band stay. Needs notam_schedule_pdf.py first. Works on
either copy of the page."""
import sys
path = sys.argv[1]
lines = open(path, encoding='utf-8').read().split('\n')
if any('function airportNotamIcaoText(icao, start, end, schedule, text) {' in l for l in lines): sys.exit('already applied')
if not any('function airportNotamIcaoText(start, end, schedule, text) {' in l for l in lines): sys.exit('apply notam_schedule_pdf.py first')
def find(t, start=0):
    hits = [i for i, l in enumerate(lines) if i >= start and l.strip() == t]
    if not hits or (len(hits) != 1 and not start): sys.exit(f'{len(hits)} matches for {t!r}')
    return hits[0]
def indent(i):
    return lines[i][:len(lines[i]) - len(lines[i].lstrip())]
def replace(old, new):
    i = find(old)
    lines[i] = indent(i) + new

replace('''// A scheduled NOTAM's text in ICAO form for the PDFs: "B) 2610192200 C) 2610240400",''',
        '''// A NOTAM's text in ICAO form for the PDFs: "A) ELLX B) 2610192200 C) 2610240400",''')
replace('''// "D) MON-FRI 2200-0400", "E) RWY 06/24 CLOSED", start and end in UTC''',
        '''// "D) MON-FRI 2200-0400" when it has a schedule, "E) RWY 06/24 CLOSED"; start and end in UTC''')
replace('function airportNotamIcaoText(start, end, schedule, text) {',
        'function airportNotamIcaoText(icao, start, end, schedule, text) {')
replace('return `B) ${stamp(start)} C) ${stamp(end)}\\nD) ${schedule}\\nE) ${text}`;',
        'return `A) ${icao} B) ${stamp(start)} C) ${stamp(end)}\\n${schedule ? `D) ${schedule}\\n` : \'\'}E) ${text}`;')
replace("const lines = (schedule ? airportNotamIcaoText(start, end, schedule, text) : text).split('\\n').flatMap(part => doc.splitTextToSize(part || ' ', USABLE_WIDTH - 4));",
        "const lines = airportNotamIcaoText(airport.icao, start, end, schedule, text).split('\\n').flatMap(part => doc.splitTextToSize(part || ' ', USABLE_WIDTH - 4));")

open(path, 'w', encoding='utf-8').write('\n'.join(lines))
print('applied')

"""TAF times (FM, BECMG, TEMPO, PROB) were built from the current time with the milliseconds
left in, so a group starting at 19Z began a fraction of a second after 19:00 and the dashboard
slider only showed it from 20Z. Works on any copy of the page."""
import re, sys
path = sys.argv[1]
page = open(path, encoding='utf-8').read()
if 'date.setUTCHours(hour, 0, 0, 0);' in page: sys.exit('already applied')
old = r'''date\.setUTCHours\(hour\);\s*\n(\s*)date\.setUTCMinutes\(0\);\s*\n\s*date\.setUTCSeconds\(0\);\n'''
found = list(re.finditer(old, page))
if len(found) != 1: sys.exit(f'{len(found)} matches')
m = found[0]
page = page[:m.start()] + 'date.setUTCHours(hour, 0, 0, 0);   // whole hours, or a group starting at 19Z would only show from 20Z\n' + page[m.end():]
open(path, 'w', encoding='utf-8').write(page)

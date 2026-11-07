"""Dashboard tile pill: recognises ceilings marked CB or TCU, and shows the lowest ceiling
of any forecast line valid at the chosen time. Works on either copy of the page."""
import sys
path = sys.argv[1]
lines = open(path, encoding='utf-8').read().split('\n')
if any('allLines' in l for l in lines): sys.exit('already applied')
def find(t, start=0):
    hits = [i for i, l in enumerate(lines) if i >= start and l.strip() == t]
    if not hits or (len(hits) != 1 and not start): sys.exit(f'{len(hits)} matches for {t!r}')
    return hits[0]
def indent(i): return lines[i][:len(lines[i]) - len(lines[i].lstrip())]

# The pill's reading of the text
i = find('function extractBriefConditions(rawText) {')
lines[i] = indent(i) + 'function extractBriefConditions(rawText, allLinesText) {'
i = find(r'const clouds = clean.match(/\b(BKN|OVC|VV)\d{3}\b/g);', i); d = indent(i)
lines[i:i + 1] = [
    d + '// The ceiling shown is the lowest in any forecast line valid at the time (a TEMPO or',
    d + '// PROB line as much as the prevailing one), so the pill gives the worst to expect.',
    d + '// A layer may carry CB or TCU on the end.',
    d + r'const clouds = cleanRawText(allLinesText || rawText).match(/\b(BKN|OVC|VV)\d{3}(?:CB|TCU)?\b/g);',
    d + 'const height = layer => parseInt(layer.replace(/\\D/g, \'\'), 10);',
    d + '// Lowest first; at the same height the one marked CB or TCU says more',
    d + 'if (clouds) clouds.sort((a, b) => height(a) - height(b) || b.length - a.length);']

# Every line valid at the time, handed on beside the merged text
i = find('function getConditionsAtTime(tafRawText, targetTime) {')
j = find('activeTempos.forEach(tmp => {', i)
k = find('rawText: activeState,', j)
lines[k + 1:k + 1] = [indent(k) + 'allLines: allLines,']
lines[j:j] = [indent(j) + '// The prevailing conditions and each active TEMPO or PROB line, side by side',
              indent(j) + "const allLines = [activeState, ...activeTempos.map(tmp => tmp.text)].join(' ');"]
i = find('const condition = getConditionsAtTime(station.taf.rawText, target);')
j = find('displayText = condition.rawText;', i)
lines[j + 1:j + 1] = [indent(j) + 'worstText = condition.allLines;']
text = '\n'.join(lines)
for old, new in [("let displayCat = 'NODATA', displayText = '', windDir = 0,", "let displayCat = 'NODATA', displayText = '', worstText = '', windDir = 0,"),
                 ("extractBriefConditions(displayText)}", "extractBriefConditions(displayText, worstText)}")]:
    if text.count(old) != 1: sys.exit(f'{text.count(old)} matches for {old!r}')
    text = text.replace(old, new)
open(path, 'w', encoding='utf-8').write(text)
print('patched', path)

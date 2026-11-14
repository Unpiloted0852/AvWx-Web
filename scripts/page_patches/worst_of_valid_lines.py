"""Forecast at a chosen time follows one rule everywhere: the worst of any line valid then.
Flight category, wind, visibility, weather and ceiling. Apply after tile_pill_lowest_ceiling.py.
Works on either copy of the page."""
import sys
path = sys.argv[1]
lines = open(path, encoding='utf-8').read().split('\n')
if any('const pictures = [activeState' in l for l in lines): sys.exit('already applied')
def find(t, start=0):
    hits = [i for i, l in enumerate(lines) if i >= start and l.strip() == t]
    if not hits or (len(hits) != 1 and not start): sys.exit(f'{len(hits)} matches for {t!r}')
    return hits[0]
def indent(i): return lines[i][:len(lines[i]) - len(lines[i].lstrip())]

# --- getConditionsAtTime: category and wind ---
f = find('function getConditionsAtTime(tafRawText, targetTime) {')
i = find('// Apply them sequentially', f)
j = find('category: analyzeCondition(activeState)', i)
assert lines[j + 1].strip() == '};' and j - i < 16
d = indent(i)
lines[i:j + 2] = [d + l if l else '' for l in r'''// The rule for a chosen time: show the worst of any line valid then. Each active TEMPO
// or PROB line is laid over the prevailing conditions on its own, giving one picture of
// the weather per line, and the worst is taken from among those pictures.
const allLines = [activeState, ...activeTempos.map(tmp => tmp.text)].join(' ');
const pictures = [activeState, ...activeTempos.map(tmp => mergeCondition(activeState, tmp.text))];

// Flight category: the worst of the pictures
const categoryOrder = ['VFR', 'MVFR', 'IFR', 'LIFR'];
const category = pictures.map(text => analyzeCondition(text))
    .reduce((worst, c) => categoryOrder.indexOf(c) > categoryOrder.indexOf(worst) ? c : worst, 'VFR');

// Wind: the strongest, counting gusts. It goes first in the text handed back, which is
// where the tiles and the runway diagram read the wind from.
const windPattern = /\b(?:\d{3}|VRB)(\d{2,3})(?:G(\d{2,3}))?KT\b/;
let worstWind = null;
pictures.forEach(text => {
    const m = cleanRawText(text).match(windPattern);
    const strength = m ? parseInt(m[2] || m[1], 10) : -1;
    if (m && (!worstWind || strength > worstWind.strength)) worstWind = { token: m[0], strength: strength };
});
const rest = allLines.replace(new RegExp(windPattern.source, 'g'), ' ');

return {
    rawText: worstWind ? `${worstWind.token} ${rest}` : allLines,
    allLines: allLines,
    category: category
};'''.split('\n')]

# --- The tile's pill: visibility and weather from every valid line too ---
f = find('function extractBriefConditions(rawText, allLinesText) {')
i = find('const clean = cleanRawText(rawText);', f); lines[i] = indent(i) + 'const clean = cleanRawText(allLinesText || rawText);'
i = find(r'const vis = clean.match(/\b(M)?(\d+(?:\/\d+)?)SM\b/);', f); d = indent(i)
lines[i:i + 1] = [d + l for l in r'''// Visibility: the lowest in any of the lines, whether in statute miles or metres
// (9999, "10 km or more", is left out)
const visMetres = token => {
  if (!/SM$/.test(token)) return parseInt(token, 10);
  return token.replace(/^[MP]|SM$/g, '').split(' ').reduce((sum, part) => { const [a, b] = part.split('/'); return sum + (b ? a / b : +a); }, 0) * 1609;
};
const visTokens = (clean.match(/(?:^|\s)(?:[MP]?(?:\d+ )?\d+(?:\/\d+)?SM|\d{4})(?=\s|$)/g) || []).map(t => t.trim()).filter(t => t !== '9999');
const vis = visTokens.length ? [visTokens.reduce((low, t) => visMetres(t) < visMetres(low) ? t : low)] : null;'''.split('\n')]
i = find("parts.push(wxCodes.map(c => c.trim()).join(' '));", f)
lines[i] = indent(i) + "parts.push([...new Set(wxCodes.map(c => c.trim()))].join(' ')); // each kind of weather once"
open(path, 'w', encoding='utf-8').write('\n'.join(lines))
print('patched', path)

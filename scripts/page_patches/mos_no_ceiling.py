"""MOS panel: sources with no ceiling forecast (MOSMIX, raw ICON/GFS) no longer claim VFR.
Good visibility shows "VIS OK" (grey) unless the cloud cover is 3 oktas or less, so that no
layer can be broken or overcast; poor visibility shows its category with a * (the ceiling could
make it worse). Needs mos_sources.py first. Works on either copy of the page."""
import sys
path = sys.argv[1]
text = open(path, encoding='utf-8').read()
if 'function _mosCatNoCeiling(' in text: sys.exit('already applied')
if 'async function _fetchMosMosmix(lat, lon) {' not in text: sys.exit('apply mos_sources.py first')

def sub(old, new, count=1):
    global text
    if text.count(old) != count: sys.exit(f'{text.count(old)} matches for {old[:60]!r}')
    text = text.replace(old, new)

sub('function _catColor(cat) {', '''// For a source with no ceiling forecast. VFR needs both the visibility and the ceiling, so it
// is only shown when the cloud cover is 3 oktas (37%) or less, too little for a broken or
// overcast layer. Otherwise good visibility shows "VIS OK", and poor visibility its category
// with a * (from visibility alone: the ceiling could make it worse).
function _mosCatNoCeiling(visSm, totalCov) {
    if (visSm === null || visSm === undefined) return { cat: 'UNKN', catLabel: '--' };
    const visCat = visSm < 1 ? 'LIFR' : visSm < 3 ? 'IFR' : visSm <= 5 ? 'MVFR' : 'VFR';
    if (totalCov !== null && totalCov !== undefined && totalCov <= 37) return { cat: visCat, catLabel: null };
    if (visCat === 'VFR') return { cat: 'UNKN', catLabel: 'VIS OK' };
    return { cat: visCat, catLabel: visCat + '*' };
}
function _catColor(cat) {''')
sub("cat: _mosCat(null, visSm, null, w.cloud_cover ?? null),", "..._mosCatNoCeiling(visSm, w.cloud_cover ?? null),")
sub("cat:         _mosCat(cigFt, visSm, weatherCode, totalCov),", "..._mosCatNoCeiling(visSm, totalCov),")
note = ("It has no ceiling forecast, so VFR is only shown when the cloud cover is 3 oktas or less. "
        "VIS OK means good visibility with the ceiling unknown; a * means the category comes from visibility alone and the ceiling could make it worse.")
sub("It has no ceiling, so the colour comes from visibility only.", note, count=2)
sub('color:${_catColor(b.cat)};">${b.cat}</span>', 'color:${_catColor(b.cat)};">${b.catLabel || b.cat}</span>')
sub('letter-spacing:0.3px;">${b.cat}</div>', 'letter-spacing:0.3px;">${b.catLabel || b.cat}</div>')
sub('<div style="font-size:9px;font-weight:900;color:${accent};">${b.cat}</div>', '<div style="font-size:9px;font-weight:900;color:${accent};">${b.catLabel || b.cat}</div>')

open(path, 'w', encoding='utf-8').write(text)
print('applied')

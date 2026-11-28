"""Draws each part of a special use airspace area as its own shape, so parts that overlap
show darker instead of cancelling each other out. Works on either copy of the page."""
import sys
path = sys.argv[1]
lines = open(path, encoding='utf-8').read().split('\n')
if any('const tapInfo = { title: area.name' in l for l in lines): sys.exit('already applied')
def find(t, start=0):
    hits = [i for i, l in enumerate(lines) if i >= start and l.strip() == t]
    if not hits or (len(hits) != 1 and not start): sys.exit(f'{len(hits)} matches for {t!r}')
    return hits[0]
def indent(i): return lines[i][:len(lines[i]) - len(lines[i].lstrip())]

i = find('const rings = area.rings.map(flat => {'); d = indent(i)
lines[i:i + 1] = [d + '// A part listed twice is drawn once',
                  d + 'const rings = area.rings.filter((flat, at) => area.rings.findIndex(other => other.join() === flat.join()) === at).map(flat => {']
i = find('const shape = L.polygon(rings.map(points => [points]), {'); d = indent(i)
j = find("shape._tapInfo = { title: area.name, note: [area.kind, isActive ? 'active now' : 'not yet active'].filter(Boolean).join(' · '), html: () => airspacePopup(area, _nowAccurate()) };", i)
k = find('airspaceLayer.addLayer(shape);', j)
assert lines[k - 1].strip() == "shape.on('click', areaTapped);"
body = ['    ' + l for l in lines[i + 1:j]]
lines[i:k + 1] = [
    d + '// Each part is its own shape: where parts overlap the fill shows darker, and a tap',
    d + '// anywhere inside any of them finds the area. Drawn as one shape, overlaps would',
    d + '// cancel each other out and leave holes.',
    d + "const tapInfo = { title: area.name, note: [area.kind, isActive ? 'active now' : 'not yet active'].filter(Boolean).join(' · '), html: () => airspacePopup(area, _nowAccurate()),",
    d + '    latlngs: rings.map(points => [points.map(point => L.latLng(point))]) }; // the whole area, for the highlight',
    d + 'rings.forEach(points => {',
    d + '    const shape = L.polygon(points, {'] + body + [
    d + '    shape._tapInfo = tapInfo;',
    d + "    shape.on('click', areaTapped);",
    d + '    airspaceLayer.addLayer(shape);',
    d + '});']
text = '\n'.join(lines)
for old, new in [("latlngs: shape.getLatLngs(), closed:", "latlngs: shape._tapInfo.latlngs || shape.getLatLngs(), closed:"),
                 ("fill: hit.closed, fillColor: hit.colour, fillOpacity: 0.35 }", "fill: hit.closed, fillColor: hit.colour, fillOpacity: 0.35, fillRule: 'nonzero' }")]:
    if text.count(old) != 1: sys.exit(f'{text.count(old)} matches for {old!r}')
    text = text.replace(old, new)
open(path, 'w', encoding='utf-8').write(text)
print('patched', path)

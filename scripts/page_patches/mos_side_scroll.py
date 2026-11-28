"""Lets the MOS forecast timeline and comparison table scroll sideways with arrow buttons, a
mouse drag or the mouse wheel, as well as a finger. Works on any copy of the page."""
import re, sys
path = sys.argv[1]
page = open(path, encoding='utf-8').read()
if '_mosEnableSideScroll' in page: sys.exit('already applied')
def sub(old, new):
    # Indentation is ignored, as the Android app's copy of the page is laid out differently
    global page
    parts = [re.escape(l.strip()) for l in old.rstrip('\n').split('\n')]
    pattern = r'[ \t]*\r?\n[ \t]*'.join(parts)
    if old[0] in ' \t': pattern = r'[ \t]*' + pattern
    if old.endswith('\n'): pattern += r'[ \t]*\r?\n'
    found = list(re.finditer(pattern, page))
    if len(found) != 1: sys.exit(f'{len(found)} matches for {old[:70]!r}')
    page = page[:found[0].start()] + new + page[found[0].end():]

sub('''return `<div style="display:flex;gap:3px;overflow-x:auto;padding:10px 10px 6px;-webkit-overflow-scrolling:touch;">${cards}</div>''',
    '''return `<div class="mos-side-scroll" style="display:flex;gap:3px;overflow-x:auto;padding:10px 10px 6px;-webkit-overflow-scrolling:touch;">${cards}</div>''')
sub('''<div id="mosCompareScroll" style="overflow-x:auto;''', '''<div id="mosCompareScroll" class="mos-side-scroll" style="overflow-x:auto;''')
sub('''                ${rows}
            </div>
        </div>`;
''', '''                ${rows}
            </div>
        </div>`;
    _mosEnableSideScroll();
''')
sub('''        // Auto-select current hour
''', '''        _mosEnableSideScroll();
        // Auto-select current hour
''')
sub('''async function _loadMosData(icao, model) {
''', r'''// A finger can swipe the forecast sideways, but a mouse wheel only moves up and down and the
// scrollbar is thin. So add arrow buttons, dragging with the mouse, and the wheel. The wheel
// goes back to moving the card up and down once the forecast reaches either end.
function _mosEnableSideScroll() {
    const row = document.querySelector('#mosContent .mos-side-scroll');
    if (!row) return;
    const wrap = document.createElement('div');
    wrap.style.position = 'relative';
    row.before(wrap);
    wrap.appendChild(row);

    const arrow = (text, label, side, direction) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.textContent = text;
        btn.setAttribute('aria-label', label);
        btn.style.cssText = `position:absolute;top:50%;${side}:4px;transform:translateY(-50%);width:26px;height:34px;border-radius:7px;` +
            'border:1px solid rgba(255,255,255,0.35);background:rgba(0,0,0,0.7);color:#fff;font-size:11px;padding:0;cursor:pointer;z-index:2;';
        btn.onclick = e => {
            e.stopPropagation();
            row.scrollBy({ left: direction * row.clientWidth * 0.8, behavior: 'smooth' });
        };
        wrap.appendChild(btn);
        return btn;
    };
    const earlier = arrow('◀', 'Earlier in the forecast', 'left', -1);
    const later = arrow('▶', 'Later in the forecast', 'right', 1);
    const showArrows = () => {
        earlier.style.display = row.scrollLeft > 2 ? '' : 'none';
        later.style.display = row.scrollLeft < row.scrollWidth - row.clientWidth - 2 ? '' : 'none';
    };
    row.addEventListener('scroll', showArrows, { passive: true });
    new ResizeObserver(showArrows).observe(row);
    showArrows();

    row.addEventListener('wheel', e => {
        if (e.ctrlKey || Math.abs(e.deltaX) >= Math.abs(e.deltaY)) return;
        const atEnd = e.deltaY > 0 ? row.scrollLeft >= row.scrollWidth - row.clientWidth - 1 : row.scrollLeft <= 0;
        if (atEnd) return;
        e.preventDefault();
        row.scrollLeft += e.deltaY * (e.deltaMode === 1 ? 16 : 1);
    }, { passive: false });

    // Mouse only: a finger already scrolls this natively
    let dragFrom = null, dragged = false;
    row.style.cursor = 'grab';
    row.addEventListener('pointerdown', e => {
        if (e.pointerType !== 'mouse' || e.button !== 0) return;
        dragFrom = { x: e.clientX, left: row.scrollLeft };
        dragged = false;
    });
    row.addEventListener('pointermove', e => {
        if (!dragFrom) return;
        const moved = e.clientX - dragFrom.x;
        if (!dragged && Math.abs(moved) < 5) return;
        if (!dragged) { dragged = true; row.setPointerCapture(e.pointerId); row.style.cursor = 'grabbing'; }
        row.scrollLeft = dragFrom.left - moved;
    });
    const endDrag = () => { dragFrom = null; row.style.cursor = 'grab'; };
    row.addEventListener('pointerup', endDrag);
    row.addEventListener('pointercancel', endDrag);
    // A drag that ends on a forecast block should not also select that block
    row.addEventListener('click', e => {
        if (dragged) { e.stopPropagation(); dragged = false; }
    }, true);
}

async function _loadMosData(icao, model) {
''')
open(path, 'w', encoding='utf-8').write(page)

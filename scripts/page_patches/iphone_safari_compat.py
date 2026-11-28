"""Makes the page work on iPhones before iOS 16.4 (no "lookbehind" in patterns there, and
one use of it stopped the whole script), and gives every blurred panel the -webkit- line
that Safari before version 18 needs. Works on either copy of the page."""
import re, sys
path = sys.argv[1]
text = open(path, encoding='utf-8').read()
old = r"const visRegex = /\b(?<!\/)\d{4}(?!\/)\b|\b(?:M|P)?\d+(?:\s?\d\/\d)?SM\b/g;"
new = r"const visRegex = /(?:^|[^\/\w])\d{4}(?![\/\w])|\b(?:M|P)?\d+(?:\s?\d\/\d)?SM\b/g;"
if text.count(old) != 1: sys.exit(f'{text.count(old)} matches for the visibility pattern')
text = text.replace(old, new)
text = text.replace("// FIX: Use Lookbehind/Lookahead to ensure we don't match time groups like 2120/2123",
                    "// Four digits standing alone, not part of a time group like 2120/2123 (written\n        // without lookbehind, which iPhones before iOS 16.4 cannot read)") if text.count("// FIX: Use Lookbehind/Lookahead to ensure we don't match time groups like 2120/2123") == 1 else text
added = 0
def fix(m):
    global added
    start = m.start()
    block_start = max(text.rfind('{', 0, start), text.rfind('}', 0, start))
    block_end = text.find('}', start)
    if '-webkit-backdrop-filter' in text[block_start:block_end if block_end > 0 else start + 200]: return m.group(0)
    added += 1
    return f'-webkit-backdrop-filter: {m.group(1)}; {m.group(0)}'
text = re.sub(r'(?<![-\w])backdrop-filter:\s*([^;}\n]+)', fix, text)
open(path, 'w', encoding='utf-8').write(text)
print('patched', path, '- blur lines added:', added)

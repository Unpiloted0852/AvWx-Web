"""Copies the slim header (the <style id="compactHeaderMock"> and <script id="compactHeaderMockScript">
blocks) from test.html into another copy of the page, e.g. the app's."""
import re, sys
source = open(sys.argv[1], encoding='utf-8').read()
path = sys.argv[2]
page = open(path, encoding='utf-8').read()
if 'compactHeaderMock' in page:
    sys.exit('already applied')
style = re.search(r'<style id="compactHeaderMock">.*?</style>\n', source, re.S).group(0)
script = re.search(r'<script id="compactHeaderMockScript">.*?</script>\n', source, re.S).group(0)
page = page.replace('</head>', style + '</head>', 1)
i = page.rindex('</body>')
page = page[:i] + script + page[i:]
open(path, 'w', encoding='utf-8').write(page)
print('patched', path)

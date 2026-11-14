"""
One self-contained file of the animated explainer, to open by double-click
or to send to someone.

    python build/explainer_bundle.py

Reads   docs/explainer/index.html, data.js, scenes.js
Writes  docs/Analog_Finder_Explained.html

docs/explainer/index.html is the page as published (it has no <html> or
<head> of its own; the publisher adds them). This bundle adds a normal
document head and puts the two scripts inline, so it works offline. The two
web fonts still load from Google Fonts when online and fall back to system
fonts when not.
"""

import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cubelib as C

SRC = os.path.join(C.ROOT, "docs", "explainer")
DST = os.path.join(C.ROOT, "docs", "Analog_Finder_Explained.html")


def main():
    rd = lambda n: io.open(os.path.join(SRC, n), encoding="utf-8").read()
    page = rd("index.html")
    for name in ("data.js", "scenes.js"):
        tag = f'<script src="{name}"></script>'
        if page.count(tag) != 1:
            raise SystemExit(f"expected exactly one {tag}")
        page = page.replace(tag, "<script>\n" + rd(name).replace("</script", "<\\/script") + "\n</script>")
    doc = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
           '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
           '<style>html,body{margin:0}body{font:14px system-ui,sans-serif}[hidden]{display:none!important}</style>\n'
           '</head>\n<body>\n' + page + '\n</body>\n</html>\n')
    io.open(DST, "w", encoding="utf-8", newline="\n").write(doc)
    print(f"wrote {DST} ({os.path.getsize(DST)/1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

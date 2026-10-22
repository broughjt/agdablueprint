"""
Resolve fully qualified Agda names against the output of `agda --html`.

Agda writes one file `M.html` per module `M`, and (since Agda 2.7) marks each
definition site with a named anchor `<a id="n"></a>`, where `n` is the name
relative to `M`: `x` for a top level definition, `R.f` for a field `f` of a
record `R` or a definition `f` in a named inner module `R`. A fully qualified
name `M.n` does not say where `M` ends and `n` begins, since both may contain
dots, so we take the longest prefix that names a module with an HTML file.
"""
import html
import re
from pathlib import Path
from typing import Dict, Optional, Set, Tuple
from urllib.parse import quote

ANCHOR_RE = re.compile(r'<a id="([^"]+)"></a>')


class AgdaHtml:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self._anchors: Dict[str, Set[str]] = {}

    def anchors(self, module: str) -> Set[str]:
        if module not in self._anchors:
            text = (self.directory/f"{module}.html").read_text(encoding="utf-8")
            self._anchors[module] = {html.unescape(m)
                                     for m in ANCHOR_RE.findall(text)}
        return self._anchors[module]

    def resolve(self, name: str) -> Optional[Tuple[str, str]]:
        """Split `name` into a module and an anchor in that module's HTML file,
        or return None when no module defines it."""
        parts = name.split(".")
        for i in range(len(parts) - 1, 0, -1):
            module = ".".join(parts[:i])
            if (self.directory/f"{module}.html").exists():
                anchor = ".".join(parts[i:])
                if anchor in self.anchors(module):
                    return module, anchor
        return None


def split_name(name: str) -> Tuple[str, str]:
    """Without HTML to resolve against, guess that the last component is the
    definition and the rest is the module."""
    module, _, anchor = name.rpartition(".")
    return module, anchor


def url(dochome: str, module: str, anchor: str) -> str:
    return f"{dochome.rstrip('/')}/{module}.html#{quote(anchor, safe='')}"

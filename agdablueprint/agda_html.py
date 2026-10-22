"""
Resolve fully qualified Agda names against the output of `agda --html`.

Agda writes one file `M.html` per module `M`, whose anchors are character
offsets into the source: the definition site of a name `n` at offset `k` is
`<a id="k" href="M.html#k">n</a>`, linking to itself, and a name introduced by
`renaming (m to n)` gets an anchor `<a id="k">n</a>` at the renaming. Agda (since 2.7) also
writes a named anchor `<a id="R.n"></a>` beside it, but only for definitions
outside anonymous modules `module _ ... where`, which in practice leaves out
most of a library like cubical. So we recover the qualified name of every
definition site ourselves: stripping the tags gives back the source, with the
same offsets, and a pass over its layout tracks the named modules, records and
data types enclosing each line.

A fully qualified name `M.n` does not say where the module `M` ends and the
name `n` relative to it begins, since both may contain dots, so we take the
longest prefix that names a module with an HTML file defining the rest.
"""
import html
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote

PRE_RE = re.compile(r'<pre class="Agda">(.*)</pre>', re.DOTALL)
TAG_RE = re.compile(r'<[^>]*>')
NAMED_ANCHOR_RE = re.compile(r'<a id="([^"]+)"></a>')
DEFINITION_RE = r'<a id="(\d+)" href="{module}\.html#\1"[^>]*>([^<]*)</a>'
# The new name in `renaming (x to y)`, which has no definition site of its own.
RENAMING_RE = re.compile(r'>to</a>\s*<a id="(\d+)" class="[^"]*">([^<]*)</a>')
# A line opening a scope that qualifies the names declared in it.
SCOPE_RE = re.compile(
    r'(?:(?:private|abstract|open|instance|opaque|mutual)\s+)*'
    r'(?:module|record|data|interleaved\s+mutual)\s+(\S+)')


class AgdaModule:
    def __init__(self, name: str, text: str):
        self.name = name
        pre = PRE_RE.search(text)
        code = pre.group(1) if pre else text
        # Named anchors carry no text, so they do not shift the offsets.
        self.named = {html.unescape(a) for a in NAMED_ANCHOR_RE.findall(code)}
        source = html.unescape(TAG_RE.sub('', code))
        lines = source.split('\n')
        prefixes = qualifiers(lines)
        line_starts = [0] + [m.end() for m in re.finditer('\n', source)]
        self.definitions: Dict[str, List[int]] = {}
        pattern = re.compile(DEFINITION_RE.format(module=re.escape(name)))
        sites = [*pattern.finditer(code), *RENAMING_RE.finditer(code)]
        for m in sites:
            offset = int(m.group(1))
            line = bisect(line_starts, offset - 1)
            prefix = prefixes[line]
            names = [prefix]
            # A record constructor is in scope both inside the record and beside it.
            if prefix and lines[line].lstrip().startswith('constructor'):
                names.append(prefix[:-1])
            for prefix in names:
                qualified = ".".join(prefix + [html.unescape(m.group(2))])
                self.definitions.setdefault(qualified, []).append(offset)

    def anchor(self, name: str) -> Optional[str]:
        """The anchor of `name`, relative to this module, if it is defined here."""
        if name in self.named:
            return name
        offsets = self.definitions.get(name, [])
        if len(offsets) == 1:
            return str(offsets[0])
        return None


def qualifiers(lines: List[str]) -> List[List[str]]:
    """For each line of the source, the names of the scopes enclosing it."""
    stack: List[Tuple[int, Optional[str]]] = []
    result = []
    for line in lines:
        stripped = line.lstrip(' ')
        if not stripped or stripped.startswith('--'):
            result.append([name for _, name in stack if name])
            continue
        indent = len(line) - len(stripped)
        while stack and stack[-1][0] >= indent:
            stack.pop()
        result.append([name for _, name in stack if name])
        m = SCOPE_RE.match(stripped)
        if m:
            name = m.group(1)
            # The top level module of the file, anonymous modules and mutual
            # blocks do not qualify the names they contain.
            if indent == 0 and not stack and '.' in name:
                name = None
            elif name in ('_', 'where') or stripped.startswith(('mutual', 'interleaved')):
                name = None
            stack.append((indent, name))
    return result


def bisect(starts: List[int], position: int) -> int:
    lo, hi = 0, len(starts)
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if starts[mid] <= position:
            lo = mid
        else:
            hi = mid
    return lo


class AgdaHtml:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self._modules: Dict[str, AgdaModule] = {}

    def module(self, name: str) -> Optional[AgdaModule]:
        if name not in self._modules:
            path = self.directory/f"{name}.html"
            if not path.exists():
                return None
            self._modules[name] = AgdaModule(name, path.read_text(encoding="utf-8"))
        return self._modules[name]

    def resolve(self, name: str) -> Optional[Tuple[str, str]]:
        """Split `name` into a module and an anchor in that module's HTML file,
        or return None when no module defines it."""
        parts = name.split(".")
        for i in range(len(parts) - 1, 0, -1):
            module = self.module(".".join(parts[:i]))
            if module:
                anchor = module.anchor(".".join(parts[i:]))
                if anchor:
                    return module.name, anchor
        return None


def split_name(name: str) -> Tuple[str, str]:
    """Without HTML to resolve against, guess that the last component is the
    definition and the rest is the module."""
    module, _, anchor = name.rpartition(".")
    return module, anchor


def url(dochome: str, module: str, anchor: str) -> str:
    return f"{dochome.rstrip('/')}/{module}.html#{quote(anchor, safe='')}"

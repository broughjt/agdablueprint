"""
Package Agda blueprint

This depends on the depgraph plugin. This plugin has to be installed but then it is
used automatically.

Options:

* showmore: enable buttons showing or hiding proofs (this requires the showmore plugin).

You can also add options that will be passed to the dependency graph package.
"""
import string
from pathlib import Path

from jinja2 import Template
from plasTeX import Command
from plasTeX.Logging import getLogger
from plasTeX.PackageResource import PackageCss, PackageTemplateDir
from plastexdepgraph.Packages.depgraph import item_kind

from agdablueprint.agda_html import AgdaHtml, split_name, url

log = getLogger()

PKG_DIR = Path(__file__).parent
STATIC_DIR = Path(__file__).parent.parent/'static'


class home(Command):
    r"""\home{url}"""
    args = 'url:url'

    def invoke(self, tex):
        Command.invoke(self, tex)
        self.ownerDocument.userdata['project_home'] = self.attributes['url']
        return []


class github(Command):
    r"""\github{url}"""
    args = 'url:url'

    def invoke(self, tex):
        Command.invoke(self, tex)
        self.ownerDocument.userdata['project_github'] = self.attributes['url'].textContent.rstrip(
            '/')
        return []


class dochome(Command):
    r"""\dochome{url}"""
    args = 'url:url'

    def invoke(self, tex):
        Command.invoke(self, tex)
        self.ownerDocument.userdata['project_dochome'] = self.attributes['url'].textContent
        return []


class agdahtml(Command):
    r"""\agdahtml{path}: local output of agda --html, relative to the blueprint
    source, used to split qualified names into a module and an anchor."""
    args = 'path:str'

    def invoke(self, tex):
        Command.invoke(self, tex)
        self.ownerDocument.userdata['project_agdahtml'] = self.attributes['path'].strip()
        return []


class graphcolor(Command):
    r"""\graphcolor{node_type}{color}{color_descr}"""
    args = 'node_type:str color:str color_descr:str'

    def digest(self, tokens):
        Command.digest(self, tokens)
        attrs = self.attributes
        colors = self.ownerDocument.userdata['dep_graph']['colors']
        node_type = attrs['node_type']
        if node_type not in colors:
            log.warning(f'Unknown node type {node_type}')
        colors[node_type] = (attrs['color'].strip(), attrs['color_descr'].strip())


class agdaok(Command):
    r"""\agdaok"""

    def digest(self, tokens):
        Command.digest(self, tokens)
        self.parentNode.userdata['agdaok'] = True


class notready(Command):
    r"""\notready"""

    def digest(self, tokens):
        Command.digest(self, tokens)
        self.parentNode.userdata['notready'] = True


class libraryok(Command):
    r"""\libraryok"""

    def digest(self, tokens):
        Command.digest(self, tokens)
        self.parentNode.userdata['agdaok'] = True
        self.parentNode.userdata['libraryok'] = True


class agda(Command):
    r"""\agda{decl list} """
    args = 'decls:list:nox'

    def digest(self, tokens):
        Command.digest(self, tokens)
        decls = [dec.strip() for dec in self.attributes['decls']]
        self.parentNode.setUserData('agdadecls', decls)
        all_decls = self.ownerDocument.userdata.setdefault('agda_decls', [])
        all_decls.extend(decls)


class discussion(Command):
    r"""\discussion{issue_number} """
    args = 'issue:str'

    def digest(self, tokens):
        Command.digest(self, tokens)
        self.parentNode.setUserData(
            'issue', self.attributes['issue'].lstrip('#').strip())


CHECKMARK_TPL = Template("""
    {% if obj.userdata.agdaok and ('proved_by' not in obj.userdata or obj.userdata.proved_by.userdata.agdaok ) %}
    ✓
    {% endif %}
""")

AGDA_DECLS_TPL = Template("""
    {% if obj.userdata.agdadecls %}
    <button class="modal agda">Agda</button>
    {% call modal('Agda declarations') %}
        <ul class="uses">
          {% for agda, url in obj.userdata.agda_urls %}
          <li><a href="{{ url }}" class="agda_decl">{{ agda }}</a></li>
          {% endfor %}
        </ul>
    {% endcall %}
    {% endif %}
""")

GITHUB_ISSUE_TPL = Template("""
    {% if obj.userdata.issue %}
    <a class="github_link" href="{{ obj.ownerDocument.userdata.project_github }}/issues/{{ obj.userdata.issue }}">Discussion</a>
    {% endif %}
""")

AGDA_LINKS_TPL = Template("""
  {% if thm.userdata['agda_urls'] -%}
    {%- if thm.userdata['agda_urls']|length > 1 -%}
  <div class="tooltip">
      <span class="agda_link">Agda</span>
      <ul class="tooltip_list">
        {% for name, url in thm.userdata['agda_urls'] %}
           <li><a href="{{ url }}" class="agda_decl">{{ name }}</a></li>
        {% endfor %}
      </ul>
  </div>
    {%- else -%}
    <a class="agda_link agda_decl" href="{{ thm.userdata['agda_urls'][0][1] }}">Agda</a>
    {%- endif -%}
    {%- endif -%}
""")

GITHUB_LINK_TPL = Template("""
  {% if thm.userdata['issue'] -%}
  <a class="issue_link" href="{{ document.userdata['project_github'] }}/issues/{{ thm.userdata['issue'] }}">Discussion</a>
  {%- endif -%}
""")


def ProcessOptions(options, document):
    """This is called when the package is loaded."""

    # We want to ensure the depgraph and showmore packages are loaded.
    # We first need to make sure the corresponding plugins are used.
    # This is a bit hacky but needed for backward compatibility with
    # project who used the blueprint package before the depgraph one was
    # split.
    plugins = document.config['general'].data['plugins'].value
    if 'plastexdepgraph' not in plugins:
        plugins.append('plastexdepgraph')
    # And now load the package.
    document.context.loadPythonPackage(document, 'depgraph', options)
    if 'showmore' in options:
        if 'plastexshowmore' not in plugins:
            plugins.append('plastexshowmore')
        # And now load the package.
        document.context.loadPythonPackage(document, 'showmore', {})

    templatedir = PackageTemplateDir(path=PKG_DIR/'renderer_templates')
    document.addPackageResource(templatedir)

    jobname = document.userdata['jobname']
    outdir = document.config['files']['directory']
    outdir = string.Template(outdir).substitute({'jobname': jobname})

    def make_agda_data() -> None:
        """
        Build url and formalization status for nodes in the dependency graphs.
        Also create the file agda_decls of all Agda names referred to in the blueprint.
        """

        project_dochome = document.userdata.get('project_dochome', 'html')
        agdahtml = document.userdata.get('project_agdahtml')
        if agdahtml:
            agdahtml = AgdaHtml(Path(document.userdata['working-dir'])/agdahtml)

        for graph in document.userdata['dep_graph']['graphs'].values():
            nodes = graph.nodes
            for node in nodes:
                agdadecls = node.userdata.get('agdadecls', [])
                agda_urls = []
                for agdadecl in agdadecls:
                    resolved = agdahtml.resolve(agdadecl) if agdahtml else None
                    if agdahtml and not resolved:
                        log.warning(f"Could not find the Agda declaration {agdadecl}.")
                    module, anchor = resolved or split_name(agdadecl)
                    agda_urls.append(
                        (agdadecl, url(project_dochome, module, anchor)))

                node.userdata['agda_urls'] = agda_urls

                used = node.userdata.get('uses', [])
                node.userdata['can_state'] = all(thm.userdata.get('agdaok')
                                                 for thm in used) and not node.userdata.get('notready', False)
                proof = node.userdata.get('proved_by')
                if proof:
                    used.extend(proof.userdata.get('uses', []))
                    node.userdata['can_prove'] = all(thm.userdata.get('agdaok')
                                                     for thm in used)
                    node.userdata['proved'] = proof.userdata.get(
                        'agdaok', False)
                else:
                    node.userdata['can_prove'] = False
                    node.userdata['proved'] = False

            for node in nodes:
                node.userdata['fully_proved'] = all(n.userdata.get('proved', False) or item_kind(
                    n) == 'definition' for n in graph.ancestors(node).union({node}))

        agda_decls_path = Path(document.userdata['working-dir']).parent/"agda_decls"
        agda_decls_path.write_text("\n".join(document.userdata.get("agda_decls", [])))

    document.addPostParseCallbacks(150, make_agda_data)

    document.addPackageResource([PackageCss(path=STATIC_DIR/'blueprint.css')])

    colors = document.userdata['dep_graph']['colors'] = {
        'library': ('darkgreen', 'Dark green'),
        'stated': ('green', 'Green'),
        'can_state': ('blue', 'Blue'),
        'not_ready': ('#FFAA33', 'Orange'),
        'proved': ('#9CEC8B', 'Green'),
        'can_prove': ('#A3D6FF', 'Blue'),
        'defined': ('#B0ECA3', 'Light green'),
        'fully_proved': ('#1CAC78', 'Dark green')
    }

    def colorizer(node) -> str:
        data = node.userdata

        color = ''
        if data.get('libraryok'):
            color = colors['library'][0]
        elif data.get('agdaok'):
            color = colors['stated'][0]
        elif data.get('can_state'):
            color = colors['can_state'][0]
        elif data.get('notready'):
            color = colors['not_ready'][0]
        return color

    def fillcolorizer(node) -> str:
        data = node.userdata
        stated = data.get('agdaok')
        can_state = data.get('can_state')
        can_prove = data.get('can_prove')
        proved = data.get('proved')
        fully_proved = data.get('fully_proved')

        fillcolor = ''
        if proved:
            fillcolor = colors['proved'][0]
        elif can_prove and (can_state or stated):
            fillcolor = colors['can_prove'][0]
        if item_kind(node) == 'definition':
            if stated:
                fillcolor = colors['defined'][0]
            elif can_state:
                fillcolor = colors['can_prove'][0]
        elif fully_proved:
            fillcolor = colors['fully_proved'][0]
        return fillcolor

    document.userdata['dep_graph']['colorizer'] = colorizer
    document.userdata['dep_graph']['fillcolorizer'] = fillcolorizer

    def make_legend() -> None:
        """
        Extend the dependency graph legend defined by the depgraph plugin
        by adding information specific to Agda blueprints. This is registered
        as a post-parse callback to allow users to redefine colors and their 
        descriptions.
        """
        document.userdata['dep_graph']['legend'].extend([
            (f"{document.userdata['dep_graph']['colors']['can_state'][1]} border",
             "the <em>statement</em> of this result is ready to be formalized; all prerequisites are done"),
            (f"{document.userdata['dep_graph']['colors']['not_ready'][1]} border",
                "the <em>statement</em> of this result is not ready to be formalized; the blueprint needs more work"),
            (f"{document.userdata['dep_graph']['colors']['can_state'][1]} background",
                "the <em>proof</em> of this result is ready to be formalized; all prerequisites are done"),
            (f"{document.userdata['dep_graph']['colors']['proved'][1]} border",
                "the <em>statement</em> of this result is formalized"),
            (f"{document.userdata['dep_graph']['colors']['proved'][1]} background",
                "the <em>proof</em> of this result is formalized"),
            (f"{document.userdata['dep_graph']['colors']['fully_proved'][1]} background", 
                "the <em>proof</em> of this result and all its ancestors are formalized"),
            (f"{document.userdata['dep_graph']['colors']['library'][1]} border",
                "this is in a library dependency"),
        ])

    document.addPostParseCallbacks(150, make_legend)

    document.userdata.setdefault(
        'thm_header_extras_tpl', []).extend([CHECKMARK_TPL])
    document.userdata.setdefault('thm_header_hidden_extras_tpl', []).extend([AGDA_DECLS_TPL,
                                                                             GITHUB_ISSUE_TPL])
    document.userdata['dep_graph'].setdefault('extra_modal_links_tpl', []).extend([
        AGDA_LINKS_TPL, GITHUB_LINK_TPL])

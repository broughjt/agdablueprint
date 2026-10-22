import http.server
import logging
import os
import platform
import re
import shutil
import socketserver
import stat
import subprocess
import sys
import tomlkit
from tomlkit.toml_file import TOMLFile
from tomlkit import TOMLDocument
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional, NoReturn
from textwrap import dedent
from abc import ABC, abstractmethod

import rich_click as click
from git.exc import GitCommandError, InvalidGitRepositoryError
from git.repo import Repo
from jinja2 import Environment, FileSystemLoader
from rich.console import Console
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.theme import Theme

log = logging.getLogger("agdablueprint tools")
log.setLevel(logging.INFO)
if (log.hasHandlers()):
    log.handlers.clear()
log.addHandler(logging.StreamHandler())

# Click aliases from Stephen Rauch at
# https://stackoverflow.com/questions/46641928


class CustomMultiCommand(click.RichGroup):
    def command(self, *args, **kwargs):  # type: ignore
        """Behaves the same as `click.Group.command()` except if passed
        a list of names, all after the first will be aliases for the first.
        """
        def decorator(f):
            if args and isinstance(args[0], list):
                _args = [args[0][0]] + list(args[1:])
                for alias in args[0][1:]:
                    cmd = super(CustomMultiCommand, self).command(
                        alias, *args[1:], **kwargs)(f)
                    cmd.short_help = "Alias for '{}'".format(_args[0])
                    cmd.hidden = True
            else:
                _args = args
            cmd = super(CustomMultiCommand, self).command(
                *_args, **kwargs)(f)
            return cmd

        return decorator

    """Allows the user to shorten commands to a (unique) prefix."""

    def get_command(self, ctx, cmd_name):
        rv = click.Group.get_command(self, ctx, cmd_name)
        if rv is not None:
            return rv
        matches = [x for x in self.list_commands(ctx)
                   if x.startswith(cmd_name)]
        if not matches:
            return None
        elif len(matches) == 1:
            return click.Group.get_command(self, ctx, matches[0])
        ctx.fail('Too many matches: %s' % ', '.join(sorted(matches)))


debug = False


def handle_exception(exc, msg):
    if debug:
        raise exc
    else:
        log.error(msg)
        sys.exit(-1)


custom_theme = Theme({
    "info": "italic",
    "warning": "yellow",
    "error": "bold red",
    "title": "bold",
    "prompt.default": "dim",
    "prompt.choices": "default"
})

console = Console(theme=custom_theme)


def ask(*args, **kwargs) -> str:
    kwargs.update({'console': console})
    return Prompt.ask(*args, **kwargs)


def confirm(*args, **kwargs) -> bool:
    kwargs.update({'console': console})
    return Confirm.ask(*args, **kwargs)


def askInt(*args, **kwargs) -> int:
    kwargs.update({'console': console})
    return IntPrompt.ask(*args, **kwargs)


def warning(msg: str) -> None:
    console.print(f"[warning]Warning:[/] {msg}")


def error(msg: str) -> NoReturn:
    console.print(f"[error]Error:[/] {msg}")
    sys.exit(1)


@click.group(cls=CustomMultiCommand, context_settings={'help_option_names': ['-h', '--help']})
@click.option('--debug', 'python_debug', default=False, is_flag=True,
              help='Display python tracebacks in case of error.')
@click.version_option(package_name="agdablueprint")
def cli(python_debug: bool) -> None:
    """Command line client to manage Agda blueprints.
    Use agdablueprint COMMAND --help to get more help on any specific command."""
    global debug
    debug = python_debug


# locate repo

repo: Optional[Repo] = None
try:
    repo = Repo(".", search_parent_directories=True)
except InvalidGitRepositoryError:
    error("Could not find an Agda project. Please run this command from inside your project folder.")

assert repo is not None

# locate Agda library files

agdalib_paths = list(Path(repo.working_dir).glob("*.agda-lib"))

# blueprint root directory

blueprint_root = Path(repo.working_dir)/"blueprint"

@cli.command()
def new() -> None:
    """
    Create a new Agda blueprint in the given repository.
    """
    loader = FileSystemLoader(Path(__file__).parent/"templates")
    env = Environment(loader=loader, variable_start_string='{|', variable_end_string='|}',
                      comment_start_string='{--', comment_end_string='--}')

    console.print("\nWelcome to Agda blueprint\n", style="title")
    can_try_ci = True

    if repo is None:
        error("Could not find an Agda project. Please run this command from inside your project folder.")

    if repo.is_dirty():
        error("The repository contains uncommitted changes. Please clean it up before creating a blueprint.")

    # Will now try to guess the author name
    try:
        name = repo.git.config("user.name")
    except GitCommandError:
        try:
            # Name of the author of the first commit.
            name = deque(repo.iter_commits(), 1)[0].author.name
        except (IndexError, ValueError):
            # This will happen if there is no commit in the repo.
            name = "Anonymous"

    if len(agdalib_paths) == 0:
        warning(
            f"Could not find an .agda-lib file in {repo.working_dir}. Will not propose to setup continuous integration.")
        can_try_ci = False

    # Will now try to guess the GitHub url
    github = ""
    githubIO = ""
    doc_home = ""
    githubUserName = ""
    githubRepoName = ""
    try:
        url = repo.remote().url
    except ValueError:
        url = None
    if url:
        patterns = [r"https://github.com/(.*)/(.*)\.git",
                    r"https://github.com/(.*)/(.*)",
                    r"git@github.com:(.*)/(.*)\.git",
                    r"git@github.com:(.*)/(.*)"]
        m = next(m for m in map(lambda p: re.match(p, url), patterns) if m is not None)
        if m:
            githubUserName = m.group(1)
            githubRepoName = m.group(2)
        if githubUserName:
            github = f"https://github.com/{githubUserName}/{githubRepoName}"
            githubIO = f"https://{githubUserName}.github.io/{githubRepoName}"
            doc_home = f"https://{githubUserName}.github.io/{githubRepoName}/docs"
        else:
            warning(
                "Could not guess GitHub information. Will not propose to setup continuous integration.")
            can_try_ci = False

    out_dir = Path(repo.working_dir)/"blueprint"
    if out_dir.exists():
        error("There is already a blueprint folder. Aborting blueprint creation.")

    console.print("We will now ask some questions to configure your blueprint. All answers can be changed later by editing either the plastex.cfg file or the tex files.")
    config: Dict[str, Any] = dict()

    if 'master' in repo.heads:
        config['master_branch'] = "master"
    elif 'main' in repo.heads:
        config['master_branch'] = "main"
    else:
        config['master_branch'] = ask("\nName of your main Git branch")

    config['github_username'] = githubUserName
    config['github_projectname'] = githubRepoName

    console.print("\nGeneral information about the project", style="title")
    config['title'] = ask("Project title", default="My formalization project")
    config['lib_name'] = ask(
        "Agda library name", default=agdalib_paths[0].stem if agdalib_paths else "")
    config['author'] = ask(
        "Author ([info]use \\and to separate authors if needed[/])", default=name)

    config['github'] = ask("URL of GitHub repository", default=github)
    config['home'] = ask("URL of project website", default=githubIO)
    config['dochome'] = ask(
        "URL of project API documentation", default=doc_home)

    console.print("\nLaTeX settings for the pdf version", style="title")
    config['documentclass'] = ask("LaTeX document class", default="report")
    config['paper'] = ask("LaTeX paper", default="a4paper")

    console.print("\nLaTeX settings for the web version", style="title")
    config['showmore'] = confirm(
        "Show buttons allowing to show or hide all proofs", default=True)
    config['toc_depth'] = askInt("Table of contents depth", default=3)
    config['split_level'] = askInt(
        "Split file level [info](0 means each chapter gets a file, 1 means the same for sections etc.[/])", default=0)
    config['localtoc_level'] = askInt(
        "Per html file local table of contents depth [info](0 means there will be no local table of contents)[/]", default=0)

    console.print("\nConfiguration completed", style="title")

    if not confirm("Proceed with blueprint creation?"):
        error("Aborting blueprint creation per user request.")

    out_dir.mkdir()
    (out_dir/"src").mkdir()
    for tpl_name in env.list_templates():
        if tpl_name.endswith("blueprint.yml"):
            continue
        tpl = env.get_template(tpl_name)
        path = out_dir/"src"/tpl_name
        path.parent.mkdir(parents=True, exist_ok=True)
        tpl.stream(config).dump(str(path))

    if platform.system() == 'Windows':
        console.print(
            "\nBlueprint source successfully created in the blueprint folder.\n")
    else:
        console.print(
            "\nBlueprint source successfully created in the blueprint folder :tada:\n")

    home_page_created = False

    console.print("\nHomepage creation", style="title")
    if confirm("Do you want to create a home page for the project, "
               "with links to the blueprint, the API documentation and the "
               "repository?"):
        jekyll_loader = FileSystemLoader(Path(__file__).parent/"jekyll_templates")
        jekyll_env = Environment(loader=jekyll_loader, variable_start_string='{|', variable_end_string='|}',
                        comment_start_string='{--', comment_end_string='--}',
                        block_start_string='{%|', block_end_string='|%}')
        jekyll_out_dir = Path(repo.working_dir)/"home_page"
        if jekyll_out_dir.exists():
            error("There is already a home_page folder. Aborting.")
        else:
            home_page_created = True  
            author = config['author'].replace("\\and", "and") 
            config['web_title'] = ask("Home page title?", default=config["title"])
            config['web_subtitle'] = ask("Home page subtitle?", default=f"by {author}") 
            config['jekyll_theme'] = ask("Jekyll theme? (see https://github.com/pages-themes)", default="pages-themes/cayman@v0.2.0") 
            jekyll_out_dir.mkdir()
            for tpl_name in jekyll_env.list_templates():
                print(f"Handling {tpl_name}")
                tpl = jekyll_env.get_template(tpl_name)
                path = jekyll_out_dir/tpl_name
                path.parent.mkdir(parents=True, exist_ok=True)
                tpl.stream(config).dump(str(path))
            console.print("Ok, the home page template is created in `home_page`.")
            console.print("The main file you want to edit there is `index.md`.")

    console.print("\nGithub CI configuration", style="title")
    workflow_files: List[Path] = []
    if can_try_ci and confirm("Do you want to configure a Github CI action to compile and deploy the blueprint?"):
        config["main_module"] = ask(
            "Agda module importing everything, from which CI generates the HTML documentation")
        tpl = env.get_template("blueprint.yml")
        path = Path(repo.working_dir)/".github"/"workflows"
        path.mkdir(parents=True, exist_ok=True)
        tpl.stream(config).dump(str(path/"blueprint.yml"))
        console.print(
            f"GitHub workflow file created at {path/'blueprint.yml'}")
        workflow_files.append(path/'blueprint.yml')

    files_to_add = [out_dir] + workflow_files

    if home_page_created:
        files_to_add.append(jekyll_out_dir)

    if not confirm("\nCommit to git repository?"):
        console.print("You are all set! Don’t forget to commit whenever you feel ready.")
        sys.exit(0)

    msg = ask("Commit message", default="Setup blueprint")
    repo.index.add(files_to_add)
    repo.index.commit(msg)
    console.print(
        "Git commit created. Don't forget to push when you are ready.")
    if platform.system() == 'Windows':
        console.print("\nYou are all set!\n")
    else:
        console.print("\nYou are all set :tada:\n")

def mk_pdf() -> None:
    (blueprint_root/"print").mkdir(exist_ok=True)
    subprocess.run("latexmk -output-directory=../print", cwd=str(
        blueprint_root/"src"), check=True, shell=True)
    bbl_path = blueprint_root/"print"/"print.bbl"
    if bbl_path.exists():
        shutil.copy(bbl_path, blueprint_root/"src"/"web.bbl")

@cli.command()
def pdf() -> None:
    """
    Compile the pdf version of the blueprint using latexmk.
    """
    mk_pdf()


def mk_web() -> None:
    web_dir = blueprint_root/"web"
    web_dir.mkdir(exist_ok=True)
    # plasTeX copies its static files with shutil.copy2, which keeps their
    # permissions. Installed read-only (as in the Nix store), they cannot be
    # overwritten by the next run, so make the previous output writable.
    for path in web_dir.rglob("*"):
        if not path.is_symlink():
            path.chmod(path.stat().st_mode | stat.S_IWUSR)
    # Run plasTeX with this interpreter, which sees the plugins, rather than
    # whichever plastex executable comes first on the PATH.
    subprocess.run([sys.executable, "-c", "from plasTeX.client import plastex; plastex()",
                    "-c", "plastex.cfg", "web.tex"],
                   cwd=str(blueprint_root/"src"), check=True)
@cli.command()
def web() -> None:
    """
    Compile the html version of the blueprint using plasTeX.
    """
    mk_web()


def do_checkdecls(html_dir: Path) -> None:
    from agdablueprint.agda_html import AgdaHtml
    decls_path = blueprint_root/"agda_decls"
    if not decls_path.exists():
        error(f"Could not find {decls_path}. Run agdablueprint web first.")
    if not html_dir.is_dir():
        error(f"Could not find the Agda HTML in {html_dir}. Run agda --html first.")
    agda_html = AgdaHtml(html_dir)
    missing = [decl for decl in decls_path.read_text().split()
               if agda_html.resolve(decl) is None]
    for decl in missing:
        # Keep each name on one line so the output stays greppable.
        console.print(f"[error]{decl}[/] is missing.", soft_wrap=True)
    if missing:
        sys.exit(1)
    console.print("All declarations exist.")


html_dir_option = click.option(
    '--html-dir', type=click.Path(path_type=Path), default=Path("html"),
    show_default=True, help="Output of agda --html, relative to the repository root.")


@cli.command()
@html_dir_option
def checkdecls(html_dir: Path) -> None:
    """
    Check that each declaration named in \\agda exists in the Agda HTML.
    """
    do_checkdecls(Path(repo.working_dir)/html_dir)


@cli.command()
@html_dir_option
def all(html_dir: Path) -> None:
    """
    Compile both the pdf and html versions of the blueprint and check declarations.
    """
    mk_pdf()
    mk_web()
    do_checkdecls(Path(repo.working_dir)/html_dir)


@cli.command()
def serve() -> None:
    """
    Launch a web server to see the (already compiled) blueprint.

    This is useful is order to see the dependency graph in particular.
    """
    cwd = os.getcwd()
    os.chdir(blueprint_root/'web')
    Handler = http.server.SimpleHTTPRequestHandler
    httpd = None
    for port in range(8000, 8010):
        try:
            httpd = socketserver.TCPServer(("", port), Handler)
            break
        except OSError:
            pass
    if httpd is None:
        print("Could not find an available port.")
        sys.exit(1)
    try:
        (ip, port) = httpd.server_address
        ip = ip or 'localhost'
        print(f'Serving http://{ip}:{port}/ \nPress Ctrl-c to interrupt.')
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    httpd.server_close()
    os.chdir(cwd)


def safe_cli():
    try:
        cli()  # pylint: disable=no-value-for-parameter
    except Exception as err:
        handle_exception(err, str(err))


if __name__ == "__main__":
    # This allows `python3 -m agdablueprint.client`.
    # This is useful for when python is on the path but its installed scripts are not
    safe_cli()

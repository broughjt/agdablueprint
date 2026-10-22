# Agda blueprints

This is a [plasTeX](https://github.com/plastex/plastex/) plugin allowing
to write blueprints for Agda projects.
You can learn what those blueprints are about by reading
Terence Tao’s excellent [blog post about it](https://terrytao.wordpress.com/2023/11/18/formalizing-the-proof-of-pfr-in-lean4-using-blueprint-a-short-tour/).

This infrastructure was originally created in 2020 as [`leanblueprint`](https://github.com/PatrickMassot/leanblueprint) for the
[Sphere Eversion Project](https://leanprover-community.github.io/sphere-eversion/).
The present project is a fork of
[`rocqblueprint`](https://github.com/reiniscirpons/rocqblueprint), itself a
fork of `leanblueprint` adapted for use with Rocq, adapted in turn for Agda.

## Installation

This package depends on `plastexdepgraph` which requires graphviz and its development libraries. 
If you have a user-friendly OS, it is as simple as 
`sudo apt install graphviz libgraphviz-dev`. 
See https://pygraphviz.github.io/documentation/stable/install.html otherwise.

Then, assuming you have a sane python environment, you only need to run:
```
pip install git+https://github.com/broughjt/agdablueprint
```
Note this will automatically install plasTeX and the other needed python
packages.

With Nix, `nix run github:broughjt/agdablueprint -- <command>` runs the client,
and the flake's `packages.default` (with graphviz, plastexdepgraph and
plastexshowmore) can go in a project's dev shell.

## Starting a blueprint

This package provides a command line tool `agdablueprint` that automates in
particular the creation of a blueprint for your Agda project. This tool is not
mandatory in any way. Its goal is to make it easy to create a blueprint without
worrying about choosing a file layout or a continuous integration and deployment
setup. As every one–size-fits-all tool, it is fairly opinionated. It assumes in
particular that your project repository is hosted on Github and you want to host
its blueprint on github.io.

If you don’t want to use the `agdablueprint` command line tool, you can use
this plugin as any other plasTeX plugin, using
`plastex --plugins agdablueprint my_file.tex` (not recommended).

In order to use the `agdablueprint` tool, you need to already have an Agda
project with an `.agda-lib` file. The generated GitHub CI job builds the
documentation with `nix develop -c agda --html`, so it assumes a flake whose
default dev shell provides Agda with the project's dependencies. Edit
`.github/workflows/blueprint.yml` if your project is built differently.

In addition, your blueprint will be easier to
configure if you have at least one commit in the git repository of your project
and you have already configured its GitHub git remote (GitHub displays
instructions allowing to do the remote setup when you create a new repository
there). You should also tell GitHub that you want to use GitHub pages using
GitHub actions. You can do that from the GitHub page of your repository by
clicking on the Settings tab in the top menu, then the Pages link in the side
menu and selecting GitHub Actions as the source, as in the following
screenshot.

![GitHub pages settings](github_settings.png)

Assuming your project is ready and GitHub is configured, from your project
folder run 
```
agdablueprint new
```
You will then have to answer some questions to configure your blueprint. If
unsure, accept all default answers by simply hitting Enter for each question.
Only two questions will insist on having an explicit y/n answer: the question
confirming you want to create the blueprint and the one proposing to commit
to your git repository.

After running this creation script, you can push to GitHub and wait
for GitHub Actions to build your blueprint. You can monitor this task 
in the Actions tab of the GitHub page of your repository. 
When building is done, the html version of your blueprint will be deployed to 
`https://user_name.github.io/repo_name/blueprint/` (with the appropriate
user or organization name and repository name). The pdf version will be at 
`https://user_name.github.io/repo_name/blueprint.pdf`.
The Agda HTML will be at `https://user_name.github.io/repo_name/docs/`.

## Local compilation

Assuming you used the `agdablueprint` command line tool to create your blueprint
(or at least that you use the same file layout), you can use `agdablueprint` to
build your blueprint locally. The available commands are:

* `agdablueprint pdf` to build the pdf version (this requires a TeX installation
  of course).
* `agdablueprint web` to build the web version
* `agdablueprint checkdecls` to check that every Agda declaration name that
  appears in the blueprint exists in the project or one of its dependencies.
  This reads the `blueprint/agda_decls` file written by `agdablueprint web` and
  the output of `agda --html`, by default in `html` at the repository root
  (`--html-dir` changes it), so run both beforehand.
* `agdablueprint all` to run the previous three commands.
* `agdablueprint serve` to start a local webserver showing your local blueprint
  (this sounds silly but web browsers paranoia makes it impossible to simply
  open the generated html pages without serving them). The url you should use
  in your browser will be displayed and will probably be `http://0.0.0.0:8000/`,
  unless the port 8000 is already in use.

Note: plasTeX does not call BibTeX. If you have a bibliography, you should use
`agdablueprint pdf` before `agdablueprint web` to get it to work in the web
version (and redo it when you add a reference).

## Editing the blueprint

Assuming you used the `agdablueprint` command line tool to create your blueprint
(or at least that you use the same file layout), the source of your blueprint
will be in the `blueprint/src` subfolder of your Agda project folder.

Here you will find two main TeX files: `web.tex` and `print.tex`. The first one
is intended for plasTeX while the second one is intended for a traditional TeX
compiler such as `xelatex` or `lualatex`. 
Each of them includes `macros/common.tex` for all TeX macros that make sense
for both kinds of outputs (this should be most of your macros). 
Macros that should behave differently depending on the target format should go
to either `macros/web.tex` or `macros/print.tex`. All those files already exist
and contains comments reminding you about the above explanations.

The main content of your blueprint should live in `content.tex` (or in files
imported in `content.tex` if you want to split your content).

The main TeX macros that relate your TeX code to your Agda code are:

* `\agda` that lists the fully qualified Agda names corresponding to the
  surrounding definition or statement, such as `Cubical.Foundations.Prelude.refl`
  or, for a record field, `Cubical.Algebra.Group.Base.IsGroup.·InvL`.
* `\agdaok` which claims the surrounding environment is fully formalized. Here
  an environment could be either a definition/statement or a proof.
* `\uses` that lists LaTeX labels that are used in the surrounding environment.
  This information is used to create the dependency graph. Here
  an environment could be either a definition/statement or a proof, depending on
  whether the referenced labels are necessary to state the definition/theorem
  or only in the proof.

The example below show those essential macros in action, assuming the existence of
LaTeX labels `def:solvable_group`, `thm:minSimple_odd_group_ind` and `lem:no_minSimple_odd_group` and
assuming the existence of an Agda declaration `FeitThompson.Main.feitThompson`.

```latex
\begin{theorem}[Feit-Thompson, 1963]
  \label{thm:Feit_Thompson}
  \agda{FeitThompson.Main.feitThompson}
  \agdaok
  \uses{def:solvable_group}
  Every finite group of odd order is solvable.
\end{theorem}
  
\begin{proof}
  \agdaok
  \uses{thm:minSimple_odd_group_ind, lem:no_minSimple_odd_group}
  This obviously follows from what we did so far.
\end{proof}
```

Note that the proof above is abbreviated in this documentation. 
Be nice to you and your collaborators and include more details in your blueprint proofs!

By default, the dependency graph will collect the environments definition,
lemma, proposition, theorem and corollary. You can change this list using the
`thms` option which expects a list of environment names separated by `+` signs. 
For instance you can write
```latex
\usepackage[thms=dfn+lem+prop+thm+cor]{blueprint}
```
if you like short environment names. See the 
[plastexdepgraph documentation](https://github.com/PatrickMassot/plastexdepgraph/blob/master/README.md) 
for other dependency graph options having nothing to do with Agda.
Note that this is giving the `depgraph` package options directly when loading
the `blueprint` package. Do not load the `depgraph` package separately.


The above macros are by far the most important, but there are a couple more.

* `\notready` which claims the surrounding environment is not ready to be formalized,
  typically because it requires more blueprint work.
* `\discussion` gives a GitHub issue number where the surrounding definition or
  statement is discussed.
* `\proves` inside a proof environment gives the LaTeX label of the LaTeX
  statement being proved. This is necessary only when the proof does not
  immediately follow the statement.
* `\libraryok` marks nodes that were already merged into a library the project
  depends on, such as the standard library or the cubical library.

## Blueprint configuration

Most of the configuration is handled during the blueprint creation if you used
the `agdablueprint` client. But some of it can be changed by LaTeX macros
in the web version of LaTeX preamble (in the file `web.tex` if you use the
default layout).

* `\home{url}` defines the url of the home page of the project.
* `\github{url}` defines the url of the git repository of the project.
* `\dochome{url}` defines the url of the output of `agda --html`. Declaration
  links point to `<url>/<module>.html#<name>`, using the named anchors Agda
  writes since version 2.7.
* `\agdahtml{path}` points to a local copy of the output of `agda --html`,
  relative to the blueprint source. A qualified name like `A.B.C.d` does not say
  whether the module is `A.B.C` with definition `d` or `A.B` with definition
  `C.d` in an inner module or record `C`. With `\agdahtml`, the plugin takes the
  longest module prefix whose HTML defines the rest, and warns about names it
  cannot find. Without it, the last component is taken as the definition.
* `\graphcolor{node_type}{color}{description}` sets a color in the dependency
  graph and its description in the legend. The default values are
    * `stated`, `green`, `Green`
    * `can_state`, `blue`, `Blue`
    * `not_ready`, `#FFAA33`, `Orange`
    * `proved`, `#9CEC8B`, `Green`
    * `can_prove`, `#A3D6FF`, `Blue`
    * `defined`, `#B0ECA3`, `Light green`
    * `fully_proved`, `#1CAC78`, `Dark green`
    * `library`, `darkgreen`, `Dark green`

    In particular you can use the above color descriptions to interpret the node
    type by comparison with the default legend.

## Acknowledgments

The `agdablueprint` tool is based on the excellent `leanblueprint` tool by
Patrick Massot, by way of Reinis Cirpons's `rocqblueprint`.

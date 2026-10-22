# agdablueprint

This is a fork of [rocqblueprint](https://github.com/reiniscirpons/rocqblueprint) for Agda, which is itself a fork of Patrick Massot's
[leanblueprint](https://github.com/PatrickMassot/leanblueprint). You should first read the READMEs for the Rocq fork and the original Lean project. Here, I will list a few things that are different for the Agda fork.

## Installation

With Nix, run the client from the flake:

```sh
nix run github:broughjt/agdablueprint -- web
```

or put it in a project's dev shell:

```nix
inputs.agdablueprint.url = "github:broughjt/agdablueprint";
# ...
devShells.default = pkgs.mkShell {
  packages = [
    agdablueprint.packages.${system}.default
    pkgs.graphviz
    pkgs.texliveFull # for agdablueprint pdf, and images in the web version
  ];
};
```

The package bundles the client with plasTeX, plastexdepgraph and
plastexshowmore.

Without Nix, run
`pip install git+https://github.com/broughjt/agdablueprint`, after installing
graphviz and its development headers for pygraphviz.

## TODO: Write rest of README

{
  description = "plasTeX plugin and client for Agda formalization blueprints";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs?ref=nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
    plastexdepgraph = {
      url = "github:PatrickMassot/plastexdepgraph";
      flake = false;
    };
    plastexshowmore = {
      url = "github:PatrickMassot/plastexshowmore";
      flake = false;
    };
  };

  outputs = { self, nixpkgs, flake-utils, plastexdepgraph, plastexshowmore }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python3;
        plugin = name: version: src: dependencies: python.pkgs.buildPythonPackage {
          pname = name;
          inherit version src dependencies;
          pyproject = true;
          build-system = [ python.pkgs.setuptools ];
        };
        plastexdepgraph' = plugin "plastexdepgraph" "0.0.5" plastexdepgraph
          (with python.pkgs; [ plasTeX pygraphviz ]);
        plastexshowmore' = plugin "plastexshowmore" "0.0.2" plastexshowmore
          (with python.pkgs; [ plasTeX ]);
        agdablueprint' = python.pkgs.buildPythonPackage {
          pname = "agdablueprint";
          version = (builtins.fromTOML (builtins.readFile ./pyproject.toml)).project.version;
          src = self;
          pyproject = true;
          build-system = [ python.pkgs.setuptools ];
          dependencies = (with python.pkgs; [
            plasTeX click rich rich-click tomlkit jinja2 gitpython
          ]) ++ [ plastexdepgraph' plastexshowmore' ];
          pythonImportsCheck = [ "agdablueprint.Packages.blueprint" ];
        };
        # `agdablueprint web` shells out to plastex, which has to see the
        # plugins, so ship both executables in one environment.
        agdablueprint = python.withPackages (_: [ agdablueprint' ]);
      in {
        packages = {
          inherit agdablueprint;
          default = agdablueprint;
        };

        apps.default = {
          type = "app";
          program = "${agdablueprint}/bin/agdablueprint";
        };

        devShells.default = pkgs.mkShell {
          packages = [ agdablueprint pkgs.graphviz ];
        };
      });
}

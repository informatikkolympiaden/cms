{
    inputs.nixpkgs.url = "nixpkgs/nixos-23.05";

    outputs = {self, nixpkgs, ...}@inputs:
    let
        allSystems = [
            "x86_64-linux"
        ];
        forAllSystems = fn: nixpkgs.lib.genAttrs allSystems
            (system: fn { inherit system; pkgs = import nixpkgs {inherit system; }; });

    in {
        packages = forAllSystems ({pkgs, system}: {
            default = import ./nix/default.nix { inherit pkgs; };
        });
    };
}

{ lib
, stdenv
, buildPythonPackage
, fetchPypi
}:

buildPythonPackage rec {
    pname = "pyxdg";
    version = "0.26";

    src = fetchPypi {
        inherit pname version;
        hash = "sha256-/iko0/Uy7TKznDKkgrVBNv52bRmTavyWyPAGRfnaGgY=";
    };
}

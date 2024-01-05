{ lib
, stdenv
, buildPythonPackage
, fetchPypi
, markupsafe
}:

buildPythonPackage rec {
    pname = "Jinja2";
    version = "2.10.3";

    src = fetchPypi {
        inherit pname version;
        hash = "sha256-n+lfGShs/vqpF2Vlg9AgvhTnhZxrAlJYg5HkfbNFJ94=";
    };

    propagatedBuildInputs = [
        markupsafe
    ];
}

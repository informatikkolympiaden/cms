{ lib
, stdenv
, buildPythonPackage
, fetchPypi
, pytz
}:

buildPythonPackage rec {
    pname = "Babel";
    version = "2.6.0";

    src = fetchPypi {
        inherit pname version;
        sha256 = "sha256-jLpQ9IxSnKP6GM+B+pQDvhdtN0rE1gc4uDkSLfqqPSM=";
    };

    doCheck = false;

    propagatedBuildInputs = [
        pytz
    ];
}

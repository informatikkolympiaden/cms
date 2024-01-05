{ lib
, stdenv
, buildPythonPackage
, fetchPypi
}:

buildPythonPackage rec {
  pname = "MarkupSafe";
  version = "0.23";
  #format = "pyproject";

  src = fetchPypi {
    inherit pname version;
    hash = "sha256-pOwa/1m5WhS0XrLiN2GgF56YMZ2lp+t2tW6ozce4ccM=";
  };
}

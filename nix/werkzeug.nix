{ lib
, stdenv
, buildPythonPackage
, fetchPypi
, setuptools
, requests
}:

buildPythonPackage rec {
  pname = "Werkzeug";
  version = "0.16.1";
  format = "pyproject";

  src = fetchPypi {
    inherit pname version;
    hash = "sha256-s1OFbTfexZ1lETWfl/akskaEQuRUvRyYKY3c5TysHwQ=";
  };

  nativeBuildInputs = [
    setuptools
  ];

  propagatedBuildInputs = [
    requests
  ];

  disabledTests = lib.optionals stdenv.isDarwin [
    "test_get_machine_id"
  ];

  disabledTestPaths = [
    # ConnectionRefusedError: [Errno 111] Connection refused
    "tests/test_serving.py"
  ];

  pytestFlagsArray = [
    # don't run tests that are marked with filterwarnings, they fail with
    # warnings._OptionError: unknown warning category: 'pytest.PytestUnraisableExceptionWarning'
    "-m 'not filterwarnings'"
  ];

  meta = with lib; {
    homepage = "https://palletsprojects.com/p/werkzeug/";
    description = "The comprehensive WSGI web application library";
    longDescription = ''
      Werkzeug is a comprehensive WSGI web application library. It
      began as a simple collection of various utilities for WSGI
      applications and has become one of the most advanced WSGI
      utility libraries.
    '';
    license = licenses.bsd3;
    maintainers = with maintainers; [ ];
  };
}

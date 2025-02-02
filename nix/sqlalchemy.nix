{ stdenv, lib, fetchPypi, buildPythonPackage, isPy3k, fetchpatch
, mock
, pytestCheckHook
}:

buildPythonPackage rec {
  pname = "SQLAlchemy";
  version = "1.3.23";

  src = fetchPypi {
    inherit pname version;
    sha256 = "6fca33672578666f657c131552c4ef8979c1606e494f78cd5199742dfb26918b";
  };

  patches = [
    # fix test_pyodbc_extra_connect_azure test failure
    (fetchpatch {
      url = "https://github.com/sqlalchemy/sqlalchemy/commit/7293b3dc0e9eb3dae84ffd831494b85355df8e73.patch";
      sha256 = "1z61lzxamz74771ddlqmbxba1dcr77f016vqfcmb44dxb228w2db";
    })
  ];

  checkInputs = [
    pytestCheckHook
    mock
  ];

  checkPhase = ''
    echo "Starting tests"
  '';

  postInstall = ''
    sed -e 's:--max-worker-restart=5::g' -i setup.cfg
  '';

  dontUseSetuptoolsCheck = true;

  # disable mem-usage tests on mac, has trouble serializing pickle files
  disabledTests = [ "exception_persistent_flush_py3k "]
    ++ lib.optionals stdenv.isDarwin [ "MemUsageWBackendTest" "MemUsageTest" ];

  meta = with lib; {
    homepage = "http://www.sqlalchemy.org/";
    description = "A Python SQL toolkit and Object Relational Mapper";
    license = licenses.mit;
  };
}

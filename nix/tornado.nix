{ lib
, stdenv
, buildPythonPackage
, fetchPypi
, pytestCheckHook
}:

buildPythonPackage rec {
    pname = "tornado";
    version = "4.5.3";

    src = fetchPypi {
        inherit pname version;
        hash = "sha256-bRTkfqsOFXmc883MhrC5gnnaaFIsqs4r185kQodoXwo=";
    };

    nativeCheckInputs = [
        pytestCheckHook
    ];

    disabledTestPaths = [
        "tornado/test/asyncio_test.py"
        "tornado/test/iostream_test.py"
    ];

    disabledTests = [
        "RunOnExecutorTest"
        "BodyLimitsTest"
        "HTTPServerRawTest"
        "QueueGetTest"
        "MaxHeaderSizeTest"
        "MaxBodySizeTest"
        "ChunkedWithContentLengthTest"
        "WaitIteratorTest"
        "UnixSocketTest"
    ];
}

{pkgs ? import <nixpkgs> {}}:

let
    oldPkgs = import (pkgs.fetchFromGitHub {
        owner = "nixos";
        repo = "nixpkgs";
        rev = "refs/tags/20.03";
        sha256 = "sha256-mEKkeLgUrzAsdEaJ/1wdvYn0YZBAKEG3AN21koD2AgU=";
    }) {};

    python = pkgs.python38;

    babel_2_6 = python.pkgs.callPackage (import ./babel.nix) {};
    sqlalchemy_1_3 = python.pkgs.callPackage (import ./sqlalchemy.nix) {};
    werkzeug_0_16 = python.pkgs.callPackage (import ./werkzeug.nix) {};
    markupsafe_0_23 = python.pkgs.callPackage (import ./markupsafe.nix) {};
    pyxdg_0_26 = python.pkgs.callPackage (import ./pyxdg.nix) {};
    jinja2_2_10 = python.pkgs.callPackage (import ./jinja2.nix) {
        markupsafe = markupsafe_0_23;
    };
    tornado_4_5 = python.pkgs.callPackage (import ./tornado.nix) {};

    #patool_1_12 = python.pkgs.callPackage (import ./patool.nix) {};
in


python.pkgs.buildPythonPackage rec {
    name = "cms";
    src = ../.;

    /*
    preCheck = ''
        rm -rf "cmstestsuite/unit_tests/service"
        rm -rf "cmstestsuite/unit_tests/server"
        rm -rf "cmstestsuite/unit_tests/io"
        rm -rf "cmstestsuite/unit_tests/db"
        rm -rf "cmstestsuite/unit_tests/cmscontrib"
        rm "cmstestsuite/unit_tests/grading/scoring_test.py"
        rm "cmstestsuite/unit_tests/cmscommon/mimetypes_test.py"
      '';
    */

    disabledTests = [
        "PrintingService"
        "setUpClass"
    ];

    disabledTestPaths = [
        "cmstestsuite/unit_tests/service/**"
        "cmstestsuite/unit_tests/server/**"
        "cmstestsuite/unit_tests/io/**"
        "cmstestsuite/unit_tests/db/**"
        "cmstestsuite/unit_tests/cmscontrib/**"
        "cmstestsuite/unit_tests/grading/scoring_test.py"
        "cmstestsuite/unit_tests/grading/scoretypes/**"
        "cmstestsuite/unit_tests/cmscommon/mimetypes_test.py"
    ];

    doCheck = false;

    nativeCheckInputs = [
        python.pkgs.pytestCheckHook
    ];

    checkInputs = [
        python.pkgs.beautifulsoup4
    ];

    propagatedBuildInputs = with python.pkgs; [
        psycopg2
        netifaces
        pycryptodomex
        psutil
        requests
        gevent
        greenlet
        bcrypt
        chardet
        pyyaml
        setuptools

        #werkzeug
        #markupsafe
        #pyxdg
        #jinja2

        babel_2_6
        sqlalchemy_1_3
        werkzeug_0_16
        markupsafe_0_23
        pyxdg_0_26
        jinja2_2_10
        tornado_4_5

        patool

    ];
}

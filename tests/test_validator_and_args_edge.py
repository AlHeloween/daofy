#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Supplementary boundary tests for Validator and ArgsGenerator

New coverage:
  Validator:
    - validate_file_path: empty path / path traversal / nonexistent / not a file / non-.pas extension
    - validate_compiler_path: non-file path (directory) / non-executable extension
    - validate_output_path: empty path (allowed) / not a directory / path traversal
    - validate_search_paths: None list / list containing a nonexistent path (warning only) / path traversal
    - validate_timeout: negative / boundaries 1 and 3600 / over 3600
    - validate_warning_level: negative / 5

  ArgsGenerator:
    - generate: no conditional defines / no search paths / DLL output type / static runtime
    - validate_args: illegal argument containing $ / illegal argument containing ; / quoted argument
    - format_command: path with spaces / path without spaces
    - generate_for_file: default namespaces / include paths / output_dir / disabled_warnings
"""

import sys
import os
import tempfile
import shutil
from pathlib import Path

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import pytest

from src.utils.validator import Validator
from src.services.args_generator import ArgsGenerator
from src.models.compile_request import (
    CompileOptions, OutputType, RuntimeLibrary, TargetPlatform,
)


# ============================================================
# Validator — validate_file_path
# ============================================================

class TestValidateFilePath:

    def test_empty_path(self):
        ok, msg = Validator.validate_file_path("")
        assert not ok
        assert "must not be empty" in msg

    def test_path_traversal(self):
        ok, msg = Validator.validate_file_path(r"C:\..\secret.pas")
        assert not ok
        assert ".." in msg

    def test_nonexistent_file(self):
        ok, msg = Validator.validate_file_path(r"C:\nonexistent_12345.pas")
        assert not ok

    def test_non_pas_extension(self):
        fd, path = tempfile.mkstemp(suffix=".txt")
        os.close(fd)
        try:
            ok, msg = Validator.validate_file_path(path)
            assert not ok
            assert ".pas" in msg
        finally:
            os.unlink(path)

    def test_directory_instead_of_file(self):
        tmpdir = tempfile.mkdtemp()
        try:
            ok, msg = Validator.validate_file_path(tmpdir)
            assert not ok
            assert "not a file" in msg
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_valid_pas_file(self):
        fd, path = tempfile.mkstemp(suffix=".pas")
        os.close(fd)
        try:
            ok, msg = Validator.validate_file_path(path)
            assert ok
        finally:
            os.unlink(path)


# ============================================================
# Validator — validate_compiler_path (supplementary)
# ============================================================

class TestValidateCompilerPathExtra:

    def test_directory_instead_of_file(self):
        tmpdir = tempfile.mkdtemp()
        try:
            ok, msg = Validator.validate_compiler_path(tmpdir)
            assert not ok
            assert "not a file" in msg
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_non_executable_extension(self):
        fd, path = tempfile.mkstemp(suffix=".pas")
        os.close(fd)
        try:
            ok, msg = Validator.validate_compiler_path(path)
            assert not ok
            assert "executable" in msg
        finally:
            os.unlink(path)


# ============================================================
# Validator — validate_output_path (supplementary)
# ============================================================

class TestValidateOutputPathExtra:

    def test_empty_path_is_valid(self):
        ok, msg = Validator.validate_output_path("")
        assert ok

    def test_path_traversal(self):
        ok, msg = Validator.validate_output_path(r"C:\..\output")
        assert not ok

    def test_file_instead_of_directory(self):
        fd, path = tempfile.mkstemp()
        os.close(fd)
        try:
            ok, msg = Validator.validate_output_path(path)
            assert not ok
            assert "not a directory" in msg
        finally:
            os.unlink(path)


# ============================================================
# Validator — validate_search_paths (supplementary)
# ============================================================

class TestValidateSearchPathsExtra:

    def test_none_is_valid(self):
        ok, msg = Validator.validate_search_paths(None)
        assert ok

    def test_path_with_nonexistent_warns_but_ok(self):
        ok, msg = Validator.validate_search_paths([r"C:\nonexistent_dir_99999"])
        assert ok

    def test_mixed_valid_and_traversal(self):
        tmpdir = tempfile.mkdtemp()
        try:
            ok, msg = Validator.validate_search_paths([tmpdir, r"C:\..\bad"])
            assert not ok
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)


# ============================================================
# Validator — validate_timeout boundaries
# ============================================================

class TestValidateTimeoutBoundary:

    def test_boundary_1(self):
        ok, _ = Validator.validate_timeout(1)
        assert ok

    def test_boundary_3600(self):
        ok, _ = Validator.validate_timeout(3600)
        assert ok

    def test_over_3600(self):
        ok, msg = Validator.validate_timeout(3601)
        assert not ok

    def test_negative(self):
        ok, msg = Validator.validate_timeout(-1)
        assert not ok


# ============================================================
# Validator — validate_warning_level boundaries
# ============================================================

class TestValidateWarningLevelBoundary:

    def test_boundary_0(self):
        ok, _ = Validator.validate_warning_level(0)
        assert ok

    def test_boundary_4(self):
        ok, _ = Validator.validate_warning_level(4)
        assert ok

    def test_negative(self):
        ok, msg = Validator.validate_warning_level(-1)
        assert not ok


# ============================================================
# ArgsGenerator — generate (supplementary)
# ============================================================

class TestArgsGeneratorGenerate:

    def test_dll_output_type(self):
        gen = ArgsGenerator()
        opts = CompileOptions(output_type=OutputType.DLL)
        args = gen.generate("Project.dpr", opts)
        assert "-LD" in args

    def test_static_runtime(self):
        gen = ArgsGenerator()
        opts = CompileOptions(runtime_library=RuntimeLibrary.STATIC)
        args = gen.generate("Project.dpr", opts)
        assert "-$Y-" in args

    def test_no_conditional_defines(self):
        gen = ArgsGenerator()
        opts = CompileOptions(conditional_defines=[])
        args = gen.generate("Project.dpr", opts)
        assert not any("-$D+" in a and ";" in a for a in args)

    def test_no_search_paths(self):
        gen = ArgsGenerator()
        opts = CompileOptions(unit_search_paths=[], resource_search_paths=[])
        args = gen.generate("Project.dpr", opts)
        assert not any(a.startswith("-U") for a in args)
        assert not any(a.startswith("-R") for a in args)

    def test_optimization_disabled(self):
        gen = ArgsGenerator()
        opts = CompileOptions(optimize=False)
        args = gen.generate("Project.dpr", opts)
        assert "-$O-" in args

    def test_debug_enabled(self):
        gen = ArgsGenerator()
        opts = CompileOptions(debug=True)
        args = gen.generate("Project.dpr", opts)
        assert "-$D+" in args

    def test_extra_args_are_appended_last(self):
        gen = ArgsGenerator()
        opts = CompileOptions(extra_args=["-VT", "-VR"])
        args = gen.generate("Project.dpr", opts)
        assert args[-3:] == ["-GD", "-VT", "-VR"]


# ============================================================
# ArgsGenerator — validate_args boundaries
# ============================================================

class TestArgsGeneratorValidateArgs:

    def test_dollar_sign_in_non_param(self):
        gen = ArgsGenerator()
        assert not gen.validate_args(["Project.dpr", "$MALICIOUS"])

    def test_semicolon_in_non_param(self):
        gen = ArgsGenerator()
        assert not gen.validate_args(["Project.dpr", "evil;rm -rf"])

    def test_quoted_arg_with_pipe_passes(self):
        """A pipe inside quotes is treated as safe (quotes isolate shell injection)"""
        gen = ArgsGenerator()
        assert gen.validate_args(['-U"C:\\Lib|evil"'])

    def test_unquoted_path_param_with_pipe(self):
        gen = ArgsGenerator()
        assert not gen.validate_args(["-UC:\\Lib|evil"])

    def test_clean_args_pass(self):
        gen = ArgsGenerator()
        assert gen.validate_args(["Project.dpr", "-U", "C:\\Lib", "-$O+"])

    def test_ampersand_in_arg(self):
        gen = ArgsGenerator()
        assert not gen.validate_args(["Project.dpr", "cmd1&cmd2"])

    def test_msbuild_extra_properties_are_batch_safe(self):
        gen = ArgsGenerator()
        assert gen.validate_batch_extra_args([
            "/p:DCC_DebugInfoInTds=true",
            "/p:DCC_UnitSearchPath=$(BDS)\\lib;C:\\Shared Lib",
        ])

    @pytest.mark.parametrize("arg", [
        "/p:Flag=true&whoami",
        "/p:Flag=%COMSPEC%",
        "/p:Flag=!COMSPEC!",
        "/p:Flag=\"quoted\"",
        "/p:Flag=true\r\nwhoami",
    ])
    def test_msbuild_extra_properties_reject_batch_metacharacters(self, arg):
        gen = ArgsGenerator()
        assert not gen.validate_batch_extra_args([arg])


# ============================================================
# ArgsGenerator — format_command
# ============================================================

class TestArgsGeneratorFormatCommand:

    def test_path_with_spaces_quoted(self):
        gen = ArgsGenerator()
        cmd = gen.format_command(r"C:\Program Files\dcc32.exe", ["Project.dpr"])
        assert '"C:\\Program Files\\dcc32.exe"' in cmd

    def test_path_without_spaces(self):
        gen = ArgsGenerator()
        cmd = gen.format_command(r"C:\dcc32.exe", ["Project.dpr"])
        assert cmd.startswith("C:\\dcc32.exe ")


# ============================================================
# ArgsGenerator — generate_for_file (supplementary)
# ============================================================

class TestArgsGeneratorGenerateForFile:

    def test_default_namespaces(self):
        gen = ArgsGenerator()
        args = gen.generate_for_file("Unit.pas")
        ns_args = [a for a in args if a.startswith("-NS")]
        assert len(ns_args) == 1
        assert "System" in ns_args[0]
        assert "Winapi" in ns_args[0]

    def test_custom_namespaces(self):
        gen = ArgsGenerator()
        args = gen.generate_for_file("Unit.pas", namespaces=["Custom.NS"])
        ns_args = [a for a in args if a.startswith("-NS")]
        assert "Custom.NS" in ns_args[0]

    def test_include_paths(self):
        gen = ArgsGenerator()
        args = gen.generate_for_file("Unit.pas", include_paths=["C:\\Include"])
        assert any(a.startswith("-I") and "Include" in a for a in args)

    def test_output_dir(self):
        gen = ArgsGenerator()
        args = gen.generate_for_file("Unit.pas", output_dir="C:\\Output")
        assert any(a.startswith("-N") and "Output" in a for a in args)

    def test_disabled_warnings(self):
        gen = ArgsGenerator()
        args = gen.generate_for_file("Unit.pas", disabled_warnings=["W1000", "W1001"])
        assert "-$W-W1000" in args
        assert "-$W-W1001" in args

    def test_no_debug_info_flag(self):
        gen = ArgsGenerator()
        args = gen.generate_for_file("Unit.pas")
        assert "-$M-" in args

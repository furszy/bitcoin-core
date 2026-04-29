#!/usr/bin/env python3
# Copyright (c) present The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.

"""Tests for test/lint/tools/scripted_diff.py.

Unit tests (no git) cover transforms and file application.
Integration tests create a temporary git repo for operations.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

# Allow importing from the same directory when running standalone.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scripted_diff import (
    OperationError, apply_to_file, build_transform,
    op_rename, op_rename_file,
)


class TestBuildTransform(unittest.TestCase):

    def test_word_replaces_whole_words_only(self):
        t = build_transform("word", "foo", "bar")
        self.assertEqual(t("foo foobar foo"), "bar foobar bar")

    def test_word_replacement_is_literal(self):
        """Backslashes in the replacement are not interpreted as backrefs."""
        t = build_transform("word", "foo", r"bar\1")
        self.assertEqual(t("foo"), r"bar\1")

    def test_literal_replaces_substrings(self):
        t = build_transform("literal", "foo", "bar")
        self.assertEqual(t("foobar"), "barbar")

    def test_regex_with_capture_groups(self):
        t = build_transform("regex", r"old(\w+)", r"new\1")
        self.assertEqual(t("oldName"), "newName")

    def test_regex_multiline_anchor(self):
        t = build_transform("regex", r"^class Foo;\n", "")
        self.assertEqual(t("int x;\nclass Foo;\nint y;\n"), "int x;\nint y;\n")

    def test_bad_mode_raises(self):
        with self.assertRaises(OperationError):
            build_transform("bad", "x", "y")

    def test_bad_regex_raises(self):
        with self.assertRaises(OperationError):
            build_transform("regex", "[invalid", "x")


class TestApplyToFile(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _write(self, name, content):
        path = os.path.join(self.tmpdir, name)
        with open(path, "w") as f:
            f.write(content)
        return path

    def _read(self, name):
        with open(os.path.join(self.tmpdir, name)) as f:
            return f.read()

    def test_modifies_and_returns_true(self):
        path = self._write("a.cpp", "int foo = 1;\n")
        self.assertTrue(apply_to_file(path, build_transform("word", "foo", "bar")))
        self.assertEqual(self._read("a.cpp"), "int bar = 1;\n")

    def test_no_match_returns_false(self):
        path = self._write("a.cpp", "int baz = 1;\n")
        self.assertFalse(apply_to_file(path, build_transform("word", "foo", "bar")))

    def test_binary_file_skipped(self):
        path = os.path.join(self.tmpdir, "bin.dat")
        with open(path, "wb") as f:
            f.write(b"\x00\x01\xff")
        self.assertFalse(apply_to_file(path, build_transform("literal", "\x00", "x")))


class TestOperations(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        repo = cls.repo = tempfile.mkdtemp(prefix="sd-test-")
        subprocess.run(["git", "-C", repo, "init", "-q", "-b", "main"],
                       check=True, capture_output=True)
        subprocess.run(["git", "-C", repo, "config", "user.email", "t@example.com"],
                       check=True, capture_output=True)
        subprocess.run(["git", "-C", repo, "config", "user.name", "Test"],
                       check=True, capture_output=True)
        os.makedirs(os.path.join(repo, "src"))
        for name, content in [("src/foo.cpp", "int oldName = 1;\n"),
                              ("src/bar.cpp", "int oldName = 2;\n")]:
            with open(os.path.join(repo, name), "w") as f:
                f.write(content)
        subprocess.run(["git", "-C", repo, "add", "-A"], check=True, capture_output=True)
        subprocess.run(["git", "-C", repo, "commit", "-q", "-m", "baseline"],
                       check=True, capture_output=True)
        cls.baseline = subprocess.run(
            ["git", "-C", repo, "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True).stdout.strip()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.repo, ignore_errors=True)

    def setUp(self):
        self.orig_cwd = os.getcwd()
        os.chdir(self.repo)

    def tearDown(self):
        os.chdir(self.orig_cwd)
        subprocess.run(["git", "-C", self.repo, "reset", "-q", "--hard", self.baseline],
                       check=True, capture_output=True)
        subprocess.run(["git", "-C", self.repo, "clean", "-fdq"],
                       check=True, capture_output=True)

    def _read(self, relpath):
        with open(os.path.join(self.repo, relpath)) as f:
            return f.read()

    def test_rename_word(self):
        result = op_rename(["word", "oldName", "newName", "src/*.cpp"])
        self.assertEqual(result, ["src/bar.cpp", "src/foo.cpp"])
        self.assertEqual(self._read("src/foo.cpp"), "int newName = 1;\n")

    def test_rename_no_match(self):
        self.assertEqual(op_rename(["word", "nonexistent", "x", "src/*.cpp"]), [])

    def test_rename_file(self):
        result = op_rename_file(["src/foo.cpp", "src/wallet/foo.cpp"])
        self.assertEqual(result, ["src/foo.cpp -> src/wallet/foo.cpp"])
        self.assertFalse(os.path.exists(os.path.join(self.repo, "src/foo.cpp")))
        self.assertTrue(os.path.exists(os.path.join(self.repo, "src/wallet/foo.cpp")))

    def test_injection_is_inert(self):
        """Shell metacharacters in args are treated as literal text."""
        canary = os.path.join(tempfile.gettempdir(), "sd-canary")
        os.makedirs(canary, exist_ok=True)
        self.addCleanup(shutil.rmtree, canary, True)
        with open(os.path.join(canary, "file"), "w") as f:
            f.write("alive\n")
        op_rename(["word", f"$(rm -rf {canary})", "newName", "src/foo.cpp"])
        self.assertTrue(os.path.exists(os.path.join(canary, "file")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
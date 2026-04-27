#!/usr/bin/env python3
# Copyright (c) present The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.

"""Sanity tests for test/lint/commit-script-check.

The verifier walks a commit range and, for each commit whose subject
starts with `scripted-diff:`, extracts a script body framed by
`-BEGIN VERIFY SCRIPT-` / `-END VERIFY SCRIPT-` markers in the
message. It checks out the commit's parent, runs the script, and
diffs the result against the recorded commit. If the diff is empty,
the recipe is faithful and the commit passes; otherwise it fails.

These tests cover the verifier's functionality:
argument handling, subject filtering, missing-recipe detection,
orphan-marker detection, and the pass/fail outcome of recipe replay.

Run standalone: python3 -m unittest <unit test name>

Note: The current commit-script-check.sh requires GNU sed and grep,
      so tests are skipped on macOS and Windows.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

# Obtain script verifier path
SCRIPT_VERIFIER = os.environ.get("VERIFIER_PATH")
if SCRIPT_VERIFIER is None:
    REPO_ROOT = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip()
    SCRIPT_VERIFIER = os.path.join(REPO_ROOT, "test", "lint", "commit-script-check.sh")


def git(repo, *args):
    """Run a git command in `repo`. Returns captured stdout."""
    return subprocess.run(["git", "-C", repo, *args], check=True,
                          capture_output=True, text=True).stdout


def write_file(repo, relpath, content):
    """Write `content` to `repo/relpath`, creating parent dirs as needed."""
    path = os.path.join(repo, relpath)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def create_commit(repo, message, mutate_fn=None):
    """Commit the current working tree with `message`.

    If `mutate_fn` is given, it is called first to mutate the tree;
    everything is then staged. If omitted, an empty commit is made
    (useful for tests that only care about the commit's metadata)."""
    if mutate_fn is not None:
        mutate_fn()
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", message)
    else:
        git(repo, "commit", "-q", "--allow-empty", "-m", message)


def make_scripted_diff_commit(repo, subject, recipe, mutate_fn):
    """Make a commit with a scripted-diff message format.

    `subject` is automatically prefixed with `scripted-diff: `; pass
    the rest of the title only. `recipe` becomes the body framed by
    `-BEGIN VERIFY SCRIPT-` / `-END VERIFY SCRIPT-` markers.
    `mutate_fn` mutates the working tree before committing; its
    result must reflect what the recipe is supposed to produce."""
    message = (f"scripted-diff: {subject}\n\n"
               "-BEGIN VERIFY SCRIPT-\n"
               f"{recipe}\n"
               "-END VERIFY SCRIPT-\n")
    create_commit(repo, message, mutate_fn)


@unittest.skipUnless(sys.platform.startswith("linux"),
    "commit-script-check.sh requires GNU sed and grep (not available by default on macOS/Windows)")
class TestCommitScriptCheck(unittest.TestCase):
    """Each test runs against a shared repo with a single baseline
    commit. tearDown resets the repo to that baseline so the next
    test starts from the same state."""

    @classmethod
    def setUpClass(cls):
        repo = cls.repo = tempfile.mkdtemp(prefix="csc-test-")
        git(repo, "init", "-q", "-b", "main")
        git(repo, "config", "user.email", "t@example.com")
        git(repo, "config", "user.name", "Test")
        create_commit(repo, "baseline",
            lambda: write_file(repo, "src/foo.cpp", "int oldName = 1;\n"))
        cls.baseline = git(repo, "rev-parse", "HEAD").strip()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.repo, ignore_errors=True)

    def tearDown(self):
        # Revert any commits or working-tree changes the test made,
        # so the next test starts from the same baseline.
        git(self.repo, "reset", "-q", "--hard", self.baseline)
        git(self.repo, "clean", "-fdq")

    def run_verifier(self, *args):
        return subprocess.run([SCRIPT_VERIFIER, *args], cwd=self.repo,
                              capture_output=True, text=True)

    def test_no_args_fails(self):
        """The verifier refuses to run without arguments."""
        r = self.run_verifier()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Usage", r.stdout + r.stderr)

    def test_regular_commit_skipped(self):
        """A commit without `scripted-diff:` in its subject is a no-op."""
        create_commit(self.repo, "regular: nothing special")
        r = self.run_verifier("HEAD~1..HEAD")
        self.assertEqual(r.returncode, 0, r.stderr)
        # The verifier shouldn't have processed the commit at all.
        self.assertNotIn("OK", r.stderr)
        self.assertNotIn("Failed", r.stderr)

    def test_recipe_that_reproduces_diff_passes(self):
        """A recipe whose result matches the recorded tree passes."""
        make_scripted_diff_commit(self.repo,
            subject="rename oldName to newName",
            recipe="git ls-files | xargs sed -i 's/oldName/newName/g'",
            mutate_fn=lambda: write_file(self.repo, "src/foo.cpp", "int newName = 1;\n"),
        )
        r = self.run_verifier("HEAD~1..HEAD")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("OK", r.stderr)

    def test_recipe_that_does_not_reproduce_diff_fails(self):
        """A recipe whose result does NOT match the recorded tree fails."""
        make_scripted_diff_commit(self.repo,
            subject="rename oldName to newName (lying recipe)",
            recipe="git ls-files | xargs sed -i 's/oldName/wrongName/g'",
            mutate_fn=lambda: write_file(self.repo, "src/foo.cpp", "int newName = 1;\n"),
        )
        r = self.run_verifier("HEAD~1..HEAD")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Failed", r.stderr)

    def test_missing_recipe_caught(self):
        """A `scripted-diff:` commit with no script body fails with
        a 'missing script' error."""
        create_commit(self.repo, "scripted-diff: empty body")
        r = self.run_verifier("HEAD~1..HEAD")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("missing script", r.stderr)

    def test_orphan_verify_markers_caught(self):
        """A commit body with VERIFY SCRIPT markers but no `scripted-diff:`
        subject is flagged as an error."""
        message = ("regular: forgot the prefix\n\n"
                   "-BEGIN VERIFY SCRIPT-\n"
                   "echo something\n"
                   "-END VERIFY SCRIPT-\n")
        create_commit(self.repo, message)
        r = self.run_verifier("HEAD~1..HEAD")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("scripted-diff", r.stderr)

    def test_multiple_scripted_diffs_all_verified(self):
        """Multiple scripted-diff commits in a range are each verified.
        The verifier does not stop at the first failure."""
        # Commit A: passes (recipe matches).
        make_scripted_diff_commit(self.repo,
            subject="rename oldName to newName",
            recipe="git ls-files | xargs sed -i 's/oldName/newName/g'",
            mutate_fn=lambda: write_file(self.repo, "src/foo.cpp", "int newName = 1;\n"),
        )
        # Commit B: fails (recipe writes wrongName, tree records finalName).
        make_scripted_diff_commit(self.repo,
            subject="rename newName to finalName (lying recipe)",
            recipe="git ls-files | xargs sed -i 's/newName/wrongName/g'",
            mutate_fn=lambda: write_file(self.repo, "src/foo.cpp", "int finalName = 1;\n"),
        )
        r = self.run_verifier("HEAD~2..HEAD")
        self.assertNotEqual(r.returncode, 0)
        # Both commits must have been processed, not just the first.
        self.assertIn("OK", r.stderr)
        self.assertIn("Failed", r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
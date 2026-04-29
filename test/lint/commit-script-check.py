#!/usr/bin/env python3
# Copyright (c) present The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.

"""Verify scripted-diff commits.

For each commit in the given range whose subject starts with
`scripted-diff:`, extract the script between `-BEGIN VERIFY SCRIPT-`
and `-END VERIFY SCRIPT-` markers in the commit message, run it from
the parent commit, and check that the result matches the recorded diff.
"""
import argparse
import os
import re
import shlex
import subprocess
import sys

TOOL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools", "scripted_diff.py")


def git(*args):
    """Run a git command. Returns stdout as a string."""
    return subprocess.check_output(["git", *args], text=True)

def extract_script(body):
    """Return the lines between -BEGIN VERIFY SCRIPT- and -END VERIFY SCRIPT-"""
    lines = []
    in_script = False
    complete = False
    for line in body.splitlines():
        if line == "-BEGIN VERIFY SCRIPT-":
            in_script = True
            continue
        if line == "-END VERIFY SCRIPT-":
            complete = in_script
            break
        if in_script:
            lines.append(line)

    if not in_script:
        sys.exit("Error: No -BEGIN VERIFY SCRIPT- marker found")

    if not complete:
        sys.exit("Error: No -END VERIFY SCRIPT- marker found")

    return "\n".join(lines)


ORPHAN_MARKER = re.compile(r"^-(BEGIN|END)[ a-zA-Z]*-$", re.MULTILINE)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Verify scripted-diff commits in a range.\n\n"
            "For each commit whose subject starts with 'scripted-diff:', "
            "the script between -BEGIN VERIFY SCRIPT- and -END VERIFY SCRIPT- "
            "markers is run from the parent commit. If the result matches "
            "the recorded diff, the commit passes.",
        epilog="examples:\n"
            "  %(prog)s HEAD              verify the latest commit\n"
            "  %(prog)s HEAD~3..HEAD      verify the last three commits\n"
            "  %(prog)s origin..HEAD      verify all commits since origin\n"
            "  %(prog)s abc123            verify a specific commit\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("commits_range", help="commit range or single commit hash")
    return parser.parse_args()


def run_recipe(script):
    """Run each line of the recipe through the scripted-diff tool.
    Returns an error string on failure, None on success."""
    for lineno, line in enumerate(script.splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        result = subprocess.run(
            [sys.executable, TOOL] + shlex.split(line),
            capture_output=True, text=True)
        if result.returncode != 0:
            error = result.stderr.strip()
            return f"L{lineno}: {error}" if error else f"L{lineno}: operation failed"
    return None


def verify_commit(commit):
    """Verify a single commit. Exits on failure, returns on success/skip."""
    subject = git("log", "-1", "--format=%s", commit).strip()
    body = git("log", "-1", "--format=%b", commit)

    if not subject.startswith("scripted-diff:"):
        if ORPHAN_MARKER.search(body):
            sys.exit(f"Error: script block marker but no scripted-diff "
                     f"in title of commit {commit}")
        return

    script = extract_script(body)
    if not script.strip():
        sys.exit(f"Error: missing script for: {commit}")

    git("checkout", "--quiet", f"{commit}^")

    print(f"Verifying {commit} ({subject})")
    print(script)

    error = run_recipe(script)

    # Stage everything (including new files) and compare.
    git("add", "-A")
    diff = subprocess.run(["git", "--no-pager", "diff", "--cached",
                           "--exit-code", commit])

    # Clean up for the next commit.
    git("reset", "--quiet", "--hard", "HEAD")
    git("clean", "-fdq")

    if error:
        sys.exit(error)
    if diff.returncode != 0:
        sys.exit("Failed")


def main():
    args = parse_args()

    # Get starting point so we can return to it.
    try:
        orig_ref = git("symbolic-ref", "--short", "HEAD").strip()
    except subprocess.CalledProcessError:
        orig_ref = git("rev-parse", "HEAD").strip()

    try:
        commit_range = args.commits_range
        if ".." not in commit_range:
            commit_range = f"{commit_range}^..{commit_range}"
        commits = git("rev-list", "--reverse", commit_range).split()
    except subprocess.CalledProcessError:
        sys.exit(f"Error: invalid commit range '{args.range}'")

    try:
        for commit in commits:
            verify_commit(commit)
    finally:
        subprocess.run(["git", "checkout", "--quiet", orig_ref],
                       capture_output=True)

    print("OK")


if __name__ == "__main__":
    main()
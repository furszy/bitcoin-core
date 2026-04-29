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
import subprocess
import sys


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

    # Run the recipe in a shell, same as the original (eval "$SCRIPT").
    subprocess.run(script, shell=True)

    # Stage all changes (catches new files) and compare to the
    # recorded commit.
    git("add", "-A")
    diff = subprocess.run(["git", "--no-pager", "diff", "--cached",
                           "--exit-code", commit])

    # Clean up for the next commit.
    git("reset", "--quiet", "--hard", "HEAD")
    git("clean", "-fdq")

    if diff.returncode != 0:
        sys.exit("Failed")


def main():
    os.environ["LC_ALL"] = "C"
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
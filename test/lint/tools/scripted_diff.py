#!/usr/bin/env python3
# Copyright (c) present The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.

"""Scripted-diff operations:

  RENAME word <old> <new> <files...>
  RENAME literal <old> <new> <files...>
  RENAME regex <old> <new> <files...>
  RENAME_FILE <src> <dst>

Example: scripted_diff.py RENAME word CWallet Wallet 'src/*.cpp' 'src/*.h'
"""
import os
import re
import subprocess
import sys


class OperationError(Exception):
    """An operation's arguments are invalid or it failed."""


def build_transform(mode, old, new):
    """Return a str->str function for the given substitution mode."""
    if mode == "word":
        pat = re.compile(r"\b" + re.escape(old) + r"\b")
        # Use a lambda so 'new' is treated as literal text,
        # not as a regex replacement string with backrefs.
        return lambda t: pat.sub(lambda m: new, t)
    if mode == "literal":
        return lambda t: t.replace(old, new)
    if mode == "regex":
        try:
            pat = re.compile(old, re.MULTILINE)
        except re.error as e:
            raise OperationError(f"bad regex: {e}")
        return lambda t: pat.sub(new, t)
    raise OperationError(f"unknown mode {mode!r}; expected: word, literal, regex")


def apply_to_file(path, transform):
    """Apply transform to a file. Returns True if modified. Skips binary."""
    with open(path, "r+b") as f:
        data = f.read()
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return False
        new_data = transform(text).encode("utf-8")
        if new_data != data:
            f.seek(0)
            f.truncate()
            f.write(new_data)
            return True
    return False


def op_rename(args):
    """RENAME mode old new files...
    Returns list of modified file paths."""
    if len(args) < 4:
        raise OperationError("needs mode old new files...")
    mode, old, new = args[0], args[1], args[2]
    transform = build_transform(mode, old, new)
    files = set()
    for pat in args[3:]:
        out = subprocess.run(["git", "ls-files", "-z", "--", f":(glob){pat}"],
                             capture_output=True)
        for f in out.stdout.decode("utf-8", "replace").split("\0"):
            if f:
                files.add(f)
    return [p for p in sorted(files) if apply_to_file(p, transform)]


def op_rename_file(args):
    """RENAME_FILE src dst
    Returns list with a single 'src -> dst' entry."""
    if len(args) != 2:
        raise OperationError("needs exactly src dst")
    src, dst = args
    parent = os.path.dirname(dst)
    if parent:
        os.makedirs(parent, exist_ok=True)
    try:
        subprocess.run(["git", "mv", "--", src, dst], check=True,
                       capture_output=True)
    except subprocess.CalledProcessError as e:
        msg = e.stderr.decode("utf-8", "replace").strip() if e.stderr else f"failed to move {src}"
        raise OperationError(msg)
    return [f"{src} -> {dst}"]


OPERATIONS = {
    "RENAME":      op_rename,
    "RENAME_FILE": op_rename_file,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return

    op = sys.argv[1].upper()
    if op not in OPERATIONS:
        sys.exit(f"Error: unknown operation {sys.argv[1]!r}")

    try:
        result = OPERATIONS[op](sys.argv[2:])
    except OperationError as e:
        sys.exit(f"Error: {e}")

    if not result:
        print("No files matched.")
        return
    for entry in result:
        print(f"  {entry}")


if __name__ == "__main__":
    main()
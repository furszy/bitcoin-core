#!/usr/bin/env python3
"""
bench_compare.py — Rigorous Bitcoin-Core benchmark comparator
======================================================================
Checks out two commits, compiles only the bench_bitcoin target for each,
then collects benchmark samples using nanobench's own internal timing loop
and produces a full statistical report.

REQUIREMENTS
------------
  Python 3.11+  |  git  |  cmake  |  ninja or make  |  a C++ toolchain

HOW SAMPLING WORKS
------------------
  Each sample is one call to bench_bitcoin with --min-time=T.
  nanobench runs the benchmark internally for T seconds, averaging over
  however many iterations fit in that window, then reports a single
  stable ns/op value.  We collect S such samples per commit.

  This is strictly better than --min-time=0 (single raw iteration) because:
    - no process-startup overhead contaminating each measurement
    - nanobench's internal averaging suppresses instruction-cache noise
    - higher --sample-time → more internal iterations → lower variance per sample
    - the distribution of S samples still captures run-to-run variance
      (OS scheduling, thermal throttling, memory bus contention)

  Sensible defaults:  --samples 500  --sample-time 0.5
  Total wall time per commit ≈ samples × sample_time = 500 × 0.5s = ~250s
  This is intentionally conservative: the main source of instability is
  per-sample noise (fixed by --sample-time), not sample count.

QUICK START — the three most common workflows
---------------------------------------------

1. Compare master against a GitHub PR
   ------------------------------------
     git -C ~/bitcoin fetch origin pull/29241/head:pr-29241

     python bench_compare.py \\
         --repo      ~/bitcoin \\
         --base-ref  master \\
         --pr-ref    pr-29241 \\
         --benchmark AddrManAdd

2. Compare master against a branch in your own fork
   --------------------------------------------------
     git -C ~/bitcoin remote add myfork https://github.com/you/bitcoin.git
     git -C ~/bitcoin fetch myfork

     python bench_compare.py \\
         --repo      ~/bitcoin \\
         --base-ref  master \\
         --pr-ref    myfork/my-feature-branch \\
         --benchmark AddrManAdd

3. Compare two arbitrary commits / branches / tags
   -------------------------------------------------
     python bench_compare.py \\
         --repo      ~/bitcoin \\
         --base-ref  v26.0 \\
         --pr-ref    v27.0 \\
         --benchmark AddrManAdd

   --pr-ref accepts anything git rev-parse understands:
   a branch, a remote-tracking branch, a tag, or a raw SHA.

LIST AVAILABLE BENCHMARKS (no --benchmark needed)
--------------------------------------------------
     python bench_compare.py \\
         --repo     ~/bitcoin \\
         --base-ref master \\
         --list-benchmarks

COMMONLY USED OPTIONS
---------------------
  --benchmark     NAME    Benchmark to run
  --samples       N       Number of samples per commit       (default: 500)
  --sample-time   SECS    nanobench window per sample in seconds  (default: 0.5)
                          (converted to milliseconds; passed as -min-time=N)
  --warmup        N       Warm-up samples discarded          (default: 20)
  --jobs          N       Parallel build threads             (default: all CPUs)
  --output-json   FILE    Save raw samples + stats to a JSON file
  --base-label    TEXT    Human-readable label for base in the report
  --pr-label      TEXT    Human-readable label for PR/branch in the report
  --keep-builds           Don't delete build dirs after the run
  --skip-build            Re-run benchmarks without recompiling
                          (requires --work-dir pointing at a previous run)
  --list-benchmarks       Print all available benchmark names and exit
  --config        FILE    Load defaults from a TOML file

FULL EXAMPLE
------------
  python bench_compare.py \\
      --repo        ~/bitcoin \\
      --base-ref    master \\
      --pr-ref      myfork/my-feature \\
      --benchmark   AddrManAdd \\
      --samples     500 \\
      --sample-time 0.5 \\
      --warmup      20 \\
      --jobs        $(nproc) \\
      --base-label  "master" \\
      --pr-label    "my-feature" \\
      --output-json results.json

CONFIG FILE
-----------
  Any flag can be set in a TOML file so you don't have to retype it every run.
  Command-line flags always override config values.

  Example ~/.btc_bench.toml:

    repo      = "/Users/you/Projects/bitcoin"
    work-dir  = "/tmp/btc_bench_myfeature"
    keep-builds = true
    jobs      = 7
    base-ref  = "master"
    base-label = "base"

  Then just run:

    python3 bench_compare.py \
        --config   ~/.btc_bench.toml \
        --pr-ref   yourname/your-branch \
        --benchmark VerifyScriptP2WPKH

  Or override any value ad-hoc:

    python3 bench_compare.py \
        --config   ~/.btc_bench.toml \
        --pr-ref   yourname/your-branch \
        --benchmark VerifyScriptP2WPKH \
        --jobs     4

REUSING A WORK DIR ACROSS RUNS (skip rebuilding)
-------------------------------------------------
  Use --work-dir to keep build artefacts on disk, then --skip-build on
  subsequent runs to jump straight to sampling without recompiling.

  # First run: build both commits and benchmark AddrManAdd
  python bench_compare.py \\
      --repo      ~/bitcoin \\
      --base-ref  master \\
      --pr-ref    myfork/my-feature \\
      --benchmark AddrManAdd \\
      --work-dir  /tmp/btc_bench_myfeature \\
      --keep-builds

  # Subsequent runs: skip the build, run a different benchmark or more samples
  python bench_compare.py \\
      --repo        ~/bitcoin \\
      --base-ref    master \\
      --pr-ref      myfork/my-feature \\
      --benchmark   MempoolEviction \\
      --work-dir    /tmp/btc_bench_myfeature \\
      --skip-build \\
      --samples     500 \\
      --output-json results.json

  Notes:
    - --work-dir must point to the same directory used in the first run.
    - --skip-build skips git checkout and cmake; the binaries must already
      exist under <work-dir>/base_build/ and <work-dir>/pr_build/.
    - You can freely change --benchmark, --samples, --sample-time, --warmup,
      and --output-json between runs; only the compiled binaries are reused.
    - Without --keep-builds on the first run the work dir is deleted
      automatically, so --skip-build on the next run would fail.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, NoReturn, Optional, Sequence

# ── Python version guard ──────────────────────────────────────────────────────
if sys.version_info < (3, 11):
    sys.exit(f"Python 3.11+ is required (running {sys.version.split()[0]}). Please invoke with python3.11 or later.")

import tomllib

SCHEMA_VERSION = "4"

# ══════════════════════════════════════════════════════════════════════════════
# Terminal helpers
# ══════════════════════════════════════════════════════════════════════════════

_IS_TTY = sys.stdout.isatty()

def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _IS_TTY else text

def bold(t: str)   -> str: return _c("1",  t)
def cyan(t: str)   -> str: return _c("96", t)
def green(t: str)  -> str: return _c("92", t)
def yellow(t: str) -> str: return _c("93", t)
def red(t: str)    -> str: return _c("91", t)
def dim(t: str)    -> str: return _c("2",  t)

def info(msg: str) -> None: print(f"{cyan('[INFO]')}  {msg}", flush=True)
def ok(msg:   str) -> None: print(f"{green('[OK]')}    {msg}", flush=True)
def warn(msg: str) -> None: print(f"{yellow('[WARN]')}  {msg}", flush=True)

def die(msg: str) -> NoReturn:
    print(f"{red('[ERROR]')} {msg}", file=sys.stderr, flush=True)
    sys.exit(1)

def _bar(done: int, total: int, width: int = 40) -> str:
    filled = int(width * done / total)
    return "█" * filled + "░" * (width - filled)


# ══════════════════════════════════════════════════════════════════════════════
# Statistics  (zero external dependencies)
# ══════════════════════════════════════════════════════════════════════════════

def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs)

def _variance(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return sum((x - m) ** 2 for x in xs) / (len(xs) - 1)

def _stdev(xs: list[float]) -> float:
    return math.sqrt(_variance(xs))

def _percentile(xs: list[float], p: float) -> float:
    """Linear-interpolation percentile (matches numpy's default)."""
    s   = sorted(xs)
    n   = len(s)
    idx = p / 100.0 * (n - 1)
    lo  = int(idx)
    hi  = min(lo + 1, n - 1)
    return s[lo] + (idx - lo) * (s[hi] - s[lo])

def _median(xs: list[float]) -> float:
    return _percentile(xs, 50)

def _mad(xs: list[float]) -> float:
    m = _median(xs)
    return _median([abs(x - m) for x in xs])

def _remove_outliers_iqr(xs: list[float], k: float = 3.0) -> tuple[list[float], int]:
    """Tukey 'far out' fence — only removes extreme OS-scheduling spikes."""
    q1  = _percentile(xs, 25)
    q3  = _percentile(xs, 75)
    iqr = q3 - q1
    lo  = q1 - k * iqr
    hi  = q3 + k * iqr
    cleaned = [x for x in xs if lo <= x <= hi]
    return cleaned, len(xs) - len(cleaned)


def _ibeta_cf(x: float, a: float, b: float) -> float:
    """
    Regularised incomplete beta I_x(a,b) via Lentz continued fraction.
    Matches scipy to 6+ significant figures for benchmark-sized degrees of freedom.
    """
    TINY = 1e-30
    qab  = a + b
    qap  = a + 1.0
    qam  = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < TINY: d = TINY
    d = 1.0 / d
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        # Even step
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < TINY: d = TINY
        c = 1.0 + aa / c
        if abs(c) < TINY: c = TINY
        d = 1.0 / d
        h *= d * c
        # Odd step
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < TINY: d = TINY
        c = 1.0 + aa / c
        if abs(c) < TINY: c = TINY
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-10:
            break
    log_bt = (
        math.lgamma(qab) - math.lgamma(a) - math.lgamma(b)
        + a * math.log(x) + b * math.log(1.0 - x)
    )
    return math.exp(log_bt) * h / a


def _t_pvalue(t: float, df: float) -> float:
    """Exact two-tailed p-value from Student's t using the incomplete-beta CDF."""
    x = df / (df + t * t)
    return _ibeta_cf(x, df / 2.0, 0.5)


def welch_ttest(a: list[float], b: list[float]) -> tuple[float, float, float]:
    """
    Welch's t-test (unequal variances, unequal sizes).
    Returns (t_statistic, degrees_of_freedom, p_value_two_tailed).
    """
    na, nb = len(a), len(b)
    va, vb = _variance(a), _variance(b)
    se2    = va / na + vb / nb
    if se2 == 0.0:
        return 0.0, float(na + nb - 2), 1.0
    t   = (_mean(a) - _mean(b)) / math.sqrt(se2)
    num = se2 ** 2
    den = (va / na) ** 2 / (na - 1) + (vb / nb) ** 2 / (nb - 1)
    df  = num / den if den else float(na + nb - 2)
    return t, df, _t_pvalue(abs(t), df)


def cohens_d(a: list[float], b: list[float]) -> float:
    na, nb   = len(a), len(b)
    pooled_v = ((na - 1) * _variance(a) + (nb - 1) * _variance(b)) / (na + nb - 2)
    return (_mean(a) - _mean(b)) / math.sqrt(pooled_v) if pooled_v else 0.0


def bootstrap_ci(
    xs: list[float],
    stat: Callable[[list[float]], float] = _mean,
    confidence: float = 0.95,
    n_boot: int = 10_000,
    seed: int = 42,
) -> tuple[float, float]:
    """Non-parametric bootstrap confidence interval for *stat*."""
    import random
    rng   = random.Random(seed)
    n     = len(xs)
    boots = sorted(stat(rng.choices(xs, k=n)) for _ in range(n_boot))
    alpha = (1.0 - confidence) / 2.0
    return _percentile(boots, alpha * 100), _percentile(boots, (1.0 - alpha) * 100)


# ══════════════════════════════════════════════════════════════════════════════
# Data model
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class BenchStats:
    n:       int
    mean:    float
    median:  float
    stdev:   float
    mad:     float
    cv:      float      # coefficient of variation (%)
    min:     float
    max:     float
    p1:      float
    p5:      float
    p25:     float
    p75:     float
    p95:     float
    p99:     float
    ci95_lo: float
    ci95_hi: float

    @classmethod
    def from_samples(cls, xs: list[float]) -> "BenchStats":
        m      = _mean(xs)
        s      = _stdev(xs)
        lo, hi = bootstrap_ci(xs)
        return cls(
            n       = len(xs),
            mean    = m,
            median  = _median(xs),
            stdev   = s,
            mad     = _mad(xs),
            cv      = s / m * 100 if m else 0.0,
            min     = min(xs),
            max     = max(xs),
            p1      = _percentile(xs, 1),
            p5      = _percentile(xs, 5),
            p25     = _percentile(xs, 25),
            p75     = _percentile(xs, 75),
            p95     = _percentile(xs, 95),
            p99     = _percentile(xs, 99),
            ci95_lo = lo,
            ci95_hi = hi,
        )

    def as_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}  # type: ignore[attr-defined]


@dataclass
class BenchRun:
    label:            str
    ref:              str
    sha:              str
    bench_name:       str
    warmup_n:         int
    sample_time_s:    float          # nanobench window used per sample
    raw_samples:      list[float]    # ns/op, including warmup
    clean_samples:    list[float]    # ns/op, warmup removed + outliers removed
    outliers_removed: int
    stats:            Optional[BenchStats] = field(default=None, init=False)

    def finalise(self) -> None:
        self.stats = BenchStats.from_samples(self.clean_samples)

    def as_dict(self) -> dict:
        return {
            "label":              self.label,
            "ref":                self.ref,
            "sha":                self.sha,
            "bench_name":         self.bench_name,
            "warmup_n":           self.warmup_n,
            "sample_time_s":      self.sample_time_s,
            "raw_sample_count":   len(self.raw_samples),
            "clean_sample_count": len(self.clean_samples),
            "outliers_removed":   self.outliers_removed,
            "stats":              self.stats.as_dict() if self.stats else {},
            "samples_ns":         self.clean_samples,
        }


# ══════════════════════════════════════════════════════════════════════════════
# Git helpers
# ══════════════════════════════════════════════════════════════════════════════

def _git(args: list[str], cwd: str) -> str:
    r = subprocess.run(
        ["git", *args], cwd=cwd,
        check=True, text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return r.stdout.strip()


def resolve_sha(repo: str, ref: str) -> str:
    try:
        return _git(["rev-parse", "--verify", f"{ref}^{{commit}}"], cwd=repo)
    except subprocess.CalledProcessError:
        die(
            f"Cannot resolve ref '{ref}' in {repo}\n"
            f"  Make sure the branch is fetched:  git -C {repo} fetch <remote>"
        )
        raise  # unreachable — silences mypy missing-return


def commit_title(repo: str, sha: str) -> str:
    """Return the first line of the commit message (subject line) for *sha*."""
    try:
        return _git(["log", "-1", "--format=%s", sha], cwd=repo)
    except subprocess.CalledProcessError:
        return ""


def _worktree_current_sha(dest: str) -> Optional[str]:
    """Return the SHA HEAD points to in an existing worktree, or None."""
    try:
        return _git(["rev-parse", "HEAD"], cwd=dest)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def worktree_create(repo: str, sha: str, dest: str) -> None:
    """
    Create a git worktree at *dest* for *sha*.

    If the directory already exists and its HEAD matches *sha*, it is reused
    as-is — this is the fast path for --keep-builds + repeated runs.
    Only removes and recreates the worktree when the SHA has changed or the
    directory appears corrupt.
    """
    dest_path = Path(dest)
    if dest_path.exists():
        current = _worktree_current_sha(dest)
        if current == sha:
            info(f"Reusing existing worktree {dest_path.name}/  [{sha[:12]}]")
            return
        warn(f"SHA mismatch in {dest_path.name}/ — recreating  "
             f"(have {(current or '?')[:12]}, need {sha[:12]})")
        try:
            _git(["worktree", "remove", "--force", dest], cwd=repo)
        except subprocess.CalledProcessError:
            shutil.rmtree(dest, ignore_errors=True)

    info(f"Checkout {sha[:12]}  →  {dest_path.name}/")
    try:
        _git(["worktree", "add", "--detach", dest, sha], cwd=repo)
    except subprocess.CalledProcessError:
        warn("git worktree failed — falling back to clone + checkout")
        subprocess.run(["git", "clone", "--quiet", repo, dest], check=True)
        subprocess.run(
            ["git", "checkout", "--quiet", "--detach", sha],
            cwd=dest, check=True,
        )


def worktree_remove(repo: str, path: str) -> None:
    try:
        _git(["worktree", "remove", "--force", path], cwd=repo)
    except Exception:
        shutil.rmtree(path, ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════════════
# Build
# ══════════════════════════════════════════════════════════════════════════════

def _cmake_generator() -> str:
    for exe, gen in [("ninja", "Ninja"), ("make", "Unix Makefiles")]:
        if shutil.which(exe):
            return gen
    die("Neither ninja nor make found. Install one and retry.")
    raise RuntimeError  # unreachable


def _cache_source(build_dir: Path) -> Optional[Path]:
    cache = build_dir / "CMakeCache.txt"
    if not cache.exists():
        return None
    for line in cache.read_text(errors="replace").splitlines():
        if line.startswith("CMAKE_HOME_DIRECTORY"):
            return Path(line.split("=", 1)[-1].strip())
    return None


def cmake_build(src: str, build_dir: str, jobs: int) -> None:
    """
    Configure and build only bench_bitcoin.

    Skips the build entirely if a binary already exists and the CMakeCache
    points to the same source tree — the fast path for --keep-builds + re-runs.
    Wipes the build dir if its CMakeCache belongs to a *different* source tree
    to prevent silent cache-poisoning.
    """
    src_path   = Path(src).resolve()
    build_path = Path(build_dir)

    cached_src = _cache_source(build_path)
    if cached_src is not None:
        if cached_src.resolve() == src_path:
            # Check whether the binary is already present
            candidates = (
                list(build_path.rglob("bench_bitcoin"))
                + list(build_path.rglob("bench_bitcoin.exe"))
            )
            if candidates:
                info(f"Reusing existing build in {build_path.name}/  (source matches)")
                return
        else:
            warn(f"CMakeCache source mismatch — wiping {build_path.name}/")
            shutil.rmtree(build_dir)

    build_path.mkdir(parents=True, exist_ok=True)
    gen = _cmake_generator()
    info(f"cmake configure  {src_path.name}/  [{gen}]")

    subprocess.run([
        "cmake", "-S", src, "-B", build_dir,
        f"-G{gen}",
        "-DCMAKE_BUILD_TYPE=Release",
        "-DBUILD_BENCH=ON",
        "-DBUILD_TESTS=OFF",
        "-DENABLE_WALLET=OFF",
        "-DBUILD_WALLET_TOOL=OFF",
        "-DBUILD_GUI=OFF",
        "-DWITH_USDT=OFF",
        "-DENABLE_IPC=OFF",
        "-DCMAKE_C_FLAGS=-ffile-prefix-map=./=",
        "-DCMAKE_CXX_FLAGS=-ffile-prefix-map=./=",
    ], check=True, cwd=src)

    info(f"cmake build  bench_bitcoin  (jobs={jobs})")
    subprocess.run(
        ["cmake", "--build", build_dir, "--target", "bench_bitcoin", f"-j{jobs}"],
        check=True, cwd=src,
    )


def find_bench_binary(build_dir: str) -> Path:
    """Return the most-recently-modified bench_bitcoin under build_dir."""
    candidates = (
        list(Path(build_dir).rglob("bench_bitcoin"))
        + list(Path(build_dir).rglob("bench_bitcoin.exe"))
    )
    if not candidates:
        die(f"bench_bitcoin not found under {build_dir}")
        raise RuntimeError  # unreachable
    return max(candidates, key=lambda p: p.stat().st_mtime).resolve()


# ══════════════════════════════════════════════════════════════════════════════
# Benchmark helpers
# ══════════════════════════════════════════════════════════════════════════════

def list_benchmarks(binary: Path) -> list[str]:
    """Return benchmark names reported by bench_bitcoin --list."""
    r = subprocess.run([str(binary), "-list"], capture_output=True, text=True)
    names: list[str] = []
    for line in (r.stdout + r.stderr).splitlines():
        line = line.strip()
        if not line or re.match(r"(bench|#|available)", line, re.I):
            continue
        names.append(line)
    return names


def validate_benchmark(binary: Path, pattern: str) -> None:
    """
    Abort if *pattern* matches no known benchmark on *binary*.
    Called separately for each binary so a renamed benchmark in the PR
    is caught before sampling begins.
    """
    available = list_benchmarks(binary)
    if not available:
        warn(f"Could not retrieve benchmark list from {binary.name} — skipping validation.")
        return
    matched = [n for n in available if re.search(pattern, n)]
    if not matched:
        die(
            f"No benchmark matching '{pattern}' in {binary}.\n"
            "Available:\n" + "\n".join(f"  {n}" for n in available)
        )
    if len(matched) > 1:
        warn(f"Pattern '{pattern}' matches {len(matched)} benchmarks — all will be aggregated.")


def _parse_bench_output(output: str) -> Optional[float]:
    """
    Parse bench_bitcoin's stdout, which is a nanobench markdown table:

        |               ns/op |                op/s |    err% |     total | benchmark
        |--------------------:|--------------------:|--------:|----------:|:----------
        |           27,302.60 |           36,626.50 |    0.2% |     0.33s | AddrManAdd

    Returns the ns/op value as a plain float, or None if unparseable.
    Handles comma thousands-separators.

    Note: --output-csv takes a *filename*, not '-', so we do not use it.
    We simply capture stdout and parse the markdown table directly.
    """
    for line in output.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        # Skip separator rows (e.g. "|---|:---|")
        if re.match(r"^\|[-:| ]+\|?$", line):
            continue
        cols = [c.strip() for c in line.split("|") if c.strip()]
        if not cols:
            continue
        # Header row has a text first cell; data rows have a numeric first cell
        try:
            ns_per_op = float(cols[0].replace(",", ""))
            if ns_per_op > 0:
                return ns_per_op
        except ValueError:
            continue
    return None


def run_benchmark_batch(
    binary:       Path,
    bench_name:   str,
    n_samples:    int,
    warmup_n:     int,
    sample_time_s: float,
    timeout_s:    float,
    label:        str,
) -> BenchRun:
    """
    Collect (warmup_n + n_samples) samples from bench_bitcoin.

    Each sample is one invocation of bench_bitcoin with --min-time=sample_time_s.
    nanobench runs the benchmark internally for that many seconds, averaging
    over all iterations that fit in the window, and reports a single stable
    ns/op value.  This approach:

      - Eliminates per-spawn process startup overhead from the measurements
      - Uses nanobench's own internal averaging to suppress I-cache noise
      - Produces a distribution of S stable samples that captures real
        run-to-run variance (thermal, OS scheduling, memory bus)

    Warmup samples are discarded to let the CPU reach steady-state frequency
    and fill the instruction cache.  Extreme outliers are removed with
    Tukey's k=3 IQR fence (only far-out values, not genuine tail latency).
    """
    n_total = warmup_n + n_samples
    raw: list[float] = []

    est_total_s = n_total * sample_time_s
    # --min-time takes milliseconds (per bench_bitcoin source)
    min_time_ms = max(1, int(round(sample_time_s * 1000)))
    info(
        f"Sampling '{bench_name}'  "
        f"(+{warmup_n} warmup, {n_samples} kept, "
        f"{sample_time_s}s/sample ≈ {est_total_s:.0f}s total)  [{label}]"
    )
    t_start = time.perf_counter()

    for i in range(n_total):
        try:
            r = subprocess.run(
                [
                    str(binary),
                    f"-filter={bench_name}",
                    f"-min-time={min_time_ms}",
                ],
                capture_output=True, text=True,
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired:
            die(
                f"Benchmark timed out ({timeout_s}s) at sample {i}.\n"
                f"Try reducing --sample-time or increasing --timeout."
            )

        if r.returncode != 0:
            die(
                f"bench_bitcoin exited {r.returncode} at sample {i}.\n"
                f"stderr: {r.stderr[:500]}"
            )

        value = _parse_bench_output(r.stdout + r.stderr)
        if value is None:
            warn(f"Unparseable output at sample {i}: {r.stdout[:200]!r}")
            continue

        raw.append(value)

        if _IS_TTY:
            done    = i + 1
            elapsed = time.perf_counter() - t_start
            eta     = (elapsed / done) * (n_total - done) if done else 0.0
            phase   = dim("warmup") if i < warmup_n else "bench "
            print(
                f"\r  {phase} [{_bar(done, n_total)}] "
                f"{done:>{len(str(n_total))}}/{n_total}  "
                f"last={value/1e6:7.3f} ms  eta={eta:5.0f}s   ",
                end="", flush=True,
            )

    if _IS_TTY:
        print()

    if len(raw) < max(n_samples // 2, 1):
        die(
            f"Only {len(raw)}/{n_total} samples collected.\n"
            "Check bench_bitcoin output format or increase --timeout."
        )

    post_warmup = raw[warmup_n:]
    if not post_warmup:
        die(f"All {len(raw)} samples were consumed as warmup. Increase --samples.")

    clean, n_removed = _remove_outliers_iqr(post_warmup, k=3.0)
    if not clean:
        die("All samples were removed as outliers — something is very wrong.")
    if n_removed:
        pct = n_removed / len(post_warmup) * 100
        msg = f"{n_removed} outlier(s) removed by Tukey IQR×3 fence ({pct:.1f}% of samples)."
        if pct > 5.0:
            warn(msg + " This is unusually high — consider checking system load.")
        else:
            info(msg)

    run = BenchRun(
        label=label, ref=bench_name, sha="",
        bench_name=bench_name, warmup_n=warmup_n,
        sample_time_s=sample_time_s,
        raw_samples=raw, clean_samples=clean,
        outliers_removed=n_removed,
    )
    run.finalise()
    s = run.stats
    assert s
    ok(
        f"Done in {time.perf_counter()-t_start:.1f}s  —  "
        f"mean={s.mean/1e6:.4f} ms  σ={s.stdev/1e6:.4f} ms  CV={s.cv:.2f}%"
    )
    return run


# ══════════════════════════════════════════════════════════════════════════════
# ASCII histogram
# ══════════════════════════════════════════════════════════════════════════════

def ascii_histogram(samples: list[float], bins: int = 24, width: int = 52) -> str:
    lo, hi = min(samples), max(samples)
    if math.isclose(lo, hi):
        return f"  (all values identical: {lo/1e6:.5f} ms)\n"
    step   = (hi - lo) / bins
    counts = [0] * bins
    for v in samples:
        counts[min(int((v - lo) / step), bins - 1)] += 1
    max_c  = max(counts)
    lines  = []
    for i, c in enumerate(counts):
        b_lo = (lo + i       * step) / 1e6
        b_hi = (lo + (i + 1) * step) / 1e6
        bar  = "▌" * int(width * c / max_c) if max_c else ""
        lines.append(f"  {b_lo:9.4f}–{b_hi:.4f} ms  {bar}  {c}")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# Report
# ══════════════════════════════════════════════════════════════════════════════

def _dpct(b: float, a: float) -> float:
    return (a - b) / b * 100.0 if b else 0.0

def _delta_colour(pct: float, threshold: float = 0.2) -> Callable[[str], str]:
    if pct >  threshold: return red
    if pct < -threshold: return green
    return dim

def _sig_label(p: float) -> str:
    if p < 0.001: return red("★★★  p < 0.001  (highly significant)")
    if p < 0.01:  return red("★★   p < 0.01")
    if p < 0.05:  return yellow("★    p < 0.05")
    return green("–    not significant")

def _effect_label(d: float) -> str:
    a = abs(d)
    if a < 0.2: return dim("negligible")
    if a < 0.5: return yellow("small")
    if a < 0.8: return yellow("medium")
    return red("large")



def _print_verdict(base: BenchRun, pr: BenchRun, dm: float, p: float, d: float) -> None:
    """
    Plain-English summary verdict printed after the detailed statistics table.

    Decision logic:
      p < 0.05 AND |Δmean| > 0.2%  →  FASTER or SLOWER
      p < 0.05 but |Δmean| ≤ 0.2%  →  NO MEANINGFUL CHANGE (statistically detectable but tiny)
      p ≥ 0.05                      →  NO CHANGE DETECTED
    """
    bs, ps = base.stats, pr.stats
    assert bs and ps

    W    = 74
    DSEP = bold("═" * W)

    sig        = p < 0.05
    meaningful = abs(dm) > 0.2
    faster     = dm < -0.2
    slower     = dm >  0.2

    delta_ns  = ps.mean   - bs.mean
    delta_p50 = ps.median - bs.median

    def _abs_us(ns: float) -> str:
        return f"{abs(ns) / 1e3:.2f} µs/op"

    if sig and meaningful and faster:
        headline = green("▼  FASTER")
        lines = [
            "The PR branch is " + green(f"{abs(dm):.2f}% faster") + " on average.",
            f"  Mean:   {_abs_us(delta_ns)} saved   "
            f"(base {bs.mean/1e6:.4f} ms  →  PR {ps.mean/1e6:.4f} ms)",
            f"  Median: {_abs_us(delta_p50)} saved",
            f"  Statistically significant: p={p:.4f}, Cohen's d={d:+.3f} ({_effect_label(d)})",
        ]
    elif sig and meaningful and slower:
        headline = red("▲  SLOWER")
        lines = [
            "The PR branch is " + red(f"{abs(dm):.2f}% slower") + " on average.",
            f"  Mean:   {_abs_us(delta_ns)} added   "
            f"(base {bs.mean/1e6:.4f} ms  →  PR {ps.mean/1e6:.4f} ms)",
            f"  Median: {_abs_us(delta_p50)} added",
            f"  Statistically significant: p={p:.4f}, Cohen's d={d:+.3f} ({_effect_label(d)})",
        ]
    elif sig and not meaningful:
        headline = dim("≈  NO MEANINGFUL CHANGE")
        lines = [
            "A real difference exists but is too small to matter in practice.",
            f"  Δ mean = {dm:+.3f}%  ({_abs_us(delta_ns)}),  p={p:.4f}",
            f"  Cohen's d = {d:+.3f} ({_effect_label(d)}) — negligible effect size.",
        ]
    else:
        headline = dim("≈  NO CHANGE DETECTED")
        lines = [
            "No statistically significant difference (p=" + f"{p:.4f}" + ").",
            f"  Δ mean = {dm:+.3f}%  ({_abs_us(delta_ns)}) — within normal run-to-run noise.",
            "  Try more --samples or a longer --sample-time if you expect a real effect.",
        ]

    print(DSEP)
    print(f"  {bold('VERDICT')}  {pr.label}  vs  {base.label}")
    print()
    print(f"  {headline}")
    print()
    for line in lines:
        print(f"  {line}")
    print()
    print(DSEP)
    print()


def print_report(base: BenchRun, pr: BenchRun) -> None:
    bs, ps = base.stats, pr.stats
    assert bs and ps

    t, df, p = welch_ttest(base.clean_samples, pr.clean_samples)
    d        = cohens_d(base.clean_samples, pr.clean_samples)
    dm       = _dpct(bs.mean,   ps.mean)
    dmed     = _dpct(bs.median, ps.median)

    direction = (
        red("SLOWER ▲")   if dm >  0.2 else
        green("FASTER ▼") if dm < -0.2 else
        dim("≈ unchanged")
    )

    W    = 74
    SEP  = bold("─" * W)
    DSEP = bold("═" * W)

    def ms(v: float) -> str:
        return f"{v/1e6:.5f} ms"

    def row(label: str, bv: float, pv: float, fmt: Callable[[float], str] = ms) -> None:
        dp = _dpct(bv, pv)
        c  = _delta_colour(dp)
        print(f"  {label:<20} {fmt(bv):>16}   {fmt(pv):>16}   {c(f'{dp:+.2f}%'):>10}")

    def pct_row(label: str, bv: float, pv: float) -> None:
        row(label, bv, pv, fmt=lambda v: f"{v:.4f} %")

    print()
    print(DSEP)
    print(f"  {bold('BENCHMARK')}  {base.bench_name}")
    print(f"  {'Base':<8} {base.label}  {dim(base.sha[:16])}")
    print(f"  {'PR':<8} {pr.label}  {dim(pr.sha[:16])}")
    print(
        f"  Samples   {bold(str(bs.n))} clean  "
        f"(+{base.warmup_n} warmup discarded, "
        f"{base.outliers_removed} outlier(s) removed, "
        f"{base.sample_time_s}s/sample)"
    )
    print(SEP)
    print(f"  {'Metric':<20} {'Base':>16}   {'PR':>16}   {'Δ':>10}")
    print(SEP)
    row("Mean",    bs.mean,   ps.mean)
    row("Median",  bs.median, ps.median)
    row("Std dev", bs.stdev,  ps.stdev)
    row("MAD",     bs.mad,    ps.mad)
    pct_row("CV", bs.cv,      ps.cv)
    row("Min",     bs.min,    ps.min)
    row("P1",      bs.p1,     ps.p1)
    row("P5",      bs.p5,     ps.p5)
    row("P25",     bs.p25,    ps.p25)
    row("P75",     bs.p75,    ps.p75)
    row("P95",     bs.p95,    ps.p95)
    row("P99",     bs.p99,    ps.p99)
    row("Max",     bs.max,    ps.max)
    print(SEP)

    def ci_str(r: BenchRun) -> str:
        assert r.stats
        return f"[{r.stats.ci95_lo/1e6:.5f}, {r.stats.ci95_hi/1e6:.5f}] ms"

    print(f"  {'95% CI (base)':<20} {ci_str(base)}")
    print(f"  {'95% CI (PR)':<20} {ci_str(pr)}")
    print(SEP)
    print(f"  Δ mean           {direction}  {_delta_colour(dm)(f'{dm:+.3f}%')}")
    print(f"  Δ median         {_delta_colour(dmed)(f'{dmed:+.3f}%')}")
    print(f"  Welch t          t = {t:+.4f}   df = {df:.1f}")
    print(f"  p-value          {p:.6f}   {_sig_label(p)}")
    print(f"  Cohen's d        {d:+.4f}   {_effect_label(d)}")
    print(DSEP)

    print()
    print(bold("  Distribution — Base"))
    print(ascii_histogram(base.clean_samples))
    print()
    print(bold("  Distribution — PR"))
    print(ascii_histogram(pr.clean_samples))
    print()

    # ── Verdict ───────────────────────────────────────────────────────────────
    _print_verdict(base, pr, dm, p, d)


# ══════════════════════════════════════════════════════════════════════════════
# JSON output
# ══════════════════════════════════════════════════════════════════════════════

def write_json(base: BenchRun, pr: BenchRun, path: str) -> None:
    t, df, p = welch_ttest(base.clean_samples, pr.clean_samples)
    d        = cohens_d(base.clean_samples, pr.clean_samples)
    bs, ps   = base.stats, pr.stats
    assert bs and ps

    doc = {
        "schema_version": SCHEMA_VERSION,
        "generated_at":   time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "base": base.as_dict(),
        "pr":   pr.as_dict(),
        "comparison": {
            "delta_mean_pct":   _dpct(bs.mean,   ps.mean),
            "delta_median_pct": _dpct(bs.median, ps.median),
            "welch_t":  t,
            "welch_df": df,
            "p_value":  p,
            "cohens_d": d,
        },
    }
    with open(path, "w") as f:
        json.dump(doc, f, indent=2)
    ok(f"JSON results → {path}")


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="bench_compare.py",
        description=(
            "Compile two Bitcoin-Core commits and rigorously compare a benchmark.\n"
            "Run with --list-benchmarks (no --benchmark needed) to see available names."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # ── Config file ───────────────────────────────────────────────────────────
    p.add_argument("--config", default=None, metavar="FILE",
                   help="TOML config file. Values are used as defaults and can "
                        "be overridden by any flag on the command line.")

    # ── Required ──────────────────────────────────────────────────────────────
    p.add_argument("--repo",      required=True,
                   help="Path to the Bitcoin-Core git repository.")
    p.add_argument("--base-ref",  default="master",
                   help="Base branch / SHA  (default: master).")
    # pr-ref is only required when NOT listing benchmarks — enforced in main().
    p.add_argument("--pr-ref",    default=None,
                   help="Branch / SHA to compare against base. "
                        "Not required with --list-benchmarks.")

    # ── Benchmark selection ───────────────────────────────────────────────────
    bench_group = p.add_mutually_exclusive_group(required=True)
    bench_group.add_argument("--benchmark",
                   help="Benchmark name or regex (passed to bench_bitcoin --filter).")
    bench_group.add_argument("--list-benchmarks", action="store_true",
                   help="Print all available benchmark names and exit. "
                        "--pr-ref is not needed in this mode.")

    # ── Sampling ──────────────────────────────────────────────────────────────
    p.add_argument("--samples",     type=int,   default=500,
                   help="Number of samples to collect per commit  (default: 500).")
    p.add_argument("--sample-time", type=float, default=0.5,
                   help="nanobench measurement window per sample in seconds  (default: 0.5).\n"
                        "Higher values → more internal iterations → lower per-sample noise.\n"
                        "~250s total per commit at defaults (500 × 0.5s).")
    p.add_argument("--warmup",      type=int,   default=20,
                   help="Warm-up samples discarded before collection begins  (default: 20).")
    p.add_argument("--timeout",     type=float, default=120.0,
                   help="Per-sample timeout in seconds  (default: 120).")

    # ── Build ─────────────────────────────────────────────────────────────────
    p.add_argument("--jobs",        type=int, default=max(1, os.cpu_count() or 4),
                   help="Parallel cmake build jobs  (default: all CPUs).")

    # ── I/O ───────────────────────────────────────────────────────────────────
    p.add_argument("--work-dir",    default=None, metavar="DIR",
                   help="Directory for build artefacts. "
                        "A temp dir is used (and cleaned up) if omitted.")
    p.add_argument("--keep-builds", action="store_true",
                   help="Keep build directories after the run.")
    p.add_argument("--skip-build",  action="store_true",
                   help="Skip checkout + build; reuse binaries already in --work-dir.")
    p.add_argument("--output-json", default=None, metavar="FILE",
                   help="Write full results and raw samples to a JSON file.")
    p.add_argument("--base-label",  default=None,
                   help="Human-readable label for base commit in the report.")
    p.add_argument("--pr-label",    default=None,
                   help="Human-readable label for the PR/branch in the report.")
    return p


# ══════════════════════════════════════════════════════════════════════════════
# Cleanup manager
# ══════════════════════════════════════════════════════════════════════════════

class _Cleanup:
    """
    Tracks resources to release on exit.
    Safe to call at any point — missing paths are silently skipped.
    """
    def __init__(self, repo: str, keep: bool) -> None:
        self._repo:      str        = repo
        self._keep:      bool       = keep
        self._worktrees: list[str]  = []
        self._tmp_dir:   Optional[str] = None

    def register_worktree(self, path: str) -> None:
        self._worktrees.append(path)

    def register_tmp_dir(self, path: str) -> None:
        self._tmp_dir = path

    def run(self) -> None:
        if self._keep:
            return
        for wt in self._worktrees:
            if Path(wt).exists():
                worktree_remove(self._repo, wt)
        if self._tmp_dir and Path(self._tmp_dir).exists():
            shutil.rmtree(self._tmp_dir, ignore_errors=True)
            info("Temporary work dir removed.")


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

def _load_config(path: str) -> dict:
    """Load a TOML config file and return its contents as a flat dict."""
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        die(f"Config file not found: {path}")
    except tomllib.TOMLDecodeError as e:
        die(f"Config file parse error: {e}")
    raise RuntimeError  # unreachable


def main(argv: Optional[Sequence[str]] = None) -> None:
    # ── First pass: get --config path only (ignore unknown args) ─────────────
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--config", default=None)
    pre_args, _ = pre.parse_known_args(argv)

    # ── Build defaults from config file, then parse proper ───────────────────
    parser = build_parser()
    if pre_args.config:
        cfg = _load_config(pre_args.config)
        # Map TOML keys (hyphens allowed) to argparse dest names (underscores)
        defaults = {k.replace("-", "_"): v for k, v in cfg.items()}
        parser.set_defaults(**defaults)
    args = parser.parse_args(argv)
    repo = str(Path(args.repo).resolve())

    if not (Path(repo) / ".git").exists():
        die(f"Not a git repository: {repo}")

    # --pr-ref is only optional for --list-benchmarks
    if not args.list_benchmarks and args.pr_ref is None:
        die("--pr-ref is required unless --list-benchmarks is used.")

    if args.sample_time <= 0:
        die("--sample-time must be greater than 0.")

    if args.samples < 2:
        die("--samples must be at least 2.")

    # ── Work directory ────────────────────────────────────────────────────────
    _tmp: Optional[str] = None
    if args.work_dir:
        work = Path(args.work_dir).resolve()
        work.mkdir(parents=True, exist_ok=True)
    else:
        _tmp = tempfile.mkdtemp(prefix="btc_bench_")
        work = Path(_tmp)
    info(f"Work dir : {work}")

    base_src   = work / "base_src"
    pr_src     = work / "pr_src"
    base_build = work / "base_build"
    pr_build   = work / "pr_build"

    cleaner = _Cleanup(repo, keep=args.keep_builds)
    if _tmp:
        cleaner.register_tmp_dir(_tmp)

    def _signal_handler(*_: object) -> None:
        try:
            cleaner.run()
        finally:
            sys.exit(130)

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, _signal_handler)

    try:
        # ── LIST-BENCHMARKS MODE: only build base, then exit ──────────────────
        if args.list_benchmarks:
            base_sha = resolve_sha(repo, args.base_ref)
            info(f"Base SHA : {base_sha}  {dim(commit_title(repo, base_sha))}")

            if not args.skip_build:
                worktree_create(repo, base_sha, str(base_src))
                cleaner.register_worktree(str(base_src))
                cmake_build(str(base_src), str(base_build), args.jobs)
            else:
                if not base_build.exists():
                    die(f"--skip-build set but base build dir not found: {base_build}")

            base_bin = find_bench_binary(str(base_build))
            names    = list_benchmarks(base_bin)
            print(f"\nAvailable benchmarks  [{base_sha[:12]}]:")
            for n in names:
                print(f"  {n}")
            return

        # ── NORMAL COMPARE MODE ───────────────────────────────────────────────
        base_sha = resolve_sha(repo, args.base_ref)
        pr_sha   = resolve_sha(repo, args.pr_ref)   # type: ignore[arg-type]
        info(f"Base SHA : {base_sha}  {dim(commit_title(repo, base_sha))}")
        info(f"PR   SHA : {pr_sha}  {dim(commit_title(repo, pr_sha))}")
        if base_sha == pr_sha:
            warn("Both refs resolve to the same commit — results will be identical.")

        base_label = args.base_label or args.base_ref
        pr_label   = args.pr_label   or args.pr_ref

        # ── Checkout + build ──────────────────────────────────────────────────
        if not args.skip_build:
            worktree_create(repo, base_sha, str(base_src))
            cleaner.register_worktree(str(base_src))
            worktree_create(repo, pr_sha, str(pr_src))
            cleaner.register_worktree(str(pr_src))
            cmake_build(str(base_src), str(base_build), args.jobs)
            cmake_build(str(pr_src),   str(pr_build),   args.jobs)
        else:
            info("--skip-build: skipping checkout and compilation.")
            for d in [base_build, pr_build]:
                if not d.exists():
                    die(f"--skip-build specified but directory not found: {d}")

        base_bin = find_bench_binary(str(base_build))
        pr_bin   = find_bench_binary(str(pr_build))
        ok(f"Base binary : {base_bin}")
        ok(f"PR   binary : {pr_bin}")

        # ── Validate benchmark name against both binaries ─────────────────────
        validate_benchmark(base_bin, args.benchmark)
        validate_benchmark(pr_bin,   args.benchmark)

        # ── Sample ────────────────────────────────────────────────────────────
        base_run = run_benchmark_batch(
            base_bin, args.benchmark,
            n_samples=args.samples,
            warmup_n=args.warmup,
            sample_time_s=args.sample_time,
            timeout_s=args.timeout,
            label=base_label,
        )
        base_run.sha = base_sha

        pr_run = run_benchmark_batch(
            pr_bin, args.benchmark,
            n_samples=args.samples,
            warmup_n=args.warmup,
            sample_time_s=args.sample_time,
            timeout_s=args.timeout,
            label=pr_label,
        )
        pr_run.sha = pr_sha

        # ── Report ────────────────────────────────────────────────────────────
        print_report(base_run, pr_run)

        if args.output_json:
            write_json(base_run, pr_run, args.output_json)

    finally:
        cleaner.run()


if __name__ == "__main__":
    main()
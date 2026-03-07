#!/usr/bin/env python3
"""
test_bench_compare.py
Full test suite for bench_compare.py (schema v4 / nanobench-native sampling).
Runs entirely against fake binaries and a temporary git repo — no real Bitcoin Core needed.

Usage:
    python3 test_bench_compare.py
    python3 -m pytest test_bench_compare.py -v
"""

import sys
if sys.version_info < (3, 11):
    raise SystemExit(f"Python 3.11+ is required (running {sys.version.split()[0]}).\n")

import importlib.util
import io
import json
import math
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

# ── Load module under test ────────────────────────────────────────────────────
# Resolve relative to this test file so it works from any working directory.
SCRIPT = Path(__file__).parent / "bench_compare.py"
spec   = importlib.util.spec_from_file_location("bbc", SCRIPT)
bbc    = importlib.util.module_from_spec(spec)
sys.modules["bbc"] = bbc           # must be registered before exec for @dataclass
spec.loader.exec_module(bbc)

# ── Test fixtures (created by setUpModule / torn down by tearDownModule) ──────
FAKE_BIN  = Path(__file__).parent / "_test_fixtures" / "bench_bitcoin"
FAKE_REPO = str(Path(__file__).parent / "_test_fixtures" / "repo")


# ══════════════════════════════════════════════════════════════════════════════
# Fixture setup / teardown  (fake binary + fake git repo)
# ══════════════════════════════════════════════════════════════════════════════

_FIXTURES = Path(__file__).parent / "_test_fixtures"

_FAKE_BIN_SRC = """#!/usr/bin/env python3
\"\"\"
Fake bench_bitcoin matching the real binary flag API (single-dash, ms min-time).
\"\"\"
import sys, random, math

BENCHMARKS = ["AddrManAdd", "AddrManGetAddr", "CCheckQueueSpeed", "MempoolEviction"]
BASE_NS    = 27_500

args         = sys.argv[1:]
do_list      = "-list" in args
filt         = next((a.split("=",1)[1] for a in args if a.startswith("-filter=")), None)
min_time_ms  = float(next((a.split("=",1)[1] for a in args if a.startswith("-min-time=")), "10"))

known_prefixes = ("-list", "-filter=", "-min-time=", "-output-csv=",
                  "-output-json=", "-sanity-check", "-asymptote=", "-testdatadir=")
for a in args:
    if not any(a.startswith(p) for p in known_prefixes):
        print(f"Error parsing command line arguments: Invalid parameter {a}", file=sys.stderr)
        sys.exit(1)

if do_list:
    print("Available benchmarks:")
    for b in BENCHMARKS:
        print(b)
    sys.exit(0)

matched = [b for b in BENCHMARKS if filt is None or filt in b]
if not matched:
    print(f"Error: no benchmark matching '{filt}'", file=sys.stderr)
    sys.exit(1)

bench = matched[0]
iters   = max(1, int(min_time_ms * 1000 / BASE_NS))
sigma   = BASE_NS * 0.04 / math.sqrt(iters)
ns_op   = max(1.0, BASE_NS + random.gauss(0, sigma))
ops_s   = 1e9 / ns_op
err_pct = abs(random.gauss(0, 0.3))
total_s = (min_time_ms / 1000) + random.uniform(0, 0.01)

print(f"|               ns/op |                op/s |    err% |     total | benchmark")
print(f"|--------------------:|--------------------:|--------:|----------:|:----------")
print(f"| {ns_op:>19,.2f} | {ops_s:>19,.1f} | {err_pct:>6.1f}% | {total_s:>8.2f}s | {bench}")
"""


def setUpModule() -> None:  # noqa: N802
    """Create the fake binary and git repo under _test_fixtures/."""
    import stat
    import subprocess

    _FIXTURES.mkdir(exist_ok=True)

    # ── Fake bench_bitcoin ────────────────────────────────────────────────────
    bin_path = _FIXTURES / "bench_bitcoin"
    bin_path.write_text(_FAKE_BIN_SRC)
    bin_path.chmod(bin_path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    # ── Fake git repo with two branches ──────────────────────────────────────
    repo = _FIXTURES / "repo"
    if not (repo / ".git").exists():
        repo.mkdir(exist_ok=True)
        subprocess.run(["git", "init", "-b", "master"], cwd=repo, check=True,
                       capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"],
                       cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"],
                       cwd=repo, check=True, capture_output=True)
        (repo / "README").write_text("base")
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "base commit"],
                       cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "feature-branch"],
                       cwd=repo, check=True, capture_output=True)
        (repo / "README").write_text("feature")
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "feature commit"],
                       cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "checkout", "master"],
                       cwd=repo, check=True, capture_output=True)


def tearDownModule() -> None:  # noqa: N802
    """Remove the _test_fixtures directory after all tests have run."""
    if _FIXTURES.exists():
        shutil.rmtree(_FIXTURES)



# ══════════════════════════════════════════════════════════════════════════════
# Statistics
# ══════════════════════════════════════════════════════════════════════════════

class TestStatistics(unittest.TestCase):

    def test_mean(self):
        self.assertAlmostEqual(bbc._mean([1, 2, 3, 4, 5]), 3.0)

    def test_variance_single(self):
        self.assertEqual(bbc._variance([42.0]), 0.0)

    def test_variance_sample(self):
        # sample variance of [2,4,4,4,5,5,7,9] = 32/7
        self.assertAlmostEqual(bbc._variance([2,4,4,4,5,5,7,9]), 32/7, places=10)

    def test_stdev(self):
        self.assertAlmostEqual(bbc._stdev([2,4,4,4,5,5,7,9]), math.sqrt(32/7), places=10)

    def test_percentile_median_odd(self):
        self.assertAlmostEqual(bbc._percentile([1,2,3,4,5], 50), 3.0)

    def test_percentile_median_even(self):
        self.assertAlmostEqual(bbc._percentile([1,2,3,4], 50), 2.5)

    def test_percentile_min_max(self):
        xs = list(range(1, 101))
        self.assertAlmostEqual(bbc._percentile(xs,   0), 1.0)
        self.assertAlmostEqual(bbc._percentile(xs, 100), 100.0)

    def test_median(self):
        self.assertAlmostEqual(bbc._median([3,1,4,1,5,9,2,6]), 3.5)

    def test_mad(self):
        self.assertAlmostEqual(bbc._mad([1,1,2,2,4,6,9]), 1.0)

    def test_remove_outliers_keeps_normal(self):
        xs = list(range(1, 101))
        clean, n = bbc._remove_outliers_iqr(xs, k=3.0)
        self.assertEqual(n, 0)
        self.assertEqual(len(clean), 100)

    def test_remove_outliers_removes_spike(self):
        xs = list(range(1, 101)) + [100_000]
        clean, n = bbc._remove_outliers_iqr(xs, k=3.0)
        self.assertEqual(n, 1)
        self.assertNotIn(100_000, clean)

    def test_welch_ttest_identical(self):
        xs = [50_000.0] * 100
        t, df, p = bbc.welch_ttest(xs, xs)
        self.assertEqual(t, 0.0)
        self.assertAlmostEqual(p, 1.0)

    def test_welch_ttest_clearly_different(self):
        import random
        rng = random.Random(0)
        a = [rng.gauss(50_000, 500) for _ in range(200)]
        b = [rng.gauss(55_000, 500) for _ in range(200)]
        t, df, p = bbc.welch_ttest(a, b)
        self.assertLess(p, 0.001)
        self.assertLess(t, 0)   # a < b → negative t

    def test_welch_pvalue_range(self):
        import random
        rng = random.Random(7)
        a = [rng.gauss(50_000, 1000) for _ in range(200)]
        b = [rng.gauss(50_000, 1000) for _ in range(200)]
        _, _, p = bbc.welch_ttest(a, b)
        self.assertGreaterEqual(p, 0.0)
        self.assertLessEqual(p,    1.0)

    # p-value accuracy vs scipy reference values
    def test_pvalue_accuracy_196(self):
        self.assertAlmostEqual(bbc._t_pvalue(1.96, 1000.0), 0.050273, places=5)

    def test_pvalue_accuracy_2576(self):
        self.assertAlmostEqual(bbc._t_pvalue(2.576, 1000.0), 0.010138, places=5)

    def test_pvalue_accuracy_3291(self):
        self.assertAlmostEqual(bbc._t_pvalue(3.291, 1000.0), 0.001033, places=5)

    def test_cohens_d_zero(self):
        xs = [50_000.0, 51_000.0, 49_000.0]
        self.assertAlmostEqual(bbc.cohens_d(xs, xs), 0.0)

    def test_cohens_d_sign(self):
        import random
        rng = random.Random(3)
        a = [rng.gauss(10_000, 500) for _ in range(50)]
        b = [rng.gauss(20_000, 500) for _ in range(50)]
        self.assertLess(bbc.cohens_d(a, b), 0)   # a < b → negative d

    def test_bootstrap_ci_contains_mean(self):
        import random
        rng = random.Random(1)
        xs  = [rng.gauss(50_000, 2000) for _ in range(300)]
        lo, hi = bbc.bootstrap_ci(xs)
        self.assertLess(lo, bbc._mean(xs))
        self.assertGreater(hi, bbc._mean(xs))

    def test_bootstrap_ci_narrows_with_n(self):
        import random
        rng   = random.Random(2)
        xs50  = [rng.gauss(0, 1) for _ in range(50)]
        xs500 = [rng.gauss(0, 1) for _ in range(500)]
        lo50,  hi50  = bbc.bootstrap_ci(xs50)
        lo500, hi500 = bbc.bootstrap_ci(xs500)
        self.assertGreater(hi50 - lo50, hi500 - lo500)


# ══════════════════════════════════════════════════════════════════════════════
# BenchStats / BenchRun
# ══════════════════════════════════════════════════════════════════════════════

class TestBenchStats(unittest.TestCase):

    def _make(self, n=200, mean=50_000, sigma=1_000):
        import random
        rng = random.Random(42)
        xs  = [rng.gauss(mean, sigma) for _ in range(n)]
        return bbc.BenchStats.from_samples(xs), xs

    def test_all_fields(self):
        s, _ = self._make()
        for f in ("n","mean","median","stdev","mad","cv","min","max",
                  "p1","p5","p25","p75","p95","p99","ci95_lo","ci95_hi"):
            self.assertTrue(hasattr(s, f), f"missing: {f}")

    def test_n(self):
        s, xs = self._make(n=150)
        self.assertEqual(s.n, 150)

    def test_percentile_order(self):
        s, _ = self._make()
        self.assertLessEqual(s.min,    s.p1)
        self.assertLessEqual(s.p1,     s.p5)
        self.assertLessEqual(s.p5,     s.p25)
        self.assertLessEqual(s.p25,    s.median)
        self.assertLessEqual(s.median, s.p75)
        self.assertLessEqual(s.p75,    s.p95)
        self.assertLessEqual(s.p95,    s.p99)
        self.assertLessEqual(s.p99,    s.max)

    def test_ci_wraps_mean(self):
        s, _ = self._make()
        self.assertLess(s.ci95_lo, s.mean)
        self.assertGreater(s.ci95_hi, s.mean)

    def test_as_dict_json_serialisable(self):
        s, _ = self._make()
        json.dumps(s.as_dict())


class TestBenchRun(unittest.TestCase):

    def _make_run(self, mean=50_000, n=100):
        import random
        rng  = random.Random(9)
        samp = [rng.gauss(mean, 1_000) for _ in range(n)]
        run  = bbc.BenchRun(
            label="test", ref="TestBench", sha="abc123",
            bench_name="TestBench", warmup_n=5,
            sample_time_s=0.1,
            raw_samples=[mean] * 5 + samp,
            clean_samples=samp, outliers_removed=0,
        )
        run.finalise()
        return run

    def test_finalise_populates_stats(self):
        self.assertIsNotNone(self._make_run().stats)

    def test_as_dict_keys(self):
        d = self._make_run().as_dict()
        for k in ("label","ref","sha","bench_name","warmup_n","sample_time_s",
                  "raw_sample_count","clean_sample_count",
                  "outliers_removed","stats","samples_ns"):
            self.assertIn(k, d)

    def test_sample_time_stored(self):
        self.assertAlmostEqual(self._make_run().sample_time_s, 0.1)

    def test_as_dict_json_serialisable(self):
        json.dumps(self._make_run().as_dict())


# ══════════════════════════════════════════════════════════════════════════════
# CSV parsing — ns/op is returned directly (no iters multiplication)
# ══════════════════════════════════════════════════════════════════════════════

class TestParseBenchOutput(unittest.TestCase):

    # ── Markdown table format (real bench_bitcoin output) ───────────────────

    _MD_OUTPUT = (
        "\n"
        "|               ns/op |                op/s |    err% |     total | benchmark\n"
        "|--------------------:|--------------------:|--------:|----------:|:----------\n"
        "|           27,302.60 |           36,626.50 |    0.2% |     0.33s | AddrManAdd\n"
    )

    def test_markdown_parses_ns_per_op(self):
        v = bbc._parse_bench_output(self._MD_OUTPUT)
        self.assertAlmostEqual(v, 27302.60)

    def test_markdown_comma_thousands_stripped(self):
        # 27,302.60 must parse as 27302.60, not fail
        v = bbc._parse_bench_output(self._MD_OUTPUT)
        self.assertGreater(v, 27000)
        self.assertLess(v, 28000)

    def test_markdown_skips_separator_row(self):
        # The |---:| row must not be returned as a value
        sep_only = "|--------------------:|--------------------:|--------:|----------:|:----------\n"
        # A separator-only output has no valid data row → None
        self.assertIsNone(bbc._parse_bench_output(sep_only))

    def test_markdown_skips_header_row(self):
        header_only = "|               ns/op |                op/s |    err% |     total | benchmark\n"
        self.assertIsNone(bbc._parse_bench_output(header_only))

    def test_markdown_real_sample(self):
        # Verbatim from the user's actual bench_bitcoin output
        raw = (
            "\n|               ns/op |                op/s |    err% |     total | benchmark\n"
            "|--------------------:|--------------------:|--------:|----------:|:----------\n"
            "|           27,847.97 |           35,909.20 |    0.1% |     0.28s | AddrManAdd\n"
        )
        v = bbc._parse_bench_output(raw)
        self.assertAlmostEqual(v, 27847.97)

    # ── Shared edge cases ─────────────────────────────────────────────────────

    def test_none_on_garbage(self):
        self.assertIsNone(bbc._parse_bench_output("not,valid,data"))

    def test_none_on_empty(self):
        self.assertIsNone(bbc._parse_bench_output(""))

    def test_none_on_zero_ns(self):
        row = "|             0.00 |    99999.0 |    0.1% |     0.10s | AddrManAdd\n"
        self.assertIsNone(bbc._parse_bench_output(row))


# ══════════════════════════════════════════════════════════════════════════════
# Git helpers
# ══════════════════════════════════════════════════════════════════════════════

class TestGitHelpers(unittest.TestCase):

    def test_resolve_sha_master(self):
        sha = bbc.resolve_sha(FAKE_REPO, "master")
        self.assertEqual(len(sha), 40)
        self.assertRegex(sha, r'^[0-9a-f]+$')

    def test_resolve_sha_branch(self):
        sha = bbc.resolve_sha(FAKE_REPO, "feature-branch")
        self.assertEqual(len(sha), 40)

    def test_master_and_branch_differ(self):
        self.assertNotEqual(
            bbc.resolve_sha(FAKE_REPO, "master"),
            bbc.resolve_sha(FAKE_REPO, "feature-branch"),
        )

    def test_invalid_ref_dies(self):
        with self.assertRaises(SystemExit):
            bbc.resolve_sha(FAKE_REPO, "no-such-branch-xyz")


# ══════════════════════════════════════════════════════════════════════════════
# Benchmark discovery
# ══════════════════════════════════════════════════════════════════════════════

class TestBenchmarkDiscovery(unittest.TestCase):

    def test_list_benchmarks(self):
        names = bbc.list_benchmarks(FAKE_BIN)
        self.assertIn("AddrManAdd", names)
        self.assertIn("AddrManGetAddr", names)
        self.assertGreater(len(names), 2)

    def test_validate_exact_match(self):
        bbc.validate_benchmark(FAKE_BIN, "AddrManAdd")   # must not raise/exit

    def test_validate_regex_match(self):
        bbc.validate_benchmark(FAKE_BIN, "AddrMan.*")    # must not raise/exit

    def test_validate_no_match_dies(self):
        with self.assertRaises(SystemExit):
            bbc.validate_benchmark(FAKE_BIN, "NoSuchBenchXYZ")


# ══════════════════════════════════════════════════════════════════════════════
# run_benchmark_batch — the core sampling loop
# ══════════════════════════════════════════════════════════════════════════════

class TestRunBenchmarkBatch(unittest.TestCase):

    def _run(self, n_samples=20, warmup_n=5, sample_time_s=0.0):
        return bbc.run_benchmark_batch(
            FAKE_BIN, "AddrManAdd",
            n_samples=n_samples,
            warmup_n=warmup_n,
            sample_time_s=sample_time_s,
            timeout_s=30.0,
            label="test",
        )

    def test_correct_raw_count(self):
        run = self._run(n_samples=20, warmup_n=5)
        self.assertEqual(len(run.raw_samples), 25)   # warmup + bench

    def test_clean_count_at_most_n_samples(self):
        run = self._run(n_samples=20, warmup_n=5)
        self.assertLessEqual(len(run.clean_samples), 20)
        self.assertGreater(len(run.clean_samples), 0)

    def test_stats_positive_mean(self):
        run = self._run(n_samples=30, warmup_n=5)
        self.assertIsNotNone(run.stats)
        self.assertGreater(run.stats.mean, 0)

    def test_warmup_n_stored(self):
        run = self._run(n_samples=20, warmup_n=7)
        self.assertEqual(run.warmup_n, 7)

    def test_sample_time_stored(self):
        run = self._run(n_samples=20, warmup_n=5, sample_time_s=0.05)
        self.assertAlmostEqual(run.sample_time_s, 0.05)

    def test_ns_per_op_range(self):
        # Fake binary baseline ~50000 ns/op; must not be multiplied by iters.
        run = self._run(n_samples=20, warmup_n=5, sample_time_s=0.1)
        mean_ns = run.stats.mean
        self.assertGreater(mean_ns, 10_000,
            f"mean {mean_ns} ns is suspiciously small — was ns/op divided somewhere?")
        self.assertLess(mean_ns, 500_000,
            f"mean {mean_ns} ns is suspiciously large — was ns/op multiplied by iters?")

    def test_higher_sample_time_lower_variance(self):
        # More time per sample → more internal iters → lower CV
        import random; random.seed(77)
        run_short = self._run(n_samples=40, warmup_n=5, sample_time_s=0.0)
        run_long  = self._run(n_samples=40, warmup_n=5, sample_time_s=0.5)
        self.assertLess(run_long.stats.cv, run_short.stats.cv,
            "Longer sample_time should yield lower coefficient of variation")

    def test_invalid_benchmark_dies(self):
        with self.assertRaises(SystemExit):
            bbc.run_benchmark_batch(
                FAKE_BIN, "NoSuchBench",
                n_samples=5, warmup_n=2,
                sample_time_s=0.0, timeout_s=10.0, label="test",
            )

    def test_as_dict_json_serialisable(self):
        json.dumps(self._run(n_samples=20, warmup_n=5).as_dict())

    def test_as_dict_has_sample_time(self):
        d = self._run(n_samples=20, warmup_n=5, sample_time_s=0.1).as_dict()
        self.assertIn("sample_time_s", d)
        self.assertAlmostEqual(d["sample_time_s"], 0.1)


# ══════════════════════════════════════════════════════════════════════════════
# ASCII histogram
# ══════════════════════════════════════════════════════════════════════════════

class TestAsciiHistogram(unittest.TestCase):

    def test_returns_string(self):
        self.assertIsInstance(bbc.ascii_histogram(list(range(1, 101))), str)

    def test_identical_values(self):
        self.assertIn("identical", bbc.ascii_histogram([42.0] * 10))

    def test_line_count(self):
        lines = [l for l in bbc.ascii_histogram(list(range(1, 1001)), bins=20).splitlines() if l.strip()]
        self.assertEqual(len(lines), 20)


# ══════════════════════════════════════════════════════════════════════════════
# print_report + write_json
# ══════════════════════════════════════════════════════════════════════════════

def _make_run(label, mean_ns, n=100, sample_time_s=0.1):
    import random
    rng  = random.Random(hash(label) & 0xFFFF)
    samp = [max(1.0, rng.gauss(mean_ns, mean_ns * 0.02)) for _ in range(n)]
    run  = bbc.BenchRun(
        label=label, ref="AddrManAdd", sha="a" * 40,
        bench_name="AddrManAdd", warmup_n=5,
        sample_time_s=sample_time_s,
        raw_samples=[mean_ns] * 5 + samp,
        clean_samples=samp, outliers_removed=0,
    )
    run.finalise()
    return run


class TestReport(unittest.TestCase):

    def test_print_report_no_crash(self):
        base = _make_run("master",   50_000)
        pr   = _make_run("mybranch", 48_000)
        buf  = io.StringIO()
        with redirect_stdout(buf):
            bbc.print_report(base, pr)
        out = buf.getvalue()
        self.assertIn("AddrManAdd", out)
        self.assertIn("BENCHMARK",  out)
        self.assertIn("Welch t",    out)
        self.assertIn("Cohen",      out)
        self.assertIn("0.1",        out)   # sample_time_s visible in header

    def test_write_json_schema_version(self):
        base = _make_run("master",   50_000)
        pr   = _make_run("mybranch", 48_000)
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            bbc.write_json(base, pr, path)
            doc = json.loads(Path(path).read_text())
        finally:
            os.unlink(path)
        self.assertEqual(doc["schema_version"], bbc.SCHEMA_VERSION)
        self.assertIn("base",          doc)
        self.assertIn("pr",            doc)
        self.assertIn("comparison",    doc)
        self.assertIn("p_value",       doc["comparison"])
        self.assertIn("cohens_d",      doc["comparison"])
        self.assertIn("sample_time_s", doc["base"])
        self.assertIn("sample_time_s", doc["pr"])


# ══════════════════════════════════════════════════════════════════════════════
# CLI argument parsing
# ══════════════════════════════════════════════════════════════════════════════

class TestCLI(unittest.TestCase):

    def _parse(self, args):
        return bbc.build_parser().parse_args(args)

    def test_list_benchmarks_no_pr_ref(self):
        args = self._parse(["--repo", "/tmp", "--base-ref", "master", "--list-benchmarks"])
        self.assertTrue(args.list_benchmarks)
        self.assertIsNone(args.pr_ref)

    def test_benchmark_and_list_mutually_exclusive(self):
        with self.assertRaises(SystemExit):
            self._parse(["--repo", "/tmp", "--pr-ref", "b",
                         "--benchmark", "Foo", "--list-benchmarks"])

    def test_one_of_benchmark_or_list_required(self):
        with self.assertRaises(SystemExit):
            self._parse(["--repo", "/tmp", "--pr-ref", "b"])

    def test_new_defaults(self):
        args = self._parse(["--repo", "/tmp", "--pr-ref", "b", "--benchmark", "Foo"])
        self.assertEqual(args.samples,          500)
        self.assertAlmostEqual(args.sample_time, 0.5)
        self.assertEqual(args.warmup,            20)
        self.assertEqual(args.base_ref,          "master")
        self.assertIsNone(args.output_json)
        self.assertFalse(args.keep_builds)
        self.assertFalse(args.skip_build)

    def test_iterations_flag_no_longer_exists(self):
        with self.assertRaises(SystemExit):
            self._parse(["--repo", "/tmp", "--pr-ref", "b",
                         "--benchmark", "Foo", "--iterations", "1000"])

    def test_samples_and_sample_time_accepted(self):
        args = self._parse(["--repo", "/tmp", "--pr-ref", "b", "--benchmark", "Foo",
                             "--samples", "50", "--sample-time", "0.5"])
        self.assertEqual(args.samples, 50)
        self.assertAlmostEqual(args.sample_time, 0.5)

    def test_pr_ref_required_without_list(self):
        with self.assertRaises(SystemExit):
            bbc.main(["--repo", FAKE_REPO, "--base-ref", "master", "--benchmark", "AddrManAdd"])

    def test_invalid_sample_time_dies(self):
        with self.assertRaises(SystemExit):
            bbc.main(["--repo", FAKE_REPO, "--base-ref", "master",
                      "--pr-ref", "feature-branch", "--benchmark", "AddrManAdd",
                      "--sample-time", "0"])

    def test_samples_too_few_dies(self):
        with self.assertRaises(SystemExit):
            bbc.main(["--repo", FAKE_REPO, "--base-ref", "master",
                      "--pr-ref", "feature-branch", "--benchmark", "AddrManAdd",
                      "--samples", "1"])


# ══════════════════════════════════════════════════════════════════════════════
# Cleanup manager
# ══════════════════════════════════════════════════════════════════════════════

class TestCleanup(unittest.TestCase):

    def test_missing_paths_safe(self):
        c = bbc._Cleanup("/tmp", keep=False)
        c.register_worktree("/nonexistent/path/xyz")
        c.run()   # must not raise

    def test_keep_skips_removal(self):
        tmp = tempfile.mkdtemp()
        c = bbc._Cleanup("/tmp", keep=True)
        c.register_tmp_dir(tmp)
        c.run()
        self.assertTrue(Path(tmp).exists())
        shutil.rmtree(tmp)

    def test_removes_tmp_dir(self):
        tmp = tempfile.mkdtemp()
        c = bbc._Cleanup("/tmp", keep=False)
        c.register_tmp_dir(tmp)
        c.run()
        self.assertFalse(Path(tmp).exists())

    def test_idempotent(self):
        tmp = tempfile.mkdtemp()
        c = bbc._Cleanup("/tmp", keep=False)
        c.register_tmp_dir(tmp)
        c.run()
        c.run()   # second call must not raise


# ══════════════════════════════════════════════════════════════════════════════
# End-to-end integration
# ══════════════════════════════════════════════════════════════════════════════

class TestEndToEnd(unittest.TestCase):

    def _run_main(self, extra_args, work=None):
        base_args = [
            "--repo",      FAKE_REPO,
            "--base-ref",  "master",
            "--pr-ref",    "feature-branch",
            "--benchmark", "AddrManAdd",
            "--samples",   "20",
            "--warmup",    "5",
            "--keep-builds",
        ]
        if work:
            base_args += ["--work-dir", work]
        buf = io.StringIO()
        with redirect_stdout(buf):
            with (
                patch.object(bbc, "find_bench_binary", return_value=FAKE_BIN),
                patch.object(bbc, "worktree_create"),
                patch.object(bbc, "worktree_remove"),
                patch.object(bbc, "cmake_build"),
            ):
                bbc.main(base_args + extra_args)
        return buf.getvalue()

    def test_report_content(self):
        with tempfile.TemporaryDirectory() as work:
            Path(work, "base_build").mkdir()
            Path(work, "pr_build").mkdir()
            out = self._run_main([], work=work)
        self.assertIn("AddrManAdd", out)
        self.assertIn("BENCHMARK",  out)
        self.assertIn("Welch t",    out)
        self.assertIn("Cohen",      out)
        self.assertIn("0.5",        out)   # default sample_time visible

    def test_sample_time_flag_in_report(self):
        with tempfile.TemporaryDirectory() as work:
            Path(work, "base_build").mkdir()
            Path(work, "pr_build").mkdir()
            out = self._run_main(["--sample-time", "0.25"], work=work)
        self.assertIn("0.25", out)

    def test_list_benchmarks_does_not_sample(self):
        with tempfile.TemporaryDirectory() as work:
            Path(work, "base_build").mkdir()
            buf = io.StringIO()
            with redirect_stdout(buf):
                with (
                    patch.object(bbc, "find_bench_binary", return_value=FAKE_BIN),
                    patch.object(bbc, "worktree_create"),
                    patch.object(bbc, "worktree_remove"),
                    patch.object(bbc, "cmake_build"),
                    patch.object(bbc, "run_benchmark_batch") as mock_sample,
                ):
                    bbc.main([
                        "--repo",            FAKE_REPO,
                        "--base-ref",        "master",
                        "--list-benchmarks",
                        "--work-dir",        work,
                        "--keep-builds",
                    ])
        mock_sample.assert_not_called()
        self.assertIn("AddrManAdd", buf.getvalue())

    def test_json_output_valid(self):
        with tempfile.TemporaryDirectory() as work:
            Path(work, "base_build").mkdir()
            Path(work, "pr_build").mkdir()
            json_path = os.path.join(tempfile.gettempdir(), "bbc_test_out.json")
            try:
                self._run_main(["--output-json", json_path, "--sample-time", "0.05"], work=work)
                doc = json.loads(Path(json_path).read_text())
            finally:
                Path(json_path).unlink(missing_ok=True)

        self.assertEqual(doc["schema_version"], bbc.SCHEMA_VERSION)
        self.assertIn("base",       doc)
        self.assertIn("pr",         doc)
        self.assertIn("comparison", doc)
        for side in ("base", "pr"):
            self.assertGreater(len(doc[side]["samples_ns"]), 0)
            for v in doc[side]["samples_ns"]:
                self.assertGreater(v, 0)
            self.assertAlmostEqual(doc[side]["sample_time_s"], 0.05)
        p = doc["comparison"]["p_value"]
        self.assertGreaterEqual(p, 0.0)
        self.assertLessEqual(p,    1.0)

    def test_json_samples_are_ns_per_op(self):
        """
        Regression: the old design stored ns/op * iters (could be ~1e8).
        The new design must store ns/op directly (~50000 for the fake binary).
        """
        with tempfile.TemporaryDirectory() as work:
            Path(work, "base_build").mkdir()
            Path(work, "pr_build").mkdir()
            json_path = os.path.join(tempfile.gettempdir(), "bbc_test_nsop.json")
            try:
                self._run_main(["--output-json", json_path, "--sample-time", "0.1"], work=work)
                doc = json.loads(Path(json_path).read_text())
            finally:
                Path(json_path).unlink(missing_ok=True)

        for side in ("base", "pr"):
            for v in doc[side]["samples_ns"]:
                self.assertGreater(v, 10_000,
                    f"{side} sample {v} ns is too small — possible ns/op division error")
                self.assertLess(v, 500_000,
                    f"{side} sample {v} ns is too large — possible ns/op * iters error")

    def test_labels_in_report(self):
        with tempfile.TemporaryDirectory() as work:
            Path(work, "base_build").mkdir()
            Path(work, "pr_build").mkdir()
            buf = io.StringIO()
            with redirect_stdout(buf):
                with (
                    patch.object(bbc, "find_bench_binary", return_value=FAKE_BIN),
                    patch.object(bbc, "worktree_create"),
                    patch.object(bbc, "worktree_remove"),
                    patch.object(bbc, "cmake_build"),
                ):
                    bbc.main([
                        "--repo",        FAKE_REPO,
                        "--base-ref",    "master",
                        "--pr-ref",      "feature-branch",
                        "--benchmark",   "AddrManAdd",
                        "--samples",     "15",
                        "--warmup",      "3",
                        "--work-dir",    work,
                        "--keep-builds",
                        "--base-label",  "my-base",
                        "--pr-label",    "my-pr",
                    ])
        out = buf.getvalue()
        self.assertIn("my-base", out)
        self.assertIn("my-pr",   out)



class TestConfigFile(unittest.TestCase):

    def _write_config(self, tmp: str, content: str) -> str:
        p = os.path.join(tmp, "bench.toml")
        open(p, "w").write(content)
        return p

    def test_config_sets_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._write_config(tmp, '''
repo = "/tmp/fake"
jobs = 3
samples = 99
''')
            # parse with config but supply required flags on CLI
            argv = ["--config", cfg, "--repo", FAKE_REPO,
                    "--benchmark", "AddrManAdd", "--pr-ref", "feature-branch"]
            args = bbc.build_parser().parse_args(argv)
            # apply config the same way main() does
            import tomllib
            with open(cfg, "rb") as f:
                cfg_data = tomllib.load(f)
            defaults = {k.replace("-", "_"): v for k, v in cfg_data.items()}
            bbc.build_parser().set_defaults(**defaults)
            # re-parse with defaults applied
            p = bbc.build_parser()
            p.set_defaults(**defaults)
            args = p.parse_args(argv)
            self.assertEqual(args.jobs, 3)
            self.assertEqual(args.samples, 99)

    def test_cli_overrides_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._write_config(tmp, "samples = 99\n")
            argv = ["--config", cfg, "--repo", FAKE_REPO,
                    "--benchmark", "AddrManAdd", "--pr-ref", "feature-branch",
                    "--samples", "42"]
            import tomllib
            p = bbc.build_parser()
            with open(cfg, "rb") as f:
                p.set_defaults(**{k.replace("-","_"): v for k,v in tomllib.load(f).items()})
            args = p.parse_args(argv)
            self.assertEqual(args.samples, 42)

    def test_missing_config_dies(self):
        with self.assertRaises(SystemExit):
            bbc.main(["--config", "/nonexistent/path/bench.toml",
                      "--repo", FAKE_REPO, "--benchmark", "AddrManAdd",
                      "--pr-ref", "feature-branch"])

    def test_invalid_toml_dies(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._write_config(tmp, "this is not valid toml ===\n")
            with self.assertRaises(SystemExit):
                bbc.main(["--config", cfg, "--repo", FAKE_REPO,
                          "--benchmark", "AddrManAdd", "--pr-ref", "feature-branch"])

    def test_hyphen_keys_accepted(self):
        """TOML keys with hyphens (e.g. work-dir) must map to underscore dest."""
        with tempfile.TemporaryDirectory() as tmp:
            cfg = self._write_config(tmp, f'work-dir = "{tmp}"\nsample-time = 0.25\n')
            import tomllib
            p = bbc.build_parser()
            with open(cfg, "rb") as f:
                p.set_defaults(**{k.replace("-","_"): v for k,v in tomllib.load(f).items()})
            args = p.parse_args(["--repo", FAKE_REPO, "--benchmark", "AddrManAdd",
                                  "--pr-ref", "feature-branch"])
            self.assertEqual(args.work_dir, tmp)
            self.assertAlmostEqual(args.sample_time, 0.25)


# ══════════════════════════════════════════════════════════════════════════════
# Runner
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite  = loader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)

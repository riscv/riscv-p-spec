#!/usr/bin/env python3
"""Compile-only API tester for RISC-V P extension intrinsics.

Generates test files from the spec dynamically and compiles each one
to verify that the intrinsic exists with the correct signature.

Usage:
  python3 intrinsic-utils/api_tester.py --cc riscv64-unknown-elf-gcc
  python3 intrinsic-utils/api_tester.py --cc gcc --march rv32gcp --mabi ilp32 -- -I/extra/include
"""

import argparse
import json
import multiprocessing
import os
import shutil
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from spec2json import parse_spec
from gen_api_test import generate_all


def compile_one(args):
    """Compile a single test file. Called in worker processes."""
    base_cmd, filepath, xlen, verbose = args
    name = Path(filepath).stem
    cmd = base_cmd + [filepath]

    if verbose:
        cmd_str = " ".join(cmd)
    else:
        cmd_str = ""

    content = Path(filepath).read_text()
    if xlen and content.startswith("#if __riscv_xlen"):
        guard_xlen = "32" if "== 32" in content.split('\n')[0] else "64"
        if guard_xlen != xlen:
            return ("SKIP", name, "", cmd_str)

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        return ("PASS", name, "", cmd_str)

    stderr = "\n".join(result.stderr.strip().splitlines()[:3])
    return ("FAIL", name, stderr, cmd_str)


def xlen_from_march(march):
    """Infer XLEN from -march string."""
    if "rv32" in march.lower():
        return "32"
    if "rv64" in march.lower():
        return "64"
    return None


def run_tests(cc, test_dir, march, mabi, extra_opts, jobs, verbose=False):
    """Compile each .c file in test_dir.

    Returns dict mapping test name -> (status, stderr).
    status is "PASS", "FAIL", or "SKIP".
    """
    test_files = sorted(test_dir.glob("*.c"))
    total = len(test_files)

    base_cmd = [cc, f"-march={march}", f"-mabi={mabi}", "-fsyntax-only"]
    base_cmd.extend(extra_opts)

    xlen = xlen_from_march(march)
    tasks = [(base_cmd, str(f), xlen, verbose) for f in test_files]
    results = {}

    if verbose:
        # Sequential for readable output
        for i, task in enumerate(tasks, 1):
            status, name, stderr, cmd_str = compile_one(task)
            results[name] = (status, stderr)
            print(f"  [{i}/{total}] {status} {name}")
            if cmd_str:
                print(f"    $ {cmd_str}")
            if stderr:
                for line in stderr.splitlines():
                    print(f"    {line}")
    else:
        with ProcessPoolExecutor(max_workers=jobs) as executor:
            futures = {executor.submit(compile_one, t): t for t in tasks}
            for future in as_completed(futures):
                status, name, stderr, _ = future.result()
                results[name] = (status, stderr)

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Compile-only API tester for RISC-V P extension intrinsics",
    )
    parser.add_argument("--cc", required=True, help="Path to C compiler")
    parser.add_argument("--march", default="rv64gcp",
                        help="Architecture string (default: rv64gcp)")
    parser.add_argument("--mabi", default="lp64",
                        help="ABI string (default: lp64)")
    parser.add_argument("--spec", default=None,
                        help="Path to spec file (default: P-ext-intrinsics.adoc)")
    parser.add_argument("-j", "--jobs", type=int, default=multiprocessing.cpu_count(),
                        help="Number of parallel jobs (default: nproc)")
    parser.add_argument("-I", dest="include_paths", action="append", default=[],
                        help="Add include path (can be specified multiple times)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Show detailed compile commands and results")
    parser.add_argument("-o", "--output", default="api-test",
                        help="Output directory for test files (default: ./api-test)")
    parser.add_argument("extra_opts", nargs="*",
                        help="Extra compiler options (put after --)")
    args = parser.parse_args()

    spec_path = Path(args.spec) if args.spec else REPO_ROOT / "P-ext-intrinsics.adoc"
    if not spec_path.exists():
        print(f"Error: spec file not found: {spec_path}", file=sys.stderr)
        sys.exit(1)

    # Verify compiler exists
    cc = shutil.which(args.cc) or args.cc
    try:
        result = subprocess.run([cc, "--version"], capture_output=True, text=True)
    except OSError as e:
        print(f"Error: cannot run compiler: {cc}: {e}", file=sys.stderr)
        sys.exit(1)
    if result.returncode != 0:
        print(f"Error: compiler not found or not working: {cc}", file=sys.stderr)
        sys.exit(1)

    # Prepend -I flags to extra opts
    for inc in args.include_paths:
        args.extra_opts = [f"-I{inc}"] + args.extra_opts

    # Auto-detect clang without riscv target prefix
    cc_basename = Path(cc).name
    is_clang = "clang" in result.stdout.lower() or "clang" in cc_basename
    has_riscv_prefix = cc_basename.startswith("riscv")
    if is_clang and not has_riscv_prefix:
        xlen = "32" if "32" in args.march else "64"
        clang_extra = [f"-target", f"riscv{xlen}-elf",
                       "-menable-experimental-extensions"]
        args.extra_opts = clang_extra + args.extra_opts

    # Parse spec -> JSON
    print(f"Parsing spec: {spec_path}")
    data = parse_spec(spec_path)
    total_intrinsics = sum(len(s["intrinsics"]) for s in data["sections"])

    # Generate test files
    test_dir = Path(args.output)

    count = generate_all(data, test_dir)
    print(f"Generated {count} test files")

    # Run compilation tests
    print(f"Compiler: {cc}")
    print(f"Options: -march={args.march} -mabi={args.mabi} {' '.join(args.extra_opts)}")
    print(f"Jobs: {args.jobs}")
    print()

    results = run_tests(
        cc, test_dir, args.march, args.mabi, args.extra_opts,
        jobs=args.jobs, verbose=args.verbose
    )

    # Build intrinsic name -> test name mapping (strip __riscv_ prefix)
    name_to_section = {}
    for section in data["sections"]:
        section_name = section["name"]
        for intr in section["intrinsics"]:
            test_name = intr["name"].removeprefix("__riscv_")
            name_to_section[test_name] = section_name

    # Group results by section
    section_results = {}
    for test_name, (status, stderr) in results.items():
        section_name = name_to_section.get(test_name, "Unknown")
        if section_name not in section_results:
            section_results[section_name] = {"PASS": 0, "FAIL": 0, "SKIP": 0}
        section_results[section_name][status] += 1

    # Print per-section summary
    total_pass = sum(r["PASS"] for r in section_results.values())
    total_fail = sum(r["FAIL"] for r in section_results.values())
    total_skip = sum(r["SKIP"] for r in section_results.values())

    # Dynamic column width based on longest section name
    col_w = max(len(s["name"]) for s in data["sections"]) + 2  # +2 for mark prefix
    line_w = col_w + 18  # 3 columns * 6 chars each

    print("=" * line_w)
    print(f"  {'Section':<{col_w - 2}} {'PASS':>5} {'FAIL':>5} {'SKIP':>5}")
    print("-" * line_w)

    # Use section order from spec
    seen = set()
    for section in data["sections"]:
        sn = section["name"]
        if sn in seen or sn not in section_results:
            continue
        seen.add(sn)
        r = section_results[sn]
        mark = " " if r["FAIL"] == 0 else "*"
        print(f"{mark} {sn:<{col_w - 2}} {r['PASS']:>5} {r['FAIL']:>5} {r['SKIP']:>5}")

    print("-" * line_w)
    print(f"  {'Total':<{col_w - 2}} {total_pass:>5} {total_fail:>5} {total_skip:>5}")
    print("=" * line_w)
    print()

    # List all failures with error details
    all_failed = sorted(
        [(name, stderr) for name, (status, stderr) in results.items()
         if status == "FAIL"]
    )
    if all_failed:
        print(f"Failed tests ({len(all_failed)}):")
        print()
        for name, stderr in all_failed:
            section_name = name_to_section.get(name, "Unknown")
            print(f"  FAIL __riscv_{name}  [{section_name}]")
            for line in stderr.splitlines():
                print(f"    {line}")
        print()

    print(f"Results: {total_pass} passed, {total_fail} failed, {total_skip} skipped "
          f"/ {count} total")
    print(f"Test files: {test_dir}")

    sys.exit(1 if total_fail else 0)


if __name__ == "__main__":
    main()

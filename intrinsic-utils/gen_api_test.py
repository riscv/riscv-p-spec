#!/usr/bin/env python3
"""Generate compile-only API test files from intrinsics JSON data.

Each intrinsic gets one .c file that verifies the intrinsic exists
and has the correct signature by calling it with dummy arguments.
"""

import json
import os
import sys
from pathlib import Path

# Default value expressions for each type used as a function argument.
DEFAULT_VALUES = {
    "int8_t":       "(int8_t)0",
    "uint8_t":      "(uint8_t)0",
    "int16_t":      "(int16_t)0",
    "uint16_t":     "(uint16_t)0",
    "int32_t":      "(int32_t)0",
    "uint32_t":     "(uint32_t)0",
    "int64_t":      "(int64_t)0",
    "uint64_t":     "(uint64_t)0",
    "int":          "(int)0",
    "unsigned":     "(unsigned)0",
    "unsigned int": "(unsigned int)0",
    "int8x4_t":     "v_i8x4",
    "uint8x4_t":    "v_u8x4",
    "int16x2_t":    "v_i16x2",
    "uint16x2_t":   "v_u16x2",
    "int8x8_t":     "v_i8x8",
    "uint8x8_t":    "v_u8x8",
    "int16x4_t":    "v_i16x4",
    "uint16x4_t":   "v_u16x4",
    "int32x2_t":    "v_i32x2",
    "uint32x2_t":   "v_u32x2",
    # Pointer types
    "int8_t *":     "&s_i8",
    "uint8_t *":    "&s_u8",
    "int16_t *":    "&s_i16",
    "uint16_t *":   "&s_u16",
    "int32_t *":    "&s_i32",
    "uint32_t *":   "&s_u32",
    # const immediate types
    "const unsigned": "1",
}

# Packed types that need local variable declarations.
PACKED_TYPES = [
    "int8x4_t", "uint8x4_t", "int16x2_t", "uint16x2_t",
    "int8x8_t", "uint8x8_t", "int16x4_t", "uint16x4_t",
    "int32x2_t", "uint32x2_t",
]

# Scalar types that need pointer targets.
POINTER_TARGETS = {
    "int8_t *":    ("int8_t",   "s_i8"),
    "uint8_t *":   ("uint8_t",  "s_u8"),
    "int16_t *":   ("int16_t",  "s_i16"),
    "uint16_t *":  ("uint16_t", "s_u16"),
    "int32_t *":   ("int32_t",  "s_i32"),
    "uint32_t *":  ("uint32_t", "s_u32"),
}


def collect_needed_decls(intrinsic):
    """Collect which local variable declarations this intrinsic needs."""
    needed_packed = set()
    needed_pointers = set()

    all_types = [a["type"] for a in intrinsic["arguments"]]

    for t in all_types:
        if t in PACKED_TYPES:
            needed_packed.add(t)
        if t in POINTER_TARGETS:
            needed_pointers.add(t)

    return needed_packed, needed_pointers


HEADER = "riscv_packed_simd.h"


def generate_test(intrinsic):
    """Generate C source for a compile-only API test."""
    name = intrinsic["name"]
    ret_type = intrinsic["return_type"]
    args = intrinsic["arguments"]
    availability = intrinsic["availability"]

    needed_packed, needed_pointers = collect_needed_decls(intrinsic)

    lines = []
    lines.append(f"/* Compile-only API test for {name} */")
    lines.append(f'#include <{HEADER}>')
    lines.append('')
    lines.append('void test(void) {')

    # Declare packed type variables
    for t in sorted(needed_packed):
        var = DEFAULT_VALUES[t]
        lines.append(f'  {t} {var} = {{0}};')

    # Declare pointer target variables
    for t in sorted(needed_pointers):
        base_type, var_name = POINTER_TARGETS[t]
        lines.append(f'  {base_type} {var_name} = 0;')

    # Build argument list
    arg_exprs = []
    for a in args:
        t = a["type"]
        val = DEFAULT_VALUES.get(t)
        if val is None:
            val = f"/* unknown type: {t} */ 0"
        arg_exprs.append(val)

    call_expr = f'{name}({", ".join(arg_exprs)})'

    # Generate the call
    if ret_type == "void":
        lines.append(f'  {call_expr};')
    else:
        lines.append(f'  {ret_type} result = {call_expr};')
        lines.append('  (void)result;')

    lines.append('}')
    lines.append('')

    body = '\n'.join(lines)

    # Wrap with availability guard if needed
    if availability == "rv32_only":
        body = f'#if __riscv_xlen == 32\n{body}\n#endif\n'
    elif availability == "rv64_only":
        body = f'#if __riscv_xlen == 64\n{body}\n#endif\n'

    return body


def generate_all(data, output_dir):
    """Generate all test files. Returns count of files generated."""
    if output_dir.exists():
        for old in output_dir.glob("*.c"):
            old.unlink()
    output_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for section in data["sections"]:
        for intrinsic in section["intrinsics"]:
            name = intrinsic["name"]
            filename = name.removeprefix("__riscv_") + ".c"
            filepath = output_dir / filename
            content = generate_test(intrinsic)
            filepath.write_text(content)
            count += 1
    return count


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate compile-only API test files")
    parser.add_argument("--json", default=None, help="Path to intrinsics.json")
    parser.add_argument("--output", default=None, help="Output directory")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent
    json_path = Path(args.json) if args.json else script_dir / "intrinsics.json"
    output_dir = Path(args.output) if args.output else script_dir / "api-test"

    if not json_path.exists():
        print(f"Error: {json_path} not found. Run spec2json.py first.",
              file=sys.stderr)
        sys.exit(1)

    with open(json_path) as f:
        data = json.load(f)

    count = generate_all(data, output_dir)
    print(f"Generated {count} test files in {output_dir}/")


if __name__ == "__main__":
    main()

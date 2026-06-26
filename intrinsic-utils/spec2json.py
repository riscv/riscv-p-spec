#!/usr/bin/env python3
"""Extract intrinsic information from P-ext-intrinsics.adoc into JSON format."""

import json
import re
import sys
from pathlib import Path


# Packed SIMD type definitions from the spec.
PACKED_TYPES = [
    {"name": "int8x4_t",   "size_bytes": 4, "alignment_bytes": 4, "description": "Four signed 8-bit integers",     "element_type": "int8_t",   "element_count": 4, "total_bits": 32},
    {"name": "uint8x4_t",  "size_bytes": 4, "alignment_bytes": 4, "description": "Four unsigned 8-bit integers",   "element_type": "uint8_t",  "element_count": 4, "total_bits": 32},
    {"name": "int16x2_t",  "size_bytes": 4, "alignment_bytes": 4, "description": "Two signed 16-bit integers",     "element_type": "int16_t",  "element_count": 2, "total_bits": 32},
    {"name": "uint16x2_t", "size_bytes": 4, "alignment_bytes": 4, "description": "Two unsigned 16-bit integers",   "element_type": "uint16_t", "element_count": 2, "total_bits": 32},
    {"name": "int8x8_t",   "size_bytes": 8, "alignment_bytes": 8, "description": "Eight signed 8-bit integers",    "element_type": "int8_t",   "element_count": 8, "total_bits": 64},
    {"name": "uint8x8_t",  "size_bytes": 8, "alignment_bytes": 8, "description": "Eight unsigned 8-bit integers",  "element_type": "uint8_t",  "element_count": 8, "total_bits": 64},
    {"name": "int16x4_t",  "size_bytes": 8, "alignment_bytes": 8, "description": "Four signed 16-bit integers",    "element_type": "int16_t",  "element_count": 4, "total_bits": 64},
    {"name": "uint16x4_t", "size_bytes": 8, "alignment_bytes": 8, "description": "Four unsigned 16-bit integers",  "element_type": "uint16_t", "element_count": 4, "total_bits": 64},
    {"name": "int32x2_t",  "size_bytes": 8, "alignment_bytes": 8, "description": "Two signed 32-bit integers",     "element_type": "int32_t",  "element_count": 2, "total_bits": 64},
    {"name": "uint32x2_t", "size_bytes": 8, "alignment_bytes": 8, "description": "Two unsigned 32-bit integers",   "element_type": "uint32_t", "element_count": 2, "total_bits": 64},
]

# Regex to extract prototype: return_type func_name(args);
PROTO_RE = re.compile(
    r'^(?P<ret>.+?)\s+(?P<name>__riscv_\w+)\((?P<args>[^)]*)\);?$'
)

# Regex to parse a single argument
ARG_RE = re.compile(
    r'^(?P<type>(?:const\s+)?[\w]+(?:\s+[\w]+)*(?:\s*\*)?)\s+(?P<name>\w+)$'
)

# Constraint column: "0 ≤ name ≤ N"
CONSTRAINT_RE = re.compile(r'(\d+)\s*[≤<=]+\s*(\w+)\s*[≤<=]+\s*(\d+)')

# AsciiDoc heading level detection
HEADING_RE = re.compile(r'^(?P<equals>={2,4})\s+(?P<title>.+)$')

# Availability from heading title
AVAILABILITY_RE = re.compile(r'\((?P<avail>RV32|RV64)\s+Only\)', re.IGNORECASE)


def parse_argument(arg_str):
    """Parse a single C argument string into type and name.

    Handles cases like:
      int32_t rs1        -> type="int32_t", name="rs1"
      const unsigned shamt -> type="const unsigned", name="shamt"
      int8_t *p          -> type="int8_t *", name="p"
      uint8x4_t v        -> type="uint8x4_t", name="v"
    """
    arg_str = arg_str.strip()
    if not arg_str:
        return None

    # Handle pointer: "int8_t *p" or "int8_t* p"
    m = re.match(r'^(.+?)\s*(\*)\s*(\w+)$', arg_str)
    if m:
        return {"type": m.group(1).strip() + ' *', "name": m.group(3)}

    # Regular: split on last whitespace
    m = ARG_RE.match(arg_str)
    if m:
        return {"type": m.group('type').strip(), "name": m.group('name').strip()}

    # Fallback: split on last space
    parts = arg_str.rsplit(None, 1)
    if len(parts) == 2:
        return {"type": parts[0].strip(), "name": parts[1].strip()}

    return {"type": arg_str, "name": ""}


def parse_prototype(proto_str):
    """Parse a C prototype string into return_type, name, and arguments."""
    proto_str = proto_str.strip().rstrip(';').strip()
    m = PROTO_RE.match(proto_str)
    if not m:
        return None
    ret = m.group('ret').strip()
    name = m.group('name').strip()
    args_str = m.group('args').strip()

    arguments = []
    if args_str:
        for arg in args_str.split(','):
            arg = arg.strip()
            parsed_arg = parse_argument(arg)
            if parsed_arg:
                arguments.append(parsed_arg)

    return {"return_type": ret, "name": name, "arguments": arguments}


def parse_instructions(instr_str, availability):
    """Parse instruction column into rv32/rv64 instruction lists.

    Platform annotations like (RV32) or (RV64) apply to all preceding
    unannotated parts since the last annotation (backward-scan).
    """
    if not instr_str or not instr_str.strip():
        return {"rv32": [], "rv64": []}

    instr_str = instr_str.strip()

    parts = split_instruction_parts(instr_str)

    # First pass: extract instruction names and platform annotations per part
    parsed_parts = []
    for part in parts:
        part = part.strip()
        if not part:
            continue

        insn_names = re.findall(r'`([^`]+)`', part)
        if not insn_names:
            continue
        insn_str = '+'.join(insn_names)

        platform = None
        plat_match = re.search(r'\(RV(32|64)\)\s*$', part)
        if plat_match:
            platform = f"rv{plat_match.group(1)}"

        parsed_parts.append({"insn": insn_str, "platform": platform})

    # Second pass: backward-scan for platform assignment
    assigned = [p["platform"] for p in parsed_parts]
    for i in range(len(assigned) - 1, -1, -1):
        if assigned[i] is not None:
            for j in range(i - 1, -1, -1):
                if assigned[j] is not None:
                    break
                assigned[j] = assigned[i]

    rv32_instrs = []
    rv64_instrs = []
    generic_instrs = []

    for i, pp in enumerate(parsed_parts):
        platform = assigned[i]
        if platform == 'rv32':
            rv32_instrs.append(pp["insn"])
        elif platform == 'rv64':
            rv64_instrs.append(pp["insn"])
        else:
            generic_instrs.append(pp["insn"])

    # Assign generic instructions based on availability
    if availability == 'rv32_only':
        rv32_instrs = generic_instrs + rv32_instrs
        rv64_instrs = []
    elif availability == 'rv64_only':
        rv64_instrs = generic_instrs + rv64_instrs
        rv32_instrs = []
    else:
        if rv32_instrs or rv64_instrs:
            if generic_instrs:
                rv32_instrs = generic_instrs + rv32_instrs
                rv64_instrs = generic_instrs + rv64_instrs
        else:
            rv32_instrs = generic_instrs[:]
            rv64_instrs = generic_instrs[:]

    return {"rv32": rv32_instrs, "rv64": rv64_instrs}


def split_instruction_parts(s):
    """Split instruction string by commas, respecting parentheses."""
    parts = []
    depth = 0
    current = []
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == '(':
            depth += 1
            current.append(ch)
        elif ch == ')':
            depth = max(0, depth - 1)
            current.append(ch)
        elif ch == ',' and depth == 0:
            parts.append(''.join(current))
            current = []
            i += 1
            while i < len(s) and s[i] == ' ':
                i += 1
            continue
        else:
            current.append(ch)
        i += 1
    if current:
        parts.append(''.join(current))
    return parts


def parse_availability(title):
    """Derive availability from section/subsection title."""
    # Match "(RV32 Only)" or "(RV64 Only)" with parentheses
    m = AVAILABILITY_RE.search(title)
    if m:
        return f"{m.group('avail').lower()}_only"
    # Match "RV32 Only" or "RV64 Only" without parentheses
    m2 = re.search(r'\bRV(32|64)\s+Only\b', title, re.IGNORECASE)
    if m2:
        return f"rv{m2.group(1)}_only"
    return "both"


def count_cols(cols_attr):
    """Count columns from AsciiDoc [cols="..."] attribute."""
    m = re.match(r'\[cols="([^"]+)"\]', cols_attr)
    if m:
        return len(m.group(1).split(','))
    return 0


def parse_table_cells(lines, start_idx):
    """Parse all cells from an AsciiDoc table body.

    start_idx should point to the line AFTER the opening |===.
    Returns (cells, end_idx) where cells is a list of cell content strings.
    """
    cells = []
    current_lines = []
    is_literal = False

    def flush():
        nonlocal current_lines, is_literal
        if not current_lines:
            return
        if is_literal:
            # Join literal cell lines with space
            content = ' '.join(l for l in current_lines if l)
        else:
            # Handle AsciiDoc soft break: strip trailing ' +' before joining
            processed = []
            for l in current_lines:
                if l.endswith(' +'):
                    l = l[:-2].rstrip()
                if l:
                    processed.append(l)
            content = ' '.join(processed)
        cells.append(content)
        current_lines = []

    i = start_idx
    while i < len(lines):
        stripped = lines[i].strip()

        if stripped == '|===':
            flush()
            return cells, i + 1

        if stripped == '':
            # Empty line - row separator in AsciiDoc tables
            flush()
            i += 1
            continue

        if stripped.startswith('l|'):
            flush()
            rest = stripped[2:].strip()
            current_lines = [rest] if rest else []
            is_literal = True
        elif stripped.startswith('|'):
            flush()
            rest = stripped[1:].strip()
            current_lines = [rest] if rest else []
            is_literal = False
        else:
            # Continuation line
            current_lines.append(stripped)

        i += 1

    flush()
    return cells, i


def parse_constraint(constraint_str):
    """Parse a constraint string like '0 ≤ name ≤ 31' into (name, min, max)."""
    if not constraint_str:
        return None
    m = CONSTRAINT_RE.search(constraint_str)
    if m:
        return (m.group(2), int(m.group(1)), int(m.group(3)))
    return None


def apply_constraint(arguments, constraint):
    """Apply a parsed constraint (name, min, max) as imm_range on matching argument."""
    if not constraint:
        return
    name, lo, hi = constraint
    for arg in arguments:
        if arg["name"] == name:
            arg["imm_range"] = [lo, hi]
            return


def extract_prototype(cell_content):
    """Extract prototype string from a cell (may be backtick-quoted or plain)."""
    # Check for backtick-quoted prototype
    m = re.search(r'`([^`]+)`', cell_content)
    if m and '__riscv_' in m.group(1):
        return m.group(1)
    # Plain text from literal cell
    if '__riscv_' in cell_content:
        return cell_content.strip()
    return None


def parse_spec(filepath):
    """Parse the AsciiDoc spec file and return structured data."""
    lines = Path(filepath).read_text().splitlines()

    sections = []
    current_category = ""
    current_section_name = ""
    current_section_desc = ""
    current_availability = "both"
    current_section = None

    # Track description lines between heading and table
    desc_lines = []
    collecting_desc = False

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Skip page breaks
        if stripped == '<<<':
            i += 1
            continue

        # Check for headings
        hm = HEADING_RE.match(stripped)
        if hm:
            level = len(hm.group('equals'))
            title = hm.group('title').strip()

            if level == 2:
                # Major category
                current_category = title
                current_section_name = ""
                current_availability = "both"
                current_section = None
                desc_lines = []
                collecting_desc = True
            elif level == 3:
                # Check if this is a bit-width sub-heading like "=== 64-bit"
                if re.match(r'^\d+-bit', title):
                    current_availability = parse_availability(title)
                else:
                    # New section
                    current_section_name = title
                    current_availability = parse_availability(title)
                    current_section = None
                    desc_lines = []
                    collecting_desc = True
            elif level == 4:
                # Sub-section: "==== 32-bit", "==== 64-bit (RV64 only)"
                current_availability = parse_availability(title)

            i += 1
            continue

        # Collect description text between heading and first table
        if collecting_desc:
            if (not stripped.startswith('[')
                    and not stripped.startswith('|')
                    and not stripped.startswith('l|')):
                if stripped and not stripped.startswith('*'):
                    desc_lines.append(stripped)
                i += 1
                continue
            else:
                collecting_desc = False
                current_section_desc = ' '.join(desc_lines) if desc_lines else ""

        # Check for table start: [cols="..."]
        if stripped.startswith('[cols='):
            num_cols = count_cols(stripped)
            i += 1
            # Find |=== on next non-empty line
            while i < len(lines) and lines[i].strip() == '':
                i += 1
            if i < len(lines) and lines[i].strip() == '|===':
                i += 1
                # Parse table cells
                all_cells, i = parse_table_cells(lines, i)
                # Skip header cells (first num_cols cells)
                data_cells = all_cells[num_cols:]
                # Group into rows
                for row_start in range(0, len(data_cells), num_cols):
                    row = data_cells[row_start:row_start + num_cols]
                    if len(row) < 1:
                        continue

                    proto_str = extract_prototype(row[0])
                    if not proto_str or '__riscv_' not in proto_str:
                        continue

                    parsed = parse_prototype(proto_str)
                    if not parsed:
                        print(f"WARNING: Failed to parse prototype: {proto_str}",
                              file=sys.stderr)
                        continue

                    # Ensure section exists
                    if current_section is None:
                        current_section = {
                            "category": current_category,
                            "name": current_section_name or current_category,
                            "description": current_section_desc,
                            "intrinsics": [],
                        }
                        sections.append(current_section)

                    instr_str = ""
                    if num_cols >= 2 and len(row) >= 2:
                        # Replace \+ with + for instruction chaining
                        instr_str = row[1].replace('\\+', '+')

                    instructions = parse_instructions(instr_str, current_availability)

                    # Parse constraint column if present
                    constraint_str = ""
                    if num_cols >= 3 and len(row) >= 3:
                        constraint_str = row[2]
                    constraint = parse_constraint(constraint_str)
                    apply_constraint(parsed["arguments"], constraint)

                    intrinsic = {
                        "name": parsed["name"],
                        "return_type": parsed["return_type"],
                        "arguments": parsed["arguments"],
                        "instructions": instructions,
                        "availability": current_availability,
                    }

                    current_section["intrinsics"].append(intrinsic)
            continue

        i += 1

    # Remove empty sections
    sections = [s for s in sections if s["intrinsics"]]

    return {"types": PACKED_TYPES, "sections": sections}


def main():
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent
    spec_path = repo_root / "P-ext-intrinsics.adoc"
    output_path = script_dir / "intrinsics.json"

    if len(sys.argv) > 1:
        spec_path = Path(sys.argv[1])
    if len(sys.argv) > 2:
        output_path = Path(sys.argv[2])

    if not spec_path.exists():
        print(f"Error: {spec_path} not found", file=sys.stderr)
        sys.exit(1)

    result = parse_spec(spec_path)

    total = sum(len(s["intrinsics"]) for s in result["sections"])
    print(f"Parsed {len(result['sections'])} sections, {total} intrinsics")
    for s in result["sections"]:
        print(f"  {s['name']}: {len(s['intrinsics'])} intrinsics")

    with open(output_path, 'w') as f:
        json.dump(result, f, indent=2)
        f.write('\n')

    print(f"Written to {output_path}")


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
Refreshes the item ID -> name lookup table in FFXIThings/Things.cs from a
Windower `res/items.lua` resource dump.

Why this exists: Things.cs's `thingNames` array is a hardcoded snapshot
generated once (originally ~May 2022). FFXI periodically backfills item
names into IDs that were previously unused/blank, so over time more and
more items show up as "Unknown Item" in Iocaine2's WMS tab even though
they're well within the array's existing bounds. Windower keeps its own
`res/items.lua` current, so re-running this script against a fresh
Windower install is the fastest way to refill those gaps.

Usage:
    python refresh_item_names.py --items-lua "E:\\FFXI\\res\\items.lua"

    # to point at a Things.cs outside this repo checkout:
    python refresh_item_names.py --items-lua "E:\\FFXI\\res\\items.lua" --things-cs "path\\to\\Things.cs"

What it does NOT do (by design):
    - It never shrinks or extends `maxID`. `thingType`, `thingStackSize`,
      `thingLogNameS`, `thingLogNameP`, and `thingSkill` are separate
      arrays in Things.cs sized to the same `maxID`, and none of them are
      touched here. If FFXI's item ID range ever grows past the current
      maxID, those arrays would need regenerating too (from data this
      script doesn't have `enlp`/plural log names, weapon skill, etc. for
      every entry) - that's a bigger job, not something to do casually.
    - It never overwrites a name that already exists with a blank one.
      If items.lua is missing an ID that Things.cs already has a real
      name for, the existing name is kept as-is.
"""

import argparse
import re
from pathlib import Path

DEFAULT_THINGS_CS = (
    Path(__file__).resolve().parents[2]
    / "Iocaine Assemblies" / "FFXIThingsDll" / "FFXIThings" / "Things.cs"
)

NAME_LINE_RE = re.compile(r'"((?:[^"\\]|\\.)*)"[,}]{0,2};?\s*//ID=(\d+)')
LUA_ENTRY_RE = re.compile(r'^\s*\[(\d+)\] = \{id=\d+,en="((?:[^"\\]|\\.)*)"', re.MULTILINE)
NO_ITEM_SENTINEL_ID = 65535


def parse_items_lua(path: Path) -> dict[int, str]:
    text = path.read_text(encoding="utf-8")
    names: dict[int, str] = {}
    for m in LUA_ENTRY_RE.finditer(text):
        item_id = int(m.group(1))
        if item_id == NO_ITEM_SENTINEL_ID:
            continue
        names[item_id] = m.group(2).replace('\\"', '"')
    return names


def parse_existing_names(block: str) -> dict[int, str]:
    names: dict[int, str] = {}
    for m in NAME_LINE_RE.finditer(block):
        names[int(m.group(2))] = m.group(1).replace('\\"', '"')
    return names


def escape_cs_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def build_array_block(names_by_id: dict[int, str], max_id: int) -> str:
    indent = " " * 38
    lines = [
        "        #region thingNames Array",
        f"        private static string[] thingNames = new string[{max_id + 1}] {{",
    ]
    for item_id in range(max_id + 1):
        escaped = escape_cs_string(names_by_id.get(item_id, ""))
        terminator = "};" if item_id == max_id else ","
        lines.append(f'{indent}"{escaped}"{terminator}\t\t//ID={item_id}')
    lines.append("        #endregion thingNames Array")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--items-lua", required=True, type=Path, help=r"Path to Windower's res\items.lua")
    parser.add_argument("--things-cs", default=DEFAULT_THINGS_CS, type=Path, help="Path to Things.cs to update")
    args = parser.parse_args()

    lua_names = parse_items_lua(args.items_lua)
    print(f"Parsed {len(lua_names)} named entries from {args.items_lua}")

    cs_text = args.things_cs.read_text(encoding="utf-8")
    header, footer = "#region thingNames Array", "#endregion thingNames Array"
    start = cs_text.index(header)
    end = cs_text.index(footer) + len(footer)

    existing_names = parse_existing_names(cs_text[start:end])
    max_id = max(existing_names)
    print(f"Existing table covers IDs 0-{max_id} ({len(existing_names)} entries)")

    merged: dict[int, str] = dict(existing_names)
    filled = 0
    for item_id, name in lua_names.items():
        if item_id > max_id:
            # Out of scope - see the module docstring for why this isn't handled here.
            continue
        if merged.get(item_id, "") in ("", ".") and name not in ("", "."):
            filled += 1
        merged[item_id] = name
    print(f"Filled {filled} previously-blank item name(s) from {args.items_lua.name}")

    new_block = build_array_block(merged, max_id)
    new_text = cs_text[:start] + new_block + cs_text[end:]

    # Things.cs is a Windows/CRLF file; keep it that way so the diff stays minimal.
    normalized = new_text.replace("\r\n", "\n").replace("\n", "\r\n")
    args.things_cs.write_bytes(normalized.encode("utf-8"))
    print(f"Wrote {args.things_cs}")


if __name__ == "__main__":
    main()

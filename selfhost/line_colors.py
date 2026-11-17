#!/usr/bin/env python3
"""Generate a MOTIS import script that adds line colours to a GTFS feed without them.

The NVBW timetable has no route_color. Colours come from the Traewelling line-colors
collection (CC0-1.0, https://github.com/Traewelling/line-colors), which is keyed by the
agency names of the DELFI feed. The NVBW feed names the same operators differently
("Stadtverkehr Tüb." vs. "Stadtverkehr Tübingen GmbH"), so agencies are matched by their
set of line names, restricted to operator groups of Baden-Württemberg transport
associations and only where the match is clear. line-colors-aliases.csv can force or
block a match, or combine several operator groups ("a|b"); line names that the combined
groups colour differently stay uncoloured (S1 exists in Stuttgart, Mannheim, Freiburg...).

Usage: line_colors.py GTFS_ZIP LINE_COLORS_CSV ALIASES_CSV OUT_LUA
"""
import csv
import io
import json
import sys
import zipfile
from collections import defaultdict

# Prefixes of shortOperatorName for transport associations in and around Baden-Württemberg
BW_GROUPS = ("bodo", "ding", "hnv", "kvsh", "kvv", "move", "naldo", "ostalb", "rvf", "rvl",
             "sweg", "tgo", "vgc", "vgf", "vhb", "vpe", "vrn", "vvs")
MIN_JACCARD = 0.4      # share of common line names
MIN_COMMON = 2
MAX_RUNNER_UP = 0.7    # second-best candidate must be clearly worse


def norm_line(name: str) -> str:
    return "".join(name.split())


def hex_color(value: str) -> int | None:
    v = value.strip().lstrip("#")
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    try:
        return int(v, 16) if len(v) == 6 else None
    except ValueError:
        return None


def text_for(bg: int) -> int:
    r, g, b = bg >> 16, (bg >> 8) & 0xFF, bg & 0xFF
    return 0x000000 if (0.299 * r + 0.587 * g + 0.114 * b) > 160 else 0xFFFFFF


def read_gtfs(path: str) -> dict[str, set[str]]:
    """agency name -> line names (only routes without their own colour)"""
    with zipfile.ZipFile(path) as z:
        def rows(name):
            return csv.DictReader(io.TextIOWrapper(z.open(name), "utf-8-sig"))
        agencies = {r.get("agency_id", ""): r["agency_name"].strip() for r in rows("agency.txt")}
        lines = defaultdict(set)
        for r in rows("routes.txt"):
            if (r.get("route_color") or "").strip():
                continue
            name = agencies.get(r.get("agency_id", ""), next(iter(agencies.values()), ""))
            lines[name].add(norm_line(r.get("route_short_name") or ""))
    return lines


def read_colors(path: str) -> dict[str, dict[str, tuple[int, int]]]:
    """operator group (shortOperatorName) -> line name -> (background, text)"""
    groups = defaultdict(dict)
    with open(path, encoding="utf-8-sig") as f:
        for raw in csv.DictReader(f):
            r = {(k or "").strip(): (v or "").strip() for k, v in raw.items()}
            group, line = r.get("shortOperatorName", ""), norm_line(r.get("lineName", ""))
            bg = hex_color(r.get("backgroundColor", ""))
            if not group or not line or bg is None:
                continue
            text = hex_color(r.get("textColor", ""))
            groups[group][line] = (bg, text if text is not None else text_for(bg))
    return groups


def read_aliases(path: str) -> dict[str, str]:
    """NVBW agency name -> operator group(s) "a|b", or "" to never colour this agency"""
    try:
        with open(path, encoding="utf-8") as f:
            rows = [r for r in csv.reader(f) if r and not r[0].startswith("#")]
    except FileNotFoundError:
        return {}
    return {r[0].strip(): (r[1].strip() if len(r) > 1 else "") for r in rows}


def merged(groups: dict, names: str) -> dict[str, tuple[int, int]]:
    """Union of the given operator groups without line names coloured differently"""
    out, conflicts = {}, set()
    for g in filter(None, names.split("|")):
        for line, c in groups.get(g, {}).items():
            if line in out and out[line] != c:
                conflicts.add(line)
            out.setdefault(line, c)
    return {l: c for l, c in out.items() if l not in conflicts}


def match(lines: dict[str, set[str]], groups: dict, aliases: dict[str, str]) -> dict[str, str]:
    bw = {g: set(c) for g, c in groups.items() if g.split("-")[0] in BW_GROUPS}
    result = {}
    for agency, names in lines.items():
        if agency in aliases:
            if aliases[agency]:
                result[agency] = aliases[agency]
            continue
        scored = sorted(((len(names & c) / len(names | c), len(names & c), g)
                         for g, c in bw.items() if len(names & c) >= MIN_COMMON), reverse=True)
        if not scored:
            continue
        best, common, group = scored[0]
        runner_up = scored[1][0] if len(scored) > 1 else 0.0
        if best >= MIN_JACCARD and common >= MIN_COMMON and runner_up < MAX_RUNNER_UP * best:
            result[agency] = group
    return result


def lua_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)   # valid Lua string literal for normal text


def write_lua(path: str, table: dict[str, dict[str, tuple[int, int]]]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write("-- Generated by selfhost/line_colors.py - do not edit.\n"
                "-- Line colours: contributors of https://github.com/Traewelling/line-colors (CC0-1.0)\n"
                "local colors = {\n")
        for agency in sorted(table):
            f.write(f"  [{lua_str(agency)}] = {{\n")
            for line, (bg, text) in sorted(table[agency].items()):
                f.write(f"    [{lua_str(line)}] = {{0x{bg:06x}, 0x{text:06x}}},\n")
            f.write("  },\n")
        f.write("}\n\n"
                "function process_route(route)\n"
                "  if route:get_color() ~= 0 then return end\n"
                "  local agency = route:get_agency():get_name():match('^%s*(.-)%s*$')\n"
                "  local lines = colors[agency]\n"
                "  if not lines then return end\n"
                "  local c = lines[(route:get_short_name():gsub('%s+', ''))]\n"
                "  if c then\n"
                "    route:set_color(c[1])\n"
                "    route:set_text_color(c[2])\n"
                "  end\n"
                "end\n")


def main(gtfs: str, colors_csv: str, aliases_csv: str, out: str) -> None:
    lines = read_gtfs(gtfs)
    groups = read_colors(colors_csv)
    matched = match(lines, groups, read_aliases(aliases_csv))
    table = {}
    for agency, group in matched.items():
        colors = merged(groups, group)
        found = {l: colors[l] for l in lines[agency] if l in colors}
        if found:
            table[agency] = found
    write_lua(out, table)
    total = sum(len(v) for v in lines.values())
    coloured = sum(len(v) for v in table.values())
    print(f"Linienfarben: {coloured} von {total} Linien, {len(table)} Betreiber")


if __name__ == "__main__":
    if len(sys.argv) != 5:
        sys.exit(__doc__)
    main(*sys.argv[1:])

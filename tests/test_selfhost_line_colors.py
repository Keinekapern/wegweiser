"""selfhost/line_colors.py: colours for a GTFS feed without route_color."""
import csv
import importlib.util
import zipfile
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "line_colors", Path(__file__).parent.parent / "selfhost" / "line_colors.py")
line_colors = importlib.util.module_from_spec(spec)
spec.loader.exec_module(line_colors)


def _gtfs(path, routes):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("agency.txt", "agency_id,agency_name\n1,Stadtverkehr Tüb.   \n2,DB AG\n3,Other\n")
        z.writestr("routes.txt", "route_id,agency_id,route_short_name,route_type\n" +
                   "".join(f"{i},{a},{n},3\n" for i, (a, n) in enumerate(routes)))


def _colors(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["shortOperatorName", "lineName", "backgroundColor", "textColor"])
        w.writerows(rows)


def test_matches_by_line_names_and_aliases(tmp_path):
    _gtfs(tmp_path / "g.zip", [(1, "1"), (1, "2"), (1, "5"), (2, "S1"), (2, "RE 4"), (3, "1")])
    _colors(tmp_path / "c.csv", [
        ["naldo-tuebus", "1", "#ce2c23", "#fff"], ["naldo-tuebus", "2", "#00f", ""],
        ["naldo-tuebus", "5", "#58102f", "#ffffff"],
        ["vvs-db-sbs", "S1", "#59af41", "#fff"], ["vrn-sbahn-rn", "S1", "#ee1c28", "#fff"],
        ["db-regio", "RE 4", "#a05a2c", "#fff"],
        ["mvv-bus", "1", "#123456", "#fff"],          # outside BW: never matched automatically
    ])
    (tmp_path / "a.csv").write_text("# comment\nDB AG,db-regio|vvs-db-sbs|vrn-sbahn-rn\nOther,\n")
    out = tmp_path / "x.lua"
    line_colors.main(str(tmp_path / "g.zip"), str(tmp_path / "c.csv"), str(tmp_path / "a.csv"), str(out))
    lua = out.read_text(encoding="utf-8")
    assert '["Stadtverkehr Tüb."] = {' in lua
    assert '["5"] = {0x58102f, 0xffffff}' in lua
    assert '["2"] = {0x0000ff, 0xffffff}' in lua      # missing text colour: computed
    assert '["RE4"] = {0xa05a2c, 0xffffff}' in lua
    assert '"S1"' not in lua                          # coloured differently in two groups
    assert '"Other"' not in lua and "0x123456" not in lua
    assert "function process_route(route)" in lua

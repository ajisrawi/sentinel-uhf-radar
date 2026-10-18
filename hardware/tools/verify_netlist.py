"""Compare KiCad's extracted netlist with the intended connectivity (expected_nets.json)."""
import json
import sys
from pathlib import Path

HERE = Path(sys.argv[1]).resolve()
NAME = sys.argv[2]
sys.path.insert(0, str(Path(__file__).parent))
from sexpr import find, find1, parse  # noqa: E402


def kicad_nets(path):
    tree = parse(path.read_text(encoding="utf-8"))
    nets = {}
    for n in find(find1(tree, "nets"), "net"):
        name = find1(n, "name")[1]
        nodes = {(find1(x, "ref")[1], find1(x, "pin")[1]) for x in find(n, "node")}
        nets[name] = nodes
    return nets


def main():
    got = kicad_nets(HERE / f"{NAME}.net")
    exp = {k: set(map(tuple, v)) for k, v in json.loads((HERE / "expected_nets.json").read_text()).items()}

    # pins KiCad leaves unconnected appear as single-node "unconnected-(...)" nets
    got_conn = {k: v for k, v in got.items() if not k.startswith("unconnected-")}
    got_parts = {frozenset(v) for v in got_conn.values() if len(v) > 1}
    exp_parts = {frozenset(v) for v in exp.values()}
    # merge expected groups that share pins (stack/net aliases)
    merged = []
    for grp in exp_parts:
        grp = set(grp)
        for m in [m for m in merged if m & grp]:
            grp |= m
            merged.remove(m)
        merged.append(grp)
    exp_parts = {frozenset(m) for m in merged if len(m) > 1}

    missing = exp_parts - got_parts
    extra = got_parts - exp_parts
    named_bad = [n for n, v in exp.items() if not n.startswith("__") and n in got and got[n] != v
                 and frozenset(got[n]) not in exp_parts]
    single = sorted(k for k, v in got.items() if k.startswith("unconnected-"))
    print(f"KiCad nets: {len(got_conn)}   expected nets: {len(exp_parts)}")
    print(f"mismatched groups: {len(missing)} missing / {len(extra)} unexpected; named mismatches: {len(named_bad)}")
    for m in list(missing)[:10]:
        print("  MISSING", sorted(m))
    for m in list(extra)[:10]:
        print("  EXTRA  ", sorted(m))
    print(f"unconnected single pins: {len(single)}", single[:10])
    ok = not missing and not extra
    print("NETLIST MATCH" if ok else "NETLIST MISMATCH")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

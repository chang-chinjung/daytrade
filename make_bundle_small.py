"""
make_bundle_small.py - 精簡版，只包 3 隻核心，給 Muse 審最快
"""
from pathlib import Path
ROOT = Path(".")
OUTPUT = ROOT / "bundle_small_for_muse.txt"
TARGETS = ["main.py", "eval_harness.py", "screen_stocks.py", "risk.py", "cost.py"]
with open(OUTPUT, "w", encoding="utf-8") as out:
    out.write("# 精簡 Bundle\n")
    for name in TARGETS:
        p = ROOT / name
        if not p.exists():
            found = list(ROOT.rglob(name))
            if found:
                p = found[0]
            else:
                out.write(f"\n=== {name} NOT FOUND ===\n")
                continue
        out.write(f"\n\n=== {p} ===\n")
        out.write(p.read_text(encoding="utf-8", errors="ignore"))
print(f"Done -> {OUTPUT}")

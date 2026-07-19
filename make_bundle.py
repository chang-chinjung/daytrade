"""
把整個 intraday_lab_full 資料夾壓成一個 txt，讓你可以一次丟給我
用法: python make_bundle.py
會產生 bundle_for_muse.txt 在同層
"""
import os
from pathlib import Path

ROOT = Path(".")  # 你 cd 到 intraday_lab_full 後跑這個
OUTPUT = ROOT / "bundle_for_muse.txt"
EXCLUDE = {".git", "__pycache__", ".venv", "node_modules", "data"} # data 太大不包
INCLUDE_EXT = {".py", ".md", ".yaml", ".yml", ".json", ".txt"}

with open(OUTPUT, "w", encoding="utf-8") as out:
    out.write("# Bundle for Muse Review\n")
    for p in ROOT.rglob("*"):
        if any(x in p.parts for x in EXCLUDE):
            continue
        if p.is_file() and p.suffix.lower() in INCLUDE_EXT:
            rel = p.relative_to(ROOT)
            out.write(f"\n\n=== FILE: {rel} ===\n")
            try:
                out.write(p.read_text(encoding="utf-8", errors="ignore"))
            except Exception as e:
                out.write(f"[read error {e}]")

print(f"Done -> {OUTPUT} , 這個 txt 直接丟給我，我就能重建全部")

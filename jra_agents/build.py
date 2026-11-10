"""JRA「騎乗依頼仲介者一覧」PDFから、エージェント（仲介者）ごとの担当騎手データを作る。

使い方:
    python build.py <PDFのあるフォルダ> <出力フォルダ> <時点(例: 2026-11-05)>

PDFの入手元: https://www.jra.go.jp/datafile/meikan/agent.html
  agent_miho.pdf / agent_rittou.pdf / agent_other.pdf
"""
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import pdfplumber

# PDFファイル → (左列の区分, 右列の区分)
SOURCES = {
    "agent_miho.pdf": ("美浦", "美浦"),
    "agent_rittou.pdf": ("栗東", "栗東"),
    "agent_other.pdf": ("地方", "短期免許・招待外国人"),
}


def read_rows(pdf_path, left_group, right_group):
    # 左列を上から下、続いて右列（PDFの五十音順どおり）
    rows = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                for row in table:
                    cells = [(c or "").strip() for c in row]
                    if cells[:2] != ["騎手名", "仲介者名"]:
                        rows.append(cells)
    for group, col in ((left_group, 0), (right_group, 2)):
        for cells in rows:
            jockey, agent = cells[col], cells[col + 1]
            if jockey:
                yield group, jockey, agent


def parse_jockey(raw):
    """'★石神 深道' → ('石神 深道', True, '')、'笹川 翼（大井）' → ('笹川 翼', False, '大井')"""
    young = raw.startswith("★")
    name = raw.lstrip("★").strip()
    track = ""
    if name.endswith("）") and "（" in name:
        name, track = name[:-1].split("（", 1)
    return name.strip(), young, track


def main(pdf_dir, out_dir, as_of):
    pdf_dir, out_dir = Path(pdf_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    records = []
    for fname, (lg, rg) in SOURCES.items():
        for group, raw, agent in read_rows(pdf_dir / fname, lg, rg):
            name, young, track = parse_jockey(raw)
            records.append({
                "騎手名": name,
                "所属": f"地方・{track}" if track else group,
                "若手騎手": young,
                "仲介者名": agent,
            })

    # 騎手ごとの一覧（仲介者なしの騎手も含む）
    with open(out_dir / "jockeys.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["騎手名", "所属", "若手騎手", "仲介者名"])
        w.writeheader()
        for r in records:
            w.writerow({**r, "若手騎手": "○" if r["若手騎手"] else ""})

    # エージェントごとにまとめる（担当騎手が多い順 → 名前順）
    by_agent = defaultdict(list)
    for r in records:
        if r["仲介者名"]:
            by_agent[r["仲介者名"]].append(r)
    agents = sorted(by_agent.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    no_agent = [r for r in records if not r["仲介者名"]]

    data = {
        "時点": as_of,
        "出典": "JRA 騎乗依頼仲介者一覧 https://www.jra.go.jp/datafile/meikan/agent.html",
        "仲介者": [
            {
                "仲介者名": a,
                "担当騎手数": len(js),
                "担当騎手": [{k: j[k] for k in ("騎手名", "所属", "若手騎手")} for j in js],
            }
            for a, js in agents
        ],
        "仲介者なしの騎手": [{k: j[k] for k in ("騎手名", "所属", "若手騎手")} for j in no_agent],
    }
    (out_dir / "agents.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    with open(out_dir / "agents.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["仲介者名", "担当騎手数", "担当騎手（★は若手）"])
        for a, js in agents:
            w.writerow([a, len(js), "、".join(("★" if j["若手騎手"] else "") + j["騎手名"] for j in js)])

    def label(j):
        s = ("★" if j["若手騎手"] else "") + j["騎手名"]
        return f"{s}（{j['所属']}）"

    lines = [
        "# エージェント（騎乗依頼仲介者）別 担当騎手一覧",
        "",
        f"{as_of} 時点。出典: [JRA 騎乗依頼仲介者一覧](https://www.jra.go.jp/datafile/meikan/agent.html)。★は若手騎手。",
        "",
        f"仲介者 {len(agents)} 名 / 騎手 {len(records)} 名（うち仲介者なし {len(no_agent)} 名）",
        "",
        "| 仲介者名 | 人数 | 担当騎手 |",
        "|---|---|---|",
    ]
    for a, js in agents:
        lines.append(f"| {a} | {len(js)} | {'、'.join(label(j) for j in js)} |")
    lines += ["", "## 仲介者なしの騎手", "", "、".join(label(j) for j in no_agent), ""]
    (out_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"agents={len(agents)} jockeys={len(records)} no_agent={len(no_agent)}")


if __name__ == "__main__":
    main(*sys.argv[1:4])

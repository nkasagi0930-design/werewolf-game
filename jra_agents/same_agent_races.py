"""同じレースに同じエージェントの騎手が複数出ていた場合（同時）と、1人だけの場合（単独）の成績を比べる。

使い方:
    python same_agent_races.py <レース結果HTMLのフォルダ> <出力フォルダ> <期間ラベル>
"""
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

import agent_results as ar

HERE = Path(__file__).parent


def main(race_dir, out_dir, label):
    agent_of = {}
    with open(HERE / "jockeys.csv", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            agent_of[ar.norm(r["騎手名"])] = r["仲介者名"]

    races = []
    for p in sorted(Path(race_dir).glob("*.html")):
        html = p.read_bytes().decode("cp932", "ignore")
        rows = ar.parse_race(html)
        # 単勝人気を馬番ごとに取る
        tbody = html[html.find("<tbody>", html.find('class="place">着順')):]
        pops = {}
        for tr in re.findall(r"<tr>(.*?)</tr>", tbody[: tbody.find("</tbody>")], re.S):
            n = re.search(r'<td class="num">\s*(\d+)', tr)
            pp = re.search(r'<td class="pop">\s*(\d+)', tr)
            if n and pp:
                pops[int(n.group(1))] = int(pp.group(1))
        for r in rows:
            r["agent"] = agent_of.get(ar.norm(r["jockey"]), "")
            r["pos"] = int(r["place"]) if r["place"].isdigit() else 99
            r["pop"] = pops.get(r["num"])
        races.append(rows)

    def blank():
        return defaultdict(int)

    total = {"同時": blank(), "単独": blank()}
    per_agent = defaultdict(lambda: {"同時": blank(), "単独": blank()})
    cases = []  # 同時出走の具体例

    def add(s, r):
        s["騎乗"] += 1
        s["1着"] += r["pos"] == 1
        s["3着内"] += r["pos"] <= 3
        s["単勝払戻"] += r["win_pay"] if r["pos"] == 1 else 0
        s["複勝払戻"] += r["place_pay"] if r["pos"] <= 3 else 0
        if r["pop"]:
            s["人気計"] += r["pop"]
            s["人気数"] += 1

    for rows in races:
        groups = defaultdict(list)
        for r in rows:
            if r["agent"]:
                groups[r["agent"]].append(r)
        for agent, rs in groups.items():
            kind = "同時" if len(rs) >= 2 else "単独"
            for r in rs:
                add(total[kind], r)
                add(per_agent[agent][kind], r)
            if kind == "同時":
                rs = sorted(rs, key=lambda r: r["pos"])
                cases.append((rs[0]["race"], agent, rs))

    def line(name, s):
        n = s["騎乗"]
        if not n:
            return f"| {name} | 0 | - | - | - | - | - | - |"
        pct = lambda a, b: f"{a * 100 / b:.1f}%"
        avg_pop = f"{s['人気計'] / s['人気数']:.1f}" if s["人気数"] else "-"
        return (f"| {name} | {n} | {s['1着']} | {pct(s['1着'], n)} | {pct(s['3着内'], n)} | "
                f"{pct(s['単勝払戻'], n * 100)} | {pct(s['複勝払戻'], n * 100)} | {avg_pop} |")

    head = ["| 区分 | 騎乗 | 1着 | 勝率 | 複勝率 | 単回収 | 複回収 | 平均人気 |", "|---|---|---|---|---|---|---|---|"]
    n_races_with = len({c[0] for c in cases})
    won = sum(1 for c in cases if c[2][0]["pos"] == 1)
    top3 = sum(1 for c in cases if c[2][0]["pos"] <= 3)
    md = [
        f"# 同じエージェントの騎手が同じレースに出たとき（{label}）",
        "",
        f"全 {len(races)} レース中 {n_races_with} レースで、同じエージェントの騎手が2人以上同時に出走していた"
        f"（のべ {len(cases)} 組）。仲介者なしの騎手は対象外。",
        "",
        "## 全体の比較",
        "",
        "「同時」= そのレースに同じエージェントの騎手が他にもいた騎乗、「単独」= そのエージェントから1人だけの騎乗。",
        "",
        *head,
        line("同時", total["同時"]),
        line("単独", total["単独"]),
        "",
        f"同時出走 {len(cases)} 組のうち、どちらか（誰か）が勝ったのは {won} 組、3着以内に入ったのは {top3} 組。",
        "",
        "## エージェントごとの比較",
        "",
        "| 仲介者名 | 同時 騎乗 | 同時 勝率 | 同時 複勝率 | 単独 騎乗 | 単独 勝率 | 単独 複勝率 |",
        "|---|---|---|---|---|---|---|",
    ]
    pct = lambda a, b: f"{a * 100 / b:.1f}%" if b else "-"
    for agent, d in sorted(per_agent.items(), key=lambda kv: -kv[1]["同時"]["騎乗"]):
        a, b = d["同時"], d["単独"]
        if not a["騎乗"]:
            continue
        md.append(f"| {agent} | {a['騎乗']} | {pct(a['1着'], a['騎乗'])} | {pct(a['3着内'], a['騎乗'])} | "
                  f"{b['騎乗']} | {pct(b['1着'], b['騎乗'])} | {pct(b['3着内'], b['騎乗'])} |")
    md += ["", "## 同時出走の一覧", "", "騎手名（人気→着順）。着順の良い順。", "",
           "| レース | 仲介者名 | 騎手（人気→着順） |", "|---|---|---|"]
    for race, agent, rs in sorted(cases):
        js = "、".join(f"{r['jockey']}（{r['pop'] or '-'}人気→{r['place']}{'着' if r['place'].isdigit() else ''}）" for r in rs)
        md.append(f"| {race} | {agent} | {js} |")
    md.append("")
    out = Path(out_dir) / f"same_agent_races_{label}.md"
    out.write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md[:60]))


if __name__ == "__main__":
    main(*sys.argv[1:4])

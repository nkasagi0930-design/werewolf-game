"""エージェント×馬主、エージェント×調教師の組み合わせごとの成績を集計する。

使い方:
    python agent_pairs.py <レース結果HTMLのフォルダ> <出馬表HTMLのフォルダ> <出力フォルダ> <期間ラベル>

出馬表HTML（JRADB/accessD.html の pw01dde...）は、レース結果HTMLと同じファイル名で保存しておく。
馬主は出馬表から、調教師はレース結果から取る。
"""
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

import agent_results as ar

HERE = Path(__file__).parent
MIN_RIDES = 3  # 表に載せる最低騎乗数（勝った組み合わせは騎乗数に関係なく載せる）


def owners_by_num(html):
    out = {}
    body = html[html.find("<tbody"):]
    for tr in re.findall(r"<tr>(.*?)</tr>", body, re.S):
        n = re.search(r'<td class="num">\s*(\d+)', tr)
        o = re.search(r'<p class="owner">(.*?)</p>', tr, re.S)
        if n and o:
            out[int(n.group(1))] = ar.text(o.group(1))
    return out


def trainers_by_num(html):
    out = {}
    body = html[html.find("<tbody>", html.find('class="place">着順')):]
    for tr in re.findall(r"<tr>(.*?)</tr>", body[: body.find("</tbody>")], re.S):
        n = re.search(r'<td class="num">\s*(\d+)', tr)
        t = re.search(r'<td class="trainer">(.*?)</td>', tr, re.S)
        if n and t:
            out[int(n.group(1))] = ar.text(t.group(1))
    return out


def main(race_dir, entry_dir, out_dir, label):
    agent_of = {}
    with open(HERE / "jockeys.csv", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            agent_of[ar.norm(r["騎手名"])] = r["仲介者名"]

    stats = {"馬主": defaultdict(lambda: defaultdict(int)), "調教師": defaultdict(lambda: defaultdict(int))}
    jockeys = {"馬主": defaultdict(set), "調教師": defaultdict(set)}
    n_races = 0
    for p in sorted(Path(race_dir).glob("*.html")):
        html = p.read_bytes().decode("cp932", "ignore")
        owners = owners_by_num((Path(entry_dir) / p.name).read_bytes().decode("cp932", "ignore"))
        trainers = trainers_by_num(html)
        n_races += 1
        for r in ar.parse_race(html):
            agent = agent_of.get(ar.norm(r["jockey"]), "")
            if not agent:
                continue  # 仲介者なしの騎手は対象外
            pos = int(r["place"]) if r["place"].isdigit() else 99
            for kind, who in (("馬主", owners.get(r["num"])), ("調教師", trainers.get(r["num"]))):
                if not who:
                    continue
                s = stats[kind][(agent, who)]
                s["騎乗"] += 1
                if pos <= 3:
                    s[f"{pos}着"] += 1
                s["単勝払戻"] += r["win_pay"] if pos == 1 else 0
                s["複勝払戻"] += r["place_pay"] if pos <= 3 else 0
                jockeys[kind][(agent, who)].add(r["jockey"])

    pct = lambda a, b: round(a * 100 / b, 1) if b else 0.0
    md = [
        f"# エージェント×馬主・エージェント×調教師の成績（{label}）",
        "",
        f"対象: JRA {n_races} レース。仲介者なしの騎手は対象外。",
        f"表は {MIN_RIDES} 騎乗以上の組み合わせと、勝った組み合わせ。全組み合わせはCSVに入っている。",
        "回収率は、その組み合わせの騎乗馬すべてに単勝・複勝を100円ずつ買った場合。",
    ]
    for kind in ("馬主", "調教師"):
        rows = []
        for (agent, who), s in stats[kind].items():
            n = s["騎乗"]
            top3 = s["1着"] + s["2着"] + s["3着"]
            rows.append({
                "仲介者名": agent, kind: who, "騎乗数": n,
                "1着": s["1着"], "2着": s["2着"], "3着": s["3着"],
                "勝率": pct(s["1着"], n), "複勝率": pct(top3, n),
                "単勝回収率": pct(s["単勝払戻"], n * 100), "複勝回収率": pct(s["複勝払戻"], n * 100),
                "騎乗した騎手": "、".join(sorted(jockeys[kind][(agent, who)])),
            })
        rows.sort(key=lambda r: (-r["騎乗数"], -r["1着"], -r["2着"], -r["3着"], r["仲介者名"]))
        key = "owner" if kind == "馬主" else "trainer"
        with open(Path(out_dir) / f"agent_x_{key}_{label}.csv", "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

        shown = [r for r in rows if r["騎乗数"] >= MIN_RIDES or r["1着"]]
        multi = [r for r in rows if r["騎乗数"] >= 2]
        md += [
            "", f"## エージェント×{kind}", "",
            f"組み合わせは全部で {len(rows)} 通り、うち2騎乗以上は {len(multi)} 通り。騎乗数の多い順。", "",
            f"| 仲介者名 | {kind} | 騎乗 | 1着 | 2着 | 3着 | 複勝率 | 単回収 | 複回収 | 騎手 |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
        for r in shown:
            md.append(f"| {r['仲介者名']} | {r[kind]} | {r['騎乗数']} | {r['1着']} | {r['2着']} | {r['3着']} | "
                      f"{r['複勝率']}% | {r['単勝回収率']}% | {r['複勝回収率']}% | {r['騎乗した騎手']} |")
        print(kind, "pairs", len(rows), "multi", len(multi), "shown", len(shown),
              "rides", sum(r["騎乗数"] for r in rows), "wins", sum(r["1着"] for r in rows))
    md.append("")
    (Path(out_dir) / f"agent_pairs_{label}.md").write_text("\n".join(md), encoding="utf-8")


if __name__ == "__main__":
    main(*sys.argv[1:5])

"""JRAのレース結果ページから、エージェント（仲介者）ごとの成績を集計する。

使い方:
    python agent_results.py <レース結果HTMLのフォルダ> <出力フォルダ> <期間ラベル(例: 2026-11-07_08)>

レース結果HTMLは JRA「レース結果」の各レースページ（JRADB/accessS.html の pw01sde... ）を保存したもの。
エージェントの割り当ては同じフォルダの jockeys.csv を使う。
"""
import csv
import re
import sys
import unicodedata
from collections import defaultdict
from html import unescape
from pathlib import Path

HERE = Path(__file__).parent


def text(s):
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", "", s))).strip()


def norm(name):
    # 全角・半角の違い（Ｃ．ルメール / C.ルメール）と空白を無視して比較する
    return re.sub(r"\s", "", unicodedata.normalize("NFKC", name))


def parse_payouts(html, kind):
    """{馬番: 払戻金(100円あたり)} を返す。kind は 'win'(単勝) / 'place'(複勝)"""
    m = re.search(rf'<li class="{kind}">(.*?)</li>', html, re.S)
    out = {}
    if m:
        for line in re.findall(r'<div class="line">(.*?)</div>\s*</div>|<div class="line">(.*?<div class="pop">.*?</div>)', m.group(1), re.S):
            seg = line[0] or line[1]
            num = re.search(r'<div class="num">\s*(\d+)', seg)
            yen = re.search(r'<div class="yen">\s*([\d,]+)', seg)
            if num and yen:
                out[int(num.group(1))] = int(yen.group(1).replace(",", ""))
    return out


def parse_race(html):
    head = text(re.search(r'<div class="cell date">(.*?)</div>', html, re.S).group(1))
    rnum = re.search(r'<div class="race_number"><img [^>]*alt="(\d+)レース"', html).group(1)
    win, place = parse_payouts(html, "win"), parse_payouts(html, "place")
    tbody = html[html.find("<tbody>", html.find('class="place">着順')):]
    tbody = tbody[: tbody.find("</tbody>")]
    rows = []
    for tr in re.findall(r"<tr>(.*?)</tr>", tbody, re.S):
        cell = lambda c: text((re.search(rf'<td class="{c}">(.*?)</td>', tr, re.S) or [None, ""])[1])
        jockey_html = re.search(r'<td class="jockey">(.*?)</td>', tr, re.S).group(1)
        jockey = text(re.sub(r'<span[^>]*class="mark[^"]*"[^>]*>.*?</span>', "", jockey_html))
        num = int(cell("num")) if cell("num").isdigit() else None
        rows.append({
            "race": f"{head} {rnum}R",
            "place": cell("place"),
            "num": num,
            "jockey": jockey,
            "win_pay": win.get(num, 0),
            "place_pay": place.get(num, 0),
        })
    return rows


def main(race_dir, out_dir, label):
    out_dir = Path(out_dir)
    agent_of = {}
    with open(HERE / "jockeys.csv", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            agent_of[norm(r["騎手名"])] = r["仲介者名"] or "（仲介者なし）"

    rows = []
    for p in sorted(Path(race_dir).glob("*.html")):
        rows += parse_race(p.read_bytes().decode("cp932", "ignore"))

    stats = defaultdict(lambda: defaultdict(int))
    jockeys_of = defaultdict(set)
    unknown = defaultdict(int)
    for r in rows:
        if not r["place"].isdigit() and r["place"] in ("取消", "除外"):
            continue  # 出走していない
        agent = agent_of.get(norm(r["jockey"]))
        if agent is None:
            unknown[r["jockey"]] += 1
            agent = "（一覧に載っていない騎手）"
        s = stats[agent]
        s["騎乗"] += 1
        pos = int(r["place"]) if r["place"].isdigit() else 99
        if pos <= 3:
            s[f"{pos}着"] += 1
        s["単勝払戻"] += r["win_pay"] if pos == 1 else 0
        s["複勝払戻"] += r["place_pay"] if pos <= 3 else 0
        jockeys_of[agent].add(r["jockey"])

    def pct(a, b):
        return round(a * 100 / b, 1) if b else 0.0

    table = []
    for agent, s in stats.items():
        n = s["騎乗"]
        top3 = s["1着"] + s["2着"] + s["3着"]
        table.append({
            "仲介者名": agent,
            "騎乗数": n,
            "1着": s["1着"], "2着": s["2着"], "3着": s["3着"],
            "勝率": pct(s["1着"], n),
            "複勝率": pct(top3, n),
            "単勝回収率": pct(s["単勝払戻"], n * 100),
            "複勝回収率": pct(s["複勝払戻"], n * 100),
            "騎乗した騎手": "、".join(sorted(jockeys_of[agent])),
        })
    # 「仲介者なし」などの区分は表の最後に回す
    table.sort(key=lambda r: (r["仲介者名"].startswith("（"), -r["1着"], -r["2着"], -r["3着"], r["騎乗数"]))

    stem = f"agent_results_{label}"
    with open(out_dir / f"{stem}.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(table[0].keys()))
        w.writeheader()
        w.writerows(table)

    races = sorted({r["race"] for r in rows})
    md = [
        f"# エージェント別成績（{label}）",
        "",
        f"対象: JRA {len(races)} レース。エージェントの割り当ては jockeys.csv（騎乗依頼仲介者一覧）による。",
        "並びは1着数の多い順（同数なら2着、3着の多い順）。回収率は、その陣営の騎乗馬すべてに単勝・複勝を100円ずつ買った場合。",
        "",
        "| 仲介者名 | 騎乗 | 1着 | 2着 | 3着 | 勝率 | 複勝率 | 単回収 | 複回収 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in table:
        md.append(f"| {r['仲介者名']} | {r['騎乗数']} | {r['1着']} | {r['2着']} | {r['3着']} | "
                  f"{r['勝率']}% | {r['複勝率']}% | {r['単勝回収率']}% | {r['複勝回収率']}% |")
    md += ["", "## 各エージェントの騎乗騎手", ""]
    md += [f"- **{r['仲介者名']}**: {r['騎乗した騎手']}" for r in table]
    md.append("")
    (out_dir / f"{stem}.md").write_text("\n".join(md), encoding="utf-8")

    print(f"races={len(races)} rows={len(rows)} agents={len(table)}")
    if unknown:
        print("一覧にない騎手:", dict(unknown))


if __name__ == "__main__":
    main(*sys.argv[1:4])

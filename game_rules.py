"""
人狼ゲーム game_rules.py
ステップ1〜9でColabで作った、ゲームのルール部分をまとめたファイルです。
Streamlitの画面(app.py など)から、ここの関数やクラスをimportして使います。
"""

# =====================================================
# 人狼ゲーム ステップ1: 陣営・役職の定義、部屋の設定、エラーチェック
# =====================================================
from dataclasses import dataclass, field
from typing import Optional


# ---------- 陣営の定義 ----------
@dataclass
class Faction:
    id: str            # 内部で使う名前
    name: str          # 画面に表示する名前
    judge_order: int   # 判定順(小さいほど先に勝敗を調べる)
    points: int = 1    # 勝利時のポイントの初期設定


FACTIONS = {
    "village": Faction("village", "村人陣営", judge_order=1),
    "wolf": Faction("wolf", "人狼陣営", judge_order=2),
}

VILLAGE_FACTION = "village"  # エラーチェックで「村人陣営」を数えるときに使う


# ---------- 役職の定義(属性の集まり) ----------
@dataclass
class Role:
    id: str
    name: str                      # 名前
    faction: str                   # 所属陣営
    counts_as_wolf: bool           # 人狼として数える
    night_action: Optional[str]    # 夜の行動("attack" / "divine" / None)
    divine_result: str             # 占われたときの結果("wolf" / "not_wolf")
    knows_allies: bool             # 仲間を知る
    ai_reports_result: bool        # AIの結果を報告する


ROLES = {
    "wolf": Role("wolf", "人狼", "wolf", True, "attack", "wolf", True, False),
    "seer": Role("seer", "占い師", "village", False, "divine", "not_wolf", False, True),
    "villager": Role("villager", "村人", "village", False, None, "not_wolf", False, False),
}


# ---------- おすすめ構成 ----------
RECOMMENDED = {
    4: {"wolf": 1, "seer": 1, "villager": 2},
    5: {"wolf": 1, "seer": 1, "villager": 3},
    6: {"wolf": 1, "seer": 1, "villager": 4},
    7: {"wolf": 2, "seer": 1, "villager": 4},
    8: {"wolf": 2, "seer": 1, "villager": 5},
    9: {"wolf": 2, "seer": 1, "villager": 6},
    10: {"wolf": 3, "seer": 1, "villager": 6},
}


def recommend(total_players):
    """総人数に合うおすすめ構成を返す。表にない人数のときは None。"""
    return RECOMMENDED.get(total_players)


# ---------- 部屋の設定 ----------
@dataclass
class RoomSettings:
    total_players: int                 # 総人数
    human_count: int                   # 人間の参加者数
    role_counts: dict                  # 役職の構成 例: {"wolf": 1, "seer": 1, "villager": 3}
    first_night_attack: bool = True    # 1日目の夜の襲撃
    protect_humans: bool = True        # 人間を保護するモード
    faction_points: dict = field(
        default_factory=lambda: {f.id: f.points for f in FACTIONS.values()}
    )                                  # 勝利時のポイント(陣営ごと)

    @property
    def ai_count(self):
        """AIの人数 = 総人数 - 人間の人数"""
        return self.total_players - self.human_count


# ---------- エラーチェック ----------
def validate(settings):
    """設定を調べて、問題点のリストを返す。問題がなければ空のリスト。"""
    errors = []
    counts = settings.role_counts

    # 前提: 知らない役職や、マイナスの人数がないか
    for role_id, n in counts.items():
        if role_id not in ROLES:
            errors.append(f"知らない役職があります: {role_id}")
        if n < 0:
            errors.append(f"役職の人数がマイナスです: {role_id}")
    if errors:
        return errors  # これ以降の計算ができないので、ここで終わる

    # チェック1: 役職の合計が総人数と一致していること
    total_roles = sum(counts.values())
    if total_roles != settings.total_players:
        errors.append(
            f"役職の合計({total_roles}人)が総人数({settings.total_players}人)と一致していません"
        )

    # 「人狼として数える人」と「村人陣営の人」の数を、属性から数える
    wolf_count = sum(n for r, n in counts.items() if ROLES[r].counts_as_wolf)
    village_count = sum(n for r, n in counts.items() if ROLES[r].faction == VILLAGE_FACTION)

    # チェック2: 人狼が1人以上いること
    if wolf_count < 1:
        errors.append("人狼(人狼として数える役職)が1人もいません")

    # チェック3: 人狼として数える人の数が、村人陣営の人数より少ないこと
    if wolf_count >= village_count:
        errors.append(
            f"人狼の数({wolf_count}人)が、村人陣営の人数({village_count}人)以上になっています"
        )

    # チェック4: 総人数が人間の参加者数以上であること
    if settings.total_players < settings.human_count:
        errors.append(
            f"総人数({settings.total_players}人)が人間の参加者数({settings.human_count}人)より少ないです"
        )
    if settings.human_count < 1:
        errors.append("人間の参加者は1人以上が必要です")

    return errors


# ---------- 表示用 ----------
def describe_composition(role_counts):
    parts = [f"{ROLES[r].name}{n}人" for r, n in role_counts.items() if n > 0]
    return "、".join(parts)



# =====================================================
# 人狼ゲーム ステップ2: プレイヤーの作成と、役職のランダムな割り振り
# ※ ステップ1のセルを先に実行してから、このセルを実行してください
# =====================================================
import random


# ---------- プレイヤー ----------
@dataclass
class Player:
    name: str
    is_human: bool
    role_id: str = ""     # 役職(あとで割り振る)
    alive: bool = True    # 生きているか

    @property
    def role(self):
        return ROLES[self.role_id]


# ---------- 人間の名前のチェック ----------
def check_human_names(names, human_count):
    """名前の前後の空白を取り除き、問題点を調べる。(整えた名前のリスト, 問題点のリスト)を返す。"""
    errors = []
    cleaned = [n.strip() for n in names]

    if len(cleaned) != human_count:
        errors.append(f"人間の名前の数({len(cleaned)}人)が、人間の参加者数({human_count}人)と一致していません")

    for n in cleaned:
        if n == "":
            errors.append("名前が空です")
        elif n.startswith("AI"):
            errors.append(f"「AI」で始まる名前は使えません: {n}")

    for n in sorted({n for n in cleaned if cleaned.count(n) > 1}):
        errors.append(f"同じ名前が重複しています: {n}")

    return cleaned, errors


# ---------- プレイヤーの作成と役職の割り振り ----------
def create_players(settings, human_names, seed=None):
    """人間とAIのプレイヤーを作り、役職をランダムに割り振って返す。
    seed を決めると、毎回同じ結果になる(テスト用)。None なら毎回変わる。"""
    errors = validate(settings)
    cleaned, name_errors = check_human_names(human_names, settings.human_count)
    errors += name_errors
    if errors:
        raise ValueError("\n".join(errors))

    # 人間 → AI(AI1, AI2, ...)の順に作る
    players = [Player(n, is_human=True) for n in cleaned]
    players += [Player(f"AI{i}", is_human=False) for i in range(1, settings.ai_count + 1)]

    # 役職の山を作って、シャッフルして配る
    roles = []
    for role_id, n in settings.role_counts.items():
        roles += [role_id] * n
    random.Random(seed).shuffle(roles)

    for player, role_id in zip(players, roles):
        player.role_id = role_id

    return players


# ---------- 表示用 ----------
def view_for(player, players):
    """そのプレイヤー本人の画面に出す内容(本人と、仲間を知る役職なら仲間の名前)。"""
    lines = [f"{player.name}さんの役職: {player.role.name}"]
    if player.role.knows_allies:
        allies = [p.name for p in players if p is not player and p.role_id == player.role_id]
        lines.append("仲間: " + ("、".join(allies) if allies else "いません"))
    return "\n".join(lines)


def show_all(players):
    """全員の役職を表示する(進行役やテスト用。実際のゲームでは本人以外に見せない)。"""
    for p in players:
        kind = "人間" if p.is_human else "AI"
        print(f"{p.name}: {p.role.name} ({kind})")



# =====================================================
# 人狼ゲーム ステップ3: 夜の行動「占う」
# ※ ステップ1、ステップ2のセルを先に実行してから、このセルを実行してください
# =====================================================


# ---------- ゲームの状態 ----------
@dataclass
class GameState:
    settings: RoomSettings
    players: list
    divine_log: dict = field(default_factory=dict)  # {占った人の名前: [占いの記録, ...]}


def find_player(state, name):
    for p in state.players:
        if p.name == name:
            return p
    raise ValueError(f"{name}というプレイヤーはいません")


# ---------- 占いの記録 ----------
@dataclass
class DivineRecord:
    seer: str            # 占った人の名前
    target: str          # 占われた人の名前
    result: str          # 結果("wolf" / "not_wolf")
    seer_is_human: bool  # 占った人が人間か


RESULT_TEXT = {"wolf": "人狼です", "not_wolf": "人狼ではありません"}


def show_divine(record):
    return f"{record.seer}さんの占い結果: {record.target}は{RESULT_TEXT[record.result]}"


# ---------- 「占う」の行動タイプ ----------
def divine_candidates(state, seer):
    """占える相手 = 自分以外で、まだ占っていない生存者"""
    done = {rec.target for rec in state.divine_log.get(seer.name, [])}
    return [p for p in state.players if p.alive and p is not seer and p.name not in done]


def do_divine(state, seer, target_name):
    """1人分の占いを実行して、記録を返す。"""
    if not seer.alive:
        raise ValueError(f"{seer.name}は死亡しているので占えません")
    if seer.role.night_action != "divine":
        raise ValueError(f"{seer.name}は占う役職ではありません")

    candidates = [p.name for p in divine_candidates(state, seer)]
    if target_name not in candidates:
        raise ValueError(f"{seer.name}は{target_name}を占えません(自分自身、死亡者、または占い済みです)")

    target = find_player(state, target_name)
    record = DivineRecord(seer.name, target.name, target.role.divine_result, seer.is_human)
    state.divine_log.setdefault(seer.name, []).append(record)
    return record


def run_divine_phase(state, human_choices, rng=None):
    """夜の「占う」をまとめて実行する。
    human_choices: 人間の占い師が選んだ相手 例: {"けんじ": "AI3"}
    AIの占い師は、占える相手からランダムに選ぶ。
    人間の占い師が選び終わっていないときは、エラーにして待つ。"""
    rng = rng or random.Random()
    seers = [p for p in state.players if p.alive and p.role.night_action == "divine"]

    waiting = [
        p.name for p in seers
        if p.is_human and p.name not in human_choices and divine_candidates(state, p)
    ]
    if waiting:
        raise ValueError("まだ選んでいない人がいます: " + "、".join(waiting))

    records = []
    for seer in seers:
        if seer.is_human:
            if seer.name not in human_choices:
                continue  # 占える相手がいないので、占わない
            target_name = human_choices[seer.name]
        else:
            candidates = divine_candidates(state, seer)
            if not candidates:
                continue  # 占える相手がいないときは、占わない
            target_name = rng.choice(candidates).name
        records.append(do_divine(state, seer, target_name))
    return records



# =====================================================
# 人狼ゲーム ステップ4: 夜の行動「襲撃」(人間を保護するモードを含む)
# ※ ステップ1〜3のセルを先に実行してから、このセルを実行してください
# =====================================================
from collections import Counter


# ---------- 襲撃の記録 ----------
@dataclass
class AttackRecord:
    target: Optional[str]   # 襲撃された人の名前(襲撃なしのときは None)
    attackers: list         # 襲撃を実行した人の名前
    reason: str             # 決め方や、襲撃なしの理由(確認用)


# ---------- 実行者と、対象の候補 ----------
def attackers_of(state):
    """襲撃を実行する人 = 夜の行動が「襲撃」の生存者全員"""
    return [p for p in state.players if p.alive and p.role.night_action == "attack"]


def attack_candidates(state):
    """襲撃の対象の候補 = 夜の行動が「襲撃」ではない生存者"""
    return [p for p in state.players if p.alive and p.role.night_action != "attack"]


# ---------- 決め方1: 実行者に人間がいるとき ----------
def choose_by_humans(human_attackers, human_choices, candidates, rng):
    """人間の実行者が選んだ相手のうち、最多の人を選ぶ。同数のときはランダム。"""
    waiting = [p.name for p in human_attackers if p.name not in human_choices]
    if waiting:
        raise ValueError("まだ選んでいない人がいます: " + "、".join(waiting))

    candidate_names = [p.name for p in candidates]
    for p in human_attackers:
        choice = human_choices[p.name]
        if choice not in candidate_names:
            raise ValueError(f"{p.name}は{choice}を襲撃できません(仲間、死亡者、または存在しない名前です)")

    votes = Counter(human_choices[p.name] for p in human_attackers)
    top = max(votes.values())
    tops = sorted(name for name, v in votes.items() if v == top)
    if len(tops) == 1:
        return tops[0], "人間の実行者の多数決で決まった"
    return rng.choice(tops), "人間の実行者の選択が同数だったので、ランダムで決まった"


# ---------- 決め方2: 実行者が全員AIのとき ----------
def choose_by_ai(state, candidates, night, rng):
    """(選ばれたプレイヤー or None, 理由) を返す。"""
    if not state.settings.protect_humans:
        return rng.choice(candidates), "AIがランダムに選んだ(保護モードなし)"

    humans_alive = sum(1 for p in state.players if p.alive and p.is_human)
    ais_alive = sum(1 for p in state.players if p.alive and not p.is_human)
    safe_targets = [p for p in candidates if not p.is_human]  # 襲撃役ではないAI

    why = None
    if night == 1 and safe_targets:
        why = "(a)最初の夜で、襲撃役ではないAIが生きている"
    elif humans_alive < ais_alive:
        why = "(b)生きている人間が、生きているAIより少ない"
    elif humans_alive == 1:
        why = "(c)生きている人間が、残り1人"

    if why:
        if not safe_targets:
            return None, f"保護モード{why}が、襲撃できるAIがいないので襲撃なし"
        return rng.choice(safe_targets), f"保護モード{why}ので、AIから選んだ"
    return rng.choice(candidates), "AIがランダムに選んだ(保護モードの条件に当てはまらない)"


# ---------- 「襲撃」の行動タイプ ----------
def run_attack_phase(state, human_choices, night, rng=None):
    """夜の「襲撃」を実行して、記録を返す。対象は、その場で死亡扱いにする。
    human_choices: 人間の実行者が選んだ相手 例: {"たろう": "けんじ"}
    night: 何日目の夜か(1 から始まる)"""
    rng = rng or random.Random()
    attackers = attackers_of(state)
    names = [p.name for p in attackers]

    if night == 1 and not state.settings.first_night_attack:
        return AttackRecord(None, names, "1日目の夜の襲撃なし(部屋の設定)")
    if not attackers:
        return AttackRecord(None, names, "襲撃する人がいない")
    candidates = attack_candidates(state)
    if not candidates:
        return AttackRecord(None, names, "襲撃できる相手がいない")

    human_attackers = [p for p in attackers if p.is_human]
    if human_attackers:
        target_name, reason = choose_by_humans(human_attackers, human_choices, candidates, rng)
        target = find_player(state, target_name)
    else:
        target, reason = choose_by_ai(state, candidates, night, rng)

    if target is None:
        return AttackRecord(None, names, reason)
    target.alive = False
    return AttackRecord(target.name, names, reason)



# =====================================================
# 人狼ゲーム ステップ5: 夜の処理のまとめと、朝の処理(死亡者の発表・AIの報告)
# ※ ステップ1〜4のセルを先に実行してから、このセルを実行してください
# =====================================================


# ---------- 選び終わっていない人を調べる ----------
def waiting_names(state, divine_choices, attack_choices, night):
    """夜の行動で、まだ選んでいない人間の名前を返す。(画面で「待っています」と出すときにも使える)"""
    waiting = []

    # 占う(占える相手が残っていないときは、選ばなくてよい)
    for p in state.players:
        if (
            p.alive and p.is_human and p.role.night_action == "divine"
            and p.name not in divine_choices
            and divine_candidates(state, p)
        ):
            waiting.append(p.name)

    # 襲撃(1日目の襲撃なし設定のときや、対象がいないときは、選ぶ必要がない)
    attack_is_active = not (night == 1 and not state.settings.first_night_attack)
    if attack_is_active and attack_candidates(state):
        for p in attackers_of(state):
            if p.is_human and p.name not in attack_choices:
                waiting.append(p.name)

    return waiting


# ---------- 夜の処理をまとめて実行する ----------
def run_night(state, divine_choices, attack_choices, night, rng=None):
    """夜の処理を「占う」→「襲撃」の順に実行する。(占いの記録のリスト, 襲撃の記録) を返す。
    人間がまだ選んでいないときは、何も実行せずにエラーにする。"""
    rng = rng or random.Random()

    waiting = waiting_names(state, divine_choices, attack_choices, night)
    if waiting:
        raise ValueError("まだ選んでいない人がいます: " + "、".join(waiting))

    divine_records = run_divine_phase(state, divine_choices, rng=rng)
    attack_record = run_attack_phase(state, attack_choices, night, rng=rng)
    return divine_records, attack_record


# ---------- 朝の発表 ----------
@dataclass
class MorningReport:
    day: int            # 何日目の朝か
    deaths: list        # 昨夜の犠牲者の名前
    ai_reports: list    # AIの結果の報告(文章のリスト)
    alive: list         # 生存者の名前

    def lines(self):
        out = [f"--- {self.day}日目の朝 ---"]
        if self.deaths:
            out.append("昨夜の犠牲者: " + "、".join(self.deaths))
        else:
            out.append("昨夜は、誰も亡くなりませんでした")
        if self.ai_reports:
            out.append("【AIの報告】")
            out += self.ai_reports
        out.append("生存者: " + "、".join(self.alive))
        return out


def make_morning_report(state, night, attack_record, divine_records):
    """朝の発表を作る。
    AIの結果の報告は、次の条件をすべて満たす占いだけ。
      ・占ったのがAI
      ・その役職の「AIの結果を報告する」が「はい」
      ・そのAIが、夜が明けた時点で生きている"""
    deaths = [attack_record.target] if attack_record and attack_record.target else []

    reports = []
    for rec in divine_records:
        if rec.seer_is_human:
            continue
        seer = find_player(state, rec.seer)
        if not seer.alive or not seer.role.ai_reports_result:
            continue
        reports.append(
            f"{seer.name}({seer.role.name})の報告: {rec.target}を占いました。結果は{RESULT_TEXT[rec.result]}"
        )

    alive = [p.name for p in state.players if p.alive]
    return MorningReport(night, deaths, reports, alive)


def private_lines(divine_records, name):
    """人間の占い師の結果(本人にだけ表示する)"""
    return [show_divine(r) for r in divine_records if r.seer_is_human and r.seer == name]



# =====================================================
# 人狼ゲーム ステップ6: 投票の集計
# ※ ステップ1〜5のセルを先に実行してから、このセルを実行してください
# =====================================================


# ---------- 投票結果 ----------
@dataclass
class VoteResult:
    executed: Optional[str]   # 処刑された人の名前(処刑なしのときは None)
    tally: dict               # {名前: 得票数}(1票以上入った人だけ)
    votes: dict               # {投票した人: 投票先 or None(棄権)}(AIの棄権も含む)
    reason: str               # 決まり方(確認用)

    def lines(self, show_votes=True):
        out = ["--- 投票結果 ---"]
        if show_votes:
            for voter, target in self.votes.items():
                out.append(f"{voter} → {target if target else '棄権'}")
        if self.tally:
            ranking = sorted(self.tally.items(), key=lambda kv: (-kv[1], kv[0]))
            out.append("得票: " + "、".join(f"{name} {n}票" for name, n in ranking))
        out.append("処刑: " + (self.executed if self.executed else "なし") + f"({self.reason})")
        return out


# ---------- 投票できる人・相手 ----------
def waiting_voters(state, human_votes):
    """まだ投票していない(棄権もしていない)、生きている人間の名前"""
    return [p.name for p in state.players if p.alive and p.is_human and p.name not in human_votes]


def vote_candidates(state, voter):
    """投票できる相手 = 自分以外の生存者"""
    return [p.name for p in state.players if p.alive and p is not voter]


# ---------- 投票の集計 ----------
def run_vote(state, human_votes, rng=None):
    """投票を集計して、最多得票の人を処刑する。
    human_votes: 人間の投票 例: {"たろう": "AI1", "はなこ": None}   (None は棄権)
    AIは棄権する。人間が投票(または棄権)を選び終わるまで、エラーにして待つ。"""
    rng = rng or random.Random()

    waiting = waiting_voters(state, human_votes)
    if waiting:
        raise ValueError("まだ投票していない人がいます: " + "、".join(waiting))

    # 投票の一覧を作る(生きている人だけが投票する)
    votes = {}
    for p in state.players:
        if not p.alive:
            continue
        if not p.is_human:
            votes[p.name] = None  # AIは棄権
            continue
        target = human_votes[p.name]
        if target is not None and target not in vote_candidates(state, p):
            raise ValueError(f"{p.name}は{target}に投票できません(自分自身、死亡者、または存在しない名前です)")
        votes[p.name] = target

    tally = dict(Counter(t for t in votes.values() if t is not None))
    if not tally:
        return VoteResult(None, {}, votes, "全員が棄権したので、処刑なし")

    top = max(tally.values())
    tops = sorted(name for name, n in tally.items() if n == top)
    if len(tops) == 1:
        executed, reason = tops[0], "最多得票"
    else:
        executed, reason = rng.choice(tops), "同数のため、同数の中からランダム"

    find_player(state, executed).alive = False
    return VoteResult(executed, tally, votes, reason)



# =====================================================
# 人狼ゲーム ステップ7: 勝敗の判定
# ※ ステップ1〜6のセルを先に実行してから、このセルを実行してください
# =====================================================


# ---------- 数える道具 ----------
def alive_wolf_count(state):
    """「人狼として数える」生存者の数"""
    return sum(1 for p in state.players if p.alive and p.role.counts_as_wolf)


def alive_faction_count(state, faction_id):
    """その陣営に所属する生存者の数"""
    return sum(1 for p in state.players if p.alive and p.role.faction == faction_id)


# ---------- 陣営ごとの勝利条件 ----------
# (条件を調べる関数, 勝った理由の文章)
# 新しい陣営を足すときは、ここに条件を1つ足す
WIN_CONDITIONS = {
    "village": (
        lambda state: alive_wolf_count(state) == 0,
        "人狼がいなくなった",
    ),
    "wolf": (
        lambda state: alive_wolf_count(state) >= alive_faction_count(state, VILLAGE_FACTION),
        "人狼の数が、村人陣営の人数以上になった",
    ),
}


# ---------- 勝敗の結果 ----------
@dataclass
class GameResult:
    faction: str     # 勝った陣営のid
    winners: list    # 勝者の名前(死亡者も含む)
    reason: str      # 勝った理由

    def lines(self):
        return [
            f"勝利: {FACTIONS[self.faction].name}({self.reason})",
            "勝者: " + "、".join(self.winners),
        ]


def check_winner(state):
    """陣営を判定順(小さい方から)に調べて、最初に勝利条件が成り立った陣営の結果を返す。
    まだ勝敗がついていなければ None。"""
    for faction in sorted(FACTIONS.values(), key=lambda f: f.judge_order):
        if faction.id not in WIN_CONDITIONS:
            raise ValueError(f"{faction.name}の勝利条件が、WIN_CONDITIONS にありません")
        condition, reason = WIN_CONDITIONS[faction.id]
        if condition(state):
            winners = [p.name for p in state.players if p.role.faction == faction.id]
            return GameResult(faction.id, winners, reason)
    return None


def reveal_roles(state):
    """ゲーム終了後に、全員の役職を公開する。"""
    out = []
    for p in state.players:
        status = "生存" if p.alive else "死亡"
        out.append(f"{p.name}: {p.role.name}({status})")
    return out



# =====================================================
# 人狼ゲーム ステップ8: 1ゲームを最後まで通すテスト
# ※ ステップ1〜7のセルを先に実行してから、このセルを実行してください
# =====================================================


# ---------- 1ゲームを最初から最後まで進める ----------
def play_game(state, human_divine, human_attack, human_vote, rng=None, max_days=20, verbose=True):
    """
    human_divine(state, day) -> {名前: 占う相手}   人間の占い師の選択を返す関数
    human_attack(state, day) -> {名前: 襲撃する相手} 人間の人狼の選択を返す関数
    human_vote(state, day)   -> {名前: 投票先 or None} 人間の投票を返す関数
    (テストでは、これらの関数に、あらかじめ決めた選択を返させる)

    戻り値: GameResult(勝敗が最後までつかなければ None)
    """
    rng = rng or random.Random()
    log = []

    def say(text):
        if verbose:
            print(text)
        log.append(text)

    for day in range(1, max_days + 1):
        # --- 夜 ---
        divine_choices = human_divine(state, day)
        attack_choices = human_attack(state, day)
        divs, atk = run_night(state, divine_choices, attack_choices, night=day, rng=rng)

        # --- 襲撃の直後に、勝敗を判定 ---
        result = check_winner(state)
        if result:
            say(f"{day}日目の夜、襲撃の直後に決着しました")
            say("\n".join(result.lines()))
            return result

        # --- 朝の発表 ---
        report = make_morning_report(state, day, atk, divs)
        say("\n".join(report.lines()))

        # --- 投票 ---
        vote_choices = human_vote(state, day)
        vresult = run_vote(state, vote_choices, rng=rng)
        say("\n".join(vresult.lines(show_votes=False)))

        # --- 処刑の直後に、勝敗を判定 ---
        result = check_winner(state)
        if result:
            say(f"{day}日目の処刑の直後に決着しました")
            say("\n".join(result.lines()))
            return result

    say(f"{max_days}日たっても、決着しませんでした")
    return None


# ---------- 選択を作る、小さな道具 ----------
def always(name_to_choice):
    """毎回同じ選択を返す関数を作る。例: always({"けんじ": "AI1"})"""
    return lambda state, day: dict(name_to_choice)


def abstain_all(state, day):
    """生きている人間、全員が棄権する投票"""
    return {p.name: None for p in state.players if p.alive and p.is_human}


def nobody(state, day):
    """誰も選ばない(占い師や人狼が、人間にいないときに使う)。
    人間の占い師・人狼がいるときに使うと、「まだ選んでいない」エラーになるので注意。"""
    return {}


def autopick_divine(state, day):
    """生きている人間の占い師、全員に、候補からランダムに選ばせる(テスト用)。"""
    rng = random.Random(1000 + day)
    choices = {}
    for p in state.players:
        if p.alive and p.is_human and p.role.night_action == "divine":
            candidates = divine_candidates(state, p)
            if candidates:
                choices[p.name] = rng.choice(candidates).name
    return choices


def autopick_attack(state, day):
    """生きている人間の、夜の行動が「襲撃」の人、全員に、候補からランダムに選ばせる(テスト用)。"""
    rng = random.Random(2000 + day)
    candidates = attack_candidates(state)
    if not candidates:
        return {}
    choices = {}
    for p in state.players:
        if p.alive and p.is_human and p.role.night_action == "attack":
            choices[p.name] = rng.choice(candidates).name
    return choices



# =====================================================
# 人狼ゲーム ステップ9: ポイントの加算(フェーズ1の最後)
# ※ ステップ1〜8のセルを先に実行してから、このセルを実行してください
# =====================================================


# ---------- ポイントの保存先(サーバーのメモリ内。外部の保存先は使わない) ----------
class PointBoard:
    def __init__(self):
        self._points = {}  # {名前: 累計ポイント}

    def add(self, name, amount):
        self._points[name] = self._points.get(name, 0) + amount

    def get(self, name):
        return self._points.get(name, 0)

    def ranking(self):
        """累計ポイントの多い順の一覧を返す。[(名前, ポイント), ...]"""
        return sorted(self._points.items(), key=lambda kv: (-kv[1], kv[0]))

    def lines(self):
        out = ["--- ランキング ---"]
        for i, (name, pt) in enumerate(self.ranking(), start=1):
            out.append(f"{i}位 {name}: {pt}点")
        return out or ["--- ランキング ---", "(まだ記録がありません)"]


# ---------- 勝った陣営へのポイント付与 ----------
def award_points(board, state, result):
    """result(GameResult)の勝者全員に、その陣営に設定されたポイントを加算する。
    人間もAIも対象。名前が同じなら、同じ参加者として累計する。"""
    point = state.settings.faction_points.get(result.faction, FACTIONS[result.faction].points)
    for name in result.winners:
        board.add(name, point)
    return point

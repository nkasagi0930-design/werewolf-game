"""
人狼ゲーム rooms_store.py
複数人で共有する、部屋の置き場所です。
Streamlitのサーバー(1つ)が動いている間、この中身は、全員のブラウザから、共通に見えます。
※ サーバーが再起動すると、中身は消えます(ポイントと同じ扱いです)。
"""
import random
import string
from dataclasses import dataclass, field
from game_rules import (
    RoomSettings, GameState, create_players, validate, find_player,
    divine_candidates, attack_candidates, waiting_names, run_night,
    make_morning_report, check_winner, vote_candidates, waiting_voters, run_vote,
    PointBoard, award_points,
)


@dataclass
class RoomState:
    code: str
    host_name: str                      # 部屋を作った人の名前
    settings: RoomSettings
    participants: list = field(default_factory=list)  # 参加者の名前(人間だけ。参加した順)
    started: bool = False
    game: object = None                 # ゲームが始まったら、ここにGameStateを入れる
    day: int = 1                        # 今、何日目か
    phase: str = "role_check"           # 今のフェーズ("role_check" など。夜・朝・投票は、次のステップで足す)
    confirmed: set = field(default_factory=set)  # 役職の確認を終えた、人間の名前
    divine_choices: dict = field(default_factory=dict)  # {占った人の名前: 占う相手}
    attack_choices: dict = field(default_factory=dict)  # {襲撃する人の名前: 襲撃する相手}
    morning_report: object = None       # 朝の発表(MorningReport)
    divine_records: list = field(default_factory=list)  # この夜の占いの記録(本人にだけ見せる)
    game_result: object = None          # 勝敗が決まったら、ここにGameResultを入れる
    vote_choices: dict = field(default_factory=dict)  # {投票した人の名前: 投票先 or None(棄権)}
    vote_result: object = None          # 投票の結果(VoteResult)
    points_awarded: bool = False        # このゲームの分の、ポイントを、もう加算したか


# ---------- 共有の置き場所本体 ----------
# モジュールの中に、直接、辞書として持たせる。
# Streamlitは、このファイルを1回だけ読み込んで使い回すので、
# 誰のブラウザから触っても、同じ ROOMS が使われる。
ROOMS: dict[str, RoomState] = {}


def _new_room_code():
    """4桁の、数字だけの部屋コードを作る(重複しないもの)"""
    while True:
        code = "".join(random.choices(string.digits, k=4))
        if code not in ROOMS:
            return code


# ---------- 部屋を作る ----------
def create_room(host_name, settings):
    """部屋を作って、作った人を、参加者の1人目として登録する。部屋コードを返す。"""
    host_name = host_name.strip()
    if not host_name:
        raise ValueError("名前を入力してください")
    errors = validate(settings)
    if errors:
        raise ValueError("\n".join(errors))

    code = _new_room_code()
    room = RoomState(code=code, host_name=host_name, settings=settings, participants=[host_name])
    ROOMS[code] = room
    return code


# ---------- 部屋に参加する ----------
def join_room(code, name):
    """既にある部屋に、参加者を1人足す。"""
    code = code.strip()
    name = name.strip()

    if code not in ROOMS:
        raise ValueError(f"部屋コード「{code}」は見つかりません")
    room = ROOMS[code]

    if room.started:
        raise ValueError("このゲームは、もう始まっています")
    if not name:
        raise ValueError("名前を入力してください")
    if name.startswith("AI"):
        raise ValueError("「AI」で始まる名前は使えません")
    if name in room.participants:
        # 同じ名前で、もう一度アクセスしてきた場合(再入場)は、エラーにせず、そのまま戻す
        return room
    if len(room.participants) >= room.settings.human_count:
        raise ValueError("この部屋は、もう定員に達しています")

    room.participants.append(name)
    return room


def get_room(code):
    """部屋コードから、部屋の状態を取り出す。なければ None。"""
    return ROOMS.get((code or "").strip())


def is_participant(room, name):
    return bool(room) and name in room.participants


# ---------- ゲームの開始 ----------
def start_game(room, seed=None):
    """参加者がそろったら、役職を割り振って、ゲームを開始する。"""
    if room.started:
        raise ValueError("すでに開始しています")
    if len(room.participants) != room.settings.human_count:
        raise ValueError(
            f"人間の参加者が、まだそろっていません({len(room.participants)}/{room.settings.human_count}人)"
        )
    players = create_players(room.settings, room.participants, seed=seed)
    room.game = GameState(room.settings, players)
    room.started = True
    return room.game


# ---------- 役職の確認 ----------
def confirm_role(room, name):
    """「役職を確認しました」を記録する。全員そろえば、次のフェーズに進める。"""
    room.confirmed.add(name)
    if len(room.confirmed) >= len(room.participants) and room.phase == "role_check":
        room.phase = "night"  # 次のステップで、夜の行動画面につなげる


def not_yet_confirmed(room):
    """まだ役職を確認していない、人間の名前の一覧"""
    return [n for n in room.participants if n not in room.confirmed]


# ---------- 夜の行動 ----------
def my_divine_candidates(room, name):
    """その人(占い師)が、今夜、占える相手の名前の一覧"""
    me = find_player(room.game, name)
    return [p.name for p in divine_candidates(room.game, me)]


def my_attack_candidates(room):
    """今夜、襲撃できる相手の名前の一覧(人狼、全員で共通)"""
    return [p.name for p in attack_candidates(room.game)]


def submit_divine_choice(room, name, target):
    room.divine_choices[name] = target
    resolve_night_if_ready(room)


def submit_attack_choice(room, name, target):
    room.attack_choices[name] = target
    resolve_night_if_ready(room)


def night_waiting(room):
    """夜の行動で、まだ選んでいない人間の名前の一覧"""
    return waiting_names(room.game, room.divine_choices, room.attack_choices, room.day)


def resolve_night_if_ready(room):
    """まだ選んでいない人がいなければ、夜の処理をまとめて実行し、朝の発表を作る。
    人間が誰も選ぶ必要がない夜(全員、夜に何もしない役職のとき)にも、
    画面を開いただけで、自動的に朝へ進められるよう、何度呼んでも安全な作りにしてある。"""
    if room.phase != "night":
        return  # すでに、夜の処理は済んでいる
    if night_waiting(room):
        return  # まだ、そろっていない

    divine_records, attack_record = run_night(room.game, room.divine_choices, room.attack_choices, room.day)
    room.divine_records = divine_records

    result = check_winner(room.game)
    if result:
        room.phase = "game_over"
        room.game_result = result
        return

    room.morning_report = make_morning_report(room.game, room.day, attack_record, divine_records)
    room.phase = "morning"


def my_divine_result_lines(room, name):
    """人間の占い師の、今夜の結果(本人にだけ見せる分)"""
    return [
        f"{r.target}は{'人狼です' if r.result == 'wolf' else '人狼ではありません'}"
        for r in room.divine_records if r.seer_is_human and r.seer == name
    ]


def go_to_vote(room):
    """朝の発表から、議論を終えて、投票フェーズに進める。"""
    room.phase = "vote"


# ---------- 投票 ----------
def my_vote_candidates(room, name):
    """その人が、投票できる相手の名前の一覧(自分以外の生存者)"""
    me = find_player(room.game, name)
    return vote_candidates(room.game, me)


def submit_vote(room, name, target):
    """target は、名前、または棄権のとき None"""
    room.vote_choices[name] = target
    resolve_vote_if_ready(room)


def vote_waiting(room):
    """まだ投票(棄権も含む)していない、人間の名前の一覧"""
    return waiting_voters(room.game, room.vote_choices)


def resolve_vote_if_ready(room):
    """まだ投票していない人がいなければ、集計する。
    生きている人間が、もう1人もいないときにも、自動的に進められるよう、
    何度呼んでも安全な作りにしてある。"""
    if room.phase != "vote":
        return  # すでに、投票の処理は済んでいる
    if vote_waiting(room):
        return  # まだ、そろっていない

    room.vote_result = run_vote(room.game, room.vote_choices)

    result = check_winner(room.game)
    if result:
        room.phase = "game_over"
        room.game_result = result
        return

    room.phase = "vote_result"


def advance_to_next_night(room):
    """投票結果を確認したあと、次の夜に進む。"""
    room.day += 1
    room.divine_choices = {}
    room.attack_choices = {}
    room.divine_records = []
    room.morning_report = None
    room.vote_choices = {}
    room.vote_result = None
    room.phase = "night"


# ---------- ポイント(部屋をまたいで、累計する。外部の保存先は使わない) ----------
POINTS = PointBoard()


def award_points_once(room):
    """ゲームが終わったとき、まだポイントを加算していなければ、加算する。
    (画面が何度も再描画されても、二重に加算されないようにするため)"""
    if room.points_awarded or not room.game_result:
        return None
    pt = award_points(POINTS, room.game, room.game_result)
    room.points_awarded = True
    return pt


def ranking_lines():
    return POINTS.lines()


# ---------- もう一度遊ぶ ----------
def reset_for_replay(room):
    """同じ部屋コード・同じ参加者・同じ設定のまま、待機画面からやり直せるようにする。"""
    room.started = False
    room.game = None
    room.day = 1
    room.phase = "role_check"
    room.confirmed = set()
    room.divine_choices = {}
    room.attack_choices = {}
    room.morning_report = None
    room.divine_records = []
    room.game_result = None
    room.vote_choices = {}
    room.vote_result = None
    room.points_awarded = False
"""
人狼ゲーム app.py (フェーズ2 前半 ステップ2)
今回、新しく動くようになった画面
  3. 部屋に参加する画面
  4. 待機画面(参加者の一覧と、「開始」ボタン)

複数人で共有する部分は、rooms_store.py に任せています。
ブラウザを閉じて開き直しても、同じ自分として戻れるように、
「部屋コード」と「名前」を、st.session_state だけでなく、URL(query params)にも残しています。
"""
import streamlit as st
from game_rules import recommend, ROLES, FACTIONS, RoomSettings, validate, describe_composition, find_player, view_for
import rooms_store as rs

st.set_page_config(page_title="人狼ゲーム", page_icon="🐺")

# ---------- 自分が誰かを、URLから復元する ----------
# ブラウザを開き直すと、st.session_state は空に戻ってしまうが、
# URLの ?room=1234&name=たろう は、そのまま残るので、ここから読み直す。
qp = st.query_params
if "screen" not in st.session_state:
    st.session_state.screen = "top"
if "room_code" not in st.session_state:
    st.session_state.room_code = qp.get("room", "")
if "player_name" not in st.session_state:
    st.session_state.player_name = qp.get("name", "")

def go_to(screen_name):
    st.session_state.screen = screen_name


def set_identity(room_code, name):
    """自分が誰かを、session_state と URL の、両方に記録する。"""
    st.session_state.room_code = room_code
    st.session_state.player_name = name
    st.query_params["room"] = room_code
    st.query_params["name"] = name


def phase_screen(room):
    """部屋の、今の本当の状態(phase)から、表示すべき画面名を返す。
    どの画面からでも、この関数の答えと、自分が今いる画面が違っていたら、
    正しい画面に、案内し直す(他の人の操作で、部屋の状態が、
    自分の知らないうちに進んでいたときのための、共通の仕組み)。"""
    if not room.started or room.game is None:
        return "waiting_room"
    if room.phase == "role_check":
        return "role_check"
    if room.phase in ("vote", "vote_result"):
        return "vote"
    return "night_action"  # night / morning / game_over は、同じ画面の中で、切り替える


def sync_screen(room, this_screen):
    """今いる画面(this_screen)が、部屋の本当の状態と違っていたら、正しい画面に進める。
    進めた場合は True を返す(呼び出し元は、それ以上、何も描画せずに戻ること)。"""
    target = phase_screen(room)
    if target != this_screen:
        go_to(target)
        st.rerun()
        return True
    return False


# URLに、部屋コードと名前が入っていて、かつ、その部屋に、自分がすでに参加者として
# 登録されているなら、正しい画面に、自動で戻す(再入場)。
if st.session_state.room_code and st.session_state.player_name and st.session_state.screen == "top":
    room = rs.get_room(st.session_state.room_code)
    if rs.is_participant(room, st.session_state.player_name):
        st.session_state.screen = phase_screen(room)


# ---------- 画面1: トップ画面 ----------
def show_top():
    st.title("🐺 人狼ゲーム")
    st.write("友達と、別の場所から遊べる人狼ゲームです。")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("部屋を作る", use_container_width=True):
            go_to("create_room")
    with col2:
        if st.button("部屋に参加する", use_container_width=True):
            go_to("join_room")


# ---------- 画面2: 部屋を作る画面 ----------
def show_create_room():
    st.title("部屋を作る")
    if st.button("← トップに戻る"):
        go_to("top")
        st.rerun()

    host_name = st.text_input("あなたの名前")

    total_players = st.number_input("総人数", min_value=4, max_value=15, value=6, step=1)
    human_count = st.number_input("人間の参加者数(自分を含む)", min_value=1, max_value=total_players, value=1, step=1)
    ai_count = total_players - human_count
    st.caption(f"AIの人数: {ai_count}人")

    st.subheader("役職の構成")
    rec = recommend(total_players)
    if rec is None:
        st.info(f"{total_players}人のおすすめ構成は、まだ用意されていません。下で自由に決めてください。")
        rec = {"wolf": 1, "seer": 1, "villager": max(total_players - 2, 0)}
    else:
        st.caption("おすすめ: " + describe_composition(rec))

    role_counts = {}
    cols = st.columns(len(ROLES))
    for col, (role_id, role) in zip(cols, ROLES.items()):
        with col:
            role_counts[role_id] = st.number_input(
                role.name, min_value=0, max_value=total_players,
                value=rec.get(role_id, 0), step=1, key=f"role_{role_id}",
            )

    st.subheader("部屋の設定")
    first_night_attack = st.toggle("1日目の夜の襲撃", value=True)
    protect_humans = st.toggle("人間を保護するモード", value=True)

    st.subheader("勝利時のポイント")
    faction_points = {}
    cols2 = st.columns(len(FACTIONS))
    for col, (faction_id, faction) in zip(cols2, FACTIONS.items()):
        with col:
            faction_points[faction_id] = st.number_input(
                f"{faction.name}", min_value=0, max_value=99,
                value=faction.points, step=1, key=f"points_{faction_id}",
            )

    st.divider()

    if st.button("この設定で、部屋を作る", type="primary"):
        settings = RoomSettings(
            total_players=total_players,
            human_count=human_count,
            role_counts=role_counts,
            first_night_attack=first_night_attack,
            protect_humans=protect_humans,
            faction_points=faction_points,
        )
        try:
            code = rs.create_room(host_name, settings)
        except ValueError as e:
            for line in str(e).split("\n"):
                st.error(line)
        else:
            set_identity(code, host_name.strip())
            go_to("waiting_room")
            st.rerun()


# ---------- 画面3: 部屋に参加する画面 ----------
def show_join_room():
    st.title("部屋に参加する")
    if st.button("← トップに戻る"):
        go_to("top")
        st.rerun()

    code = st.text_input("部屋コード(4桁)")
    name = st.text_input("あなたの名前")

    if st.button("参加する", type="primary"):
        try:
            rs.join_room(code, name)
        except ValueError as e:
            st.error(str(e))
        else:
            set_identity(code.strip(), name.strip())
            go_to("waiting_room")
            st.rerun()


# ---------- 画面4: 待機画面 ----------
def show_waiting_room():
    room = rs.get_room(st.session_state.room_code)
    if room is None:
        st.error("部屋が見つかりませんでした。トップに戻ります。")
        if st.button("トップに戻る"):
            go_to("top")
            st.rerun()
        return

    st.title("部屋で待っています")
    st.write(f"部屋コード: **{room.code}**(友達に、この番号を伝えてください)")
    st.write(f"あなたの名前: {st.session_state.player_name}")

    st.subheader(f"参加者 {len(room.participants)} / {room.settings.human_count} 人")
    for n in room.participants:
        tag = "(部屋を作った人)" if n == room.host_name else ""
        st.write(f"- {n} {tag}")

    if st.button("🔄 更新"):
        st.rerun()

    is_host = st.session_state.player_name == room.host_name
    ready = len(room.participants) == room.settings.human_count

    if is_host and not room.started:
        st.divider()
        if not ready:
            st.info("全員がそろうまで、開始できません。")
        if st.button("ゲームを開始する", type="primary", disabled=not ready):
            rs.start_game(room)
            go_to("role_check")
            st.rerun()
    elif not room.started:
        st.info("部屋を作った人が、開始するのを待っています。")

    if room.started:
        go_to("role_check")
        st.rerun()


# ---------- 画面5: 役職の確認画面 ----------
def show_role_check():
    room = rs.get_room(st.session_state.room_code)
    if room is None:
        st.error("部屋が見つかりませんでした。トップに戻ります。")
        if st.button("トップに戻る"):
            go_to("top")
            st.rerun()
        return
    if sync_screen(room, "role_check"):
        return

    my_name = st.session_state.player_name
    me = find_player(room.game, my_name)

    st.title("あなたの役職")
    st.write(view_for(me, room.game.players))

    already_confirmed = my_name in room.confirmed

    if not already_confirmed:
        st.warning("役職を、他の人に見られないように、気をつけてください。")
        if st.button("役職を確認しました", type="primary"):
            rs.confirm_role(room, my_name)
            st.rerun()
    else:
        st.success("確認、ありがとうございます。他の人を、待っています。")

    waiting = rs.not_yet_confirmed(room)
    st.write(f"まだ確認していない人: {'、'.join(waiting) if waiting else 'いません'}")
    if st.button("🔄 更新"):
        st.rerun()


# ---------- 画面6: 夜の行動画面 ----------
def show_night_action():
    room = rs.get_room(st.session_state.room_code)
    if room is None:
        st.error("部屋が見つかりませんでした。トップに戻ります。")
        if st.button("トップに戻る"):
            go_to("top")
            st.rerun()
        return
    if sync_screen(room, "night_action"):
        return

    my_name = st.session_state.player_name
    me = find_player(room.game, my_name)

    # 人間が誰も選ぶ必要がない夜(全員、夜に何もしない役職のとき)でも、
    # 自動で朝に進めるよう、ここで毎回、確認する。
    rs.resolve_night_if_ready(room)

    # --- 勝敗がついていたら、結果画面を出す ---
    if room.phase == "game_over":
        rs.award_points_once(room)  # まだなら、ここでポイントを加算する(2回目以降は、何もしない)

        st.title("🏁 ゲーム終了")
        st.write("\n".join(room.game_result.lines()))

        st.subheader("全員の役職")
        for p in room.game.players:
            kind = "人間" if p.is_human else "AI"
            status = "生存" if p.alive else "死亡"
            st.write(f"- {p.name}: {p.role.name}({kind}・{status})")

        st.subheader("ランキング")
        for line in rs.ranking_lines()[1:]:  # 1行目の見出しは、st.subheaderと重なるので飛ばす
            st.write(line)

        is_host = my_name == room.host_name
        if is_host:
            st.divider()
            if st.button("もう一度遊ぶ(同じメンバーで)", type="primary"):
                rs.reset_for_replay(room)
                go_to("waiting_room")
                st.rerun()
        else:
            st.info("部屋を作った人が、「もう一度遊ぶ」を押すのを、待っています。")
            if st.button("🔄 更新"):
                st.rerun()
        return

    # --- 朝の発表(まだ投票画面がないので、ここまでを、今回のゴールにします) ---
    if room.phase == "morning":
        st.title("☀️ 朝の発表")
        st.write("\n".join(room.morning_report.lines()))

        if me.is_human and me.alive and me.role.night_action == "divine":
            private = rs.my_divine_result_lines(room, my_name)
            if private:
                st.subheader("あなたの占い結果")
                for line in private:
                    st.write(line)

        st.divider()
        st.write("ここで、音声通話などで、議論してください。")
        if st.button("議論を終えて、投票に進む(押すと、全員の画面が切り替わります)", type="primary"):
            rs.go_to_vote(room)
            go_to("vote")
            st.rerun()
        if st.button("🔄 更新"):
            st.rerun()
        return

    # --- 夜の行動を選ぶ ---
    st.title(f"🌙 {room.day}日目の夜")

    if not me.alive:
        st.info("あなたは、亡くなっています。他の人の行動を、静かに待ちましょう。")
    elif me.role.night_action == "divine":
        if my_name in room.divine_choices:
            st.success(f"{room.divine_choices[my_name]} を占いました。他の人を、待っています。")
        else:
            candidates = rs.my_divine_candidates(room, my_name)
            if not candidates:
                st.info("今夜、占える相手がいません。そのまま、次に進みます。")
            else:
                st.write("誰を占いますか？")
                target = st.radio("占う相手", candidates, label_visibility="collapsed")
                if st.button("この人を占う", type="primary"):
                    rs.submit_divine_choice(room, my_name, target)
                    st.rerun()
    elif me.role.night_action == "attack":
        if my_name in room.attack_choices:
            st.success(f"{room.attack_choices[my_name]} を選びました。他の人を、待っています。")
        else:
            candidates = rs.my_attack_candidates(room)
            if not candidates:
                st.info("今夜、襲撃できる相手がいません。そのまま、次に進みます。")
            else:
                st.write("誰を襲撃しますか？(仲間と、相談してから選んでください)")
                target = st.radio("襲撃する相手", candidates, label_visibility="collapsed")
                if st.button("この人を襲撃する", type="primary"):
                    rs.submit_attack_choice(room, my_name, target)
                    st.rerun()
    else:
        st.info("今夜、あなたが選ぶことは、ありません。他の人を、待ちましょう。")

    waiting = rs.night_waiting(room)
    st.write(f"まだ選んでいない人: {'、'.join(waiting) if waiting else 'いません'}")
    if st.button("🔄 更新"):
        st.rerun()


# ---------- 画面8: 投票画面 ----------
def show_vote():
    room = rs.get_room(st.session_state.room_code)
    if room is None:
        st.error("部屋が見つかりませんでした。トップに戻ります。")
        if st.button("トップに戻る"):
            go_to("top")
            st.rerun()
        return
    if sync_screen(room, "vote"):
        return

    my_name = st.session_state.player_name
    me = find_player(room.game, my_name)

    # 生きている人間が、もう1人もいないときにも、自動で先に進めるよう、ここで毎回、確認する。
    rs.resolve_vote_if_ready(room)
    if sync_screen(room, "vote"):  # 上の行で、決着がついた(game_over)可能性があるため
        return

    # --- 投票結果が出ている ---
    if room.phase == "vote_result":
        st.title("🗳️ 投票結果")
        st.write("\n".join(room.vote_result.lines(show_votes=False)))
        st.info("ゲームは、まだ続きます。")
        if st.button("次の夜へ進む(押すと、全員の画面が切り替わります)", type="primary"):
            rs.advance_to_next_night(room)
            go_to("night_action")
            st.rerun()
        if st.button("🔄 更新"):
            st.rerun()
        return

    # --- 投票する ---
    st.title(f"🗳️ {room.day}日目の投票")

    if not me.alive:
        st.info("あなたは、亡くなっています。投票できません。他の人を、待ちましょう。")
    elif my_name in room.vote_choices:
        chosen = room.vote_choices[my_name]
        st.success(f"{'棄権しました' if chosen is None else f'{chosen} に投票しました'}。他の人を、待っています。")
    else:
        candidates = rs.my_vote_candidates(room, my_name)
        options = candidates + ["(棄権する)"]
        choice = st.radio("投票先", options, label_visibility="collapsed")
        if st.button("この内容で、投票する", type="primary"):
            target = None if choice == "(棄権する)" else choice
            rs.submit_vote(room, my_name, target)
            st.rerun()

    waiting = rs.vote_waiting(room)
    st.write(f"まだ投票していない人: {'、'.join(waiting) if waiting else 'いません'}")
    if st.button("🔄 更新"):
        st.rerun()


# ---------- 今の画面を表示する ----------
screen = st.session_state.screen
if screen == "top":
    show_top()
elif screen == "create_room":
    show_create_room()
elif screen == "join_room":
    show_join_room()
elif screen == "waiting_room":
    show_waiting_room()
elif screen == "role_check":
    show_role_check()
elif screen == "night_action":
    show_night_action()
elif screen == "vote":
    show_vote()
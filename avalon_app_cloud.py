import streamlit as st
import pandas as pd
import json
import datetime
import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- 1. 云端数据库连接配置 ---
# 既然是云端版，我们不再用本地文件，而是连接 Google Sheets
# 我们稍后会在 Streamlit Cloud 的 Secrets 里配置 key

SCOPES = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/drive']

@st.cache_resource
def get_db_connection():
    # 从 Streamlit Secrets 读取配置
    if "gcp_service_account" not in st.secrets:
        st.error("未找到密钥配置！请在 Streamlit Cloud 的 Secrets 中配置 gcp_service_account。")
        st.stop()
        
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPES)
    client = gspread.authorize(creds)
    
    # 打开你的表格，这里需要在 Secrets 里配置表格名称或 URL
    sheet_url = st.secrets["private_gsheets_url"]
    sh = client.open_by_url(sheet_url)
    return sh

def init_db(sh):
    # 检查并创建 Players 工作表
    try:
        ws_p = sh.worksheet("Players")
    except:
        ws_p = sh.add_worksheet(title="Players", rows=100, cols=2)
        ws_p.append_row(["name", "joined_at"]) # 表头
        
    # 检查并创建 Games 工作表
    try:
        ws_g = sh.worksheet("Games")
    except:
        ws_g = sh.add_worksheet(title="Games", rows=1000, cols=4)
        ws_g.append_row(["game_date", "winner", "assassination_success", "roles"]) # 表头

def get_all_players():
    sh = get_db_connection()
    ws = sh.worksheet("Players")
    # 获取第一列，排除表头
    names = ws.col_values(1)
    if len(names) > 1:
        return names[1:]
    return []

def add_new_player(name):
    sh = get_db_connection()
    ws = sh.worksheet("Players")
    existing = get_all_players()
    if name in existing:
        return False
    ws.append_row([name, str(datetime.datetime.now())])
    return True

def delete_player(name):
    sh = get_db_connection()
    ws = sh.worksheet("Players")
    cell = ws.find(name)
    if cell:
        ws.delete_rows(cell.row)

def save_game(game_date, winner, assassination_success, role_dict):
    sh = get_db_connection()
    ws = sh.worksheet("Games")
    date_str = game_date.strftime("%Y-%m-%d")
    roles_json = json.dumps(role_dict, ensure_ascii=False)
    # 写入一行
    ws.append_row([date_str, winner, "TRUE" if assassination_success else "FALSE", roles_json])

def load_games():
    sh = get_db_connection()
    ws = sh.worksheet("Games")
    data = ws.get_all_records()
    # 转换为 DataFrame
    df = pd.DataFrame(data)
    # Google Sheets 有时候读出来的布尔值是字符串，处理一下
    if not df.empty and 'assassination_success' in df.columns:
        df['assassination_success'] = df['assassination_success'].apply(lambda x: True if str(x).upper() == 'TRUE' else False)
    return df

# --- 游戏逻辑配置 (保持 V8 逻辑) ---
GAME_RULES = {
    5: {"good": 3, "bad": 2},
    6: {"good": 4, "bad": 2},
    7: {"good": 4, "bad": 3},
    8: {"good": 5, "bad": 3},
    9: {"good": 6, "bad": 3},
    10: {"good": 6, "bad": 4}
}

ROLE_DISPLAY = {
    "Merlin": "🧙‍♂️ 梅林", "Percival": "👀 派西维尔", "Civilian": "🛡️ 忠臣",
    "Assassin": "🗡️ 刺客", "Morgana": "😈 莫甘娜", "Mordred": "👺 莫德雷德",
    "Oberon": "👽 奥博伦", "Minion": "👿 爪牙"
}

# --- 界面部分 (基本保持 V8，微调数据库调用) ---
st.set_page_config(page_title="阿瓦隆助手 Cloud", page_icon="🛡️", layout="centered") 
st.title("🛡️ 阿瓦隆战绩助手 Cloud")

# 初始化（确保 Sheet 结构存在）
try:
    sh = get_db_connection()
    init_db(sh)
except Exception as e:
    st.error(f"数据库连接失败，请检查 Secrets 配置。错误信息: {e}")
    st.stop()

tab_input, tab_history, tab_stats = st.tabs(["📝 记一局", "📊 看战绩", "📈 个人分析"])

# === Tab 1: 录入 ===
with tab_input:
    current_players = get_all_players()
    with st.expander("⚙️ 玩家管理", expanded=False):
        tab_add, tab_del = st.tabs(["➕ 添加", "🗑️ 删除"])
        with tab_add:
            c1, c2 = st.columns([3, 1])
            with c1: new_name = st.text_input("新玩家名字", label_visibility="collapsed")
            with c2: 
                if st.button("添加"):
                    if new_name:
                        if add_new_player(new_name):
                            st.success(f"已添加 {new_name}")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.warning("玩家已存在")
        with tab_del:
            if current_players:
                to_delete = st.selectbox("选择删除", current_players, index=None)
                if st.button("❌ 删除玩家", type="primary"):
                    if to_delete:
                        delete_player(to_delete)
                        st.success("已删除")
                        time.sleep(1)
                        st.rerun()

    if not current_players:
        st.warning("请先添加玩家")
    else:
        st.markdown("##### 步骤1：选择玩家")
        selected_players = st.pills("玩家列表", current_players, selection_mode="multi")
        num_players = len(selected_players)
        
        if num_players < 5:
            st.caption(f"已选 {num_players} 人，至少需 5 人。")
        elif num_players > 10:
            st.warning("暂不支持超过 10 人。")
        else:
            rule = GAME_RULES.get(num_players, {"good": 0, "bad": 0})
            target_good, target_bad = rule["good"], rule["bad"]
            st.info(f"📋 **{num_players}人局**：好人 {target_good} | 坏人 {target_bad}")
            st.divider()

            c_date, c_conf = st.columns([1, 2])
            with c_date: game_date = st.date_input("日期", datetime.date.today())
            with c_conf:
                special_chars = st.pills("特殊角色", ["派西维尔", "莫甘娜", "莫德雷德", "奥博伦"], selection_mode="multi", default=["派西维尔", "莫甘娜"])
            
            has_percival, has_morgana = "派西维尔" in special_chars, "莫甘娜" in special_chars
            has_mordred, has_oberon = "莫德雷德" in special_chars, "奥博伦" in special_chars

            role_map = {}
            pool = list(selected_players)
            
            st.markdown(":blue[**🔵 蓝方**]")
            p_merlin = st.selectbox("🧙‍♂️ 梅林", pool, index=None)
            if p_merlin: role_map[p_merlin]="Merlin"; pool.remove(p_merlin)
            
            if has_percival:
                p_percival = st.selectbox("👀 派西维尔", pool, index=None)
                if p_percival: role_map[p_percival]="Percival"; pool.remove(p_percival)
            
            st.markdown("---")
            st.markdown(":red[**🔴 红方**]")
            p_assassin = st.selectbox("🗡️ 刺客", pool, index=None)
            if p_assassin: role_map[p_assassin]="Assassin"; pool.remove(p_assassin)
            
            if has_morgana:
                p_m = st.selectbox("😈 莫甘娜", pool, index=None)
                if p_m: role_map[p_m]="Morgana"; pool.remove(p_m)
            if has_mordred:
                p_md = st.selectbox("👺 莫德雷德", pool, index=None)
                if p_md: role_map[p_md]="Mordred"; pool.remove(p_md)
            if has_oberon:
                p_o = st.selectbox("👽 奥博伦", pool, index=None)
                if p_o: role_map[p_o]="Oberon"; pool.remove(p_o)
            
            curr_bad = sum(1 for r in role_map.values() if r in ["Assassin", "Morgana", "Mordred", "Oberon"])
            needed = target_bad - curr_bad
            if needed > 0:
                p_mins = st.multiselect(f"👿 还需 {needed} 个爪牙", pool, max_selections=needed)
                for p in p_mins: role_map[p]="Minion"; 
                # 这里如果用 multiselect 不会自动 remove pool，为了简单直接标记即可
            
            # 补全逻辑
            for p in selected_players:
                if p not in role_map: role_map[p] = "Civilian"

            st.divider()
            winner = st.radio("获胜方", ["蓝方(正义)", "红方(邪恶)"], horizontal=True)
            assassination = False
            if winner == "红方(邪恶)": assassination = st.checkbox("🗡️ 刺梅成功？")
            
            if st.button("💾 提交", type="primary", use_container_width=True):
                # 简单校验
                bad_cnt = sum(1 for r in role_map.values() if r in ["Assassin", "Morgana", "Mordred", "Oberon", "Minion"])
                if bad_cnt != target_bad:
                    st.error(f"坏人数量错误：当前{bad_cnt}，应为{target_bad}")
                elif len(role_map) != num_players:
                    st.error("人数不符")
                else:
                    save_game(game_date, winner, assassination, role_map)
                    st.success("已保存到云端表格！")
                    time.sleep(1.5)
                    st.rerun()

# === Tab 2 & 3 (保持 V8 逻辑，只需确保 df 来源正确) ===
with tab_history:
    df = load_games()
    if df.empty:
        st.info("暂无数据")
    else:
        view = st.radio("View", ["📱 卡片", "🖥️ 表格"], horizontal=True, label_visibility="collapsed")
        if "卡片" in view:
            for i, row in df.sort_values(by="game_date", ascending=False).iterrows():
                try: roles = json.loads(row['roles'])
                except: continue
                with st.container(border=True):
                    c1, c2 = st.columns([2, 1])
                    wt = "🔴 红胜" if "红方" in row['winner'] else "🔵 蓝胜"
                    c1.markdown(f"**{row['game_date']}**")
                    c2.markdown(f"**{wt}**")
                    if row['assassination_success']: st.caption("🗡️ 刺梅成功")
                    st.divider()
                    bl, rl = [], []
                    for p, r in roles.items():
                        line = f"{ROLE_DISPLAY.get(r,r)}: {p}"
                        if r in ["Merlin", "Percival", "Civilian"]: bl.append(line)
                        else: rl.append(line)
                    cb, cr = st.columns(2)
                    with cb: 
                        st.markdown(":blue[**蓝方**]")
                        for l in bl: st.markdown(l)
                    with cr: 
                        st.markdown(":red[**红方**]")
                        for l in rl: st.markdown(l)
        else:
            # 表格视图
            td = []
            cols = ["梅林", "派西维尔", "忠臣", "刺客", "莫甘娜", "莫德雷德", "奥博伦", "爪牙"]
            for i, row in df.sort_values(by="game_date", ascending=False).iterrows():
                roles = json.loads(row['roles'])
                d = {"日期": row['game_date'], "胜方": row['winner'], "刺杀": "✅" if row['assassination_success'] else ""}
                grps = {k:[] for k in cols}
                for p, r in roles.items():
                    cn = ROLE_DISPLAY.get(r,r).split(" ")[-1]
                    if cn in grps: grps[cn].append(p)
                for k,v in grps.items(): d[k]=", ".join(v)
                td.append(d)
            st.dataframe(pd.DataFrame(td).fillna("-"), use_container_width=True, hide_index=True)

with tab_stats:
    df = load_games()
    if not df.empty:
        fd = []
        for i, row in df.iterrows():
            roles = json.loads(row['roles'])
            is_r_win = "红方" in row['winner']
            for p, r in roles.items():
                is_blue = r in ["Merlin", "Percival", "Civilian"]
                win = (is_blue and not is_r_win) or (not is_blue and is_r_win)
                fd.append({"Player":p, "Role":ROLE_DISPLAY.get(r,r), "Win":1 if win else 0})
        sdf = pd.DataFrame(fd)
        
        st.subheader("🏆 胜率天梯")
        rk = sdf.groupby("Player").agg(场次=("Win","count"), 胜场=("Win","sum"))
        rk["胜率"] = rk["胜场"]/rk["场次"]
        st.dataframe(rk.sort_values("胜率", ascending=False).style.format({"胜率":"{:.1%}"}), use_container_width=True)
        
        st.divider()
        st.subheader("👤 个人详情")
        user = st.selectbox("选择", get_all_players())
        if user:
            ud = sdf[sdf["Player"]==user]
            if not ud.empty:
                c1,c2 = st.columns(2)
                c1.metric("总场次", len(ud))
                c1.metric("总胜率", f"{ud['Win'].sum()/len(ud):.1%}")
                rc = ud["Role"].value_counts()
                st.bar_chart(rc)
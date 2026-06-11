"""美銀牛熊指標(高擬真復刻版 v2) · Streamlit 看板。"""
import os
from datetime import datetime, timedelta
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import indicator as ind

import json
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
HISTORY_CSV = os.path.join(DATA_DIR, "history.csv")
LATEST_JSON = os.path.join(DATA_DIR, "latest.json")


def committed_is_seed() -> bool:
    """種子資料(合成)不應蓋掉真實值;偵測 latest.json 的 SEED 標記。"""
    try:
        with open(LATEST_JSON, encoding="utf-8") as fh:
            return "SEED" in str(json.load(fh).get("note", "")).upper()
    except Exception:
        return False

st.set_page_config(page_title="🐂🐻 美銀牛熊指標", page_icon="🐂",
                   layout="wide", initial_sidebar_state="expanded")
st.markdown("""<style>
  html, body, [class*="css"] { font-family:"Microsoft JhengHei","PingFang TC",sans-serif; }
  #MainMenu, footer { visibility:hidden; }
  .big { font-size:64px; font-weight:800; line-height:1; }
  .sig { font-size:22px; font-weight:700; }
  .muted { color:#888; font-size:13px; }
</style>""", unsafe_allow_html=True)


@st.cache_data(ttl=3600, show_spinner="計算牛熊指標中…")
def load_live():
    return ind.compute()


def load_committed():
    if not os.path.exists(HISTORY_CSV):
        return None
    try:
        return pd.read_csv(HISTORY_CSV, parse_dates=["date"]).set_index("date")
    except Exception:
        return None


def get_data(force_live):
    # 種子資料是合成的,不可當真實值顯示 → 一律即時計算
    if not force_live and not committed_is_seed():
        df = load_committed()
        if df is not None and len(df) > 5:
            stale = (datetime.utcnow().date() - df.index.max().date()) > timedelta(days=5)
            if not stale:
                return df, "GitHub Action 每日更新檔"
    tag = "即時市場資料回補" + ("(偵測到種子檔,改用真實資料)" if committed_is_seed() else "")
    return load_live(), tag


st.sidebar.title("🐂🐻 設定")
force_live = st.sidebar.toggle("即時重新計算(忽略快取檔)", value=False)
if st.sidebar.button("🔄 清除快取並重算"):
    st.cache_data.clear(); st.rerun()
st.sidebar.markdown("---")
st.sidebar.markdown("**高擬真版 v2**\n\n對應美銀 6 大支柱:資金流 / 避險基金部位(COT)/ "
                    "多頭部位(NAAIM)/ 市場廣度 / 信用利差 / 散戶情緒(AAII)+ 波動率 + 動能。\n\n"
                    "- **0–2** 極度恐慌→逆向**買進**\n- **8–10** 極度貪婪→逆向**賣出**\n\n"
                    "抓不到的來源會自動退出,權重重新分配。")

try:
    df, source_tag = get_data(force_live)
except Exception as exc:
    st.error(f"資料載入失敗:{exc}"); st.stop()

last = ind.latest(df); val = last["composite"]
active = ind.active_components(df) if hasattr(ind, "active_components") else \
    [k for k in ind.COMPONENT_LABELS if k in df.columns and df[k].notna().any()]

_aff = ind.load_affine() if hasattr(ind, "load_affine") else None
_aff_tag = f" · 已套用水位校準(a={_aff['a']}, b={_aff['b']})" if _aff else ""
st.title("🐂🐻 美銀牛熊指標(高擬真復刻版)")
st.caption(f"資料來源:{source_tag} · 最新日期 {last['date']} · "
           f"啟用成分 {len(active)}/{len(ind.COMPONENT_LABELS)}{_aff_tag}")


def gauge(value):
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=value, number={"font": {"size": 46}},
        gauge={"axis": {"range": [0, 10], "dtick": 1},
               "bar": {"color": "rgba(255,255,255,0.0)"},
               "steps": [{"range": [0, 2], "color": "#1b5e20"},
                         {"range": [2, 4], "color": "#388e3c"},
                         {"range": [4, 6], "color": "#9e9d24"},
                         {"range": [6, 8], "color": "#ef6c00"},
                         {"range": [8, 10], "color": "#b71c1c"}],
               "threshold": {"line": {"color": "white", "width": 5},
                             "thickness": 0.85, "value": value}}))
    fig.update_layout(height=300, margin=dict(t=20, b=10, l=30, r=30),
                      paper_bgcolor="rgba(0,0,0,0)", font_color="#fff")
    return fig


sig_color = "#26a69a" if val <= 2 else "#ef5350" if val >= 8 else "#ffd700"
c1, c2 = st.columns([1.1, 1])
with c1:
    st.plotly_chart(gauge(val), use_container_width=True)
with c2:
    st.markdown(f"<div class='muted'>綜合指數</div><div class='big' style='color:{sig_color}'>{val:.2f}</div>"
                f"<div class='sig' style='color:{sig_color}'>{last['signal']}</div>", unsafe_allow_html=True)
    if len(df) > 6:
        diff = val - df["composite"].iloc[-6]
        st.markdown(f"<div class='muted' style='margin-top:14px'>較一週前 "
                    f"{'▲' if diff>=0 else '▼'} {abs(diff):.2f}</div>", unsafe_allow_html=True)
    st.markdown("<div class='muted' style='margin-top:6px'>0–2 買進 ｜ 8–10 賣出</div>", unsafe_allow_html=True)

st.subheader("📈 近一年走勢")
h = go.Figure()
h.add_hrect(y0=0, y1=2, fillcolor="#26a69a", opacity=0.12, line_width=0)
h.add_hrect(y0=8, y1=10, fillcolor="#ef5350", opacity=0.12, line_width=0)
h.add_trace(go.Scatter(x=df.index, y=df["composite"], mode="lines",
            line=dict(color="#00d4aa", width=2.4), fill="tozeroy",
            fillcolor="rgba(0,212,170,0.08)"))
h.add_hline(y=2, line=dict(color="#26a69a", dash="dot"))
h.add_hline(y=8, line=dict(color="#ef5350", dash="dot"))
h.update_layout(height=380, margin=dict(t=20, b=20, l=10, r=10),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font_color="#ddd", yaxis=dict(range=[0, 10], gridcolor="#222"),
                xaxis=dict(gridcolor="#222"), showlegend=False)
st.plotly_chart(h, use_container_width=True)

st.subheader("🧩 成分分解(0–10,越高越貪婪)")
weights = last.get("weights", ind.DEFAULT_WEIGHTS)
cols = st.columns(4)
for i, k in enumerate(ind.COMPONENT_LABELS):
    v = last["components"].get(k)
    with cols[i % 4]:
        label = ind.COMPONENT_LABELS[k]
        if v is None:
            st.markdown(f"<div class='muted'>{label}</div>"
                        f"<div style='font-size:22px;color:#555'>—(來源無資料)</div>",
                        unsafe_allow_html=True)
            continue
        col = "#26a69a" if v <= 2 else "#ef5350" if v >= 8 else "#ffd700"
        st.markdown(f"<div class='muted'>{label} · 權重{weights.get(k,0)*100:.0f}%</div>"
                    f"<div style='font-size:28px;font-weight:700;color:{col}'>{v:.2f}</div>",
                    unsafe_allow_html=True)
        st.progress(min(v / 10, 1.0))

cf = go.Figure()
palette = ["#00d4aa", "#ffd700", "#ef5350", "#2196f3", "#9c27b0", "#ff9800", "#4caf50", "#e91e63"]
for c, k in zip(palette, active):
    cf.add_trace(go.Scatter(x=df.index, y=df[k], mode="lines",
                 name=ind.COMPONENT_LABELS[k], line=dict(color=c, width=1.5)))
cf.update_layout(height=380, margin=dict(t=20, b=20, l=10, r=10),
                 paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                 font_color="#ddd", yaxis=dict(range=[0, 10], gridcolor="#222"),
                 xaxis=dict(gridcolor="#222"),
                 legend=dict(orientation="h", y=-0.22, font=dict(size=10)))
st.plotly_chart(cf, use_container_width=True)

with st.expander("📋 原始資料 / 下載 CSV"):
    show = df.copy(); show.index = show.index.strftime("%Y-%m-%d")
    st.dataframe(show.iloc[::-1], use_container_width=True, height=300)
    st.download_button("⬇️ 下載一年數據 CSV", df.to_csv().encode("utf-8-sig"),
                       file_name="bull_bear_history.csv", mime="text/csv")

st.caption("⚠️ 公開資料高擬真復刻,非美銀官方數值,僅供研究參考,不構成投資建議。"
           "美銀官方用付費專有資料(EPFR 等),本版目標為走勢相關與訊號同步。")

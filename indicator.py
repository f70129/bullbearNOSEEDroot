"""
美銀牛熊指標(高擬真復刻版 v2) / BofA-style Bull & Bear Indicator — High Fidelity
==================================================================================

對應美銀 6 大支柱,改用更貼近的「公開免費」代理變數,並支援權重校準。

支柱 (component) ─ 對應美銀概念 ─ 免費資料來源
  1. flows      資金流(股/債/信用)     HYG/LQD 風險偏好比值動能
  2. positioning_hf  避險基金部位        CFTC COT 槓桿基金 S&P500 期貨淨多頭
  3. positioning_lo  多頭/法人部位        NAAIM 經理人曝險指數(週)
  4. breadth    市場廣度                 等權 RSP / 市值 SPY + 200MA
  5. credit     信用市場技術面           FRED 高收益債利差 BAMLH0A0HYM2(反向)
  6. sentiment  散戶/投資人情緒          AAII 多空差(週)
  + vol         波動率(風險胃納)        VIX(反向)
  + momentum    中期動能                 S&P500 125 日報酬

標準化:各成分 → 滾動百分位(252日)×10。
綜合:加權平均;抓不到的成分自動退出,權重於可用成分間重新正規化。
所有外部抓取皆 try/except,失敗回傳空序列 → 該成分以中性(5.0)或退出處理。

說明:美銀官方指標為付費專有(EPFR 等),本版無法逐點吻合,目標是「走勢高度相關、
買賣訊號區大致同步」。若提供 data/bofa_reference.csv 官方歷史值,可用 calibrate.py 校準權重。
"""

from __future__ import annotations

import io
import json
import os
import urllib.request
import zipfile

import numpy as np
import pandas as pd

# ── 設定 ────────────────────────────────────────────────────────────────────
PRICE_TICKERS = ["^GSPC", "^VIX", "HYG", "LQD", "TLT", "SPY", "RSP"]
FRED_HY_OAS = "BAMLH0A0HYM2"
ROLL_WIN = 252
HISTORY_DAYS = 252
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

# 預設權重(可被 data/weights.json 覆蓋;校準後自動更新)
DEFAULT_WEIGHTS = {
    "flows":          0.15,
    "positioning_hf": 0.15,
    "positioning_lo": 0.15,
    "breadth":        0.15,
    "credit":         0.15,
    "sentiment":      0.10,
    "vol":            0.075,
    "momentum":       0.075,
}

COMPONENT_LABELS = {
    "flows":          "資金流 (HYG/LQD)",
    "positioning_hf": "避險基金部位 (COT 槓桿基金)",
    "positioning_lo": "多頭部位 (NAAIM 曝險)",
    "breadth":        "市場廣度 (等權 vs 市值)",
    "credit":         "信用利差 (高收益債 反向)",
    "sentiment":      "散戶情緒 (AAII 多空差)",
    "vol":            "波動率 (VIX 反向)",
    "momentum":       "中期動能 (S&P500 125日)",
}

_HDR = {"User-Agent": "Mozilla/5.0"}


# ── 通用工具 ─────────────────────────────────────────────────────────────────
def _get(url: str, timeout: int = 40) -> bytes:
    req = urllib.request.Request(url, headers=_HDR)
    return urllib.request.urlopen(req, timeout=timeout).read()


def _roll_pctile(s: pd.Series, win: int = ROLL_WIN) -> pd.Series:
    return s.rolling(win, min_periods=max(40, win // 5)).apply(
        lambda x: pd.Series(x).rank(pct=True).iloc[-1], raw=False)


def _score(s: pd.Series, invert: bool = False, win: int = ROLL_WIN) -> pd.Series:
    if s is None or s.dropna().empty:
        return pd.Series(dtype=float)
    pct = _roll_pctile(s, win)
    if invert:
        pct = 1.0 - pct
    return (pct * 10).clip(0, 10)


def load_weights() -> dict:
    path = os.path.join(DATA_DIR, "weights.json")
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                w = json.load(fh)
            return {k: float(w.get(k, DEFAULT_WEIGHTS[k])) for k in DEFAULT_WEIGHTS}
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] weights.json 讀取失敗,改用預設: {exc!r}")
    return dict(DEFAULT_WEIGHTS)


def load_affine() -> dict | None:
    """讀取仿射校準 data/affine.json {"a":..,"b":..};用於把整體水位對齊官方值。"""
    path = os.path.join(DATA_DIR, "affine.json")
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                a = json.load(fh)
            return {"a": float(a.get("a", 1.0)), "b": float(a.get("b", 0.0))}
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] affine.json 讀取失敗: {exc!r}")
    return None


# ── 資料抓取 ─────────────────────────────────────────────────────────────────
def fetch_prices(period: str = "3y") -> pd.DataFrame:
    import yfinance as yf
    raw = yf.download(PRICE_TICKERS, period=period, interval="1d",
                      auto_adjust=True, progress=False, threads=True)
    close = raw["Close"].copy() if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]].copy()
    return close.dropna(how="all").ffill()


def fetch_fred(series_id: str, start: str = "2018-01-01") -> pd.Series:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd={start}"
    try:
        df = pd.read_csv(io.BytesIO(_get(url))); df.columns = ["date", "value"]
        df["date"] = pd.to_datetime(df["date"])
        s = pd.to_numeric(df.set_index("date")["value"], errors="coerce").dropna()
        s.name = series_id
        return s
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] FRED {series_id} 失敗: {exc!r}")
        return pd.Series(dtype=float)


def fetch_cot_sp500_lev() -> pd.Series:
    """CFTC COT 槓桿基金在 E-mini S&P500 的淨多頭 %OI(週)。用 Socrata API。"""
    base = "https://publicreporting.cftc.gov/resource/gpe5-46if.csv"
    url = (base + "?$limit=600&$order=report_date_as_yyyy_mm_dd"
           "&$where=" + urllib.request.quote(
               "contract_market_name like 'E-MINI S&P 500%'"))
    try:
        df = pd.read_csv(io.BytesIO(_get(url)))
        df.columns = [c.lower() for c in df.columns]
        dcol = next(c for c in df.columns if "report_date" in c)
        lcol = next(c for c in df.columns if "lev_money_positions_long" in c)
        scol = next(c for c in df.columns if "lev_money_positions_short" in c)
        ocol = next(c for c in df.columns if c.startswith("open_interest"))
        df[dcol] = pd.to_datetime(df[dcol])
        for c in (lcol, scol, ocol):
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df = df.dropna(subset=[dcol, lcol, scol, ocol]).set_index(dcol).sort_index()
        net = (df[lcol] - df[scol]) / df[ocol].replace(0, np.nan)
        net.name = "cot_lev_net"
        return net.dropna()
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] CFTC COT 失敗: {exc!r}")
        return pd.Series(dtype=float)


def fetch_naaim() -> pd.Series:
    """NAAIM 經理人曝險指數(週)。嘗試官方頁面表格,失敗回空。"""
    candidates = [
        "https://naaim.org/programs/naaim-exposure-index/",
    ]
    for url in candidates:
        try:
            html = _get(url).decode("utf-8", "ignore")
            tables = pd.read_html(io.StringIO(html))
            for t in tables:
                cols = [str(c).lower() for c in t.columns]
                date_i = next((i for i, c in enumerate(cols) if "date" in c), None)
                exp_i = next((i for i, c in enumerate(cols)
                              if "mean" in c or "exposure" in c or "naaim" in c), None)
                if date_i is None or exp_i is None:
                    continue
                s = t.iloc[:, [date_i, exp_i]].copy()
                s.columns = ["date", "exposure"]
                s["date"] = pd.to_datetime(s["date"], errors="coerce")
                s["exposure"] = pd.to_numeric(s["exposure"], errors="coerce")
                s = s.dropna().set_index("date")["exposure"].sort_index()
                if len(s) >= 8:
                    s.name = "naaim"
                    return s
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] NAAIM {url} 失敗: {exc!r}")
    return pd.Series(dtype=float)


def fetch_aaii() -> pd.Series:
    """AAII 散戶多空差 = bullish - bearish(週)。嘗試官方 xls,失敗回空。"""
    url = "https://www.aaii.com/files/surveys/sentiment.xls"
    try:
        raw = _get(url)
        df = pd.read_excel(io.BytesIO(raw), skiprows=3)
        df.columns = [str(c).strip().lower() for c in df.columns]
        dcol = next(c for c in df.columns if "date" in c)
        bull = next(c for c in df.columns if c.startswith("bull"))
        bear = next(c for c in df.columns if c.startswith("bear"))
        df[dcol] = pd.to_datetime(df[dcol], errors="coerce")
        for c in (bull, bear):
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df = df.dropna(subset=[dcol, bull, bear]).set_index(dcol).sort_index()
        spread = (df[bull] - df[bear])
        spread.name = "aaii_spread"
        return spread
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] AAII 失敗: {exc!r}")
        return pd.Series(dtype=float)


# ── 主計算 ───────────────────────────────────────────────────────────────────
def compute(period: str = "3y", tail_days: int | None = HISTORY_DAYS) -> pd.DataFrame:
    px = fetch_prices(period=period)
    idx = px.index
    hy = fetch_fred(FRED_HY_OAS)
    cot = fetch_cot_sp500_lev()
    naaim = fetch_naaim()
    aaii = fetch_aaii()

    def _daily(s):  # 週資料對齊日線並前向填補
        return s.reindex(idx, method=None).ffill() if not s.empty else pd.Series(dtype=float)

    scores = {}

    # 1) 資金流:HYG/LQD 20日動能
    scores["flows"] = _score((px["HYG"] / px["LQD"]).pct_change(20))

    # 2) 避險基金部位:COT 槓桿基金淨多頭 %OI(淨多頭高=貪婪)
    scores["positioning_hf"] = _score(_daily(cot))

    # 3) 多頭部位:NAAIM 曝險(高=貪婪)
    scores["positioning_lo"] = _score(_daily(naaim))

    # 4) 市場廣度:等權 RSP / 市值 SPY 比值動能 + 200MA 乖離
    if "RSP" in px.columns and px["RSP"].notna().any():
        bre1 = _score((px["RSP"] / px["SPY"]).pct_change(20))
    else:
        bre1 = pd.Series(dtype=float)
    ma200 = px["^GSPC"].rolling(200, min_periods=100).mean()
    bre2 = _score(px["^GSPC"] / ma200 - 1.0)
    scores["breadth"] = pd.concat([bre1, bre2], axis=1).mean(axis=1, skipna=True) \
        if not bre1.empty else bre2

    # 5) 信用利差(反向);FRED 失敗時用 HYG/LQD 價格比替代
    if not hy.empty:
        scores["credit"] = _score(_daily(hy), invert=True)
    else:
        scores["credit"] = _score(px["HYG"] / px["LQD"])

    # 6) 散戶情緒:AAII 多空差(高=貪婪)
    scores["sentiment"] = _score(_daily(aaii))

    # + 波動率(反向)
    scores["vol"] = _score(px["^VIX"], invert=True)
    # + 中期動能
    scores["momentum"] = _score(px["^GSPC"].pct_change(125))

    out = pd.DataFrame(index=idx)
    for k, s in scores.items():
        out[k] = s if (s is not None and not s.empty) else np.nan

    # 加權合成(只用可用成分,權重重新正規化)
    weights = load_weights()
    avail = [k for k in DEFAULT_WEIGHTS if k in out.columns and out[k].notna().any()]
    w = np.array([weights[k] for k in avail], dtype=float)
    w = w / w.sum() if w.sum() > 0 else w
    comp = out[avail].mul(w, axis=1).sum(axis=1, skipna=True)
    # 某些日缺成分時用可用權重比例還原
    wsum = out[avail].notna().mul(w, axis=1).sum(axis=1)
    out["composite"] = (comp / wsum.replace(0, np.nan)).clip(0, 10)

    # 仿射校準:把整體水位對齊官方值(若有 affine.json)
    aff = load_affine()
    if aff is not None:
        out["composite"] = (aff["a"] * out["composite"] + aff["b"]).clip(0, 10)

    def _sig(v):
        if pd.isna(v): return ""
        if v <= 2: return "極度恐慌 · 逆向買進"
        if v >= 8: return "極度貪婪 · 逆向賣出"
        if v < 4: return "偏空"
        if v > 6: return "偏多"
        return "中性"

    out["signal"] = out["composite"].apply(_sig)
    out = out.dropna(subset=["composite"])
    if tail_days is not None:
        out = out.tail(tail_days)
    out = out.round(3)
    out.index.name = "date"
    return out


def active_components(df: pd.DataFrame) -> list[str]:
    return [k for k in COMPONENT_LABELS if k in df.columns and df[k].notna().any()]


def latest(df: pd.DataFrame) -> dict:
    row = df.iloc[-1]
    comps = {k: (float(row[k]) if pd.notna(row[k]) else None)
             for k in COMPONENT_LABELS if k in df.columns}
    return {
        "date": df.index[-1].strftime("%Y-%m-%d"),
        "composite": float(row["composite"]),
        "signal": row["signal"],
        "components": comps,
        "weights": load_weights(),
    }


if __name__ == "__main__":
    d = compute()
    print(d.tail())
    print("latest:", json.dumps(latest(d), ensure_ascii=False, indent=2))

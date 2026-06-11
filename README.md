# 🐂🐻 美銀牛熊指標(高擬真復刻版 v2) · Bull & Bear Indicator

以**免費公開資料**高擬真復刻 Bank of America(美銀)Bull & Bear Indicator,
0–10 綜合市場情緒量表,部署於 **Streamlit Cloud**,**GitHub Actions 每日自動更新**,
保留**最近一整年**數據與圖表,並支援**權重校準**。

> ⚠️ 美銀官方指標為付費 / 專有資料(EPFR 基金流向、避險基金部位…),無法逐點復刻。
> 本版以公開代理變數逼近,目標為**走勢高度相關、買賣訊號區同步**,非官方數值,不構成投資建議。

---

## 📊 指標解讀

| 區間 | 含義 | 操作意涵(逆向) |
|------|------|------------------|
| **0–2** | 極度恐慌 | 逆向 **買進** |
| 2–4 | 偏空 | — |
| 4–6 | 中性 | — |
| 6–8 | 偏多 | — |
| **8–10** | 極度貪婪 | 逆向 **賣出** |

### 對應美銀 6 大支柱(+2 風險面)的成分與免費來源
| 成分 | 對應美銀概念 | 免費資料來源 |
|------|--------------|--------------|
| 資金流 | 股/債/信用 fund flows | HYG/LQD 風險偏好比值動能 |
| 避險基金部位 | hedge fund positioning | **CFTC COT** 槓桿基金 S&P500 期貨淨多頭 |
| 多頭部位 | long-only positioning | **NAAIM** 經理人曝險指數(週) |
| 市場廣度 | market breadth | 等權 RSP / 市值 SPY + 200MA |
| 信用利差 | credit technicals | **FRED** 高收益債利差 `BAMLH0A0HYM2`(反向) |
| 散戶情緒 | investor sentiment | **AAII** 多空差(週) |
| 波動率 | 風險胃納 | VIX(反向) |
| 中期動能 | momentum | S&P500 125 日報酬 |

每個成分標準化為「滾動百分位(252日)×10」;綜合為**加權平均**。
**抓不到的來源會自動退出,權重於可用成分間重新正規化**,App 永不崩。

---

## 📁 專案結構
```
bull-bear/
├── app.py            # Streamlit 看板
├── indicator.py      # 指標計算核心(8 成分 + 加權)
├── update_data.py    # 每日更新(合併歷史,自我修復)
├── calibrate.py      # 權重校準(選用)
├── requirements.txt
├── .streamlit/config.toml
└── data/
    ├── history.csv   # 最近一年數據(自動更新)
    ├── latest.json   # 最新摘要 + 當前權重
    ├── weights.json  # 校準後權重(選用;有則自動採用)
    └── bofa_reference.csv  # 你提供的官方/參考歷史值(選用)
.github/workflows/bull-bear-update.yml
```

---

## 🚀 部署到 Streamlit Cloud(3 步驟)
1. 把本 repo push 到 GitHub。
2. <https://share.streamlit.io> → **New app** → 選 repo / 分支。
3. **Main file path** 填 `bull-bear/app.py` → **Deploy**。

> Streamlit Cloud 與 GitHub Actions 網路開放,可正常抓 Yahoo / FRED / CFTC /(嘗試)NAAIM / AAII。

---

## 🤖 自動更新
`.github/workflows/bull-bear-update.yml` 每天 **UTC 23:00(台灣 07:00)**:
1.(若有參考值)`calibrate.py` 校準權重 → `weights.json`
2. `update_data.py` 重算近一年並與既有歷史合併
3. commit & push 回 repo

**啟用**:repo → **Settings → Actions → General → Workflow permissions** 設
**Read and write**;到 **Actions** 分頁可手動 **Run workflow**。

---

## 🎯 校準(讓數值貼近美銀)
1. 把美銀官方(或任何參考)歷史值放成 `bull-bear/data/bofa_reference.csv`:
   ```csv
   date,value
   2026-06-09,8.7
   2026-06-02,8.4
   ```
2. 執行:`cd bull-bear && python calibrate.py`
3. 依樣本數自動選策略:
   - **1 點**:純平移,直接把那天對齊官方值 → `affine.json`(例:6/9 我們 6.98 → 校準後 8.70)
   - **2–11 點**:仿射 `a*x+b` 對齊整體水位 → `affine.json`
   - **≥12 點**:非負最小平方回歸各成分權重 → `weights.json`,並印出**相關係數/RMSE**
4. `compute()` 之後會自動採用,App 標題也會顯示已套用校準。

> ⚠️ 校準只調整「水位/加權」,不改成分定義;能讓買賣訊號區與官方同步,
> 但仍非官方逐點值。官方點越多、越新,校準越準。

---

## 🖥️ 本機執行
```bash
cd bull-bear
pip install -r requirements.txt
streamlit run app.py        # 看板
python update_data.py       # 手動更新 data/
python calibrate.py         # 權重校準(需 data/bofa_reference.csv)
```

## 📝 備註
- `data/` 內附**種子資料(SEED)**僅供畫面預覽;App 會**自動偵測 SEED 標記並改用即時真實計算**(不會顯示合成數字),首次 Action 後以**真實市場數據**覆蓋。
- NAAIM / AAII 無穩定免費 API,抓取較脆弱;失敗時該成分自動退出,不影響其他成分與整體運作。
- 想要 100% 官方數值,需訂閱來源(EPFR / 彭博終端機 `BULLBEAR`),再走「方案 A 接真值」。

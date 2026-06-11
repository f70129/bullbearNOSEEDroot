"""
每日資料更新腳本(由 GitHub Action 執行)
=========================================
1. 用 indicator.compute() 重新計算最近一年的牛熊指標
2. 與既有 data/history.csv 合併(累積長期紀錄,自我修復)
3. 寫回 data/history.csv 與 data/latest.json

由於 compute() 會用市場歷史「回補」整年,每次執行都會重建近一年,
再與舊紀錄 union,因此資料具自我修復能力(缺漏會自動補上)。
"""

import json
import os
from datetime import datetime, timezone

import pandas as pd

import indicator as ind

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
HISTORY_CSV = os.path.join(DATA_DIR, "history.csv")
LATEST_JSON = os.path.join(DATA_DIR, "latest.json")


def main() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)

    fresh = ind.compute()  # index=date

    # 合併既有紀錄
    if os.path.exists(HISTORY_CSV):
        try:
            old = pd.read_csv(HISTORY_CSV, parse_dates=["date"]).set_index("date")
            merged = pd.concat([old, fresh])
            merged = merged[~merged.index.duplicated(keep="last")].sort_index()
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] 讀取舊檔失敗,改用全新資料: {exc!r}")
            merged = fresh
    else:
        merged = fresh

    merged.to_csv(HISTORY_CSV)
    print(f"[ok] 寫入 {HISTORY_CSV}: {len(merged)} 列, "
          f"{merged.index.min().date()} ~ {merged.index.max().date()}")

    latest = ind.latest(merged)
    latest["updated_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    with open(LATEST_JSON, "w", encoding="utf-8") as fh:
        json.dump(latest, fh, ensure_ascii=False, indent=2)
    print(f"[ok] 寫入 {LATEST_JSON}: {latest}")


if __name__ == "__main__":
    main()

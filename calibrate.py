"""
權重 / 水位校準 — Calibration
=============================
把美銀官方(或任何參考)歷史值放成 data/bofa_reference.csv:

    date,value
    2026-06-09,8.7
    2026-06-02,8.4
    ...

策略(依樣本數自動選擇):
  • >= 12 筆 : 非負最小平方回歸「各成分權重」→ data/weights.json
  • 2 ~ 11 筆: 仿射對齊 composite = a*x + b → data/affine.json(把整體水位拉到官方值)
  • 1 筆     : 純平移 b = 官方 - 目前 → data/affine.json(a=1)

兩種檔案 compute() 都會自動採用(weights 改加權,affine 改水位)。
"""

import json
import os

import numpy as np
import pandas as pd

import indicator as ind

REF_CSV = os.path.join(ind.DATA_DIR, "bofa_reference.csv")
WEIGHTS_JSON = os.path.join(ind.DATA_DIR, "weights.json")
AFFINE_JSON = os.path.join(ind.DATA_DIR, "affine.json")
MIN_FOR_WEIGHTS = 12


def _nnls(A, b):
    try:
        from scipy.optimize import nnls
        x, _ = nnls(A, b)
        return x
    except Exception:  # noqa: BLE001
        x, *_ = np.linalg.lstsq(A, b, rcond=None)
        return np.clip(x, 0, None)


def main() -> None:
    if not os.path.exists(REF_CSV):
        print(f"[skip] 找不到 {REF_CSV};放入官方/參考歷史值後再執行。")
        return

    ref = pd.read_csv(REF_CSV)
    ref.columns = [c.lower() for c in ref.columns]
    ref["date"] = pd.to_datetime(ref["date"])
    ref = ref.dropna().set_index("date")["value"].sort_index()

    # 取「未校準」的成分與 composite(避免拿已校準值再校準)
    for f in (WEIGHTS_JSON, AFFINE_JSON):
        if os.path.exists(f):
            os.remove(f)
    df = ind.compute(period="5y", tail_days=None)
    comps = ind.active_components(df)

    rows, comp_x, ys = [], [], []
    for d, y in ref.items():
        sub = df[df.index <= d]
        if sub.empty:
            continue
        rows.append(sub.iloc[-1][comps].values)
        comp_x.append(float(sub.iloc[-1]["composite"]))
        ys.append(float(y))
    n = len(ys)
    if n == 0:
        print("[error] 參考日期與資料無交集,放棄。")
        return
    b = np.array(ys)

    if n >= MIN_FOR_WEIGHTS:
        A = np.nan_to_num(np.array(rows, dtype=float), nan=5.0)
        w = _nnls(A, b)
        if w.sum() <= 0:
            print("[error] 權重全 0,放棄。"); return
        w = w / w.sum()
        weights = {k: 0.0 for k in ind.DEFAULT_WEIGHTS}
        for k, val in zip(comps, w):
            weights[k] = round(float(val), 4)
        json.dump(weights, open(WEIGHTS_JSON, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        pred = A @ w
        corr = np.corrcoef(pred, b)[0, 1]
        print(f"[ok] 權重校準 → {WEIGHTS_JSON}  n={n}  相關={corr:.3f}  "
              f"RMSE={np.sqrt(np.mean((pred-b)**2)):.3f}")
        print("     ", json.dumps(weights, ensure_ascii=False))
    else:
        x = np.array(comp_x)
        if n == 1:
            a, bb = 1.0, float(b[0] - x[0])
        else:
            a, bb = np.polyfit(x, b, 1)
            a = float(np.clip(a, 0.2, 5.0))
        aff = {"a": round(float(a), 4), "b": round(float(bb), 4)}
        json.dump(aff, open(AFFINE_JSON, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        pred = np.clip(a * x + bb, 0, 10)
        rmse = float(np.sqrt(np.mean((pred - b) ** 2)))
        print(f"[ok] 水位校準(仿射)→ {AFFINE_JSON}  n={n}  "
              f"a={aff['a']} b={aff['b']}  RMSE={rmse:.3f}")
        print(f"     例:原 composite {x[-1]:.2f} → 校準後 "
              f"{np.clip(a*x[-1]+bb,0,10):.2f}(官方 {b[-1]:.2f})")


if __name__ == "__main__":
    main()

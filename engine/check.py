# -*- coding: utf-8 -*-
"""同律计划 · 不变量自检（纯标准库）

它检验的不是"代码有没有 bug"，是"模型有没有自相矛盾"。
任何一条 FAIL，说明公式或实现与库内结论冲突，必须先修再谈赚钱。

用法：python engine/check.py
退出码：0 全过；1 有失败
"""
import os
import sys
from math import inf, log, ceil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from model import (  # noqa: E402
    pi_of, pi_amortized, cycles, w_star, kelly,
    usable_fraction, ruin_prob, geo_growth, cash_runway,
)

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))


def main():
    # 1 固定成本越高，小本金越难；大本金趋近 a-c
    a, c = 2.0, 1.0            # a-c = 1.0 (100%)
    bC = 7.5
    check("pi(W) 随 W 单调上升（b_C>0）",
          pi_of(15, a, c, 0, bC) < pi_of(150, a, c, 0, bC) < pi_of(1e9, a, c, 0, bC))
    check("pi(W->inf) -> a-c",
          abs(pi_of(1e12, a, c, 0, bC) - (a - c)) < 1e-6)
    check("W=15,b_C=7.5,pi0=100% 时仍为正", pi_of(15, a, c, 0, bC) > 0,
          "pi=%.3f" % pi_of(15, a, c, 0, bC))
    check("W=5,b_C=7.5 时转负（墙下）", pi_of(5, a, c, 0, bC) < 0,
          "pi=%.3f" % pi_of(5, a, c, 0, bC))

    # 2 W* 的定义：在 W* 处 pi 恰好为 0
    p0 = 0.5
    ws = w_star(7.5, p0)
    check("W* = b_C/pi0 = 15", abs(ws - 15.0) < 1e-9, "W*=%.3f" % ws)
    check("pi(W*) 约等于 0", abs(pi_of(ws, 1.0, 0.5, 0, 7.5)) < 1e-9)

    # 3 周期数：(1+pi)^n 必须 >= m，且 n 是最小的
    for m, p in [(10, 0.05), (10, 0.5), (100, 0.2), (10000, 0.5)]:
        n = cycles(m, p)
        check("n 足够达到 %dx @ %.0f%%" % (m, p * 100), (1 + p) ** n >= m - 1e-9,
              "n=%d, 结果=%.2f" % (n, (1 + p) ** n))
        check("n 是最小的 %dx @ %.0f%%" % (m, p * 100),
              n == 0 or (1 + p) ** (n - 1) < m, "n=%d" % n)
    check("pi<=0 时周期为 inf", cycles(10, 0.0) == inf)
    check("10 倍 @50% = 6 周期（v0.1.66 更正后的值）", cycles(10, 0.5) == 6,
          "n=%d" % cycles(10, 0.5))

    # 4 摊薄：N 越大，b_C 越不重要
    v1 = pi_amortized(15, 1.0, 0.0, F=70.0, N=1)
    v2 = pi_amortized(15, 1.0, 0.0, F=70.0, N=10)
    v3 = pi_amortized(15, 1.0, 0.0, F=70.0, N=10 ** 6)
    check("F=70 时第一份严重亏损", v1 < 0, "pi=%.2f" % v1)
    check("N 增大后恢复", v1 < v2 < v3, "%.2f < %.2f < %.2f" % (v1, v2, v3))
    check("N->inf 时 pi -> a-c", abs(v3 - 1.0) < 1e-3, "pi=%.4f" % v3)

    # 5 凯利：f* 与打折
    fs = kelly(0.1, 0.04)
    check("f* = mu/var = 2.5", abs(fs - 2.5) < 1e-9)
    check("实用 f <= f*/2 且 <= 1", usable_fraction(0.1, 0.04) <= 1.0)
    check("负优势 -> f=0", usable_fraction(-0.05, 0.04) == 0.0)

    # 6 破产单调性：同样的下注比例，有优势 vs 无优势
    p_over = ruin_prob(1.0, 1.0, 0.0, 0.20, 200, trials=4000)   # 无优势，全仓
    p_tiny = ruin_prob(1.0, 0.01, 0.0, 0.20, 200, trials=4000)  # 无优势，极小仓
    p_edge = ruin_prob(1.0, 1.0, 0.30, 0.20, 200, trials=4000)  # 大优势，全仓
    check("无优势+全仓 -> 多数被吸收", p_over > 0.5, "%.3f" % p_over)
    check("无优势+极小仓 -> 几乎不出局", p_tiny < 0.05, "%.3f" % p_tiny)
    check("有优势时全仓的破产率更低", p_edge < p_over,
          "%.3f vs %.3f" % (p_edge, p_over))

    # 7 波动拖累：同样算术均值，波动越大几何增长越低
    g_low = geo_growth(0.5, 0.05, 0.05, trials=8000)
    g_high = geo_growth(0.5, 0.05, 0.40, trials=8000)
    check("波动拖累：高波动 g 更低", g_high < g_low, "%.4f vs %.4f" % (g_high, g_low))

    # 8 现金跑道
    check("跑道 = 现金/月净流出", abs(cash_runway(150, -30) - 5.0) < 1e-9)
    check("净流入时跑道为 inf", cash_runway(150, 10) == inf)

    # 9 一组真实量级：15 元 + F<=7.5 -> 段 I 尾部
    check("15 元在 b_C=7.5,pi0=50% 处恰好在墙上", abs(pi_of(15, 1.0, 0.5, 0, 7.5)) < 1e-9)
    check("15 元在 b_C=8 处已在墙下", pi_of(15, 1.0, 0.5, 0, 8.0) < 0,
          "pi=%.4f" % pi_of(15, 1.0, 0.5, 0, 8.0))

    # 输出
    print("=" * 62)
    print("同律计划 · 不变量自检")
    print("=" * 62)
    fails = 0
    for name, ok, detail in RESULTS:
        if not ok:
            fails += 1
        print("[%s] %s%s" % ("PASS" if ok else "FAIL", name,
                             ("  <- " + detail) if detail else ""))
    print("-" * 62)
    print("共 %d 条，失败 %d 条" % (len(RESULTS), fails))
    print("=" * 62)
    return 1 if fails else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())

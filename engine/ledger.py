# -*- coding: utf-8 -*-
"""同律计划 · 账本与三道门（纯标准库）

账本格式（data/ledger.csv），每行 = 一个周期：
    date,pool,W,revenue,cost,build,n_sold,note

    W       本周起投入的本金（元）
    revenue 本周收到的钱（元，真实到账）
    cost    本周花掉的钱（元，不含本金）
    build   一次性建设成本（元，只在第一笔填；以后填 0）
    n_sold  本周卖出的份数

三道门（来自 v0.1.64 §4.2）：
    V1  跑通一次闭环：有记录 且 a > c
    V2  a 是常数：记录 >= 10 且 a 的标准差 < 50% 均值
    V3  标度不变：把记录按 W 分成低/高两半，|a_hi - a_lo| / a_lo < 30%

退出码：0=继续  1=修  2=判废（可直接用于脚本/定时任务）
"""
import csv
import os
import sys
from math import inf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from model import pi_of, pi_amortized, cycles, w_star  # noqa: E402

FIELDS = ["date", "pool", "W", "revenue", "cost", "build", "n_sold", "note"]

CONTINUE, FIX, KILL = 0, 1, 2


def _f(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def load(path):
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            if not r or not r.get("date"):
                continue
            rows.append({
                "date": r.get("date", "").strip(),
                "pool": r.get("pool", "").strip(),
                "W": _f(r.get("W")),
                "revenue": _f(r.get("revenue")),
                "cost": _f(r.get("cost")),
                "build": _f(r.get("build")),
                "n_sold": int(_f(r.get("n_sold"))),
                "note": (r.get("note") or "").strip(),
            })
    return rows


def summary(rows):
    """整本账的核心量：a、c、F、N、pi0。"""
    W = sum(r["W"] for r in rows)
    rev = sum(r["revenue"] for r in rows)
    cost = sum(r["cost"] for r in rows)
    build = sum(r["build"] for r in rows)
    n = sum(r["n_sold"] for r in rows)
    a = (rev / W) if W > 0 else 0.0
    c = (cost / W) if W > 0 else 0.0
    return {
        "records": len(rows),
        "W": W, "revenue": rev, "cost": cost, "build": build, "n_sold": n,
        "a": a, "c": c, "pi0": a - c,
        "profit": rev - cost - build,
        "per_sale_bC": (build / n) if n > 0 else inf,
    }


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _stdev(xs):
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return (sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5


def gate_v1(rows, s):
    if s["records"] < 1:
        return False, "无记录：先跑通一次真实的收付款"
    if s["a"] <= s["c"]:
        return False, "a <= c：比例项本身不赚钱（不是规模问题，是模型问题）"
    if s["revenue"] <= 0:
        return False, "有成本无收入：这不是闭环，是消耗"
    return True, "闭环成立：a=%.3f > c=%.3f，pi0=%.1f%%" % (s["a"], s["c"], s["pi0"] * 100)


def gate_v2(rows, s):
    if s["records"] < 10:
        return False, "记录 %d 条 < 10：a 还只是运气，不是常数" % s["records"]
    per = []
    for r in rows:
        if r["W"] > 0:
            per.append(r["revenue"] / r["W"])
    sd = _stdev(per)
    m = _mean(per)
    if m <= 0:
        return False, "a 均值 <= 0"
    cv = sd / m
    if cv >= 0.5:
        return False, "a 的变异系数 %.0f%% >= 50%%：a 不是常数" % (cv * 100)
    return True, "a 稳定：变异系数 %.0f%% < 50%%" % (cv * 100)


def gate_v3(rows, s):
    """标度不变检验：低 W 段 vs 高 W 段（至少各 3 条，且 W 必须真的变过）。"""
    usable = [r for r in rows if r["W"] > 0]
    if len(usable) < 6:
        return False, "有效记录 %d < 6：无法做标度检验" % len(usable)
    usable.sort(key=lambda r: r["W"])
    w_lo_min = usable[0]["W"]
    w_hi_max = usable[-1]["W"]
    if w_hi_max < w_lo_min * 1.5:
        return False, ("本金没有放大过（%.2f -> %.2f 少于 1.5 倍）："
                       "V3 测不了——标度不变只能靠「真的换了数字」来证伪" % (w_lo_min, w_hi_max))
    half = len(usable) // 2
    lo, hi = usable[:half], usable[half:]
    a_lo = sum(r["revenue"] for r in lo) / sum(r["W"] for r in lo)
    a_hi = sum(r["revenue"] for r in hi) / sum(r["W"] for r in hi)
    if a_lo <= 0:
        return False, "低本金段 a <= 0：还在墙下，谈不上标度"
    dev = abs(a_hi - a_lo) / a_lo
    if dev >= 0.30:
        return False, "放大后 a 偏差 %.0f%% >= 30%%：标度不变不成立（有隐藏 b_C 或撞了容量 K）" % (dev * 100)
    return True, "标度不变成立：低段 a=%.3f / 高段 a=%.3f，偏差 %.0f%%" % (a_lo, a_hi, dev * 100)


def compound_state(rows, s):
    """复利是否真的启动：W 有没有跟着利润长。

    W(n+1) = W(n)(1+pi) 的前提是「利润留在分母里」。
    若利润被取走，pi 再高，W 也不动 —— 那不是复利，是工资。
    """
    if s["records"] < 3 or s["profit"] <= 0:
        return None, "样本不足或无利润"
    head = [r["W"] for r in rows[:3] if r["W"] > 0]
    tail = [r["W"] for r in rows[-3:] if r["W"] > 0]
    if not head or not tail:
        return None, "W 记录不足"
    w_head = sum(head) / len(head)
    w_tail = sum(tail) / len(tail)
    if w_tail <= w_head * 1.10:
        return False, ("利润 %.2f 元已入账，但 W 从 %.2f 变成 %.2f："
                       "利润没有留在分母里，复利未启动（你赚的是工资，不是资本）"
                       % (s["profit"], w_head, w_tail))
    return True, "W 随利润增长（%.2f -> %.2f）：复利在跑" % (w_head, w_tail)


def verdict(rows, s, v1, v2, v3, msgs):
    if s["records"] < 1:
        return KILL, "空账本：先跑 V1，不要谈规模"
    if not v1:
        return FIX, "V1 未过 —— " + msgs[0] + "；先修模型（a/c），不要放大"
    if not v2:
        return CONTINUE, "V1 已过，V2 未过 —— " + msgs[1] + "；此阶段不许加钱"
    if not v3:
        return FIX, "V2 已过但 V3 未过 —— " + msgs[2] + "；回设计，不许靠加钱解决"
    return CONTINUE, "V1/V2/V3 全过：可进入 V4（换池子），此时才允许谈规模"


def report(rows, path, out=sys.stdout):
    s = summary(rows)
    v1, m1 = gate_v1(rows, s)
    v2, m2 = gate_v2(rows, s)
    v3, m3 = gate_v3(rows, s)
    code, mv = verdict(rows, s, v1, v2, v3, (m1, m2, m3))
    comp_ok, comp_msg = compound_state(rows, s)

    w = out.write
    w("=" * 62 + "\n")
    w("同律计划 · 账本报告   %s\n" % path)
    w("=" * 62 + "\n")
    w("记录 %d 条 | 累计本金 W=%.2f | 收入 %.2f | 费用 %.2f | 建设 F=%.2f\n"
      % (s["records"], s["W"], s["revenue"], s["cost"], s["build"]))
    w("a=%.4f  c=%.4f  pi0=%.2f%%  净额=%.2f  已卖 %d 份  每份摊 F=%.2f\n"
      % (s["a"], s["c"], s["pi0"] * 100, s["profit"], s["n_sold"], s["per_sale_bC"]))
    if s["W"] > 0:
        w("当前 W 下 pi(W)=%.2f%%   达到 10 倍需 %s 个周期\n"
          % (pi_of(s["W"], s["a"], s["c"], 0.0, s["build"]) * 100,
             _fmt_cycles(cycles(10, pi_of(s["W"], s["a"], s["c"], 0.0, s["build"])))))
        w("平台区下界 W*=%.2f（低于此值 pi<0）\n" % w_star(s["build"], s["pi0"]) if s["pi0"] > 0 else "")
    w("-" * 62 + "\n")
    for tag, ok, msg in (("V1", v1, m1), ("V2", v2, m2), ("V3", v3, m3)):
        w("[%s] %s  %s\n" % ("PASS" if ok else "FAIL", tag, msg))
    if comp_ok is None:
        w("[SKIP] 复利  %s\n" % comp_msg)
    else:
        w("[%s] 复利  %s\n" % ("PASS" if comp_ok else "WARN", comp_msg))
    w("-" * 62 + "\n")
    w("判定：%s\n" % {CONTINUE: "继续", FIX: "修", KILL: "判废"}[code])
    w("理由：%s\n" % mv)
    w("=" * 62 + "\n")
    return code


def _fmt_cycles(n):
    return "∞" if n == inf else str(n)


def main(argv):
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = argv[1] if len(argv) > 1 else os.path.join(base, "data", "ledger.csv")
    rows = load(path)
    return report(rows, path)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main(sys.argv))

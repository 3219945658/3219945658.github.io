# -*- coding: utf-8 -*-
"""同律计划 · 标度不变模型（纯标准库，零第三方依赖）

公式全部来自库内：
    v0.1.64  R = a*W + b_R ,  C = c*W + b_C ,  pi(W) = (a-c) + (b_R-b_C)/W
    v0.1.65  W* = b_C / pi0 ;  n = ln(m)/ln(1+pi)
    v0.1.66  b_C(每份) = F / N
    v0.1.67  无人化 = 把 b_labor 换成一次性 F，靠 N 摊薄

本模块只做计算，不做任何判断。判断在 ledger.py 的门里。
"""
from math import log, ceil, inf, sqrt
import random

__all__ = [
    "pi_of", "pi_amortized", "cycles", "w_star", "kelly",
    "usable_fraction", "ruin_prob", "geo_growth", "cash_runway",
]


def pi_of(W, a, c, b_R=0.0, b_C=0.0):
    """连续经营：一周期利润率。W 为本金。"""
    if W <= 0:
        raise ValueError("W 必须 > 0")
    return (a - c) + (b_R - b_C) / W


def pi_amortized(W, a, c, F=0.0, N=1, b_R=0.0):
    """每份摊薄：F 为一次性建设成本，N 为累计份数。

    N=1 时，第一份必须自己吃掉全部 F —— 所以"第一份是资本支出，不是收入"。
    """
    if W <= 0:
        raise ValueError("W 必须 > 0")
    if N <= 0:
        raise ValueError("N 必须 >= 1")
    return (a - c) + b_R / W - F / (N * W)


def cycles(m, pi):
    """达到 m 倍所需完整周期数（向上取整）。pi<=0 返回 inf。"""
    if m <= 1:
        return 0
    if pi <= 0:
        return inf
    return ceil(log(m) / log(1.0 + pi))


def w_star(b_C, pi0):
    """平台区下界：本金低于此值，pi < 0。"""
    if pi0 <= 0:
        return inf
    return b_C / pi0


def kelly(mu, var):
    """凯利最优比例 f* = mu / var（var 为收益率的方差）。"""
    if var <= 0:
        return 0.0 if mu <= 0 else inf
    return mu / var


def usable_fraction(mu, var, cap=1.0, divisor=2.0):
    """实用比例：f <= f*/2，上限 cap。因为参数一定会估错。"""
    f = kelly(mu, var)
    if f == inf:
        return cap
    if f <= 0:
        return 0.0
    return max(0.0, min(f / divisor, cap))


def ruin_prob(W0, f, mu, sigma, periods, trials=20000, seed=7, floor_ratio=0.01):
    """蒙特卡洛：给定下注比例 f，periods 期后「实质出局」的概率。

    出局定义：资本跌破初始资本的 floor_ratio（默认 1%）。
    为什么不用 W<=0：连续分布永远到不了 0，但现实中你会被强平/停业。
    单期收益率 r ~ N(mu, sigma)，截断在 -1 以上。
    """
    if W0 <= 0:
        return 1.0
    floor = W0 * floor_ratio
    rng = random.Random(seed)
    ruined = 0
    for _ in range(trials):
        w = W0
        for _ in range(periods):
            r = rng.gauss(mu, sigma)
            if r < -1.0:
                r = -1.0
            w *= (1.0 + f * r)
            if w <= floor:
                break
        if w <= floor:
            ruined += 1
    return ruined / trials


def geo_growth(f, mu, sigma, trials=20000, seed=11):
    """几何增长率 g = E[ln(1 + f*r)]。这是真正决定长期结果的数。"""
    rng = random.Random(seed)
    total = 0.0
    for _ in range(trials):
        r = rng.gauss(mu, sigma)
        if r < -1.0:
            r = -1.0
        v = 1.0 + f * r
        if v <= 0.0:
            return -inf
        total += log(v)
    return total / trials


def cash_runway(cash, monthly_net):
    """现金跑道（月）。monthly_net<0 时有意义；>=0 返回 inf。"""
    if monthly_net >= 0:
        return inf
    return cash / (-monthly_net)

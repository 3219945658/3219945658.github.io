# -*- coding: utf-8 -*-
"""《清算日》—— 现金流与破产阈值体检（纯标准库，单文件，可离线运行）

这不是理财建议工具，是算术工具。它只回答四个问题：
    1 我的现金还能撑几个月？
    2 我单笔最多能亏多少而不出局？
    3 我这门生意的盈亏平衡点在哪，需要多少周转本金？
    4 我这笔下注的比例，是不是已经超过"必死线"？

用法：
    python product/qingsuanri.py --income 8000 --expense 5000 --debt 120000 --payment 2500 --cash 20000
    python product/qingsuanri.py --demo
    python product/qingsuanri.py --demo --html out/体检报告.html
"""
import argparse
import datetime as dt
import os
import sys
from math import inf

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engine"))
from model import w_star, kelly, usable_fraction, cash_runway  # noqa: E402


def s(x):
    """钱：两位小数，inf 显示为 ——"""
    if x == inf:
        return "——"
    return "{:,.2f}".format(x)


def build(args):
    income = args.income
    expense = args.expense
    payment = args.payment
    cash = args.cash
    debt = args.debt
    fixed = args.fixed
    margin = args.margin
    turnover = max(0.0, args.turnover)
    edge = args.edge
    vol = args.vol

    ncf = income - expense - payment
    runway = cash_runway(cash, ncf)

    today = dt.date.today()
    if runway == inf:
        break_date = "不存在（当前净现金流为正）"
    else:
        m = int(runway)
        d = int(round((runway - m) * 30))
        break_date = (today + dt.timedelta(days=m * 30 + d)).isoformat()

    single_loss = cash / 3.0
    debt_ratio = debt / (12.0 * income) if income > 0 else inf

    # 维度必须对：毛利率是"每单收入里的毛利占比"（无量纲），不能直接除本金
    breakeven_rev = (fixed / margin) if margin > 0 else inf      # 元/月
    working_capital = breakeven_rev * turnover                    # 元

    var = vol ** 2
    f_star = kelly(edge, var) if edge > 0 else 0.0
    f_use = usable_fraction(edge, var) if edge > 0 else 0.0
    if f_use == inf:
        f_use = 1.0

    pay_back = (debt / ncf) if ncf > 0 else inf

    rows = []

    def add(k, v, note):
        rows.append((k, v, note))

    add("月净现金流", s(ncf) + " 元", "收入 − 必要支出 − 债务月供")
    add("现金跑道", ("——（不会断）" if runway == inf else "%.1f 个月" % runway),
        "现金 ÷ 每月净流出")
    add("现金流断裂日", break_date, "按当前趋势推算，非预言")
    add("单笔最大可承受亏损", s(single_loss) + " 元", "现金 ÷ 3：能承受三次才叫资本")
    add("债务 / 年收入", ("——" if debt_ratio == inf else "%.2f 倍" % debt_ratio),
        ">3 倍即高杠杆，>5 倍即脆弱")
    add("还清债务需要", ("——（净现金流为负）" if pay_back == inf else "%.1f 年" % pay_back),
        "债务 ÷ 年净现金流")
    add("盈亏平衡月营业额", ("——" if breakeven_rev == inf else s(breakeven_rev) + " 元/月"),
        "月固定成本 ÷ 毛利率：低于此营业额，做多少亏多少")
    add("所需周转本金", ("——" if working_capital == inf else s(working_capital) + " 元"),
        "平衡营业额 × 周转月数（当前设定 %.1f 个月）" % turnover)
    add("凯利上限 f*", ("——" if edge <= 0 else "%.1f%%" % (f_star * 100)),
        "单笔预期回报 ÷ 方差；超过它就是数学上的必死线")
    add("实用下注比例", ("——" if edge <= 0 else "%.1f%%" % (f_use * 100)),
        "f* ÷ 2；因为你的参数一定是估错的")

    flags = []
    if ncf < 0:
        flags.append(("红", "净现金流为负：现在不是「怎么赚更多」的问题，是「怎么让每月为正」的问题。"))
    if runway != inf and runway < 6:
        flags.append(("红", "现金跑道不足 6 个月：任何「先投入后回收」的方案都不许做。"))
    if debt_ratio != inf and debt_ratio > 3:
        flags.append(("红", "债务超过年收入 3 倍：你的「资本」其实是别人的资产。"))
    if working_capital != inf and cash < working_capital:
        flags.append(("黄", "现金低于所需周转本金：先把固定成本或周转期降下来，别用借来的钱当周转金。"))
    if f_star > 1:
        flags.append(("红", "凯利上限 > 100%：这个结果不是你厉害，是你的两个参数里至少有一个是错的。"))
    if edge > 0 and f_use > 0.5:
        flags.append(("黄", "实用下注比例 > 50%：一次判断错就出局，降到 25% 以下。"))
    if not flags:
        flags.append(("绿", "四项体检未触发红线。仍需按「三次原则」控制单笔亏损。"))

    return {
        "rows": rows, "flags": flags, "ncf": ncf, "runway": runway,
        "single_loss": single_loss, "breakeven_rev": breakeven_rev,
        "working_capital": working_capital,
        "f_use": f_use, "break_date": break_date, "cash": cash,
    }


def render_text(res):
    out = []
    w = out.append
    w("=" * 60)
    w("清算日 · 现金流与破产阈值体检")
    w("生成时间：" + dt.datetime.now().strftime("%Y-%m-%d %H:%M"))
    w("=" * 60)
    for k, v, note in res["rows"]:
        w("%-16s %-18s %s" % (k, v, note))
    w("-" * 60)
    w("结论")
    w("-" * 60)
    for level, text in res["flags"]:
        w("[%s] %s" % (level, text))
    w("-" * 60)
    w("三条动作（按顺序，不许跳）")
    w("1 先让月净现金流 >= 0：这是唯一能改变「断裂日」的变量。")
    w("2 再把单笔亏损压到 %.2f 元以下：这样你永远还有下一手。" % res["single_loss"])
    w("3 最后才谈增长：下注比例不超过 %.1f%%。" % (res["f_use"] * 100 if res["f_use"] else 0))
    w("=" * 60)
    w("本报告是算术，不是理财建议。它不预测市场，只计算你自己的数字。")
    return "\n".join(out)


def render_html(res):
    rows = "\n".join(
        "<tr><th>%s</th><td>%s</td><td class=note>%s</td></tr>" % (k, v, n)
        for k, v, n in res["rows"]
    )
    flags = "\n".join(
        "<li class='%s'>%s</li>" % ("red" if lv == "红" else ("yellow" if lv == "黄" else "green"), t)
        for lv, t in res["flags"]
    )
    return """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>清算日 · 现金流体检报告</title>
<style>
body{font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;max-width:760px;margin:40px auto;padding:0 20px;color:#1a1a1a;line-height:1.6}
h1{font-size:22px;border-bottom:3px solid #1a1a1a;padding-bottom:10px}
table{width:100%%;border-collapse:collapse;margin:20px 0}
th{text-align:left;font-weight:600;width:34%%;padding:8px 6px;border-bottom:1px solid #e5e5e5}
td{padding:8px 6px;border-bottom:1px solid #e5e5e5}
td.note{color:#777;font-size:13px}
ul{list-style:none;padding:0}
li{padding:10px 12px;margin:8px 0;border-left:4px solid #ccc;background:#fafafa}
li.red{border-color:#c0392b}li.yellow{border-color:#d68910}li.green{border-color:#1e8449}
.act{background:#f4f6f8;padding:16px 20px;border-radius:6px;margin-top:24px}
.act ol{margin:8px 0 0 18px}
footer{margin-top:36px;color:#888;font-size:12px;border-top:1px solid #e5e5e5;padding-top:12px}
@media print{body{margin:0}}
</style></head><body>
<h1>清算日 · 现金流与破产阈值体检</h1>
<p style="color:#777;font-size:13px">生成时间：%s</p>
<table>%s</table>
<h2 style="font-size:17px">结论</h2><ul>%s</ul>
<div class="act"><strong>三条动作（按顺序，不许跳）</strong><ol>
<li>先让月净现金流 ≥ 0：这是唯一能改变"断裂日"的变量。</li>
<li>再把单笔亏损压到 %s 元以下：这样你永远还有下一手。</li>
<li>最后才谈增长：下注比例不超过 %.1f%%。</li>
</ol></div>
<footer>本报告是算术，不是理财建议。它不预测市场，只计算你自己的数字。<br>
所有输入均为你本人提供，本工具不上传、不联网、不存储。</footer>
</body></html>""" % (
        dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        rows,
        flags,
        s(res["single_loss"]),
        res["f_use"] * 100 if res["f_use"] else 0,
    )


def main(argv):
    p = argparse.ArgumentParser(description="清算日 · 现金流与破产阈值体检")
    p.add_argument("--income", type=float, default=8000, help="月收入（元）")
    p.add_argument("--expense", type=float, default=5000, help="月必要支出（元）")
    p.add_argument("--debt", type=float, default=0, help="债务总余额（元）")
    p.add_argument("--payment", type=float, default=0, help="月债务还款（元）")
    p.add_argument("--cash", type=float, default=20000, help="可动用现金（元）")
    p.add_argument("--fixed", type=float, default=0, help="这门生意的月固定成本（元）")
    p.add_argument("--margin", type=float, default=0.30, help="毛利率（0-1，每单收入里的毛利占比）")
    p.add_argument("--turnover", type=float, default=1.0, help="周转月数（备货到收款的月数）")
    p.add_argument("--edge", type=float, default=0.10, help="单笔预期回报率（相对这笔投入，0-1）")
    p.add_argument("--vol", type=float, default=0.40, help="单笔回报的波动率（0-1）")
    p.add_argument("--html", default="", help="额外输出 HTML 报告到该路径")
    p.add_argument("--demo", action="store_true", help="用一组示例数字运行")
    a = p.parse_args(argv)

    if a.demo:
        a.income, a.expense, a.debt, a.payment = 8000.0, 5000.0, 120000.0, 2500.0
        a.cash, a.fixed, a.margin = 20000.0, 3000.0, 0.30
        a.turnover, a.edge, a.vol = 3.0, 0.10, 0.40

    res = build(a)
    print(render_text(res))

    if a.html:
        os.makedirs(os.path.dirname(os.path.abspath(a.html)), exist_ok=True)
        with open(a.html, "w", encoding="utf-8") as fh:
            fh.write(render_html(res))
        print("\n[已生成] " + os.path.abspath(a.html))
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main(sys.argv[1:]))

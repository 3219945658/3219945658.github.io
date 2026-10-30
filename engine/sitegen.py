# -*- coding: utf-8 -*-
"""同律计划 · 静态站生成器（纯标准库）

为什么是静态站，而不是自动发小红书/闲鱼：
    v0.1.67 已判：平台反自动化 → 成本随规模超线性（λW²）+ 吸收壁。
    只有「自己拥有的静态站 + 免费子域 + 长尾搜索」这一条，b_C=0 且不违规。

输入 data/topics.csv → 输出 out/site/
    index.html / <slug>.html / sitemap.xml / robots.txt

用法：python engine/sitegen.py [--base https://example.pages.dev]
"""
import csv
import os
import sys
import datetime as dt

CSS = """
:root{--ink:#16181d;--mut:#6b7280;--line:#e6e8ec;--bg:#fbfbfc;--accent:#1a56db}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
 font:16px/1.75 -apple-system,"Segoe UI","Microsoft YaHei",system-ui,sans-serif}
.wrap{max-width:720px;margin:0 auto;padding:48px 22px 80px}
h1{font-size:27px;line-height:1.35;margin:0 0 6px;letter-spacing:-.2px}
h2{font-size:18px;margin:36px 0 10px}
p{margin:14px 0}
.mut{color:var(--mut);font-size:14px}
.card{background:#fff;border:1px solid var(--line);border-radius:10px;padding:22px 24px;margin:26px 0}
.calc{font-family:ui-monospace,Consolas,monospace;background:#f3f4f6;border-radius:8px;
 padding:14px 16px;font-size:14px;overflow-x:auto;white-space:pre-wrap}
.cta{display:block;text-align:center;background:var(--accent);color:#fff;text-decoration:none;
 padding:15px;border-radius:9px;font-weight:600;margin:28px 0 8px}
.cta:hover{opacity:.92}
nav{border-bottom:1px solid var(--line);padding-bottom:14px;margin-bottom:34px;font-size:14px}
nav a{color:var(--mut);text-decoration:none;margin-right:14px}
footer{border-top:1px solid var(--line);margin-top:56px;padding-top:18px;color:var(--mut);font-size:13px}
ul{padding-left:20px}li{margin:8px 0}
"""

TEMPLATE = """<!doctype html><html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{base}/{slug}.html">
<style>{css}</style>
</head><body><div class="wrap">
<nav><a href="index.html">首页</a><a href="calc.html">免费试算</a><a href="buy.html">完整版</a><a href="index.html#all">全部工具页</a></nav>
<h1>{title}</h1>
<p class="mut">{query}</p>
<h2>你可能正在经历的</h2>
<p>{pain}</p>
<h2>算一遍</h2>
<div class="calc">{example}</div>
<h2>这个数为什么重要</h2>
<p>{why}</p>
<a class="cta" href="{buy}">{cta} →</a>
<p class="mut" style="text-align:center">纯本地计算，不上传数据，不联网，不需要注册。</p>
<footer>
<p><strong>免责声明</strong>：本站提供的是算术工具与会计口径说明，不是投资建议、不是贷款建议、不预测市场。
所有结论只对你输入的数字成立。</p>
<p>© {year} 清算日</p>
</footer>
</div></body></html>"""

INDEX_TEMPLATE = """<!doctype html><html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>清算日 · 现金流与破产阈值体检</title>
<meta name="description" content="用你自己的数字，算清现金跑道、最低本金、单笔下注上限。纯本地计算，不上传数据。">
<style>{css}</style>
</head><body><div class="wrap">
<h1>你的钱，能撑几个月？</h1>
<p class="mut">一个只做算术的工具。不预测，不承诺，只把你自己输入的数字算清楚。</p>
<p><a href="calc.html" style="color:#1a56db;font-weight:600">→ 先免费算一份，不用付款</a></p>
<div class="card">
<h2 style="margin-top:0">它回答四个问题</h2>
<ul>
<li>我的现金还能撑几个月？</li>
<li>我单笔最多能亏多少，而不至于出局？</li>
<li>这门生意至少要多少本金，才不亏？</li>
<li>我这笔投入的比例，是不是已经越过必死线？</li>
</ul>
<a class="cta" href="{buy}">获取《清算日》体检工具 →</a>
<p class="mut" style="text-align:center">一次性买断，本地运行，后续更新免费。</p>
</div>
<h2 id="all">全部工具页</h2>
<ul>{links}</ul>
<footer>
<p><strong>免责声明</strong>：本站提供算术工具与会计口径说明，不是投资建议、不是贷款建议、不预测市场。</p>
<p>© {year} 清算日</p>
</footer>
</div></body></html>"""

WHY = ("因为这个数一旦算出来，它会改变你的动作顺序——"
       "先让净现金流为正，再谈增长；先把单笔亏损压到能承受三次，再谈下注比例。"
       "顺序反了，前面所有的判断都会在某一次归零时被一起抹掉。")


def read_topics(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        return [r for r in csv.DictReader(fh) if r.get("slug")]


def main(argv):
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    topics_path = os.path.join(base_dir, "data", "topics.csv")
    out_dir = os.path.join(base_dir, "out", "site")
    base = "https://example.pages.dev"
    if "--base" in argv:
        base = argv[argv.index("--base") + 1].rstrip("/")

    buy = os.environ.get("ISON_BUY_URL", "buy.html")
    rows = read_topics(topics_path)
    os.makedirs(out_dir, exist_ok=True)
    year = dt.date.today().year

    links = []
    for r in rows:
        desc = r["pain"][:80]
        html = TEMPLATE.format(
            title=r["title"], desc=desc, base=base, slug=r["slug"], css=CSS,
            query=r["query"], pain=r["pain"], example=r["example"],
            why=WHY, cta=r["cta"], buy=buy, year=year,
        )
        with open(os.path.join(out_dir, r["slug"] + ".html"), "w", encoding="utf-8") as fh:
            fh.write(html)
        links.append('<li><a href="%s.html">%s</a></li>' % (r["slug"], r["title"]))

    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(INDEX_TEMPLATE.format(css=CSS, buy=buy, year=year, links="\n".join(links)))

    urls = (["%s/index.html" % base, "%s/calc.html" % base, "%s/buy.html" % base,
             "%s/qingsuanri.html" % base]
            + ["%s/%s.html" % (base, r["slug"]) for r in rows])
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        sm.append("  <url><loc>%s</loc></url>" % u)
    sm.append("</urlset>")
    with open(os.path.join(out_dir, "sitemap.xml"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(sm))

    with open(os.path.join(out_dir, "robots.txt"), "w", encoding="utf-8") as fh:
        fh.write("User-agent: *\nAllow: /\nSitemap: %s/sitemap.xml\n" % base)

    # 复制手写的静态页（免费试算等）
    static_dir = os.path.join(base_dir, "static")
    copied = 0
    if os.path.isdir(static_dir):
        for name in os.listdir(static_dir):
            src = os.path.join(static_dir, name)
            if os.path.isfile(src):
                with open(src, "rb") as fh:
                    data = fh.read()
                with open(os.path.join(out_dir, name), "wb") as fh:
                    fh.write(data)
                copied += 1

    print("生成 %d 页 + 首页 + sitemap + robots + 静态页 %d 个 -> %s"
          % (len(rows), copied, out_dir))
    print("base = %s" % base)
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main(sys.argv[1:]))

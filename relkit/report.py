"""Self-contained HTML report built from the CSV/JSON outputs in output_dir."""
from __future__ import annotations

import csv
import datetime as dt
import html
import json
import math
from collections import defaultdict


def _read(path):
    if not path.exists():
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def _f(x, default=float("nan")):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def esc(x):
    return html.escape(str(x))


def heat(v, scale=1.0):
    """Background for a 0-1 (or 0-scale) value: one hue, darker = higher."""
    if math.isnan(v):
        return ""
    a = 0.05 + 0.5 * max(0, min(1, v / scale))
    return f' style="background:rgba(var(--seq),{a:.2f})"'


def heat_bad(v):
    """For rates where higher is worse (irrelevant, zero results)."""
    if math.isnan(v) or v <= 0:
        return ""
    return f' style="background:rgba(var(--neg),{0.05 + 0.5 * min(1, v / 0.6):.2f})"'


def diverge(d, scale=0.15):
    if math.isnan(d):
        return ""
    a = min(0.55, abs(d) / scale * 0.55)
    return f' style="background:rgba(var({"--pos" if d > 0 else "--neg"}),{a:.2f})"'


def fmt(v, pct=False, nd=2):
    if math.isnan(v):
        return "–"
    return f"{v:.0%}" if pct else f"{v:.{nd}f}"


CSS = """
:root{--bg:#fbfbf9;--surface:#ffffff;--ink:#1d1d1b;--ink2:#55554f;--muted:#8a8a82;--line:#e6e5df;
--seq:37,99,235;--pos:22,128,94;--neg:200,80,40;--pass:#16805e;--fail:#c0392b;--chip:#f1f0ea}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#161615;--surface:#1f1f1d;--ink:#ecebe6;
--ink2:#b5b4ad;--muted:#85847d;--line:#34332f;--seq:96,145,255;--pos:60,190,140;--neg:240,120,80;--pass:#4cc38a;--fail:#ff7a6b;--chip:#2a2a27}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,sans-serif}
main{max-width:1160px;margin:0 auto;padding:32px 16px 64px}
h1{font-size:26px;margin:0 0 4px;letter-spacing:-.01em}h2{font-size:18px;margin:40px 0 6px}h3{font-size:15px;margin:18px 0 6px}
.sub{color:var(--ink2);margin:0 0 4px}.note{color:var(--muted);font-size:13px;margin:4px 0 12px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin:20px 0}
.card{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.card b{display:block;font-size:13px;color:var(--ink2);font-weight:600;margin-bottom:4px}
.card .big{font-size:24px;font-weight:650;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}
.judges{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:12px}
.judge{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:14px 16px;font-size:13px}
.judge h3{margin:0 0 2px}.judge p{margin:6px 0;color:var(--ink2)}
.wrap{overflow-x:auto;background:var(--surface);border:1px solid var(--line);border-radius:10px}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
th,td{padding:7px 10px;text-align:right;border-bottom:1px solid var(--line);white-space:nowrap}
th{font-size:12px;color:var(--ink2);font-weight:600;background:var(--surface)}
td:first-child,th:first-child{text-align:left}tr:last-child td{border-bottom:0}
tr.grp td{background:var(--chip);font-weight:600;font-size:13px;text-align:left}
td small{display:block;color:var(--ink2);font-size:11px}
.l{text-align:left;white-space:normal}.pass{color:var(--pass);font-weight:650}.fail{color:var(--fail);font-weight:650}
.chip{display:inline-block;background:var(--chip);border-radius:20px;padding:1px 8px;font-size:12px;color:var(--ink2);margin:2px 2px 0 0}
ul.find{padding-left:18px;margin:8px 0}ul.find li{margin:5px 0}
details{margin-top:8px}summary{cursor:pointer;color:var(--ink2);font-size:13px}
dl.gl{display:grid;grid-template-columns:max-content 1fr;gap:4px 14px;font-size:13px;margin:8px 0;color:var(--ink2)}
dl.gl dt{font-weight:600;color:var(--ink)}dl.gl dd{margin:0}
"""

COLS = [("precision", "Precision@k", False), ("recall_capped", "Recall@k", False), ("recall", "Pool recall@k", False),
        ("f1", "F1@k", False), ("ndcg", "nDCG@k", False), ("mrr", "MRR", False), ("hit_exact", "Exact hit", True),
        ("irrelevant_rate", "Irrelevant", True), ("zero_results", "Zero results", True)]


def build_report(p):
    out = p.out
    sc = _read(out / "scorecard.csv")
    kws = _read(out / "keywords.csv")
    comps = _read(out / "engine_vs_baseline.csv")
    judg = _read(out / "judgments.csv")
    val = json.loads((out / "validation.json").read_text()) if (out / "validation.json").exists() else None
    cal = json.loads((out / "calibration.json").read_text()) if (out / "calibration.json").exists() else None
    prof = p.profiles
    if not prof and (out / "judges.json").exists():
        prof = json.loads((out / "judges.json").read_text())
    mode = p.cfg.get("report_mode", "history" if "history" in p.modes else p.modes[0])
    engines = [e["name"] for e in p.cfg.get("engines", [])]
    segs = sorted(p.segments)
    segname = {s: p.segments[s].name for s in segs}
    segname["ALL"] = "All judges"
    cell = {(r["engine"], r["mode"], r["segment"]): r for r in sc}
    k = p.k
    jc = p.cfg.get("judge", {})
    run = json.loads((out / "run.json").read_text()) if (out / "run.json").exists() else {}
    jtype, jmodel = run.get("judge_type", jc.get("type")), run.get("judge_model", jc.get("model"))
    judge_desc = f"LLM ({jmodel})" if jtype == "llm" else "offline rules judge"
    n_search = int(_f(cell.get((engines[0], mode, "ALL"), {}).get("searches"), 0)) if engines and sc else 0

    def m(e, s, key, md=None):
        return _f(cell.get((e, md or mode, s), {}).get(key))

    H = [f"<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
         f"<title>Relevance report</title><style>{CSS}</style></head><body><main>"]
    H.append(f"<h1>Search relevance report</h1><p class=sub>{esc(p.name)} · {len(segs)} segment judges · "
             f"{n_search:,} searches · {len(engines)} engines · top {k} · judge: {esc(judge_desc)} · {dt.date.today().isoformat()}</p>")
    H.append(f"<p class=note>Each segment judge replays its shoppers' searches against every engine. Every result is graded "
             f"0–3 for the shopper who searched (3 = exactly what they want, 0 = irrelevant or won't work for them); "
             f"grade ≥ {p.cfg.get('relevant_grade', 2)} counts as relevant. To find all relevant products for recall, each "
             f"engine's top {p.cfg.get('pool_depth', 20)} results are pooled and graded.</p>")
    H.append(f"<details><summary>What the metrics mean</summary><dl class=gl>"
             f"<dt>Precision@{k}</dt><dd>Share of the {k} results shown that are relevant.</dd>"
             f"<dt>Recall@{k}</dt><dd>Relevant results shown ÷ the most that could be shown (all relevant products found by any engine, capped at {k}). 1.0 is reachable.</dd>"
             f"<dt>Pool recall@{k}</dt><dd>Relevant results shown ÷ all relevant products found by any engine (uncapped; low when many products are relevant).</dd>"
             f"<dt>nDCG@{k}, MRR</dt><dd>Order-aware: are the best results near the top; how early the first relevant result appears.</dd>"
             f"<dt>Exact hit</dt><dd>Searches with at least one result graded 3.</dd>"
             f"<dt>Irrelevant</dt><dd>Share of results shown graded 0.</dd>"
             f"<dt>Zero results</dt><dd>Searches where the engine returned nothing.</dd></dl></details>")

    # ---- cards + findings
    best = {}
    for s in ["ALL"] + segs:
        vals = [(m(e, s, "recall_capped"), e) for e in engines]
        vals = [v for v in vals if not math.isnan(v[0])]
        if vals:
            best[s] = max(vals)
    H.append("<div class=cards>")
    if "ALL" in best:
        v, e = best["ALL"]
        H.append(f"<div class=card><b>Best engine</b><div class=big>{esc(e)}</div><span class=note>recall@{k} {v:.2f} · "
                 f"precision@{k} {m(e, 'ALL', 'precision'):.2f}</span></div>")
    if val:
        a = val["summary"]["ALL"]
        H.append(f"<div class=card><b>Judge vs golden labels</b><div class=big>{a['kappa']:.2f}</div>"
                 f"<span class={'pass' if val['passed'] else 'fail'}>{'PASS' if val['passed'] else 'FAIL'}</span> "
                 f"<span class=note>weighted kappa, gate {val['gate_min_kappa']}</span></div>")
    if cal and "ALL" in cal and mode in cal["ALL"]:
        c = cal["ALL"][mode]
        H.append(f"<div class=card><b>Judge vs shopper choices</b><div class=big>{c['mean']:.2f}</div>"
                 f"<span class=note>AUC of the chosen item; 0.50 = chance</span></div>")
    H.append("</div>")

    findings = []
    if "ALL" in best:
        for s in segs:
            if s in best and best[s][1] != best["ALL"][1]:
                findings.append(f"For <b>{esc(segname[s])}</b> the best engine is <b>{esc(best[s][1])}</b>, not the overall winner.")
        if "generic" in p.modes and mode != "generic":
            g = max(((m(e, "ALL", "recall_capped", "generic"), e) for e in engines), default=None)
            gp = max(((m(e, "ALL", "precision", "generic"), e) for e in engines), default=None)
            e0 = best["ALL"][1]
            pg, ph = m(e0, "ALL", "precision", "generic"), m(e0, "ALL", "precision")
            if pg - ph >= 0.05:
                findings.append(f"A judge with no shopper context rates <b>{esc(e0)}</b> at precision@{k} {pg:.2f}; "
                                f"graded for the shoppers who actually searched it is {ph:.2f}. Generic grading "
                                "overstates relevance.")
            elif ph - pg >= 0.05:
                findings.append(f"<b>{esc(e0)}</b> scores higher for the actual shoppers (precision@{k} {ph:.2f}) than "
                                f"for a generic shopper ({pg:.2f}): it finds what these shoppers need.")
            if g and g[1] != best["ALL"][1]:
                findings.append(f"Graded generically, <b>{esc(g[1])}</b> would look best; for real shoppers <b>{esc(e0)}</b> is. "
                                "Shopper context changes the decision.")
        worst = min(((best[s][0], s) for s in segs if s in best), default=None)
        if worst:
            verb = "are" if segname[worst[1]].endswith("s") else "is"
            findings.append(f"<b>{esc(segname[worst[1]])}</b> {verb} served worst: even the best engine reaches recall@{k} {worst[0]:.2f}.")
        for c in comps:
            if c["mode"] == mode and c["segment"] == "ALL" and c["metric"] == "recall_capped":
                d, lo, hi = _f(c["diff"]), _f(c["lo"]), _f(c["hi"])
                sig = "clearly better" if lo > 0 else "clearly worse" if hi < 0 else "not clearly different"
                findings.append(f"<b>{esc(c['engine'])}</b> vs {esc(c['baseline'])}: recall@{k} {d:+.2f} [{lo:+.2f}, {hi:+.2f}], {sig}.")
        nr = m(engines[0], "ALL", "no_relevant_product")
        if nr > 0.005:
            findings.append(f"{nr:.0%} of searches have no relevant product from any engine for the shopper: a catalog or "
                            "retrieval gap rather than a ranking problem (see weakest keywords).")
    if findings:
        H.append("<h2>Key findings</h2><ul class=find>" + "".join(f"<li>{f}</li>" for f in findings) + "</ul>")

    # ---- judges
    if prof:
        H.append("<h2>Segment judges</h2><p class=note>Each judge's profile was built from its shoppers' data; its keyword set "
                 "is the searches they ran.</p><div class=judges>")
        for s in segs:
            pr = prof.get(s)
            if not pr:
                continue
            chips = "".join(f"<span class=chip>{esc(kw)} · {n}</span>" for kw, n in pr["top_keywords"][:8])
            H.append(f"<div class=judge><h3>{esc(pr['name'])}</h3><span class=note>{pr['shoppers']} shoppers · "
                     f"{pr['searches']:,} searches · {pr['distinct_keywords']} distinct keywords · price sensitivity "
                     f"{esc(pr['price_sensitivity'])}</span><div>{chips}</div><details><summary>Profile given to the judge"
                     f"</summary><p>{esc(pr['profile'])}</p></details></div>")
        H.append("</div>")

    # ---- main scorecard
    if sc:
        H.append(f"<h2>Scorecard by judge</h2><p class=note>Graded with each shopper's own history ({esc(mode)} mode). "
                 "Mean over searches.</p><div class=wrap><table><tr><th>Engine</th>" +
                 "".join(f"<th>{esc(lbl.replace('@k', '@' + str(k)))}</th>" for _, lbl, _ in COLS) + "<th>Searches</th></tr>")
        for s in ["ALL"] + segs:
            H.append(f"<tr class=grp><td colspan={len(COLS) + 2}>{esc(segname[s])}</td></tr>")
            for e in engines:
                H.append(f"<tr><td>{esc(e)}</td>")
                for key, _, pct in COLS:
                    v = m(e, s, key)
                    style = heat_bad(v) if key in ("irrelevant_rate", "zero_results") else heat(v)
                    H.append(f"<td{style}>{fmt(v, pct)}</td>")
                H.append(f"<td>{int(m(e, s, 'searches')):,}</td></tr>")
        H.append("</table></div>")

        # ---- judge point of view
        H.append(f"<h2>How the judge's point of view changes the numbers</h2><p class=note>Same results, all searches. "
                 f"Precision@{k} / recall@{k} graded for a typical shopper (generic), for the segment profile, and for the "
                 "searching shopper's own history.</p>")
        H.append("<div class=wrap><table><tr><th>Engine</th>" + "".join(f"<th>{esc(md)}</th>" for md in p.modes) + "</tr>")
        for e in engines:
            H.append(f"<tr><td>{esc(e)}</td>" + "".join(
                f"<td{heat(m(e, 'ALL', 'precision', md))}>{fmt(m(e, 'ALL', 'precision', md))} / "
                f"{fmt(m(e, 'ALL', 'recall_capped', md))}</td>" for md in p.modes) + "</tr>")
        H.append("</table></div>")

    # ---- vs baseline
    rel = [c for c in comps if c["mode"] == mode]
    if rel:
        base = rel[0]["baseline"]
        H.append(f"<h2>Engines vs baseline ({esc(base)})</h2><p class=note>Paired difference on the same searches with a 95% "
                 "bootstrap interval; shaded only when the interval excludes zero.</p>")
        by = {(c["engine"], c["segment"], c["metric"]): c for c in rel}
        for metric, lbl in [("recall_capped", f"Recall@{k}"), ("precision", f"Precision@{k}"), ("ndcg", f"nDCG@{k}")]:
            H.append(f"<h3>{lbl}</h3><div class=wrap><table><tr><th>Engine</th>" +
                     "".join(f"<th>{esc(segname[s])}</th>" for s in ["ALL"] + segs) + "</tr>")
            for e in engines:
                if e == base:
                    continue
                H.append(f"<tr><td>{esc(e)}</td>")
                for s in ["ALL"] + segs:
                    c = by.get((e, s, metric))
                    if not c:
                        H.append("<td>–</td>")
                        continue
                    d, lo, hi = _f(c["diff"]), _f(c["lo"]), _f(c["hi"])
                    H.append(f"<td{diverge(d) if (lo > 0 or hi < 0) else ''}>{d:+.2f}<small>[{lo:+.2f}, {hi:+.2f}]</small></td>")
                H.append("</tr>")
            H.append("</table></div>")

    # ---- weakest keywords per judge
    if kws and "ALL" in best:
        e0 = best["ALL"][1]
        H.append(f"<h2>Weakest keywords per judge</h2><p class=note>For the best engine ({esc(e0)}), keywords ranked by "
                 f"lost relevance = searches × (1 − recall@{k}). \"No relevant product\" means no engine found anything that "
                 "suits these shoppers.</p>")
        for s in segs:
            rows = [r for r in kws if r["engine"] == e0 and r["mode"] == mode and r["segment"] == s]
            for r in rows:
                rc = _f(r["recall_capped"])
                r["_loss"] = int(r["searches"]) * (1 - (rc if not math.isnan(rc) else 0))
            rows = sorted(rows, key=lambda r: -r["_loss"])[:8]
            if not rows:
                continue
            H.append(f"<h3>{esc(segname[s])}</h3><div class=wrap><table><tr><th class=l>Keyword</th><th>Searches</th>"
                     f"<th>Recall@{k}</th><th>Precision@{k}</th><th>Relevant products</th><th class=l>Note</th></tr>")
            for r in rows:
                rc, pr_, nrel, zr = _f(r["recall_capped"]), _f(r["precision"]), _f(r["relevant_in_pool"]), _f(r["zero_results"])
                note = "No relevant product" if nrel == 0 else "Engine returns nothing" if zr > 0.5 else ""
                H.append(f"<tr><td class=l>{esc(r['keyword'])}</td><td>{r['searches']}</td><td{heat(rc)}>{fmt(rc)}</td>"
                         f"<td{heat(pr_)}>{fmt(pr_)}</td><td>{fmt(nrel, nd=1)}</td><td class=l>{note}</td></tr>")
            H.append("</table></div>")
        H.append("<p class=note>Every keyword for every engine is in keywords.csv.</p>")

    # ---- trust
    if val or cal:
        H.append("<h2>Can the judge be trusted?</h2>")
    if val:
        H.append("<p class=note>Agreement with hand-labelled golden cases. Replace these with your raters' labels.</p>"
                 "<div class=wrap><table><tr><th>Judge mode</th><th>Cases</th><th>Exact grade</th><th>Within 1 grade</th>"
                 "<th>Relevant / not agree</th><th>Weighted kappa</th></tr>")
        for md, s in val["summary"].items():
            H.append(f"<tr><td>{esc(md)}</td><td>{s['n']}</td><td>{s['exact']:.0%}</td><td>{s['within1']:.0%}</td>"
                     f"<td>{s['relevant_agree']:.0%}</td><td>{s['kappa']:.2f}</td></tr>")
        H.append("</table></div>")
        if val["disagreements"]:
            H.append("<details><summary>Cases where the judge is off by 2+ grades</summary><div class=wrap><table>"
                     "<tr><th>Shopper</th><th class=l>Search</th><th class=l>Product</th><th>Expected</th><th>Judge</th>"
                     "<th class=l>Judge's reason</th></tr>")
            for d in val["disagreements"]:
                t = p.catalog[d["product_id"]].title if d["product_id"] in p.catalog else d["product_id"]
                H.append(f"<tr><td>{esc(d['context'])}</td><td class=l>{esc(d['query'])}</td><td class=l>{esc(t)}</td>"
                         f"<td>{d['expected']}</td><td>{d['judge']}</td><td class=l>{esc(d['reason'])}</td></tr>")
            H.append("</table></div></details>")
    if cal:
        H.append("<p class=note style='margin-top:16px'>Behavioural check: when a shopper chose one item from those shown, how "
                 "often the judge grades it above the others (AUC; 0.50 = chance; 95% interval).</p>"
                 "<div class=wrap><table><tr><th>Segment</th>" + "".join(f"<th>{esc(md)}</th>" for md in p.modes) + "<th>Choices</th></tr>")
        for s, ms in cal.items():
            n = next(iter(ms.values()))["n"]
            H.append(f"<tr><td>{esc(segname.get(s, s))}</td>" + "".join(
                f"<td>{ms[md]['mean']:.2f}<small>[{ms[md]['lo']:.2f}, {ms[md]['hi']:.2f}]</small></td>" for md in p.modes if md in ms)
                + f"<td>{n}</td></tr>")
        H.append("</table></div>")

    # ---- flagged results
    flags = [r for r in judg if r["mode"] == mode and int(r["grade"]) == 0 and int(r["rank"]) <= 3]
    if flags and sc:
        cnt = defaultdict(int)
        for r in flags:
            cnt[(r["engine"], r["segment"])] += 1
            cnt[(r["engine"], "ALL")] += 1
        H.append(f"<h2>Irrelevant results in the top 3</h2><p class=note>Per 100 searches: results graded 0 for the shopper "
                 "who searched. The clearest fixes.</p><div class=wrap><table><tr><th>Engine</th>" +
                 "".join(f"<th>{esc(segname[s])}</th>" for s in ["ALL"] + segs) + "</tr>")
        for e in engines:
            H.append(f"<tr><td>{esc(e)}</td>" + "".join(
                f"<td>{100 * cnt[(e, s)] / max(1, m(e, s, 'searches')):.0f}</td>" for s in ["ALL"] + segs) + "</tr>")
        H.append("</table></div><details><summary>Examples (first 200; all are in judgments.csv)</summary><div class=wrap><table>"
                 "<tr><th>Engine</th><th class=l>Search</th><th>Shopper</th><th>Rank</th><th class=l>Product</th><th class=l>Why</th></tr>")
        for r in sorted(flags, key=lambda r: (r["engine"], r["query_id"], int(r["rank"])))[:200]:
            H.append(f"<tr><td>{esc(r['engine'])}</td><td class=l>{esc(r['query'])}</td><td>{esc(r['user_id'])} "
                     f"<span class=chip>{esc(segname.get(r['segment'], r['segment']))}</span></td><td>{r['rank']}</td>"
                     f"<td class=l>{esc(r['title'])}</td><td class=l>{esc(r['reason'])}</td></tr>")
        H.append("</table></div></details>")

    H.append("<p class=note style='margin-top:32px'>Files: scorecard.csv, keywords.csv, per_query.csv, judgments.csv (top-k grades "
             "with reasons), pool_judgments.csv, search_results.csv, engine_vs_baseline.csv, judges.json, validation.csv, "
             "calibration_per_choice.csv.</p></main></body></html>")
    path = out / "report.html"
    path.write_text("".join(H))
    return path

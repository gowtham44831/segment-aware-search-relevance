# Results on the mock store

This page documents what relkit produces on the included **mock** phone-accessories store, using both
judges: the free offline rules judge and an LLM judge (gpt-4.1-mini). Everything here is invented data. These
numbers show **how the tool behaves and how to read its output**; they are not evidence about real shoppers.
For evidence on real customers, see the study this tool is based on: *Personas or Purchase History?*
(`personas-vs-history`).

## Setup

| | |
|---|---|
| Store | `config/mock_large.yaml`: 628 products (cases, screen protectors, chargers, cables, earbuds, power banks, watch bands, mounts, grips), 15 phone models plus Apple and Galaxy watches |
| Segment judges | 4: Apple premium mainstream, Samsung loyalists, Budget hunters, Frequent multi-device buyers; 55 shoppers each |
| Keyword sets | 1,000 searches per judge, generated from each segment's usage (owned devices, brand and price taste), including synonyms and about 3% typos; 266–315 distinct keywords per judge |
| Searches measured | 200 per judge (800), a fixed random sample (`max_searches_per_judge: 200`) |
| Engines | `keyword_bm25` (baseline); `hybrid_expanded` (typo fixing + synonyms, a stand-in for semantic or hybrid search); `hybrid_personalised` (the same plus a boost for items that fit the shopper's devices); `bestsellers` (lexical matches ordered by review count) |
| Measurement | Top 10 shown; each engine's top 20 pooled per search (about 40 products) and graded; grade ≥ 2 = relevant |
| Grades | 96,858 pooled judgments per judge type (3 modes: generic, segment, history) |
| LLM judge | gpt-4.1-mini, temperature 0, 10 products per call; estimated cost about $6 for this run |

## 1. Can the judge be trusted?

### Agreement with golden labels (59 hand-labelled cases)

| Judge | Exact grade | Within 1 grade | Relevant/not agree | Weighted kappa | Gate (0.6) |
|---|---|---|---|---|---|
| Rules | 92% | 97% | – | 0.93 | PASS |
| LLM | 78% | 97% | 95% | **0.90** | PASS |

By mode, the LLM's kappa was 0.94 for generic, 0.95 for segment and 0.86 for history.

- **The rules judge's 0.93 is inflated:** its rules and the golden labels were written by the same person.
- **The LLM's 0.90 is a fairer test.** Its typical error is leniency: in 9 cases it gave grade 1 where the label
  was 0.
- **Its two large misses are the same mistake.** It graded a case for a different model of the same phone
  family (iPhone 15 vs 15 Pro Max) as 2, "relevant but not an exact fit", where the label says it doesn't
  fit at all (0). The `guidelines` option fixes this kind of mistake (see GUIDE.md).

### Agreement with shopper choices (767 simulated choices)

AUC of the chosen item among the 8 shown (0.50 = chance), LLM judge:

| Segment | Generic | Segment profile | Own history |
|---|---|---|---|
| All | 0.53 [0.52, 0.55] | 0.63 [0.61, 0.65] | **0.64** [0.62, 0.65] |
| Apple premium | 0.55 | **0.68** | 0.66 |
| Samsung loyalists | 0.51 | **0.62** | 0.60 |
| Budget hunters | 0.55 | 0.63 | **0.66** |
| Multi-device buyers | 0.52 | 0.56 | **0.61** |

- **A judge with no shopper context barely beats chance** at predicting what shoppers choose.
- **Either kind of shopper context helps clearly.**
- **The segment profile is enough for single-ecosystem segments** (Apple, Samsung). **Individual history wins
  for mixed segments** (budget, multi-device), where shoppers in one segment own different devices. This is
  the same pattern as the study: personas work only when the segment is homogeneous.
- The choices are simulated (hidden preferences plus noise; see `scripts/make_mock_clicks.py`), so read this as
  a demonstration of the check, not a finding.

## 2. Scorecard (history grading, all judges)

| Engine | Precision@10 | Recall@10 | nDCG@10 | MRR | Exact hit | Irrelevant shown | Zero results |
|---|---|---|---|---|---|---|---|
| keyword_bm25 | 0.55 | 0.64 | 0.61 | 0.71 | 84% | 24% | 3% |
| hybrid_expanded | 0.57 | 0.66 | 0.63 | 0.72 | 87% | 24% | 0% |
| **hybrid_personalised** | **0.76** | **0.89** | **0.89** | **0.98** | **96%** | **6%** | 0% |
| bestsellers | 0.19 | 0.21 | 0.21 | 0.33 | 54% | 57% | 3% |

Recall@10 here is capped recall: relevant results shown ÷ min(10, relevant products found by any engine).

### By segment judge (recall@10 / precision@10)

| Engine | Apple premium | Samsung loyalists | Budget hunters | Multi-device |
|---|---|---|---|---|
| keyword_bm25 | 0.70 / 0.60 | 0.58 / 0.48 | 0.59 / 0.49 | 0.71 / 0.64 |
| hybrid_expanded | 0.72 / 0.61 | 0.62 / 0.50 | 0.60 / 0.50 | 0.72 / 0.66 |
| hybrid_personalised | 0.88 / 0.76 | **0.86 / 0.70** | 0.92 / 0.76 | 0.89 / 0.83 |
| bestsellers | 0.22 / 0.20 | 0.16 / 0.14 | 0.19 / 0.18 | 0.26 / 0.25 |

### Engine differences vs the baseline (paired, 95% bootstrap interval)

| Engine | Recall@10 |
|---|---|
| hybrid_expanded | +0.02 [+0.01, +0.03] |
| hybrid_personalised | +0.25 [+0.22, +0.27] |
| bestsellers | −0.44 [−0.46, −0.41] |

All three intervals exclude zero, so all three differences are reliable.

## 3. Key findings

1. **Shopper context changes which engine wins.** This is the main reason to use the tool.

   | Engine | Generic judge (P@10 / R@10) | Segment judge | History judge |
   |---|---|---|---|
   | keyword_bm25 | 0.77 / 0.85 | 0.55 / 0.64 | 0.55 / 0.64 |
   | hybrid_expanded | **0.81 / 0.89** | 0.58 / 0.68 | 0.57 / 0.66 |
   | hybrid_personalised | 0.78 / 0.86 | **0.65 / 0.75** | **0.76 / 0.89** |

   - **Graded for a typical shopper, the three main engines look almost the same,** and the synonym engine
     appears best.
   - **Graded for the shopper who actually searched, the personalised engine is far ahead.** A generic
     relevance metric would have hidden its main benefit.
   - **The segment judge sits in between.** It knows the segment's main ecosystem, but not each shopper's
     exact phone.

2. **Generic grading inflates "relevant".** On average a search has 19.4 relevant products for a generic
   shopper but only 13.3 for the actual shopper. About **a third of what looks relevant doesn't fit the
   person searching**, mostly cases and screen protectors for other phone models.

3. **Most irrelevant results are compatibility errors.** In the top 3 positions the LLM flagged 494 results
   from keyword BM25, 536 from the expanded engine and 19 from the personalised engine (of 2,400 each). Typical
   reasons:
   - "Case for iPhone 13, incompatible with shopper's devices" (search: *protective case*, Samsung loyalist)
   - "This is a charger, not a cover" (search: *samsung cover*)
   - "Compatible only with iPhones, not Galaxy devices" (search: *wireless charging stand*, Samsung loyalist)

4. **Samsung loyalists are served worst** with every engine (best: recall 0.86, precision 0.70). Many of
   their searches are for wireless charging ("wireless charger", "charging pad", "wireless charging stand"),
   and most wireless chargers in the catalog are MagSafe products that only fit iPhones. That's a catalog
   gap as much as a ranking problem.

5. **Typo and synonym handling adds little here** (+0.02 recall): only a small share of searches need it. Its
   effect is concentrated in specific keywords ("cover", "charging block", "screen guard"), so check those
   rows in `keywords.csv` rather than the average.

6. **Ranking by popularity alone is poor** (precision 0.19): best-sellers match the words but not the shopper.

### Weakest keywords (lost relevance = searches × (1 − recall))

| Judge | keyword_bm25 | hybrid_personalised |
|---|---|---|
| Apple premium | screen protector (0.13), phone case (0.10), screen guard (0.13) | screen protector (0.58), screen guard (0.68), wireless charging stand (0.71) |
| Samsung loyalists | wireless charger (0.32), phone case (0.00), tempered glass (0.18) | sports earbuds (0.67), tempered glass (0.74), 65w power adapter (0.57) |
| Budget hunters | cover (0.00), phone case (0.06), case (0.07) | magnetic battery pack (0.00), cheap protective case (0.66), 3ft charger cord (0.20) |
| Multi-device | cover (0.00), charging cable (0.19), case (0.19) | wireless charging stand (0.66), 65w charging block (0.54), charging block (0.56) |

Recall@10 is in brackets.

- For keyword search, **broad one-word or two-word searches fail**: "case", "cover", "phone case". There are
  about 20 relevant cases for each shopper, but the engine shows cases for every phone.
- For the personalised engine, the remaining gaps are **synonyms it doesn't know** ("charging block",
  "charger cord") and **attribute searches** ("65w", "sports").

## 4. Rules judge vs LLM judge (same 800 searches, history grading)

| Engine | Rules (P@10 / R@10) | LLM (P@10 / R@10) |
|---|---|---|
| keyword_bm25 | 0.52 / 0.56 | 0.55 / 0.64 |
| hybrid_expanded | 0.54 / 0.59 | 0.57 / 0.66 |
| hybrid_personalised | 0.76 / 0.85 | 0.76 / 0.89 |
| bestsellers | 0.18 / 0.19 | 0.19 / 0.21 |

- **The two judges agree on the engine order.** The free rules judge is a reasonable smoke test for plumbing
  and for big differences.
- **They disagree about Budget hunters.** The rules judge marks down anything above a budget price, which
  makes Budget hunters the worst-served segment (personalised: recall 0.80). The LLM accepts a well-reviewed
  item at a fair price, which makes them the best served (0.92). This matches the study's finding that budget
  shoppers don't simply buy the cheapest item. Judgment calls like this are why you need the LLM judge for
  real measurement.

## 5. Caveats

- **Everything is invented:** catalog, shoppers, keyword sets and choices. The keyword sets follow simple
  generation rules, so they're more regular than real search logs.
- **The personalised engine's lead is partly built in.** It boosts by the same device fit that drives the
  simulated shoppers, and that the judges check. Expect smaller and more mixed differences on real data.
- **Recall is relative to the pool** (each engine's top 20). A relevant product that no engine returns is
  never counted.
- **The golden labels are only 59 simple cases.** Real use needs 100–300 cases labelled by your own raters.

## Reproduce

```bash
python -m relkit all --config config/mock_large.yaml                 # rules judge, free
python -m relkit all --config config/mock_large.yaml --judge llm     # needs OPENAI_API_KEY, about $6
```

The outputs are in `out/mock_large/`: `report.html`, `scorecard.csv`, `keywords.csv`, `judgments.csv`
(every grade with its reason), `validation.json` and `calibration.json`.

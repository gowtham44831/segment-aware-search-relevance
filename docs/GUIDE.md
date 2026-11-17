# Usage guide: tips and tricks

Practical advice for running relkit on your own store, collected from building and running it. The README
covers installation and configuration; this page covers how to get trustworthy numbers at a sensible cost.

## The workflow in one picture

```
your data ──► judges ──► validate ──► calibrate ──► estimate ──► measure ──► report
  catalog     profile     golden       shopper      cost check    replay       HTML + CSVs
  shoppers    per         labels       choices                    keyword
  keywords    segment     (kappa)      (AUC)                      sets
  engines
```

Never skip validate and calibrate. If the judge can't reproduce your raters' labels or your shoppers'
choices, its precision and recall numbers mean nothing.

---

## 1. Start free, then pay

1. **Plumbing first, with the rules judge** (`judge.type: rules`). It costs nothing and runs in seconds to
   minutes. Use it to check that your catalog loads, columns are mapped, engines return product IDs that
   exist in the catalog, and the report renders.
2. **Then check the cost:** `python -m relkit estimate --config ... --judge llm`. It prints the number of
   judgments, LLM calls and the estimated cost, and grades nothing.
3. **First LLM run on a sample:** set `max_searches_per_judge: 200`. That's enough for stable averages per
   segment (intervals of a few points) at about a fifth of the cost.
4. **Full run only when you need it,** for example for keyword-level diagnostics.

## 2. Keep cost down

| Lever | Effect | Notes |
|---|---|---|
| `max_searches_per_judge` | Linear | 200–300 per segment is usually enough for engine comparisons |
| `judge.batch_size: 10` | About 4–5× fewer tokens than one product per call | Products for the same search and shopper share one prompt |
| `modes: [generic, history]` | Saves about a third | Drop `segment` once you know whether personas help in your store |
| `pool_depth` | Roughly linear | 20 is typical; 10 is cheaper but under-counts relevant products, so recall reads too high |
| Cache | Reruns are free | Grades are saved in `out/<name>/cache/`. Adding an engine only pays for products not yet graded |
| Self-hosted model | No per-token cost | Point `base_url` at Ollama or vLLM; validate it first, as small models may fail the gate |

**Cache trick: stopping costs nothing.** If a run is too big, press Ctrl+C, lower `max_searches_per_judge`
and rerun. Everything already graded is reused.

**Cache trick: changing the judge on purpose.** The cache key includes the model, temperature, batch size,
guidelines, prompt, product card, search and shopper context. Change any of these and those items are graded
again; otherwise nothing is. To force a fresh run, delete `out/<name>/cache/`.

## 3. Make the judge right for your store

**Add store guidelines when the judge gets something wrong.** Read the reasons in `judgments.csv` and in the
report's "off by 2+ grades" list. In the mock run the LLM claimed a USB-C cable doesn't fit an iPhone 16, and
it treated a case for a different model of the same phone family as "relevant". Fix such errors with:

```yaml
judge:
  guidelines: |
    - iPhone 15 and 16 use USB-C; iPhone 14 and earlier use Lightning.
    - A case or screen protector for a different phone model (e.g. 15 vs 15 Pro Max) does not fit: grade 0.
    - Refurbished products are acceptable substitutes unless the search says "new".
```

Keep guidelines short and factual: compatibility facts, policy decisions, house definitions. Rerun
`validate` after changing them.

**Describe the store in one sentence** (`store:`). "An online store selling phone and wearable accessories"
changes how the model reads ambiguous searches such as "band" or "stand".

**Give the judge the attributes that decide relevance.** Everything in the catalog file beyond the standard
fields is shown to the judge. Include size, colour, material, compatibility and pack size if shoppers search
by them. Leave out internal fields (cost, supplier IDs) with `extra_fields: [...]`.

**Choose the relevance threshold deliberately.** `relevant_grade: 2` counts "relevant but a weaker fit" as
relevant (good for recall). Use `3` for a strict view, such as "did we show exactly what they wanted?".

## 4. Build good judges and keyword sets

- **Sample keywords from logs with repeats.** Frequency matters: a keyword searched 50 times should weigh 50
  times. Don't deduplicate.
- **Sample per segment,** so small segments get enough searches.
- **Use a time window the engines haven't been tuned on,** for example last month's searches.
- **Keep the searcher's user ID.** History mode needs to know who searched.
- **Let profiles build themselves** (`segment_profiles: auto`). Add an analyst note in `segments.yaml` only
  for things the data can't show (for example "B2B buyers who order in bulk").
- **Check `judges.md` before paying for a run.** If a profile looks wrong (wrong devices, odd price level),
  the segment assignment or the order data is off.
- **New shoppers with no history:** history mode falls back to a generic description. If many searches come
  from new shoppers, keep `segment` mode in the run and compare.

## 5. Golden labels and calibration

- **100–300 golden cases,** labelled by your relevance raters, covering every segment and the tricky cases
  (wrong model, wrong connector, price outliers, complementary items). Use the context `user:<id>` for
  personal cases and `segment:<id>` or `generic` for others.
- **Gate at kappa 0.6.** Human raters typically agree with each other at 0.5–0.7, so a judge in that range
  is doing about as well as a person. Use `--strict` in CI so a failing judge stops the pipeline.
- **Calibrate on real choices.** Export impressions (shown product IDs plus the clicked or bought one). Take
  them from a period **before** the keyword sample, so the judge isn't tuned on the same data.
- **Read calibration by segment.** In our study and in the mock run, a segment persona was enough for
  homogeneous segments (single ecosystem) but individual history won for mixed ones. Your data decides which
  mode to report.

## 6. Reading the numbers

| You see | It usually means | Do |
|---|---|---|
| High precision, low recall | Good items shown, but other engines found more | Check whether the engine truncates results or filters too hard |
| Generic precision much higher than history precision | Results match the words but not the shopper (often compatibility) | Personalise, or filter by the shopper's devices or size |
| Engines tie under generic but differ under history | The difference is personalisation | Report the history numbers; that's the shopper's experience |
| "No relevant product" for a keyword | Nothing suitable in any engine's top 20 | Check the catalog: a range gap, not a ranking problem |
| Zero results | The engine returned nothing | Typos and synonyms; compare with the expanded engine |
| High recall, low nDCG | Right items, wrong order | A ranking problem; look at MRR too |
| One segment much worse everywhere | Catalog mix or vocabulary gap for that group | Look at the segment's weakest keywords |

**Compare engines on the paired differences** (`engine_vs_baseline.csv`), not on the raw averages. The same
searches are compared, and the interval tells you whether a difference is real. Shading in the report means
the interval excludes zero.

**Recall is relative to the pool.** Adding a strong engine to a run makes recall stricter for everyone.
Compare engines **within one run**, and keep the engine set fixed when you track numbers over time.

## 7. Plugging in your engines

| Your situation | Engine type | Tip |
|---|---|---|
| Results pages already logged (impressions, A/B arms) | `results_file` | Cheapest start, with no load on production. Make sure every logged search has a `query_id` matching the keyword file |
| A search API | `http` | Use a staging endpoint. Pass the user ID only if the API personalises. Put tokens in `.env` as `$TOKEN` |
| A model in Python | `python` | A class with `search(query, user, k)` returning product IDs |

Ask every engine for at least `pool_depth` results (20), not just the 10 shown, or recall can't be measured
fairly.

## 8. Running it regularly

- **On every release or candidate ranker:** `measure` with the same keyword sample, then compare against
  the last run's `scorecard.csv`.
- **Monthly:** refresh the keyword sample and rerun `calibrate`. Catalogs, shoppers and model versions drift.
- **In CI:** `python -m relkit validate --config ... --strict`. It fails the build if the judge stops
  agreeing with the golden labels.
- **Big decisions:** confirm with an A/B test. relkit tells you where to look and what to expect; it doesn't
  replace live traffic.

## 9. Privacy and security

- **The judge receives only** product data, the search text, a device summary and recent purchase titles. No
  names, emails, addresses or raw IDs.
- **Keys live in `.env`** (git-ignored) or the environment, never in the config. To set one without echoing
  it on macOS or Linux:
  ```bash
  read -s "KEY?Paste key: " && echo "OPENAI_API_KEY=$KEY" > .env && unset KEY
  ```
  (In bash, use `read -s -p "Paste key: " KEY`.)
- **Use a model provider your company has approved,** or a self-hosted model for sensitive catalogs.
- **`out/` is git-ignored.** It contains shopper histories and grades, so don't commit or share it outside
  the team.

## 10. Troubleshooting

| Problem | Fix |
|---|---|
| `401` / "refused the key" | Wrong or expired key; update `.env` |
| `429` rate limit | Lower `judge.workers` (for example 4); the run resumes from the cache |
| Run slower than expected | Raise `workers` (16) if your rate limit allows; keep the Mac awake with `caffeinate -i` |
| Report header shows the wrong judge | Rerun `measure`, which records the judge it used in `run.json` |
| Few searches per segment | Check that the `segment` column, or the user's segment, is filled in |
| Engine IDs not in the catalog | They're dropped silently; check ID formats such as leading zeros and prefixes |
| Estimate is much higher than expected | `max_searches_per_judge` is commented out, or `pool_depth` is high |

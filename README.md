# relkit: segment-aware search relevance measurement

relkit measures how relevant your search results are **for your own customer segments**, with the
numbers search teams use: precision, recall, nDCG, MRR, zero-result rate and irrelevant rate.

1. **Judges are built from your data.** Each customer segment becomes one LLM judge. Its profile
   (devices, price position, favourite brands and categories, typical purchases) is computed from the
   segment's shoppers.
2. **Each judge has a keyword set:** the searches its shoppers ran, for example 1,000 per segment
   sampled from search logs.
3. **Every keyword is replayed against every engine.** Each returned product (ID, title, description,
   price and other attributes) is graded 0–3 for the shopper who searched, with a reason.
4. **Recall needs every relevant product, not just those returned.** relkit pools each engine's top 20
   per search and grades them all (standard TREC-style pooling). Recall@10 is measured against
   everything relevant that any engine found.

| Grade | Meaning |
|---|---|
| 3 | Exactly what this shopper is looking for |
| 2 | Relevant, but a weaker fit (brand, price, fit can't be confirmed) |
| 1 | Related or complementary, not what they meant |
| 0 | Irrelevant, or won't work for this shopper |

relkit comes from our study *Personas or Purchase History?* (phone accessories and video games, public
Amazon data). There, judging with each shopper's **own recent history** matched real purchases better than
segment personas or a generic judge. relkit supports all three modes so you can check this on your own data.

**Docs:** [Results on the mock store](docs/RESULTS.md) · [Usage guide: tips and tricks](docs/GUIDE.md)

## Quick start (offline, no API key)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m relkit all --config config/mock_large.yaml     # 4 judges x 1,000 searches, about 1 minute
open out/mock_large/report.html
```

Two mock stores are included, both invented:

| Config | Catalog | Shoppers | Searches | Use |
|---|---|---|---|---|
| `config/mock.yaml` | 57 products | 20 | 80 (4 per shopper) | Small and readable; quick checks |
| `config/mock_large.yaml` | 628 products, 15 phone models | 220 | 4,000 (1,000 per segment judge) | The full workflow |

The large store's keyword sets follow each segment's usage: the devices they own, the brands they like and
how price-driven they are. They include synonyms ("charging block", "screen guard") and typos ("iphoen 15
case") that a keyword engine misses. It compares four engines: keyword BM25, an expanded engine with typo
fixing and synonyms (a stand-in for semantic or hybrid search), the same engine with a device-fit boost
(personalised), and a best-sellers ranking.

### Using the LLM judge

Put `OPENAI_API_KEY=...` in `.env` (git-ignored), then check the size of a run before you start it:

```bash
python -m relkit estimate --config config/mock_large.yaml --judge llm
python -m relkit all      --config config/mock_large.yaml --judge llm
```

For the large store with all three judge modes, `estimate` reports about 230k judgments in about 25k
calls (10 products per call), roughly $30 with gpt-4.1-mini. To cut cost:

- set `max_searches_per_judge: 200` (about $6);
- use `modes: [generic, history]`;
- use a self-hosted model.

Grades are cached, so reruns and new engines only pay for products not yet graded.

## Commands

| Command | What it does |
|---|---|
| `judges` | Builds each segment judge's profile from its shoppers' data and lists its keyword set (`judges.md`, `judges.json`) |
| `validate` | Compares the judge with hand-labelled golden cases (exact agreement, within one grade, weighted kappa), with a pass/fail gate. Use `--strict` in CI |
| `calibrate` | Checks the judge against real behaviour: from logged impressions (shown items, chosen item), the AUC of the chosen item per judge mode and segment (0.5 = chance) |
| `estimate` | Counts searches, pooled products, judgments, LLM calls and cost. Grades nothing |
| `measure` | Replays every judge's keywords on every engine, grades the pooled results and computes the metrics |
| `report` | Builds `report.html` from saved outputs |
| `all` | Runs judges, validate, calibrate, measure and report in order |

## Metrics (per search, then averaged per judge and engine)

| Metric | Meaning |
|---|---|
| Precision@k | Share of the k results shown that are relevant (grade ≥ 2) |
| Recall@k | Relevant results shown ÷ min(k, all relevant products found by any engine). 1.0 is reachable |
| Pool recall@k | Relevant results shown ÷ all relevant products found by any engine (uncapped) |
| F1@k | Harmonic mean of precision and pool recall |
| nDCG@k, MRR | Order-aware: are the best results on top; how early the first relevant result appears |
| Exact hit | Search has at least one grade-3 result |
| Irrelevant | Share of results shown graded 0 |
| Zero results | Engine returned nothing |
| No relevant product | No engine found anything suitable for this shopper: a catalog or retrieval gap |

Recall is relative to the pool: a relevant product that no engine returns in its top `pool_depth` is
never counted. Adding a strong engine (or a broad candidate source) to the pool makes recall stricter for
all engines. Compare engines within one run, on the same pool.

The outputs are:

- `scorecard.csv`: engine × judge mode × segment
- `keywords.csv`: per keyword, frequency-weighted
- `per_query.csv`: per search
- `judgments.csv`: top-k grades with reasons
- `pool_judgments.csv`
- `engine_vs_baseline.csv`: paired differences with 95% bootstrap intervals
- `report.html`

## Judge modes

| Mode | What the judge is told | When to use |
|---|---|---|
| `generic` | Nothing; a typical shopper | Baseline; shows what a context-free judge would conclude |
| `segment` | The segment judge's profile, built from data (`segment_profiles: auto`) or written by hand | Shoppers with no history; cheap |
| `history` | The searching shopper's devices and recent purchases | Default for measurement |

Results are always reported per segment judge. In `history` mode each keyword is graded with the history
of the shopper who searched it, so the segment's numbers reflect its real members.

## Adapting it to your company

Usually you only change a config file. Copy `config/mock.yaml` to `config/mystore.yaml`, then:

**1. Catalog.** Point it at your product export (CSV, TSV, JSONL, JSON or Parquet) and map your column names:

```yaml
catalog:
  path: data/products.parquet
  columns: {product_id: sku, title: product_name, price: list_price, category: leaf_category}
```

Required: `product_id`, `title`. Recommended: `description`, `category`, `brand`, `price`, `rating`,
`review_count`, `fits` (compatible models, `;`-separated, or `any`). Any other columns are passed to the
judge as attributes (size, colour, material, ...). Use `extra_fields: [size, colour]` to limit them.

**2. Shoppers and segments.** `segments.yaml` holds each segment's name and description. The users file
holds `user_id` and `segment`. History can come from the users file or from an orders export:

```yaml
users:
  path: data/customers.csv
  purchases: {path: data/orders.csv, columns: {product_id: sku, timestamp: order_ts}}
  history_len: 20
```

**3. Keyword sets.** `query_id, user_id, segment, query`: sample about 1,000 searches per segment from your
search logs (keep repeats, since frequency matters). `segment` defaults to the user's segment. With no logs
yet, generate mock keyword sets per segment from usage, as `scripts/make_mock_large.py` does.

**3b. Devices (optional).** If shoppers type model names ("galaxy s24 case"), list them in a devices file
(`id: {name, ecosystem, aliases}`) so the rules judge can check fit. The LLM judge doesn't need it.

**4. Engines.** Use any of these:

```yaml
engines:
  - {name: prod, type: http, url: "https://search.internal/v1?q={query}&user={user_id}&n={k}",
     ids_path: "results[].sku", headers: {Authorization: "$SEARCH_TOKEN"}}
  - {name: logged, type: results_file, path: data/results.csv}       # query_id, rank, product_id
  - {name: new_model, type: python, class: "my_search:NewModel"}     # class with search(query, user, k)
```

The `results_file` type is the easiest place to start: export the result pages already shown to users
(from impression logs, or from an A/B arm) and grade them.

**5. Judge.** Use any OpenAI-compatible endpoint: OpenAI, a gateway to Azure/Bedrock (LiteLLM), or a
self-hosted model (Ollama `http://localhost:11434/v1`, vLLM). Set `store:` to one sentence about your
store. Add `guidelines:` for store-specific rules the model gets wrong, such as compatibility facts (see
the guide). The key is read from the environment variable named in `api_key_env`; never write keys into the
config.

**6. Golden labels and interactions.** Replace `golden.csv` with 100–300 cases your relevance raters
labelled (`context` is `generic`, `segment:<id>` or `user:<id>`). Replace `interactions.csv` with
impressions from your logs (`user_id, query, shown (a;b;c), chosen`).

**7. Pooling and cost.** `top_k` is what shoppers see (metrics @k). `pool_depth` is how deep each engine
is pooled for recall (20 is typical; deeper costs more, shallower under-counts relevant products).
`judge.batch_size` sends several products for the same search and shopper in one call.

For anything config can't express, the code is small and split by job:

- `relkit/adapters/data.py`: loading
- `adapters/search.py`: engines
- `judges/profiles.py`: judges built from data
- `judges/llm.py`: prompts
- `judges/rules.py`: offline rules
- `metrics.py`, `steps.py`, `report.py`

## Recommended rollout

1. Run the mock store to see the outputs.
2. Point the config at your data with `judge.type: rules` to check the plumbing (free).
3. Switch to `llm`: run `validate` and `calibrate` on a past time window. Adopt the judge only if it
   passes the golden gate and history-mode AUC clearly beats 0.5 and the generic judge.
4. Run `measure` on every release or candidate model. The report shows which segments a change helps or
   hurts and which irrelevant results to fix first. Confirm big decisions with an A/B test.
5. Recalibrate periodically; catalogs, customers and model versions change.

## Privacy

The judge receives only product data, the search text, a device summary and recent purchase titles. No
names, addresses, emails or raw customer IDs are sent. Use a model provider your company has approved,
or a self-hosted model.

## About the mock data

Everything in `data/mock/` and `data/mock_large/` is invented (`scripts/make_mock.py`,
`scripts/make_mock_large.py`). The choices in `interactions.csv` are
simulated: each shopper picks from the top 8 using hidden preferences plus noise
(`scripts/make_mock_clicks.py`), so the calibration numbers show how the method works, not real
customer behaviour. The offline rules judge was written alongside the golden labels, so its high
agreement there is expected. Treat the rules judge as a plumbing test and a source of must-never-happen
checks (an iPhone case shown to a Galaxy owner), not as a measurement. Likewise, the personalised mock
engine boosts by the same device fit the rules judge checks, so its large lead in the mock run is partly
built in. With an LLM judge on real data, expect smaller and less one-sided differences.

## Tests

```bash
python -m pytest -q
```

## License

MIT

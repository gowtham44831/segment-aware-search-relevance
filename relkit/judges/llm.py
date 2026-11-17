"""LLM judge over any OpenAI-compatible chat API (OpenAI, Azure OpenAI via
compatible gateway, Ollama /v1, vLLM, LiteLLM, ...). No SDK needed.

The API key is read from the environment variable named in judge.api_key_env.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request

from ..schema import GRADE_LABELS, Judgment
from .base import Judge

SYSTEM = """You judge search results for an online store from the point of view of one specific shopper.
Grade how relevant ONE product is to the shopper's search, on this scale:
{scale}
Consider: does it match what the search asks for; would it work with this shopper's devices;
does its price, brand and quality suit this shopper. Judge only this product; ignore its position on the page.
Reply with JSON: {{"grade": <0-3>, "reason": "<one short sentence>"}}"""

USER = """Store: {store}

About the shopper:
{shopper}

Search: "{query}"

Product:
{product}"""

SCHEMA = {
    "name": "relevance_grade",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {"grade": {"type": "integer", "enum": [0, 1, 2, 3]}, "reason": {"type": "string"}},
        "required": ["grade", "reason"],
        "additionalProperties": False,
    },
}


BATCH_USER = """Store: {store}

About the shopper:
{shopper}

Search: "{query}"

Grade EACH product below on its own for this shopper and search (don't compare them or rank them).

{products}

Reply with JSON: {{"grades": [{{"id": "<product id>", "grade": <0-3>, "reason": "<one short sentence>"}}, ...]}}
with one entry per product, in the same order."""

BATCH_SCHEMA = {
    "name": "relevance_grades",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {"grades": {"type": "array", "items": {
            "type": "object",
            "properties": {"id": {"type": "string"}, "grade": {"type": "integer", "enum": [0, 1, 2, 3]},
                           "reason": {"type": "string"}},
            "required": ["id", "grade", "reason"], "additionalProperties": False}}},
        "required": ["grades"],
        "additionalProperties": False,
    },
}


class LLMJudge(Judge):
    def __init__(self, model="gpt-4.1-mini", base_url="https://api.openai.com/v1", api_key_env="OPENAI_API_KEY",
                 temperature=0.0, workers=8, structured="json_schema", store="An online store",
                 include_segment=False, max_retries=5, timeout=60, batch_size=1, guidelines="", **_):
        self.model, self.base_url = model, base_url.rstrip("/")
        self.key = os.environ.get(api_key_env, "") if api_key_env else ""
        self.api_key_env = api_key_env
        self.temperature, self.workers, self.structured = temperature, int(workers), structured
        self.store, self.include_segment = store, include_segment
        self.max_retries, self.timeout = max_retries, timeout
        self.batch_size = int(batch_size)
        self.signature = f"llm:{model}:{temperature}:v1" + (f":b{batch_size}" if int(batch_size) > 1 else "")
        scale = "\n".join(f"{g} = {t}" for g, t in sorted(GRADE_LABELS.items(), reverse=True))
        self.system = SYSTEM.format(scale=scale)
        if guidelines and guidelines.strip():
            # store-specific relevance rules, e.g. compatibility facts the model gets wrong
            self.system += "\n\nStore relevance guidelines (follow these):\n" + guidelines.strip()
            import hashlib
            self.signature += ":g" + hashlib.sha1(guidelines.strip().encode()).hexdigest()[:8]

    def _call(self, messages, schema=SCHEMA):
        if self.api_key_env and not self.key and "api.openai.com" in self.base_url:
            raise SystemExit(f"Set {self.api_key_env} (e.g. in .env) or use judge.type: rules for an offline run")
        body = {"model": self.model, "messages": messages, "temperature": self.temperature}
        if self.structured == "json_schema":
            body["response_format"] = {"type": "json_schema", "json_schema": schema}
        elif self.structured == "json_object":
            body["response_format"] = {"type": "json_object"}
        req = urllib.request.Request(f"{self.base_url}/chat/completions", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json",
                                              **({"Authorization": f"Bearer {self.key}"} if self.key else {})})
        for attempt in range(self.max_retries):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    return json.load(r)["choices"][0]["message"]["content"]
            except urllib.error.HTTPError as e:
                if e.code in (401, 403):
                    raise SystemExit(f"Judge API refused the key ({e.code}). Check {self.base_url} and your key.")
                if e.code not in (429, 500, 502, 503, 504) or attempt == self.max_retries - 1:
                    raise
            except (urllib.error.URLError, TimeoutError):
                if attempt == self.max_retries - 1:
                    raise
            time.sleep(2 ** attempt)

    @staticmethod
    def _parse(text: str) -> Judgment:
        try:
            d = json.loads(text)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", text, re.S)
            d = json.loads(m.group(0)) if m else {}
        g = d.get("grade")
        if g is None:
            m = re.search(r"[0-3]", text)
            g = int(m.group(0)) if m else 0
        return Judgment(max(0, min(3, int(g))), str(d.get("reason", ""))[:300])

    def grade(self, query, product, ctx) -> Judgment:
        msg = USER.format(store=self.store, shopper=ctx.describe(self.include_segment), query=query, product=product.card())
        return self._parse(self._call([{"role": "system", "content": self.system}, {"role": "user", "content": msg}]))

    def grade_batch(self, query, products, ctx):
        """Several products for the same search and shopper in one call (cheaper).
        Each is still graded on its own; products the model skips fall back to single calls."""
        cards = "\n\n".join(f"[Product id: {p.product_id}]\n{p.card()}" for p in products)
        msg = BATCH_USER.format(store=self.store, shopper=ctx.describe(self.include_segment), query=query, products=cards)
        text = self._call([{"role": "system", "content": self.system}, {"role": "user", "content": msg}], BATCH_SCHEMA)
        try:
            d = json.loads(text)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", text, re.S)
            d = json.loads(m.group(0)) if m else {}
        got = {str(g.get("id")): g for g in d.get("grades", []) if isinstance(g, dict)}
        out = []
        for p in products:
            g = got.get(p.product_id)
            if g is None or g.get("grade") is None:
                out.append(self.grade(query, p, ctx))
            else:
                out.append(Judgment(max(0, min(3, int(g["grade"]))), str(g.get("reason", ""))[:300]))
        return out

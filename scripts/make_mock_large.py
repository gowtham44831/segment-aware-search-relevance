"""Generate a larger mock store: about 600 products, 220 shoppers, and 1,000 searches
per segment judge, drawn from each segment's usage (their devices, favourite brands,
price taste), including typos and synonyms a keyword engine can't match.

Everything is invented. The hand-written items and shoppers from make_mock.py are
included, so the golden labels still apply.

Run:  python scripts/make_mock_large.py   (writes data/mock_large/*)
"""
import csv
import json
import math
import random
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import make_mock as small  # noqa: E402

OUT = ROOT / "data" / "mock_large"
OUT.mkdir(parents=True, exist_ok=True)
rng = random.Random(2026)

# device id -> (display name, ecosystem, connector, magsafe)
DEVICES = {
    "iphone13": ("iPhone 13", "apple", "lightning", True),
    "iphone14": ("iPhone 14", "apple", "lightning", True),
    "iphone15": ("iPhone 15", "apple", "usb-c", True),
    "iphone15pro": ("iPhone 15 Pro", "apple", "usb-c", True),
    "iphone15promax": ("iPhone 15 Pro Max", "apple", "usb-c", True),
    "iphone16": ("iPhone 16", "apple", "usb-c", True),
    "galaxys22": ("Galaxy S22", "samsung", "usb-c", False),
    "galaxys23": ("Galaxy S23", "samsung", "usb-c", False),
    "galaxys24": ("Galaxy S24", "samsung", "usb-c", False),
    "galaxys24ultra": ("Galaxy S24 Ultra", "samsung", "usb-c", False),
    "galaxya15": ("Galaxy A15", "samsung", "usb-c", False),
    "galaxya54": ("Galaxy A54", "samsung", "usb-c", False),
    "pixel7": ("Pixel 7", "google", "usb-c", False),
    "pixel8": ("Pixel 8", "google", "usb-c", False),
    "pixel8pro": ("Pixel 8 Pro", "google", "usb-c", False),
}
WATCHES = {"applewatch": ("Apple Watch", "apple"), "galaxywatch": ("Galaxy Watch", "samsung")}
OFFICIAL = {"apple": "Apple", "samsung": "Samsung", "google": "Google"}
MID = ["Spigen", "ESR", "Caseology", "Speck", "Anker", "Belkin"]
BUDGET = ["Generic", "Lumo", "Zeta", "Brio"]
PREMIUM = ["OtterBox", "Nomad", "Sony", "Bose"]

CATEGORY_PRICE = {"phone_case": 18, "screen_protector": 10, "charger": 20, "wireless_charger": 30, "cable": 12,
                  "earbuds": 80, "power_bank": 30, "watch_band": 18, "car_mount": 20, "phone_grip": 14,
                  "phone_stand": 15, "tablet_case": 22, "phone": 350, "phone_charm": 6}
TIER_MULT = {"official": 2.4, "premium": 2.6, "mid": 1.0, "budget": 0.45}

products = []
seen = set()


def tier_of(brand):
    if brand in OFFICIAL.values():
        return "official"
    if brand in PREMIUM:
        return "premium"
    if brand in BUDGET:
        return "budget"
    return "mid"


def add(cat, brand, title, desc, fits, base_mult=1.0):
    pid = f"G{len(products)+1:04d}"
    tier = tier_of(brand)
    price = CATEGORY_PRICE[cat] * TIER_MULT[tier] * base_mult * math.exp(rng.gauss(0, 0.18))
    price = round(max(3.99, price)) - 0.01
    rating = round(min(4.9, max(3.4, rng.gauss({"budget": 4.15, "mid": 4.45, "official": 4.6, "premium": 4.55}[tier], 0.18))), 1)
    reviews = int(math.exp(rng.gauss({"budget": 7.5, "mid": 8.6, "official": 9.0, "premium": 8.2}[tier], 1.1)))
    key = (title, brand)
    if key in seen:
        return
    seen.add(key)
    products.append([pid, title, desc, cat, brand, price, rating, reviews, ";".join(fits)])


# --- device-specific: cases and screen protectors
CASE_STYLES = [("Clear", "crystal clear protective phone case, anti-yellowing"),
               ("Silicone", "soft silicone phone case with microfiber lining"),
               ("Rugged", "rugged shockproof phone case, military grade drop protection"),
               ("Wallet", "leather wallet phone case with card holder"),
               ("Slim", "ultra thin slim fit phone case"),
               ("Leather", "genuine leather phone case")]
for dev, (name, eco, conn, mag) in DEVICES.items():
    for style, desc in CASE_STYLES:
        brands = rng.sample(MID, 2) + rng.sample(BUDGET, 1)
        if style in ("Silicone", "Leather", "Clear") and eco in OFFICIAL:
            brands.append(OFFICIAL[eco])
        if style == "Rugged":
            brands.append("OtterBox")
        for b in brands:
            ms = " with MagSafe" if mag and b != "Generic" and rng.random() < 0.6 else ""
            add("phone_case", b, f"{b} {style} Case for {name}{ms}", f"{desc.capitalize()} for {name}.{' MagSafe compatible.' if ms else ''}", [dev],
                1.3 if style in ("Rugged", "Leather", "Wallet") else 1.0)
    for kind, desc, mult in [("Tempered Glass Screen Protector", "9H tempered glass screen protector", 1.0),
                             ("Privacy Screen Protector", "anti-spy privacy tempered glass", 1.6),
                             ("Camera Lens Protector", "camera lens protector glass", 0.8)]:
        for b in rng.sample(BUDGET, 1) + rng.sample(MID, 1):
            pack = ", 3 Pack" if b in BUDGET else ""
            add("screen_protector", b, f"{b} {kind} for {name}{pack}", f"{desc.capitalize()} for {name}.", [dev], mult)

# --- chargers
for w in (20, 25, 30, 45, 65, 100):
    for b in ["Anker", "Belkin", "Generic", "Zeta", "Spigen"]:
        if rng.random() < 0.55:
            ports = "3 Port" if w >= 65 else "USB-C"
            add("charger", b, f"{b} {w}W {ports} Fast Charger", f"{w}W USB-C PD wall charger power adapter, fast charging for phones{', tablets and laptops' if w >= 45 else ''}.", ["any"], 0.6 + w / 40)
add("charger", "Apple", "Apple 35W Dual USB-C Port Power Adapter", "Official Apple dual port fast charger.", ["any"], 1.0)
for w, fits in [(25, ["galaxys22", "galaxys23", "galaxys24", "galaxya54", "galaxya15"]), (45, ["galaxys22", "galaxys23", "galaxys24", "galaxys24ultra"])]:
    add("charger", "Samsung", f"Samsung {w}W Super Fast Charger (2 Pack)", f"Samsung super fast charging {w}W USB-C wall charger for Galaxy.", fits, 1.0)
add("charger", "Google", "Google 30W USB-C Charger", "Official Google fast charger for Pixel phones.", ["pixel7", "pixel8", "pixel8pro"], 0.6)

iphones = [d for d, v in DEVICES.items() if v[3]]
galaxies = [d for d, v in DEVICES.items() if v[1] == "samsung"]
for b in ["Apple", "Belkin", "Anker", "ESR", "Generic", "Lumo"]:
    add("wireless_charger", b, f"{b} MagSafe Wireless Charger", "Magnetic wireless charging pad for iPhone with MagSafe.", iphones, 1.0)
for b in ["Belkin", "Anker", "Nomad"]:
    add("wireless_charger", b, f"{b} 3-in-1 MagSafe Charging Station", "Wireless charging stand for iPhone, Apple Watch and AirPods.", iphones, 2.2)
for b in ["Anker", "Generic", "Zeta", "Belkin", "Brio"]:
    add("wireless_charger", b, f"{b} 15W Qi Wireless Charging Pad", "Universal Qi wireless charger pad for iPhone, Galaxy and Pixel.", ["any"], 0.8)
add("wireless_charger", "Samsung", "Samsung 15W Wireless Charger Duo", "Samsung wireless charging pad for Galaxy phone and Galaxy Watch.", galaxies, 1.4)
add("wireless_charger", "Google", "Google Pixel Stand 2", "Wireless charging stand for Pixel.", ["pixel8", "pixel8pro"], 2.4)

# --- cables
for b in ["Anker", "Apple", "Belkin", "Generic", "Zeta", "Samsung", "Lumo"]:
    for length in ("3ft", "6ft", "10ft"):
        if rng.random() < 0.6:
            add("cable", b, f"{b} USB-C to USB-C Cable {length}", f"Fast charging USB-C cable {length} for Galaxy, Pixel, iPhone 15 and laptops.", ["any"], {"3ft": 0.9, "6ft": 1.0, "10ft": 1.3}[length])
lightning = [d for d, v in DEVICES.items() if v[2] == "lightning"]
for b in ["Apple", "Anker", "Belkin", "Generic", "Brio"]:
    for length in ("3ft", "6ft"):
        add("cable", b, f"{b} USB-C to Lightning Cable {length}", f"MFi certified Lightning charging cable for iPhone 14 and earlier, {length}.", lightning, 1.0)
for b in ["Generic", "Zeta"]:
    add("cable", b, f"{b} Micro USB Cable 3 Pack", "Micro USB charging cable for older Android phones and speakers.", ["legacy"], 0.6)

# --- earbuds
for b, name, mult, fits in [("Apple", "AirPods Pro 2", 3.0, ["any"]), ("Apple", "AirPods 4", 1.6, ["any"]),
                            ("Samsung", "Galaxy Buds3 Pro", 3.0, ["any"]), ("Samsung", "Galaxy Buds FE", 1.2, ["any"]),
                            ("Google", "Pixel Buds Pro 2", 2.8, ["any"]), ("Sony", "WF-1000XM5 Noise Cancelling Earbuds", 3.6, ["any"]),
                            ("Bose", "QuietComfort Ultra Earbuds", 3.6, ["any"]), ("Anker", "Soundcore Liberty 4 NC Earbuds", 1.0, ["any"]),
                            ("Anker", "Soundcore P20i Earbuds", 0.35, ["any"])]:
    add("earbuds", b, f"{b} {name}", f"Wireless earbuds{' with active noise cancellation' if mult > 1 else ''}, Bluetooth, charging case.", fits, mult)
for b in BUDGET:
    for feat in ("Wireless Earbuds Bluetooth 5.3", "Noise Cancelling Wireless Earbuds", "Sports Wireless Earbuds with Ear Hooks"):
        if rng.random() < 0.7:
            add("earbuds", b, f"{b} {feat}", f"Budget {feat.lower()} with mic and charging case.", ["any"], 0.6)

# --- power banks
for b in ["Anker", "Belkin", "Generic", "Zeta", "Lumo", "Samsung"]:
    for cap in (5000, 10000, 20000):
        if rng.random() < 0.6:
            add("power_bank", b, f"{b} {cap}mAh Power Bank", f"Portable charger battery pack {cap}mAh with USB-C fast charging.", ["any"], cap / 10000)
for b in ["Anker", "ESR", "Belkin", "Generic"]:
    add("power_bank", b, f"{b} Magnetic MagSafe Power Bank 5000mAh", "Magnetic wireless portable charger for iPhone MagSafe.", iphones, 1.6)

# --- watch bands
for w, (wname, eco) in WATCHES.items():
    for style in ("Sport Band", "Nylon Sport Loop", "Leather Band", "Metal Link Band", "Silicone Bands 3 Pack"):
        for b in ([OFFICIAL[eco]] if style in ("Sport Band", "Leather Band") else []) + rng.sample(BUDGET, 1) + rng.sample(MID, 1):
            add("watch_band", b, f"{b} {style} for {wname}", f"{style} compatible with {wname}.", [w], 1.6 if "Leather" in style or "Metal" in style else 1.0)

# --- car mounts, grips, stands
for b in ["ESR", "Belkin", "Anker", "Generic"]:
    add("car_mount", b, f"{b} MagSafe Car Vent Mount", "Magnetic car phone mount for iPhone MagSafe.", iphones, 1.2)
for b in ["Generic", "Zeta", "Lumo", "Brio", "Spigen"]:
    add("car_mount", b, f"{b} Universal Car Phone Holder", "Adjustable clamp car vent and dashboard phone mount, fits any phone.", ["any"], 0.8)
for b in ["Generic", "Anker"]:
    add("car_mount", b, f"{b} Wireless Charging Car Mount Auto Clamp", "15W Qi wireless charging car mount for iPhone and Galaxy.", ["any"], 1.6)
for b in ["PopSockets", "Generic", "ESR"]:
    add("phone_grip", b, f"{b} MagSafe Phone Grip and Stand", "Magnetic phone grip for iPhone MagSafe.", iphones, 1.4)
    add("phone_grip", b, f"{b} Phone Grip and Stand", "Adhesive phone grip and stand for any phone.", ["any"], 0.9)
for b in ["Generic", "Lumo", "Anker", "Belkin"]:
    add("phone_stand", b, f"{b} Adjustable Phone Stand for Desk", "Aluminum cell phone stand holder for any phone.", ["any"], 1.0)

# --- distractors
for t in ["iPad 10th Gen", "iPad Air", "Galaxy Tab S9", "Galaxy Tab A9"]:
    for b in ["ESR", "Generic"]:
        add("tablet_case", b, f"{b} Case for {t}", f"Trifold stand tablet case for {t}.", ["tablet"], 1.0)
for b, t in [("Samsung", "Galaxy A15 Unlocked Phone"), ("Google", "Pixel 8a Unlocked Phone"), ("Generic", "Refurbished iPhone 13 128GB")]:
    add("phone", b, f"{b} {t}", "Unlocked cell phone.", ["self"], 1.0)
for b in ["Generic", "Lumo"]:
    add("phone_charm", b, f"{b} Phone Case Charm Strap", "Beaded phone case charm and lanyard.", ["any"], 1.0)

# combine with the hand-written catalog
catalog = [list(r) for r in small.CATALOG] + products
with open(OUT / "catalog.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["product_id", "title", "description", "category", "brand", "price", "rating", "review_count", "fits"])
    w.writerows(catalog)

# devices file: aliases used by the rules judge to read device names in searches
dev_yaml = {d: {"name": v[0], "ecosystem": v[1], "aliases": [v[0].lower()]} for d, v in DEVICES.items()}
dev_yaml.update({w: {"name": v[0], "ecosystem": v[1], "aliases": [v[0].lower()]} for w, v in WATCHES.items()})
with open(OUT / "devices.yaml", "w") as f:
    yaml.safe_dump(dev_yaml, f, sort_keys=False)
with open(OUT / "segments.yaml", "w") as f:
    yaml.safe_dump(small.SEGMENTS, f, sort_keys=False, width=100)

# ---------------------------------------------------------------- shoppers
by_id = {r[0]: r for r in catalog}
median = {}
for c in CATEGORY_PRICE:
    ps = sorted(r[5] for r in catalog if r[3] == c)
    median[c] = ps[len(ps) // 2] if ps else 1
PRICE_TASTE = {"budget": -1.6, "apple_premium": 0.5, "samsung_loyal": -0.2, "multi_device": -0.2}
BRAND_LOVE = {"apple_premium": "Apple", "samsung_loyal": "Samsung"}


def utility(r, seg, devices):
    fits = set(r[8].split(";"))
    if fits & {"self", "tablet", "legacy"}:
        return -9
    u = 0.0
    if not fits & {"any"}:
        if not fits & set(devices):
            return -9
        u += 1.0
    u += PRICE_TASTE[seg] * math.log(r[5] / median[r[3]])
    u += 1.2 * (r[6] - 4.3) + 0.12 * math.log1p(r[7])
    if BRAND_LOVE.get(seg) == r[4]:
        u += 1.2
    return u


def pick(cands, seg, devices, temp=1.0):
    us = [utility(r, seg, devices) / temp for r in cands]
    m = max(us)
    if m < -8:
        return None
    ws = [math.exp(u - m) if u > -8 else 0 for u in us]
    return rng.choices(cands, weights=ws)[0]


SEG_DEVICES = {
    "apple_premium": (["iphone15", "iphone15pro", "iphone15promax", "iphone16", "iphone14"], 0.6, "applewatch"),
    "samsung_loyal": (["galaxys24", "galaxys24ultra", "galaxys23", "galaxys22", "galaxya54"], 0.45, "galaxywatch"),
    "budget": (["iphone13", "iphone14", "galaxya15", "galaxya54", "pixel7", "galaxys22", "iphone15"], 0.3, None),
    "multi_device": (list(DEVICES), 0.4, None),
}
CAT_TASTE = {  # how much each segment buys / searches each category
    "apple_premium": {"phone_case": 3, "screen_protector": 2, "wireless_charger": 2.5, "charger": 1.5, "cable": 1.2, "earbuds": 1.5, "power_bank": 1.2, "watch_band": 2, "car_mount": 1, "phone_grip": 0.8},
    "samsung_loyal": {"phone_case": 3, "screen_protector": 2, "charger": 2, "wireless_charger": 1.2, "cable": 1.2, "earbuds": 1.5, "power_bank": 1, "watch_band": 1.5, "car_mount": 1, "phone_grip": 0.6},
    "budget": {"phone_case": 3.5, "screen_protector": 2.5, "charger": 2, "cable": 2, "earbuds": 1.5, "power_bank": 1, "car_mount": 1, "watch_band": 0.6, "wireless_charger": 0.5, "phone_grip": 0.5},
    "multi_device": {"phone_case": 2.5, "screen_protector": 1.5, "charger": 2, "wireless_charger": 1.5, "cable": 2, "earbuds": 1.5, "power_bank": 1.5, "car_mount": 1, "watch_band": 1, "phone_stand": 1},
}

users = []
for uid, seg, devices, hist, _ in small.USERS:
    users.append({"user_id": uid, "segment": seg, "devices": devices, "history": hist})
n = 0
for seg, (devs, watch_p, watch) in SEG_DEVICES.items():
    for _ in range(50):
        n += 1
        if seg == "multi_device":
            devices = rng.sample([d for d in devs if DEVICES[d][1] == "apple"], 1) + rng.sample([d for d in devs if DEVICES[d][1] != "apple"], 1)
            if rng.random() < 0.4:
                devices.append(rng.choice(list(WATCHES)))
        else:
            devices = [rng.choice(devs)]
            if watch and rng.random() < watch_p:
                devices.append(watch)
            elif seg == "budget" and rng.random() < 0.25:
                devices.append("applewatch" if DEVICES[devices[0]][1] == "apple" else "galaxywatch")
        hist = []
        cats = CAT_TASTE[seg]
        for _ in range(rng.randint(3, 10 if seg == "multi_device" else 7)):
            c = rng.choices(list(cats), weights=list(cats.values()))[0]
            r = pick([r for r in catalog if r[3] == c], seg, devices)
            if r and r[0] not in hist:
                hist.append(r[0])
        users.append({"user_id": f"S{n:03d}", "segment": seg, "devices": devices, "history": hist})
with open(OUT / "users.jsonl", "w") as f:
    for u in users:
        f.write(json.dumps(u) + "\n")

# ---------------------------------------------------------------- searches
PHRASES = {
    "phone_case": ["phone case", "case", "cover", "protective case"],
    "screen_protector": ["screen protector", "tempered glass", "screen guard"],
    "charger": ["charger", "fast charger", "wall charger", "charging block", "power adapter"],
    "wireless_charger": ["wireless charger", "charging pad", "magsafe charger", "wireless charging stand"],
    "cable": ["usb c cable", "charging cable", "lightning cable", "charger cord"],
    "earbuds": ["earbuds", "wireless earbuds", "noise cancelling earbuds", "bluetooth headphones"],
    "power_bank": ["power bank", "portable charger", "battery pack"],
    "watch_band": ["watch band", "watch strap"],
    "car_mount": ["car mount", "car phone holder"],
    "phone_grip": ["phone grip", "popsocket"],
    "phone_stand": ["phone stand", "desk phone holder"],
}
ATTRS = {"phone_case": ["clear", "rugged", "wallet", "slim", "leather", "silicone", "magsafe"],
         "screen_protector": ["privacy", "camera lens"], "charger": ["65w", "20w", "3 port", "usb c"],
         "cable": ["6ft", "10ft", "3ft"], "power_bank": ["20000mah", "magnetic", "10000mah"],
         "watch_band": ["leather", "nylon", "metal"], "earbuds": ["sports", "noise cancelling"]}
DEVICE_CATS = {"phone_case", "screen_protector"}
BRAND_P = {"apple_premium": 0.18, "samsung_loyal": 0.15, "budget": 0.04, "multi_device": 0.08}
CHEAP_P = {"apple_premium": 0.01, "samsung_loyal": 0.04, "budget": 0.22, "multi_device": 0.04}
DEVICE_P = {"apple_premium": 0.45, "samsung_loyal": 0.45, "budget": 0.3, "multi_device": 0.35}


def typo(s):
    i = rng.randrange(len(s) - 1)
    if s[i] == " " or s[i + 1] == " ":
        return s
    return s[:i] + s[i + 1] + s[i] + s[i + 2:]


rows = []
qn = 0
seg_users = {}
for u in users:
    seg_users.setdefault(u["segment"], []).append(u)
for seg in small.SEGMENTS:
    cats = CAT_TASTE[seg]
    for _ in range(1000):
        u = rng.choice(seg_users[seg])
        owns_watch = any(d in WATCHES for d in u["devices"])
        c = rng.choices(list(cats), weights=[w if (k != "watch_band" or owns_watch) else 0 for k, w in cats.items()])[0]
        phrase = rng.choice(PHRASES[c])
        if phrase == "lightning cable" and not any(DEVICES.get(d, ("", "", ""))[2] == "lightning" for d in u["devices"]):
            phrase = "usb c cable"
        if phrase == "magsafe charger" and not any(DEVICES.get(d, ("", "", "", False))[3] for d in u["devices"]):
            phrase = "wireless charger"
        q = phrase
        r = rng.random()
        phones = [d for d in u["devices"] if d in DEVICES]
        watches = [d for d in u["devices"] if d in WATCHES]
        if c in DEVICE_CATS and phones and r < DEVICE_P[seg]:
            q = f"{DEVICES[rng.choice(phones)][0].lower()} {phrase.replace('phone ', '')}"
        elif c == "watch_band" and watches and r < 0.7:
            q = f"{WATCHES[watches[0]][0].lower()} band"
        elif c in ATTRS and r < DEVICE_P[seg] + 0.2:
            a = rng.choice(ATTRS[c])
            if a == "magsafe" and not any(DEVICES.get(d, ("", "", "", False))[3] for d in phones):
                a = "clear"
            q = f"{a} {phrase}"
        if rng.random() < BRAND_P[seg]:
            q = f"{rng.choice([BRAND_LOVE.get(seg) or rng.choice(MID), rng.choice(MID)]).lower()} {q}"
        if rng.random() < CHEAP_P[seg]:
            q = f"cheap {q}"
        if rng.random() < 0.03:
            q = typo(q)
        qn += 1
        rows.append([f"Q{qn:05d}", u["user_id"], seg, q])
with open(OUT / "queries.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["query_id", "user_id", "segment", "query"])
    w.writerows(rows)
# golden labels are shared with the small store
(OUT / "golden.csv").write_text((ROOT / "data" / "mock" / "golden.csv").read_text())
print(f"wrote {len(catalog)} products, {len(users)} shoppers, {len(rows)} searches "
      f"({len({r[3] for r in rows})} distinct keywords) to {OUT}")

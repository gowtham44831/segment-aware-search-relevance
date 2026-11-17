"""Generate the mock dataset used to demo and test relkit.

Everything here is invented: a small phone-accessories catalog, four shopper
segments, 20 shoppers with purchase histories, 4 search terms per shopper and a
simulated click log. Replace these files with your own data (see README).

Run:  python scripts/make_mock.py   (writes data/mock/*)
"""
import csv
import json
import random
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "mock"
OUT.mkdir(parents=True, exist_ok=True)

# product_id, title, description, category, brand, price, rating, reviews, fits
# fits = device models the item fits ("any" = works with any phone)
CATALOG = [
    # --- phone cases
    ("CASE-IP15-SIL", "Apple iPhone 15 Silicone Case with MagSafe", "Official Apple silicone case for iPhone 15, soft microfiber lining, MagSafe compatible.", "phone_case", "Apple", 49.00, 4.7, 12000, "iphone15"),
    ("CASE-IP15-CLR", "Spigen Ultra Hybrid Clear Case for iPhone 15", "Crystal clear protective phone case for iPhone 15 with air cushion corners.", "phone_case", "Spigen", 15.99, 4.6, 45000, "iphone15"),
    ("CASE-IP15-BUD", "Slim TPU Case for iPhone 15, 2 Pack", "Thin flexible clear phone case for iPhone 15, two pack, budget.", "phone_case", "Generic", 6.99, 4.1, 3100, "iphone15"),
    ("CASE-IP15PM-CLR", "Clear Case for iPhone 15 Pro Max", "Shockproof clear phone case for iPhone 15 Pro Max 6.7 inch.", "phone_case", "ESR", 13.99, 4.5, 9000, "iphone15promax"),
    ("CASE-IP14-OTB", "OtterBox Defender Series Case for iPhone 14", "Rugged multi-layer phone case for iPhone 14 with holster.", "phone_case", "OtterBox", 54.95, 4.7, 21000, "iphone14"),
    ("CASE-IP14-BUD", "Shockproof Clear Case for iPhone 14", "Affordable clear phone case for iPhone 14, anti-yellowing.", "phone_case", "Generic", 7.49, 4.2, 5200, "iphone14"),
    ("CASE-S24-SIL", "Samsung Galaxy S24 Silicone Case", "Official Samsung silicone phone case for Galaxy S24, soft touch.", "phone_case", "Samsung", 29.99, 4.6, 6400, "galaxys24"),
    ("CASE-S24-CLR", "Spigen Liquid Air Case for Galaxy S24", "Matte black slim phone case for Samsung Galaxy S24.", "phone_case", "Spigen", 12.99, 4.7, 18000, "galaxys24"),
    ("CASE-S24-BUD", "Clear TPU Case for Galaxy S24, 2 Pack", "Budget clear phone case for Samsung Galaxy S24, two pack.", "phone_case", "Generic", 5.99, 4.0, 1900, "galaxys24"),
    ("CASE-S23-OTB", "OtterBox Commuter Case for Galaxy S23", "Slim protective phone case for Samsung Galaxy S23.", "phone_case", "OtterBox", 39.95, 4.6, 7700, "galaxys23"),
    ("CASE-PX8-CLR", "Clear Case for Google Pixel 8", "Slim clear phone case for Pixel 8 with raised camera lip.", "phone_case", "Spigen", 11.99, 4.5, 4300, "pixel8"),
    ("CASE-UNI-POUCH", "Universal Waterproof Phone Pouch", "Waterproof phone pouch bag fits any phone up to 7 inch, for beach and swimming.", "phone_case", "Generic", 8.99, 4.3, 26000, "any"),
    ("CASE-IPAD-10", "Case for iPad 10th Generation", "Trifold stand tablet case for iPad 10th gen 10.9 inch.", "tablet_case", "ESR", 19.99, 4.6, 14000, "ipad10"),
    ("CHARM-CASE", "Phone Case Charm Keychain", "Cute beaded phone case charm strap and keychain lanyard.", "phone_charm", "Generic", 4.99, 4.4, 800, "any"),
    # --- chargers
    ("CHG-APL-20W", "Apple 20W USB-C Power Adapter", "Official Apple fast charger wall plug, USB-C power adapter.", "charger", "Apple", 19.00, 4.8, 90000, "any"),
    ("CHG-ANK-65W", "Anker 65W GaN Charger, 3 Port", "Compact fast charger with 2 USB-C and 1 USB-A ports for phone and laptop.", "charger", "Anker", 45.99, 4.7, 30000, "any"),
    ("CHG-SAM-45W", "Samsung 45W Super Fast Charger", "Samsung super fast charging 2.0 USB-C wall charger for Galaxy S24 Ultra.", "charger", "Samsung", 34.99, 4.7, 15000, "galaxys24;galaxys23"),
    ("CHG-SAM-25W", "Samsung 25W USB-C Fast Charger", "Samsung super fast charging wall charger for Galaxy phones.", "charger", "Samsung", 14.99, 4.7, 52000, "galaxys24;galaxys23"),
    ("CHG-GEN-20W", "20W USB-C Fast Charger, 2 Pack", "Budget USB-C fast charger wall plug block, two pack.", "charger", "Generic", 9.99, 4.3, 11000, "any"),
    ("CHG-MAG-APL", "Apple MagSafe Charger 1m", "Magnetic wireless charger for iPhone 12 and later, MagSafe.", "wireless_charger", "Apple", 39.00, 4.6, 40000, "iphone15;iphone14;iphone15promax"),
    ("CHG-MAG-BEL", "Belkin 3-in-1 MagSafe Charging Stand", "Wireless charging stand for iPhone, Apple Watch and AirPods.", "wireless_charger", "Belkin", 129.99, 4.5, 8000, "iphone15;iphone14;iphone15promax"),
    ("CHG-QI-GEN", "15W Qi Wireless Charging Pad", "Universal Qi wireless charger pad for iPhone, Galaxy and Pixel.", "wireless_charger", "Generic", 13.99, 4.2, 9500, "any"),
    ("CHG-SAM-WL", "Samsung Wireless Charger Duo", "Samsung wireless charging pad for Galaxy phone and Galaxy Watch.", "wireless_charger", "Samsung", 59.99, 4.5, 6100, "galaxys24;galaxys23"),
    # --- cables
    ("CBL-C2L-APL", "Apple USB-C to Lightning Cable 1m", "Official Apple charging cable for iPhone 14 and earlier with Lightning port.", "cable", "Apple", 19.00, 4.7, 38000, "iphone14"),
    ("CBL-C2C-APL", "Apple 240W USB-C Charge Cable 2m", "Apple woven USB-C to USB-C cable for iPhone 15, iPad and Mac.", "cable", "Apple", 29.00, 4.7, 9000, "any"),
    ("CBL-C2C-ANK", "Anker USB-C to USB-C Cable 6ft, 2 Pack", "Durable fast charging USB-C cable for Galaxy, Pixel and iPhone 15.", "cable", "Anker", 12.99, 4.8, 60000, "any"),
    ("CBL-C2L-GEN", "Lightning Cable 3 Pack 6ft", "Budget iPhone charger cable, Lightning, three pack.", "cable", "Generic", 8.99, 4.2, 22000, "iphone14"),
    ("CBL-C2C-SAM", "Samsung 5A USB-C Cable 1m", "Samsung USB-C to USB-C cable for 45W super fast charging.", "cable", "Samsung", 14.99, 4.6, 7000, "any"),
    ("CBL-MICRO-GEN", "Micro USB Cable 3 Pack", "Micro USB charging cable for older Android phones and speakers.", "cable", "Generic", 6.99, 4.3, 15000, "legacy"),
    # --- screen protectors
    ("SCR-IP15-GLS", "Tempered Glass Screen Protector for iPhone 15, 3 Pack", "9H tempered glass screen protector for iPhone 15 with install frame.", "screen_protector", "Generic", 8.99, 4.5, 33000, "iphone15"),
    ("SCR-IP15-PRV", "Privacy Screen Protector for iPhone 15", "Anti-spy privacy tempered glass for iPhone 15.", "screen_protector", "ZAGG", 24.99, 4.3, 5000, "iphone15"),
    ("SCR-IP14-GLS", "Screen Protector for iPhone 14, 3 Pack", "Tempered glass screen protector for iPhone 14.", "screen_protector", "Generic", 7.99, 4.5, 28000, "iphone14"),
    ("SCR-S24-GLS", "Tempered Glass Screen Protector for Galaxy S24", "Screen protector for Samsung Galaxy S24, fingerprint unlock compatible.", "screen_protector", "Generic", 9.99, 4.4, 12000, "galaxys24"),
    ("SCR-S24-FLM", "Samsung Anti-Reflecting Film for Galaxy S24", "Official Samsung screen protector film for Galaxy S24.", "screen_protector", "Samsung", 19.99, 4.2, 2100, "galaxys24"),
    ("SCR-PX8-GLS", "Screen Protector for Pixel 8, 2 Pack", "Tempered glass screen protector for Google Pixel 8.", "screen_protector", "Generic", 8.99, 4.4, 6000, "pixel8"),
    # --- earbuds
    ("AUD-APP-PRO2", "Apple AirPods Pro 2 with USB-C", "Wireless earbuds with active noise cancellation, made for iPhone.", "earbuds", "Apple", 249.00, 4.7, 110000, "any"),
    ("AUD-APP-4", "Apple AirPods 4", "Wireless earbuds with personalized spatial audio for iPhone.", "earbuds", "Apple", 129.00, 4.5, 20000, "any"),
    ("AUD-SAM-BUD3P", "Samsung Galaxy Buds3 Pro", "Wireless earbuds with noise cancelling, best with Galaxy phones.", "earbuds", "Samsung", 249.99, 4.4, 6000, "any"),
    ("AUD-SAM-FE", "Samsung Galaxy Buds FE", "Affordable wireless earbuds with ANC for Galaxy.", "earbuds", "Samsung", 99.99, 4.4, 14000, "any"),
    ("AUD-SNY-XM5", "Sony WF-1000XM5 Wireless Earbuds", "Premium noise cancelling wireless earbuds, works with iPhone and Android.", "earbuds", "Sony", 299.99, 4.4, 9000, "any"),
    ("AUD-SDC-LIB", "Soundcore Liberty 4 NC Wireless Earbuds", "Noise cancelling wireless earbuds with long battery life.", "earbuds", "Anker", 79.99, 4.4, 35000, "any"),
    ("AUD-GEN-BUD", "Wireless Earbuds Bluetooth 5.3", "Budget wireless earbuds with charging case and mic.", "earbuds", "Generic", 18.99, 4.2, 47000, "any"),
    # --- power banks
    ("PWR-ANK-10K", "Anker Power Bank 10000mAh", "Portable charger battery pack with USB-C, slim.", "power_bank", "Anker", 25.99, 4.6, 70000, "any"),
    ("PWR-MAG-ANK", "Anker MagGo Magnetic Power Bank", "Magnetic wireless portable charger for iPhone, MagSafe.", "power_bank", "Anker", 69.99, 4.4, 9000, "iphone15;iphone14;iphone15promax"),
    ("PWR-SAM-10K", "Samsung 10000mAh 25W Battery Pack", "Samsung super fast charging portable battery for Galaxy.", "power_bank", "Samsung", 39.99, 4.5, 5000, "any"),
    ("PWR-GEN-20K", "20000mAh Portable Charger Power Bank", "Budget high capacity power bank with 2 USB outputs.", "power_bank", "Generic", 17.99, 4.3, 25000, "any"),
    # --- watch bands
    ("WAT-AW-SPT", "Apple Watch Sport Band 45mm", "Official Apple fluoroelastomer sport band for Apple Watch.", "watch_band", "Apple", 49.00, 4.7, 15000, "applewatch"),
    ("WAT-AW-GEN", "Nylon Bands for Apple Watch, 3 Pack", "Budget nylon sport loop bands compatible with Apple Watch.", "watch_band", "Generic", 11.99, 4.4, 30000, "applewatch"),
    ("WAT-GW-SPT", "Samsung Galaxy Watch Sport Band 20mm", "Official Samsung sport band for Galaxy Watch 6 and 7.", "watch_band", "Samsung", 24.99, 4.5, 3000, "galaxywatch"),
    ("WAT-GW-GEN", "Silicone Bands for Galaxy Watch, 3 Pack", "Budget 20mm bands compatible with Samsung Galaxy Watch.", "watch_band", "Generic", 9.99, 4.4, 11000, "galaxywatch"),
    # --- car mounts and grips
    ("CAR-MAG-ESR", "ESR MagSafe Car Mount", "Magnetic car vent phone mount for iPhone MagSafe.", "car_mount", "ESR", 29.99, 4.5, 16000, "iphone15;iphone14;iphone15promax"),
    ("CAR-UNI-VNT", "Universal Car Vent Phone Mount", "Adjustable clamp car phone holder fits any phone.", "car_mount", "Generic", 10.99, 4.3, 41000, "any"),
    ("CAR-WL-AUT", "Wireless Charging Car Mount, Auto Clamp", "15W Qi wireless charging car phone mount for iPhone and Galaxy.", "car_mount", "Generic", 34.99, 4.2, 12000, "any"),
    ("GRP-POP-MAG", "PopSockets MagSafe PopGrip", "Magnetic phone grip and stand for iPhone MagSafe.", "phone_grip", "PopSockets", 29.99, 4.5, 20000, "iphone15;iphone14;iphone15promax"),
    ("GRP-POP-STD", "PopSockets PopGrip", "Adhesive phone grip and stand for any phone.", "phone_grip", "PopSockets", 12.99, 4.7, 150000, "any"),
    ("STD-UNI-ADJ", "Adjustable Phone Stand for Desk", "Aluminum cell phone stand holder for any phone.", "phone_stand", "Generic", 11.99, 4.6, 33000, "any"),
    # --- a phone (lexical trap for "phone ..." queries)
    ("PHN-SAM-A15", "Samsung Galaxy A15 Unlocked Phone", "Budget Android cell phone, 128GB, unlocked.", "phone", "Samsung", 199.99, 4.3, 4000, "self"),
]

SEGMENTS = {
    "apple_premium": {
        "name": "Apple premium mainstream",
        "description": "Owns an iPhone and often an Apple Watch. Prefers official Apple or well-known brands, pays for quality, values MagSafe and fit with the Apple ecosystem.",
        "price_sensitivity": "low",
        "ecosystem": "apple",
    },
    "samsung_loyal": {
        "name": "Samsung loyalists",
        "description": "Owns a Samsung Galaxy phone and often a Galaxy Watch. Prefers Samsung or brands made for Galaxy, mid-range prices.",
        "price_sensitivity": "medium",
        "ecosystem": "samsung",
    },
    "budget": {
        "name": "Budget hunters",
        "description": "Mixed devices. Looks for low prices and multi-packs but still wants well-reviewed items that fit their phone.",
        "price_sensitivity": "high",
        "ecosystem": "mixed",
    },
    "multi_device": {
        "name": "Frequent multi-device buyers",
        "description": "Buys often for several devices (e.g. an iPhone and a Galaxy in one household). Brand-neutral, mid-to-high spend, values universal and multi-device accessories.",
        "price_sensitivity": "medium",
        "ecosystem": "mixed",
    },
}

# user_id, segment, devices, history (product ids, oldest first), search terms
USERS = [
    ("U01", "apple_premium", ["iphone15", "applewatch"], ["CASE-IP15-SIL", "CHG-MAG-APL", "WAT-AW-SPT", "AUD-APP-PRO2", "CBL-C2C-APL"], ["phone case", "screen protector", "car mount", "power bank"]),
    ("U02", "apple_premium", ["iphone15"], ["CHG-APL-20W", "CASE-IP15-CLR", "AUD-APP-4", "GRP-POP-MAG"], ["wireless charger", "phone case", "earbuds", "phone grip"]),
    ("U03", "apple_premium", ["iphone14", "applewatch"], ["CASE-IP14-OTB", "CBL-C2L-APL", "WAT-AW-SPT", "CHG-APL-20W"], ["charging cable", "screen protector", "watch band", "magsafe charger"]),
    ("U04", "apple_premium", ["iphone15promax"], ["CASE-IP15PM-CLR", "CHG-MAG-BEL", "AUD-APP-PRO2"], ["phone case", "car mount", "fast charger", "power bank"]),
    ("U05", "apple_premium", ["iphone15", "applewatch"], ["WAT-AW-SPT", "CASE-IP15-SIL", "PWR-MAG-ANK"], ["watch band", "earbuds", "wireless charger", "usb c cable"]),
    ("U06", "samsung_loyal", ["galaxys24", "galaxywatch"], ["CASE-S24-SIL", "CHG-SAM-45W", "WAT-GW-SPT", "AUD-SAM-BUD3P"], ["phone case", "screen protector", "power bank", "car mount"]),
    ("U07", "samsung_loyal", ["galaxys24"], ["CASE-S24-CLR", "CHG-SAM-25W", "CBL-C2C-SAM"], ["fast charger", "wireless charger", "earbuds", "phone case"]),
    ("U08", "samsung_loyal", ["galaxys23", "galaxywatch"], ["CASE-S23-OTB", "WAT-GW-SPT", "CHG-SAM-25W"], ["watch band", "phone case", "usb c cable", "wireless charger"]),
    ("U09", "samsung_loyal", ["galaxys24", "galaxywatch"], ["SCR-S24-FLM", "AUD-SAM-FE", "CHG-SAM-WL", "WAT-GW-GEN"], ["screen protector", "earbuds", "charger", "phone grip"]),
    ("U10", "samsung_loyal", ["galaxys23"], ["CHG-SAM-45W", "PWR-SAM-10K"], ["phone case", "car mount", "fast charger", "screen protector"]),
    ("U11", "budget", ["iphone14"], ["CASE-IP14-BUD", "CBL-C2L-GEN", "CHG-GEN-20W"], ["cheap phone case", "charging cable", "earbuds", "screen protector"]),
    ("U12", "budget", ["galaxys24"], ["CASE-S24-BUD", "CHG-GEN-20W", "AUD-GEN-BUD"], ["phone case", "screen protector", "power bank", "charger"]),
    ("U13", "budget", ["pixel8"], ["CASE-PX8-CLR", "CBL-C2C-ANK", "PWR-GEN-20K"], ["screen protector", "phone case", "wireless charger", "earbuds"]),
    ("U14", "budget", ["iphone15", "applewatch"], ["CASE-IP15-BUD", "WAT-AW-GEN", "SCR-IP15-GLS"], ["watch band", "charger", "car mount", "phone case"]),
    ("U15", "budget", ["galaxys23", "galaxywatch"], ["WAT-GW-GEN", "CHG-GEN-20W", "AUD-GEN-BUD"], ["cheap earbuds", "phone case", "usb c cable", "watch band"]),
    ("U16", "multi_device", ["iphone15", "galaxys24"], ["CHG-ANK-65W", "CBL-C2C-ANK", "CASE-IP15-CLR", "CASE-S24-CLR", "PWR-ANK-10K", "AUD-SNY-XM5"], ["wireless charger", "phone case", "car mount", "screen protector"]),
    ("U17", "multi_device", ["iphone14", "galaxys23", "applewatch"], ["CBL-C2L-APL", "CASE-S23-OTB", "CHG-ANK-65W", "WAT-AW-SPT", "CHG-QI-GEN"], ["charging cable", "watch band", "power bank", "phone case"]),
    ("U18", "multi_device", ["iphone15", "pixel8"], ["CASE-PX8-CLR", "SCR-IP15-GLS", "AUD-SDC-LIB", "CBL-C2C-ANK", "STD-UNI-ADJ"], ["fast charger", "earbuds", "phone stand", "screen protector"]),
    ("U19", "multi_device", ["galaxys24", "iphone15promax"], ["CASE-IP15PM-CLR", "CASE-S24-SIL", "CHG-ANK-65W", "CAR-WL-AUT"], ["phone case", "power bank", "usb c cable", "earbuds"]),
    ("U20", "multi_device", ["iphone15", "galaxys24", "galaxywatch"], ["CHG-QI-GEN", "WAT-GW-SPT", "PWR-ANK-10K", "CASE-IP15-SIL", "CASE-S24-CLR", "AUD-SAM-BUD3P"], ["watch band", "car mount", "charger", "screen protector"]),
]


def main():
    with open(OUT / "catalog.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["product_id", "title", "description", "category", "brand", "price", "rating", "review_count", "fits"])
        w.writerows(CATALOG)

    import yaml
    with open(OUT / "segments.yaml", "w") as f:
        yaml.safe_dump(SEGMENTS, f, sort_keys=False, width=100)

    with open(OUT / "users.jsonl", "w") as f:
        for uid, seg, devices, hist, _ in USERS:
            f.write(json.dumps({"user_id": uid, "segment": seg, "devices": devices, "history": hist}) + "\n")

    with open(OUT / "queries.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["query_id", "user_id", "query"])
        n = 0
        for uid, _, _, _, terms in USERS:
            for t in terms:
                n += 1
                w.writerow([f"Q{n:03d}", uid, t])
    print(f"wrote {len(CATALOG)} products, {len(SEGMENTS)} segments, {len(USERS)} users, {n} queries to {OUT}")


if __name__ == "__main__":
    random.seed(7)
    main()

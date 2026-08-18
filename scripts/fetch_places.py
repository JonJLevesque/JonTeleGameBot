"""Build places.json: ~2000 famous scenic places with photo URLs.

Pulls named places (mountains, lakes, islands, castles, cities, World
Heritage sites, ...) from Wikidata ranked by fame (sitelink count), then
resolves each item's Commons photo to a direct 1280px thumbnail URL that
Telegram can fetch. No API keys required.

Run from the repo root:  .venv/bin/python scripts/fetch_places.py
"""
import json
import sys
import time
import urllib.parse

import httpx

SPARQL = "https://query.wikidata.org/sparql"
COMMONS = "https://commons.wikimedia.org/w/api.php"
UA = "PartyBot-places-fetcher/1.0 (Telegram group game; contact: local script)"
TARGET = 2000

# (wikidata class or heritage flag, human label, max items, min sitelinks)
SOURCES = [
    ("Q8502",   "mountain",            300, 25),
    ("Q8072",   "volcano",              80, 20),
    ("Q34038",  "waterfall",           120, 15),
    ("Q23397",  "lake",                200, 25),
    ("Q46169",  "national park",       160, 15),
    ("Q23442",  "island",              160, 30),
    ("Q40080",  "beach",                60, 10),
    ("Q150784", "canyon",               60, 10),
    ("Q35666",  "glacier",              60, 15),
    ("Q45776",  "fjord",                30,  8),
    ("Q39594",  "bay",                  50, 20),
    ("Q8514",   "desert",               50, 20),
    ("Q35509",  "cave",                 50, 15),
    ("Q4022",   "river",               100, 40),
    ("Q23413",  "castle",              150, 20),
    ("Q16560",  "palace",              100, 25),
    ("Q44613",  "monastery",            60, 20),
    ("Q39715",  "lighthouse",           40, 10),
    ("Q12280",  "bridge",               60, 30),
    ("Q839954", "archaeological site", 120, 30),
    ("Q570116", "tourist attraction",  150, 20),
    ("Q515",    "city",                220, 60),
    ("WHS",     "world heritage site", 250, 20),
    ("Q2977",   "cathedral",            80, 25),
    ("Q32815",  "mosque",               60, 25),
    ("Q44539",  "temple",               60, 15),
    ("Q39816",  "valley",               40, 15),
    ("Q33837",  "archipelago",          40, 25),
    ("Q167346", "botanical garden",     30, 10),
]

BAD_EXT = (".svg", ".gif", ".webm", ".ogv", ".pdf", ".stl", ".xcf", ".djvu")


def sparql(query: str) -> list[dict]:
    for attempt in range(4):
        try:
            r = httpx.get(
                SPARQL,
                params={"query": query, "format": "json"},
                headers={"User-Agent": UA},
                timeout=120,
            )
            if r.status_code == 429:
                time.sleep(10 * (attempt + 1))
                continue
            r.raise_for_status()
            return r.json()["results"]["bindings"]
        except (httpx.HTTPError, KeyError, ValueError) as e:
            print(f"    retry {attempt + 1}: {e}", file=sys.stderr)
            time.sleep(5 * (attempt + 1))
    return []


def query_source(qid: str, limit: int, min_links: int) -> str:
    if qid == "WHS":
        member = "?item wdt:P1435 wd:Q9259; wdt:P18 ?image; wikibase:sitelinks ?links."
    else:
        member = f"?item wdt:P31 wd:{qid}; wdt:P18 ?image; wikibase:sitelinks ?links."
    return f"""
    SELECT ?item ?itemLabel ?countryLabel ?image ?links WHERE {{
      {{ SELECT ?item (SAMPLE(?img) AS ?image) (MAX(?l) AS ?links) WHERE {{
           {member.replace('?image', '?img').replace('?links', '?l')}
           FILTER(?l >= {min_links})
         }} GROUP BY ?item ORDER BY DESC(?links) LIMIT {limit} }}
      OPTIONAL {{ ?item wdt:P17 ?country. }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}"""


def filename_from_p18(url: str) -> str | None:
    # http://commons.wikimedia.org/wiki/Special:FilePath/Matterhorn.jpg
    marker = "Special:FilePath/"
    if marker not in url:
        return None
    name = urllib.parse.unquote(url.split(marker, 1)[1]).replace("_", " ")
    if name.lower().endswith(BAD_EXT):
        return None
    return name[:1].upper() + name[1:]


def resolve_thumbs(filenames: list[str]) -> dict[str, str]:
    """Commons filename -> direct 1280px thumburl on upload.wikimedia.org."""
    out: dict[str, str] = {}
    for i in range(0, len(filenames), 50):
        batch = filenames[i : i + 50]
        for attempt in range(3):
            try:
                r = httpx.get(
                    COMMONS,
                    params={
                        "action": "query",
                        "titles": "|".join("File:" + f for f in batch),
                        "prop": "imageinfo",
                        "iiprop": "url|mime",
                        "iiurlwidth": 1280,
                        "redirects": 1,
                        "format": "json",
                    },
                    headers={"User-Agent": UA},
                    timeout=60,
                )
                r.raise_for_status()
                data = r.json().get("query", {})
                renamed = {
                    n["to"]: n["from"] for n in data.get("normalized", [])
                }
                for page in data.get("pages", {}).values():
                    info = (page.get("imageinfo") or [{}])[0]
                    thumb = info.get("thumburl")
                    mime = info.get("mime", "")
                    if not thumb or mime in ("image/svg+xml", "image/gif"):
                        continue
                    title = renamed.get(page["title"], page["title"])
                    out[title.removeprefix("File:")] = thumb
                break
            except (httpx.HTTPError, ValueError) as e:
                print(f"    commons retry {attempt + 1}: {e}", file=sys.stderr)
                time.sleep(5)
        time.sleep(0.3)
        print(f"  thumbs {min(i + 50, len(filenames))}/{len(filenames)}")
    return out


def main():
    by_item: dict[str, dict] = {}
    for qid, label, limit, min_links in SOURCES:
        print(f"query: {label} (up to {limit})")
        rows = sparql(query_source(qid, limit, min_links))
        added = 0
        for row in rows:
            item = row["item"]["value"].rsplit("/", 1)[1]
            if item in by_item:
                continue
            name = row.get("itemLabel", {}).get("value", "")
            if not name or name == item:  # no english label
                continue
            fname = filename_from_p18(row["image"]["value"])
            if not fname:
                continue
            by_item[item] = {
                "name": name,
                "country": row.get("countryLabel", {}).get("value", ""),
                "kind": label,
                "links": int(row["links"]["value"]),
                "file": fname,
            }
            added += 1
        print(f"  +{added} new (total {len(by_item)})")
        time.sleep(1)

    places = sorted(by_item.values(), key=lambda p: -p["links"])
    # Dedupe photos: two items sometimes share the same Commons file.
    seen_files: set[str] = set()
    places = [
        p for p in places
        if not (p["file"] in seen_files or seen_files.add(p["file"]))
    ]

    print(f"resolving thumbnails for {len(places)} files...")
    thumbs = resolve_thumbs([p["file"] for p in places])

    final = []
    for p in places:
        url = thumbs.get(p["file"])
        if not url:
            continue
        final.append(
            {
                "id": len(final),
                "name": p["name"],
                "country": p["country"],
                "kind": p["kind"],
                "img": url,
            }
        )
        if len(final) >= TARGET:
            break

    with open("places.json", "w") as f:
        json.dump(final, f, ensure_ascii=False, indent=0)
    print(f"wrote places.json with {len(final)} places")


if __name__ == "__main__":
    main()

"""Download one freely licensed photo per team (its home ballpark) from Wikimedia Commons.

One-time script; the photos and credits are committed, so the app never downloads anything.
- Source: the main image of each ballpark's English Wikipedia article, hosted on Wikimedia Commons.
- Only free licenses are accepted (Creative Commons BY / BY-SA / CC0, or public domain). Logos are skipped.
- If the article's photo isn't usable, Commons is searched for other free landscape photos of the ballpark;
  only then is the city's article image (usually a skyline) used.
- Photos are resized to 1280 px wide and re-compressed (Pillow, a build-time-only dependency).
- Credits (photographer, license, source page) go to frontend/public/teams/credits.json; the app shows
  them under every photo, as the licenses require.

Usage:
  python scripts/fetch_team_photos.py
"""

from __future__ import annotations

import html
import json
import re
import sys
import time
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "frontend" / "public" / "teams"
UA = {"User-Agent": "MLBVirtualManager/1.0 (MGT 409 class project; https://github.com/cjm277/mlb-virtual-manager)"}
FREE = re.compile(r"^(cc[- ]by(-sa)?[- ]?\d|cc0|public domain|pd)", re.I)

# team_id: (ballpark article, city article for the fallback)
TEAMS = {
    108: ("Angel Stadium", "Anaheim, California"), 109: ("Chase Field", "Phoenix, Arizona"),
    110: ("Oriole Park at Camden Yards", "Baltimore"), 111: ("Fenway Park", "Boston"),
    112: ("Wrigley Field", "Chicago"), 113: ("Great American Ball Park", "Cincinnati"),
    114: ("Progressive Field", "Cleveland"), 115: ("Coors Field", "Denver"), 116: ("Comerica Park", "Detroit"),
    117: ("Daikin Park", "Houston"), 118: ("Kauffman Stadium", "Kansas City, Missouri"),
    119: ("Dodger Stadium", "Los Angeles"), 120: ("Nationals Park", "Washington, D.C."),
    121: ("Citi Field", "Queens"), 133: ("Sutter Health Park", "Sacramento, California"),
    134: ("PNC Park", "Pittsburgh"), 135: ("Petco Park", "San Diego"), 136: ("T-Mobile Park", "Seattle"),
    137: ("Oracle Park", "San Francisco"), 138: ("Busch Stadium", "St. Louis"),
    139: ("Tropicana Field", "St. Petersburg, Florida"), 140: ("Globe Life Field", "Arlington, Texas"),
    141: ("Rogers Centre", "Toronto"), 142: ("Target Field", "Minneapolis"),
    143: ("Citizens Bank Park", "Philadelphia"), 144: ("Truist Park", "Atlanta"), 145: ("Rate Field", "Chicago"),
    146: ("LoanDepot Park", "Miami"), 147: ("Yankee Stadium", "The Bronx"),
    158: ("American Family Field", "Milwaukee"),
}


# Hand-picked after reviewing a contact sheet: the automatic pick for these was an anthem singer (Citi Field),
# a thin panorama (Great American Ball Park), and a grey exterior (Rogers Centre).
OVERRIDES = {
    113: "Great American Ball Park (15550307823).jpg",
    121: "Citi Field Night Game.jpg",
    141: "The Blue Jays host the Orioles in the AL Wild Card Game (30243609331).jpg",
}


def try_file(team_id: int) -> dict | None:
    name = OVERRIDES.get(team_id)
    info = commons_info(name) if name else None
    return {**info, "file": name, "article": TEAMS[team_id][0]} if info and info["free"] else None


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", text or ""))).strip()


def page_image(title: str) -> str | None:
    r = requests.get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(title.replace(' ', '_'))}",
                     headers=UA, timeout=30)
    if r.status_code != 200:
        return None
    src = (r.json().get("originalimage") or {}).get("source", "").split("?")[0]   # drop tracking parameters
    name = src.rsplit("/", 1)[-1]
    return requests.utils.unquote(name) if name else None


def commons_info(filename: str) -> dict | None:
    r = requests.get("https://commons.wikimedia.org/w/api.php", headers=UA, timeout=30, params={
        "action": "query", "format": "json", "titles": f"File:{filename}", "prop": "imageinfo",
        "iiprop": "url|size|extmetadata", "iiurlwidth": 1600})
    pages = r.json()["query"]["pages"]
    page = next(iter(pages.values()))
    if "imageinfo" not in page:
        return None   # not on Commons (e.g. a non-free image uploaded only to Wikipedia)
    info = page["imageinfo"][0]
    meta = info.get("extmetadata", {})
    lic = clean(meta.get("LicenseShortName", {}).get("value", ""))
    return {"license": lic, "free": bool(FREE.match(lic)), "license_url": meta.get("LicenseUrl", {}).get("value", ""),
            "author": clean(meta.get("Artist", {}).get("value", "")) or "Unknown",
            "width": info["width"], "height": info["height"], "thumb": info.get("thumburl") or info["url"],
            "source": info["descriptionurl"]}


def try_title(title: str) -> dict | None:
    name = page_image(title)
    if not name or "logo" in name.lower() or name.lower().endswith((".svg", ".png", ".gif")):
        return None
    info = commons_info(name)
    if not info or not info["free"] or info["width"] < info["height"]:   # free, landscape photos only
        return None
    return {**info, "file": name, "article": title}


def search_commons(query: str, limit: int = 15) -> list[str]:
    r = requests.get("https://commons.wikimedia.org/w/api.php", headers=UA, timeout=30, params={
        "action": "query", "format": "json", "list": "search", "srnamespace": 6, "srlimit": limit,
        "srsearch": f'"{query}" filetype:bitmap'})
    names = [h["title"].removeprefix("File:") for h in r.json().get("query", {}).get("search", [])]
    skip = ("logo", "map", "seat", "ticket", "sign", "plaque", "statue", "diagram", "chart", "jersey")
    return [n for n in names if n.lower().endswith((".jpg", ".jpeg")) and not any(s in n.lower() for s in skip)]


def try_search(query: str) -> dict | None:
    for name in search_commons(query):
        info = commons_info(name)
        if info and info["free"] and info["width"] >= 1.3 * info["height"] and info["width"] >= 1200:
            return {**info, "file": name, "article": query}
        time.sleep(0.2)
    return None


def shrink(data: bytes) -> bytes:
    from PIL import Image
    img = Image.open(BytesIO(data)).convert("RGB")
    if img.width > 1280:
        img = img.resize((1280, round(img.height * 1280 / img.width)), Image.LANCZOS)
    out = BytesIO()
    img.save(out, "JPEG", quality=74, optimize=True, progressive=True)
    return out.getvalue()


def make_thumbs() -> None:
    """Small versions for the landing-page mosaic (so it doesn't load 30 full photos)."""
    from PIL import Image
    (OUT / "thumbs").mkdir(exist_ok=True)
    for f in OUT.glob("*.jpg"):
        img = Image.open(f).convert("RGB")
        img.thumbnail((360, 240))
        img.save(OUT / "thumbs" / f.name, "JPEG", quality=70, optimize=True)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    OUT.mkdir(parents=True, exist_ok=True)
    credits = {}
    for team_id, (park, city) in TEAMS.items():
        chosen, kind = None, None
        for finder, arg, k in ((try_file, team_id, "ballpark"), (try_title, park, "ballpark"),
                               (try_search, park, "ballpark"), (try_title, city, "city")):
            chosen = finder(arg)
            if chosen:
                kind = k
                break
            time.sleep(0.3)
        if not chosen:
            print(f"{team_id}: no free photo found")
            continue
        img = requests.get(chosen["thumb"], headers=UA, timeout=60)
        img.raise_for_status()
        data = shrink(img.content)
        (OUT / f"{team_id}.jpg").write_bytes(data)
        credits[team_id] = {"kind": kind, "subject": chosen["article"], "author": chosen["author"][:120],
                            "license": chosen["license"], "license_url": chosen["license_url"],
                            "source": chosen["source"]}
        print(f"{team_id}: {kind:8s} {chosen['article']:28s} {chosen['license']:14s} "
              f"{len(data) // 1024:4d} KB  by {chosen['author'][:40]}")
        time.sleep(0.5)
    (OUT / "credits.json").write_text(json.dumps(credits, indent=2, ensure_ascii=False), encoding="utf-8")
    make_thumbs()
    print(f"\n{len(credits)} of {len(TEAMS)} teams have a photo. Credits: {OUT / 'credits.json'}")


if __name__ == "__main__":
    main()

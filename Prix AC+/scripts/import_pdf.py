#!/usr/bin/env python3
import argparse
import datetime
import json
import os
import re
import sys
import tempfile
import urllib.request
from typing import Optional

try:
    import pdfplumber
except Exception:
    pdfplumber = None

PRICE_RE = re.compile(r"\d+(?:[.,]\d+)?\s*€")
RANGE_RE = re.compile(r"\d+\s*[–-]\s*\d+\s*€")


def normalize(text: str) -> str:
    text = text.lower()
    text = text.replace("–", "-").replace("—", "-")
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    # Repair common PDF extraction artifacts like "a pple" or "i mac"
    text = re.sub(r"\b([a-z])\s+([a-z])\b", r"\1\2", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_tables(pdf_path: str):
    tables = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_tables = page.extract_tables() or []
            for table in page_tables:
                for row in table:
                    if not row:
                        continue
                    cells = [cell.strip() if cell else "" for cell in row]
                    if any(cells):
                        tables.append(cells)
    return tables


def extract_text_rows(pdf_path: str):
    rows = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.splitlines():
                line = line.strip()
                if line:
                    rows.append([line])
    return rows


def extract_text_blocks(pdf_path: str) -> list[str]:
    blocks = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if text.strip():
                blocks.append(text)
    return blocks


def find_price_tokens(text: str):
    tokens = []
    tokens.extend(RANGE_RE.findall(text))
    for match in PRICE_RE.findall(text):
        if match not in tokens:
            tokens.append(match)
    return tokens


ALIASES = {
    "iphone-17-pro": [r"\biphone 17 pro\b"],
    "iphone-17-pro-max": [r"\biphone 17 pro max\b", r"\b17 pro max\b"],
    "iphone-air": [r"\biphone air\b"],
    "iphone-17": [r"\biphone 17, 16\b", r"\biphone 17\b"],
    "iphone-16": [r"\biphone 17, 16\b", r"\biphone 16\b(?!\s*(e|plus))"],
    "iphone-16-plus": [r"\biphone 16 plus\b"],
    "iphone-16e": [r"\biphone 16e\b"],
    "ipad-10-a16": [r"\bipad, ipad mini\b", r"\bipad\b.*\ba16\b", r"\bipad \(a16\)\b"],
    "ipad-mini-a17-pro": [r"\bipad, ipad mini\b", r"\bipad mini\b.*\ba17 pro\b", r"\bipad mini \(a17 pro\)\b"],
    "ipad-air-11": [r"\bipad air 11\b", r"\bipad air 11\b.*\bm3\b", r"\bipad air 11\b.*\bm2\b"],
    "ipad-air-13": [r"\bipad air 13\b", r"\bipad air 13\b.*\bm3\b", r"\bipad air 13\b.*\bm2\b"],
    "ipad-pro-11": [r"\bipad pro 11\b.*\bm5\b", r"\bipad pro 11\b.*\bm4\b"],
    "ipad-pro-13": [r"\bipad pro 13\b.*\bm5\b", r"\bipad pro 13\b.*\bm4\b"],
    "watch-se-3": [r"\bapple watch\b.*\bse\b"],
    "watch-series-11": [r"\bapple watch\b.*\bseries\b.*\b11\b"],
    "watch-ultra-3": [r"\bapple watch\b.*\bultra\b"],
    "watch-hermes-11": [r"\bapple watch edition\b", r"\bherm[eè]s\b.*\bultra\b"],
    "watch-hermes-ultra-3": [r"\bapple watch edition\b", r"\bherm[eè]s\b.*\bultra\b"],
    "macbook-air-13": [r"\bmacbook air 13\b"],
    "macbook-air-15": [r"\bmacbook air 15\b"],
    "macbook-pro-14": [r"\bmacbook pro 14\b"],
    "macbook-pro-16": [r"\bmacbook pro 16\b"],
    "imac": [r"\bimac\b"],
    "mac-mini": [r"\bmac mini\b"],
    "mac-studio": [r"\bmac studio\b"],
    "mac-pro": [r"\bmac pro\b"],
    "studio-display": [r"\bstudio display\b"],
    "pro-display-xdr": [r"\bpro display xdr\b", r"\bpro display\b"],
    "airpods-4": [r"\bairpods, airpods pro\b.*\b2e\b", r"\bairpods\b"],
    "airpods-4-anc": [r"\bairpods, airpods pro\b.*\b2e\b", r"\bairpods\b"],
    "airpods-pro-3": [r"\bairpods pro\b.*\b3e\b", r"\bairpods pro\b.*\b3\b"],
    "airpods-max": [r"\bairpods max\b"],
    "appletv-4k": [r"\bapple tv\b"],
    "homepod-mini": [r"\bhomepod mini\b"],
    "homepod-2": [r"\bhomepod\b(?! mini)"],
    "beats-studio-pro": [r"\bbeats\b"],
    "beats-solo-4": [r"\bbeats\b"],
    "beats-solo-buds": [r"\bbeats\b"],
    "powerbeats-fit": [r"\bbeats\b"],
    "powerbeats-pro-2": [r"\bbeats\b"],
    "beats-studio-buds-plus": [r"\bbeats\b"],
    "beats-flex": [r"\bbeats\b"],
    "beats-pill": [r"\bbeats\b"],
}


def choose_row(item_id: str, product_name: str, rows):
    candidates = ALIASES.get(item_id, [])
    if candidates:
        for pattern in candidates:
            regex = re.compile(pattern)
            for row in rows:
                row_text = " ".join(row)
                row_norm = normalize(row_text)
                if regex.search(row_norm):
                    return row_text
        return None

    target = normalize(product_name)
    target_words = [w for w in target.split(" ") if w]
    best = None
    best_score = 0
    for row in rows:
        row_text = " ".join(row)
        row_norm = normalize(row_text)
        if not row_norm:
            continue
        score = sum(1 for w in target_words if w in row_norm)
        if score > best_score:
            best_score = score
            best = row_text
    if best_score >= max(2, len(target_words) // 2):
        return best
    return None


def search_in_text(product_id: str, product_name: str, text_blocks: list[str]) -> Optional[str]:
    patterns = ALIASES.get(product_id, [])
    if not patterns:
        patterns = [re.escape(product_name)]
    for block in text_blocks:
        for pattern in patterns:
            flexible = pattern.replace(" ", r"\W+")
            regex = re.compile(flexible, re.IGNORECASE)
            match = regex.search(block)
            if not match:
                continue
            start = match.end()
            window = block[start:start + 600]
            prices = find_price_tokens(window)
            if prices:
                return window
    return None


def update_prices(catalog: dict, rows, text_blocks, category_ids):
    matched = 0
    total = 0
    updates = []

    for category in catalog.get("categories", []):
        if category["id"] not in category_ids:
            continue
        for item in category.get("items", []):
            total += 1
            item_id = item.get("id", "")
            row_text = choose_row(item_id, item.get("name", ""), rows)
            used_text_search = False
            if not row_text and text_blocks:
                row_text = search_in_text(item_id, item.get("name", ""), text_blocks)
                used_text_search = True
            if not row_text:
                updates.append({"id": item_id, "status": "no-match"})
                continue
            prices = find_price_tokens(row_text)
            applecare = item.get("appleCare", {})
            expected = 1
            if applecare.get("standardMonthly") is not None:
                expected = 2

            if len(prices) < expected and not used_text_search and text_blocks:
                fallback_text = search_in_text(item_id, item.get("name", ""), text_blocks)
                if fallback_text:
                    row_text = fallback_text
                    prices = find_price_tokens(row_text)
                    used_text_search = True

            if len(prices) < expected:
                updates.append({"id": item_id, "status": "not-enough-prices", "row": row_text})
                continue

            if expected == 2:
                applecare["standardOneTime"] = prices[0]
                applecare["standardMonthly"] = prices[1]
            else:
                applecare["standardOneTime"] = prices[0]

            if len(prices) >= 4:
                applecare["theftOneTime"] = prices[2]
                applecare["theftMonthly"] = prices[3]

            item["appleCare"] = applecare
            matched += 1
            updates.append({"id": item_id, "status": "updated", "row": row_text})

    return matched, total, updates


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if pdfplumber is None:
        print("pdfplumber is not installed. Run: python3 -m pip install pdfplumber", file=sys.stderr)
        sys.exit(1)

    with open(args.config, "r", encoding="utf-8") as f:
        config = json.load(f)

    pdf_url = config.get("pdf_url")
    mac_pdf_url = config.get("mac_pdf_url")
    if not pdf_url:
        print("Missing pdf_url in import-config.json", file=sys.stderr)
        sys.exit(1)

    with open(args.output, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    tmp_dir = tempfile.mkdtemp(prefix="acplus-")
    pdf_path = os.path.join(tmp_dir, "main.pdf")

    urllib.request.urlretrieve(pdf_url, pdf_path)
    rows = extract_tables(pdf_path)
    text_blocks = extract_text_blocks(pdf_path)
    if not rows:
        rows = extract_text_rows(pdf_path)

    matched_main, total_main, updates_main = update_prices(
        catalog,
        rows,
        text_blocks,
        category_ids={"iphone", "ipad", "watch", "airpods", "beats", "appletv", "homepod"}
    )

    if mac_pdf_url:
        mac_pdf_path = os.path.join(tmp_dir, "mac.pdf")
        urllib.request.urlretrieve(mac_pdf_url, mac_pdf_path)
        mac_rows = extract_tables(mac_pdf_path)
        mac_blocks = extract_text_blocks(mac_pdf_path)
        if not mac_rows:
            mac_rows = extract_text_rows(mac_pdf_path)
        matched_mac, total_mac, updates_mac = update_prices(
            catalog,
            mac_rows,
            mac_blocks,
            category_ids={"mac"}
        )
    else:
        matched_mac, total_mac, updates_mac = 0, 0, []

    total = total_main + total_mac
    matched = matched_main + matched_mac
    ratio = (matched / total) if total else 0

    report = {
        "matched": matched,
        "total": total,
        "ratio": ratio,
        "main": updates_main,
        "mac": updates_mac
    }

    report_path = os.path.join(os.path.dirname(args.output), "import-report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=4)

    if ratio < 1.0 and not args.force:
        print("Not all items matched ({} / {}). Report written to Data/import-report.json".format(matched, total), file=sys.stderr)
        sys.exit(2)

    catalog["lastUpdated"] = datetime.date.today().isoformat()
    catalog["sources"] = [pdf_url] + ([mac_pdf_url] if mac_pdf_url else [])

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=4)

    print("Updated {} (matched {}/{})".format(args.output, matched, total))


if __name__ == "__main__":
    main()

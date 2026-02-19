#!/usr/bin/env python3
import argparse
import datetime
import json
import os
import re
import sys
import tempfile
import urllib.request

try:
    import pdfplumber
except Exception:
    pdfplumber = None

PRICE_RE = re.compile(r"\d+(?:[.,]\d+)?\s*€")
RANGE_RE = re.compile(r"\d+\s*[–-]\s*\d+\s*€")


def normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
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


def find_price_tokens(text: str):
    tokens = []
    tokens.extend(RANGE_RE.findall(text))
    for match in PRICE_RE.findall(text):
        if match not in tokens:
            tokens.append(match)
    return tokens


def choose_row(product_name: str, rows):
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


def update_prices(catalog: dict, rows, category_ids):
    matched = 0
    total = 0
    updates = []

    for category in catalog.get("categories", []):
        if category["id"] not in category_ids:
            continue
        for item in category.get("items", []):
            total += 1
            row_text = choose_row(item.get("name", ""), rows)
            if not row_text:
                updates.append({"id": item.get("id"), "status": "no-match"})
                continue
            prices = find_price_tokens(row_text)
            applecare = item.get("appleCare", {})
            expected = 0
            if applecare.get("theftOneTime") is not None or applecare.get("theftMonthly") is not None:
                expected = 4
            elif applecare.get("standardMonthly") is not None:
                expected = 2
            else:
                expected = 1

            if len(prices) < expected:
                updates.append({"id": item.get("id"), "status": "not-enough-prices", "row": row_text})
                continue

            if expected == 4:
                applecare["standardOneTime"] = prices[0]
                applecare["standardMonthly"] = prices[1]
                applecare["theftOneTime"] = prices[2]
                applecare["theftMonthly"] = prices[3]
            elif expected == 2:
                applecare["standardOneTime"] = prices[0]
                applecare["standardMonthly"] = prices[1]
            else:
                applecare["standardOneTime"] = prices[0]

            item["appleCare"] = applecare
            matched += 1
            updates.append({"id": item.get("id"), "status": "updated", "row": row_text})

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
    if not rows:
        rows = extract_text_rows(pdf_path)

    matched_main, total_main, updates_main = update_prices(
        catalog,
        rows,
        category_ids={"iphone", "ipad", "watch", "airpods", "beats", "appletv", "homepod"}
    )

    if mac_pdf_url:
        mac_pdf_path = os.path.join(tmp_dir, "mac.pdf")
        urllib.request.urlretrieve(mac_pdf_url, mac_pdf_path)
        mac_rows = extract_tables(mac_pdf_path)
        if not mac_rows:
            mac_rows = extract_text_rows(mac_pdf_path)
        matched_mac, total_mac, updates_mac = update_prices(
            catalog,
            mac_rows,
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

    if ratio < 0.6 and not args.force:
        print("Too few matches ({} / {}). Report written to Data/import-report.json".format(matched, total), file=sys.stderr)
        sys.exit(2)

    catalog["lastUpdated"] = datetime.date.today().isoformat()
    catalog["sources"] = [pdf_url] + ([mac_pdf_url] if mac_pdf_url else [])

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=4)

    print("Updated {} (matched {}/{})".format(args.output, matched, total))


if __name__ == "__main__":
    main()

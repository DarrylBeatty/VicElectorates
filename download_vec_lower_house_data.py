#!/usr/bin/env python3
"""Download Victorian lower house electorate results from the VEC website.

The script attempts to discover the most recent Victorian state election page, then
collects lower house electorate pages and extracts:

1) Current MP/member for each electorate.
2) Candidate vote totals for the electorate (last state election).
3) Booth-level voting table values.

Because VEC can change page templates over time, this script uses heuristic table
matching and will preserve unknown columns rather than dropping them.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import logging
import re
import sys
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

USER_AGENT = "Mozilla/5.0 (compatible; vec-data-downloader/1.0; +https://www.vec.vic.gov.au)"
DEFAULT_START_URL = "https://www.vec.vic.gov.au/results/state-election-results"


@dataclass
class HtmlLink:
    href: str
    text: str


class LinkExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[HtmlLink] = []
        self._inside_a = False
        self._href = ""
        self._text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attr_dict = dict(attrs)
        href = attr_dict.get("href")
        if not href:
            return
        self._inside_a = True
        self._href = href
        self._text_parts = []

    def handle_data(self, data: str) -> None:
        if self._inside_a:
            self._text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or not self._inside_a:
            return
        text = " ".join("".join(self._text_parts).split())
        self.links.append(HtmlLink(href=self._href, text=html.unescape(text)))
        self._inside_a = False
        self._href = ""
        self._text_parts = []


class TableExtractor(HTMLParser):
    """Minimal HTML table parser that returns all tables as rows of cell strings."""

    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._in_table = False
        self._in_row = False
        self._in_cell = False
        self._current_table: list[list[str]] = []
        self._current_row: list[str] = []
        self._cell_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "table":
            self._in_table = True
            self._current_table = []
        elif tag == "tr" and self._in_table:
            self._in_row = True
            self._current_row = []
        elif tag in {"th", "td"} and self._in_row:
            self._in_cell = True
            self._cell_parts = []

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"th", "td"} and self._in_cell:
            value = " ".join("".join(self._cell_parts).split())
            self._current_row.append(html.unescape(value))
            self._in_cell = False
            self._cell_parts = []
        elif tag == "tr" and self._in_row:
            if any(cell for cell in self._current_row):
                self._current_table.append(self._current_row)
            self._in_row = False
            self._current_row = []
        elif tag == "table" and self._in_table:
            if self._current_table:
                self.tables.append(self._current_table)
            self._in_table = False
            self._current_table = []


def fetch_text(url: str, timeout: int = 60) -> str:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def extract_links(html_text: str, base_url: str) -> list[HtmlLink]:
    parser = LinkExtractor()
    parser.feed(html_text)
    resolved = []
    for link in parser.links:
        href = urljoin(base_url, link.href)
        resolved.append(HtmlLink(href=href, text=link.text))
    return resolved


def discover_latest_election_page(start_url: str) -> str:
    page = fetch_text(start_url)
    links = extract_links(page, start_url)

    candidates: list[tuple[int, str]] = []
    for link in links:
        text = link.text.lower()
        href = link.href.lower()
        if "state" not in text and "state" not in href:
            continue
        if "election" not in text and "election" not in href:
            continue
        year_matches = re.findall(r"(20\d{2})", f"{link.text} {link.href}")
        year = max((int(y) for y in year_matches), default=0)
        if year:
            candidates.append((year, link.href))

    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    # Fallback: sometimes the landing page already is the latest election page.
    return start_url


def is_likely_lower_house_link(link: HtmlLink) -> bool:
    target = f"{link.text} {link.href}".lower()
    lower_keywords = (
        "district",
        "electoral district",
        "legislative assembly",
        "lower house",
        "district results",
    )
    exclude_keywords = (
        "region",
        "legislative council",
        "upper house",
        "privacy",
        "contact",
        "facebook",
        "twitter",
        "linkedin",
        "instagram",
    )
    return any(k in target for k in lower_keywords) and not any(k in target for k in exclude_keywords)


def discover_electorate_links(election_url: str) -> list[HtmlLink]:
    page = fetch_text(election_url)
    links = extract_links(page, election_url)

    filtered: list[HtmlLink] = []
    seen: set[str] = set()
    for link in links:
        if not is_likely_lower_house_link(link):
            continue
        normalized = link.href.rstrip("/")
        if normalized in seen:
            continue
        seen.add(normalized)
        filtered.append(HtmlLink(href=normalized, text=link.text.strip()))

    # Some election pages have an intermediate "district results" page.
    if len(filtered) <= 3:
        seed_links = [l for l in links if "district" in (l.text + l.href).lower()]
        for seed in seed_links:
            try:
                subpage = fetch_text(seed.href)
            except Exception:
                continue
            sublinks = extract_links(subpage, seed.href)
            for link in sublinks:
                if not is_likely_lower_house_link(link):
                    continue
                normalized = link.href.rstrip("/")
                if normalized in seen:
                    continue
                seen.add(normalized)
                filtered.append(HtmlLink(href=normalized, text=link.text.strip()))

    # Keep likely electorate pages only (often many links to same page anchors/files).
    cleaned = [
        l
        for l in filtered
        if urlparse(l.href).scheme in {"http", "https"}
        and not l.href.lower().endswith((".pdf", ".doc", ".docx", ".xlsx", ".zip"))
    ]
    return cleaned


def extract_current_mp(page_text: str) -> str:
    # Common patterns from VEC and results microsites.
    patterns = [
        r"Current\s+MP\s*[:\-]\s*([^<\n\r]+)",
        r"Current\s+member\s*[:\-]\s*([^<\n\r]+)",
        r"Sitting\s+member\s*[:\-]\s*([^<\n\r]+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, page_text, flags=re.IGNORECASE)
        if m:
            return " ".join(m.group(1).split()).strip()

    # Inspect text-only fallback.
    text = re.sub(r"<[^>]+>", " ", page_text)
    text = " ".join(html.unescape(text).split())
    m = re.search(r"(?:Current MP|Current member|Sitting member)\s*[:\-]\s*([^|]{3,80})", text, flags=re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return ""


def normalize_header(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def parse_tables(page_text: str) -> list[list[list[str]]]:
    parser = TableExtractor()
    parser.feed(page_text)
    return parser.tables


def choose_candidate_table(tables: list[list[list[str]]]) -> list[list[str]] | None:
    for table in tables:
        header = " ".join((cell.lower() for cell in table[0]))
        if "candidate" in header and "vote" in header:
            return table
    return None


def choose_booth_table(tables: list[list[list[str]]]) -> list[list[str]] | None:
    for table in tables:
        header = " ".join((cell.lower() for cell in table[0]))
        if "booth" in header and "vote" in header:
            return table
    return None


def table_to_dict_rows(table: list[list[str]]) -> list[dict[str, str]]:
    if not table:
        return []
    headers = [normalize_header(h) or f"column_{idx+1}" for idx, h in enumerate(table[0])]
    rows: list[dict[str, str]] = []
    for row in table[1:]:
        if not any(cell.strip() for cell in row):
            continue
        # Pad missing cells.
        row = row + [""] * (len(headers) - len(row))
        row = row[: len(headers)]
        rows.append(dict(zip(headers, row)))
    return rows


def infer_electorate_name(link_text: str, url: str, page_text: str) -> str:
    text = link_text.strip()
    if text and len(text) > 2:
        return re.sub(r"\s+district\b", "", text, flags=re.IGNORECASE).strip()

    # Try H1 title from page.
    m = re.search(r"<h1[^>]*>(.*?)</h1>", page_text, flags=re.IGNORECASE | re.DOTALL)
    if m:
        h1 = re.sub(r"<[^>]+>", "", m.group(1))
        h1 = " ".join(html.unescape(h1).split())
        h1 = re.sub(r"\s+district\b", "", h1, flags=re.IGNORECASE).strip()
        if h1:
            return h1

    slug = urlparse(url).path.rstrip("/").split("/")[-1]
    slug = slug.replace("-", " ").strip()
    return slug.title() or "Unknown"


def write_csv(path: Path, rows: Iterable[dict[str, str]], preferred_headers: list[str] | None = None) -> None:
    rows = list(rows)
    if not rows:
        path.write_text("", encoding="utf-8")
        return

    fieldnames: list[str] = []
    if preferred_headers:
        fieldnames.extend([h for h in preferred_headers if any(h in r for r in rows)])
    extra = sorted({k for r in rows for k in r.keys() if k not in fieldnames})
    fieldnames.extend(extra)

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def run(start_url: str, out_dir: Path, limit: int | None = None) -> None:
    logging.info("Discovering latest election page from %s", start_url)
    election_url = discover_latest_election_page(start_url)
    logging.info("Using election page: %s", election_url)

    electorate_links = discover_electorate_links(election_url)
    if limit is not None:
        electorate_links = electorate_links[:limit]

    logging.info("Found %d potential lower house electorate links", len(electorate_links))

    electorates: list[dict[str, str]] = []
    candidate_votes: list[dict[str, str]] = []
    booth_votes: list[dict[str, str]] = []

    for idx, link in enumerate(electorate_links, start=1):
        logging.info("[%d/%d] Fetching %s", idx, len(electorate_links), link.href)
        try:
            page = fetch_text(link.href)
        except Exception as exc:
            logging.warning("Failed to fetch electorate page %s (%s)", link.href, exc)
            continue

        electorate_name = infer_electorate_name(link.text, link.href, page)
        current_mp = extract_current_mp(page)
        electorates.append(
            {
                "electorate": electorate_name,
                "current_mp": current_mp,
                "source_url": link.href,
                "election_page": election_url,
            }
        )

        tables = parse_tables(page)
        cand_table = choose_candidate_table(tables)
        booth_table = choose_booth_table(tables)

        if cand_table:
            for row in table_to_dict_rows(cand_table):
                row.update({"electorate": electorate_name, "source_url": link.href})
                candidate_votes.append(row)
        else:
            logging.warning("No candidate votes table found for %s", electorate_name)

        if booth_table:
            for row in table_to_dict_rows(booth_table):
                row.update({"electorate": electorate_name, "source_url": link.href})
                booth_votes.append(row)
        else:
            logging.warning("No booth votes table found for %s", electorate_name)

    out_dir.mkdir(parents=True, exist_ok=True)

    write_csv(
        out_dir / "electorates.csv",
        electorates,
        preferred_headers=["electorate", "current_mp", "source_url", "election_page"],
    )
    write_csv(out_dir / "candidate_votes.csv", candidate_votes, preferred_headers=["electorate", "candidate", "party", "votes", "source_url"])
    write_csv(out_dir / "booth_votes.csv", booth_votes, preferred_headers=["electorate", "booth", "votes", "source_url"])

    metadata = {
        "start_url": start_url,
        "election_url": election_url,
        "electorate_count": len(electorates),
        "candidate_vote_rows": len(candidate_votes),
        "booth_vote_rows": len(booth_votes),
    }
    (out_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    logging.info("Wrote output files to %s", out_dir)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-url", default=DEFAULT_START_URL, help="VEC results landing page URL")
    parser.add_argument("--out-dir", default="data/vec", help="Output directory for CSV files")
    parser.add_argument("--limit", type=int, default=None, help="Optional limit of electorates to fetch for quick tests")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    try:
        run(start_url=args.start_url, out_dir=Path(args.out_dir), limit=args.limit)
    except Exception as exc:
        logging.error("Failed: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

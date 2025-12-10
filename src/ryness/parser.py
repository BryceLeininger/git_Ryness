"""Parser for Ryness weekly PDF text exports."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from dateutil import parser as date_parser

from .models import (
    CountyAggregate,
    CountySummaryRow,
    FinancialNews,
    ParsedReport,
    ProjectEntry,
    ProjectMetrics,
    RateSnapshot,
    YearlySummaryEntry,
)


NON_DIGIT_RE = re.compile(r"[^0-9.-]+")
PERCENT_RE = re.compile(r"(-?\d+(?:\.\d+)?)%")
DATE_LINE_RE = re.compile(r"Sunday,\s+[A-Za-z]+\s+\d{1,2},\s+\d{4}")
CITY_CODE_RE = re.compile(r"^[A-Z]{2,3}$")
NUMBER_TOKEN_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")
COUNTY_HEADER_RE = re.compile(r"^[A-Za-z0-9 /&'(),.-]+\|[A-Za-z0-9 /&'(),.-]+$")
PAGE_FOOTER_RE = re.compile(r"^\d+\s+of\s+\d+$")

COLUMN_HEADER_MARKERS = {
    "Units",
    "Rel.",
    "Rm'g",
    "Traffic",
    "Wk's",
    "Sales",
    "Cans",
    "Sold",
    "Date",
    "YTD",
    "Av.",
    "/Week",
    "/YTD",
}


@dataclass
class RawProjectRow:
    county_group_name: str
    text_tokens: List[str]
    number_tokens: List[str]
    type_code: str
    city_code: str
    notes_tokens: List[str]
    pre_city_tokens: List[str]


class RynessParser:
    """High-level parser for Ryness weekly report text exports."""

    def parse_text(self, text: str, *, source_pdf: Optional[str] = None) -> ParsedReport:
        lines = [line.rstrip() for line in text.splitlines()]
        week_end_date = self._extract_week_end_date(text)
        region_name = self._extract_region_name(lines)
        yearly_summary = self._parse_yearly_summary(lines)
        county_summary = self._parse_county_summary(lines)
        raw_project_rows = self._collect_project_rows(lines)
        projects = self._finalize_project_rows(raw_project_rows)
        county_aggregates = self._build_county_aggregates(projects)
        financial_news = self._parse_financial_news(lines)

        return ParsedReport(
            region_name=region_name,
            week_end_date=week_end_date,
            source_pdf=source_pdf,
            yearly_summary=yearly_summary,
            county_summary_rows=county_summary,
            projects=projects,
            county_aggregates=county_aggregates,
            financial_news=financial_news,
        )

    # ------------------------------------------------------------------
    # Header extraction
    # ------------------------------------------------------------------
    def _extract_week_end_date(self, text: str) -> date:
        match = re.search(r"Ending:\s*Sunday,\s*([^\n]+)", text)
        if not match:
            raise ValueError("Unable to locate week ending date in report")
        parsed = date_parser.parse(match.group(1), fuzzy=True)
        return parsed.date()

    def _extract_region_name(self, lines: Sequence[str]) -> str:
        for line in lines:
            match = DATE_LINE_RE.search(line)
            if match:
                tail = line[match.end():].strip()
                if tail:
                    return tail
        raise ValueError("Could not determine region name from report")

    # ------------------------------------------------------------------
    # Yearly summary and county overview
    # ------------------------------------------------------------------
    def _parse_yearly_summary(self, lines: Sequence[str]) -> List[YearlySummaryEntry]:
        entries: List[YearlySummaryEntry] = []
        seen_years: set[int] = set()
        for line in lines:
            if not line.startswith("█"):
                continue
            parts = line.replace("█", "").split()
            if len(parts) != 7:
                continue
            year = int(parts[0])
            if year in seen_years:
                continue
            seen_years.add(year)
            entries.append(
                YearlySummaryEntry(
                    calendar_year=year,
                    avg_weekly_projects=Decimal(parts[1]),
                    avg_weekly_traffic=Decimal(parts[2]),
                    avg_weekly_sales=Decimal(parts[3]),
                    avg_weekly_cancels=Decimal(parts[4]),
                    avg_project_sales=Decimal(parts[5]),
                    year_end_avg_project_sales=Decimal(parts[6]),
                )
            )
        return entries

    def _parse_county_summary(self, lines: Sequence[str]) -> List[CountySummaryRow]:
        rows: List[CountySummaryRow] = []
        try:
            start_idx = next(i for i, line in enumerate(lines) if line.startswith("Counties / Groups"))
        except StopIteration:
            return rows

        for line in lines[start_idx + 1 :]:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("Current Week Totals"):
                break
            match = re.match(
                r"^(?P<name>[A-Za-z ,/&'-]+?)\s+"
                r"(?P<projects>\d+)\s+"
                r"(?P<traffic>\d+)\s+"
                r"(?P<sales>\d+)\s+"
                r"(?P<cancels>\d+)\s+"
                r"(?P<net_sales>\d+)\s+"
                r"(?P<avg_sales>\d+(?:\.\d+)?)\s+"
                r"(?P<avg_ytd>\d+(?:\.\d+)?)\s+"
                r"(?P<ytd_delta>-?\d+(?:\.\d+)?)%\s+"
                r"(?P<prev13>\d+(?:\.\d+)?)\s+"
                r"(?P<prev13_delta>-?\d+(?:\.\d+)?)%$",
                stripped,
            )
            if not match:
                continue
            rows.append(
                CountySummaryRow(
                    name=match.group("name"),
                    projects_reporting=int(match.group("projects")),
                    traffic=int(match.group("traffic")),
                    sales=int(match.group("sales")),
                    cancellations=int(match.group("cancels")),
                    net_sales=int(match.group("net_sales")),
                    average_sales=Decimal(match.group("avg_sales")),
                    average_sales_ytd=Decimal(match.group("avg_ytd")),
                    average_sales_ytd_delta_pct=Decimal(match.group("ytd_delta")),
                    average_sales_prev13=Decimal(match.group("prev13")),
                    average_sales_prev13_delta_pct=Decimal(match.group("prev13_delta")),
                )
            )
        return rows

    # ------------------------------------------------------------------
    # Project rows
    # ------------------------------------------------------------------
    def _collect_project_rows(self, lines: Sequence[str]) -> List[RawProjectRow]:
        raw_rows: List[RawProjectRow] = []
        current_county: Optional[str] = None
        skip_mode = False

        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue

            if line.startswith("--- Page") and line.endswith("---"):
                i += 1
                continue

            if DATE_LINE_RE.search(line):
                i += 1
                continue

            if PAGE_FOOTER_RE.fullmatch(line):
                i += 1
                continue

            if line.startswith("Copyright"):
                i += 1
                continue

            if "San Ramon Valley Boulevard" in line or "Danville, California" in line:
                i += 1
                continue

            if line == "THE RYNESS REPORT":
                i += 1
                continue

            if line == "A New Home Sales, Marketing & Research Company":
                i += 1
                continue

            if line.startswith("Sponsored by"):
                i += 1
                continue

            if COUNTY_HEADER_RE.match(line):
                current_county = line.strip()
                skip_mode = False
                i += 1
                continue

            if current_county is None:
                i += 1
                continue

            if "Projects Participating" in line:
                i += 1
                continue

            if line.startswith("TOTALS:"):
                skip_mode = True
                i += 1
                continue

            if line.startswith("City Codes:"):
                current_county = None
                i += 1
                continue

            if skip_mode:
                i += 1
                continue

            if any(token in COLUMN_HEADER_MARKERS for token in line.split()):
                i += 1
                continue

            if NUMBER_TOKEN_RE.search(line) is None:
                i += 1
                continue

            raw_rows.append(self._parse_raw_project_line(current_county, line))
            i += 1

        return raw_rows

    def _parse_raw_project_line(self, county_group: str, line: str) -> RawProjectRow:
        tokens = line.split()
        if not tokens:
            raise ValueError(f"Unable to parse empty project line for county {county_group}")

        number_start = len(tokens)
        while number_start > 0 and (NUMBER_TOKEN_RE.fullmatch(tokens[number_start - 1]) or tokens[number_start - 1] in ["N/A", "TSO"]):
            number_start -= 1
        number_tokens = tokens[number_start:]
        text_tokens = tokens[:number_start]

        if not text_tokens:
            raise ValueError(f"Unable to parse project text tokens: {line}")

        type_code = text_tokens[-1]
        text_tokens = text_tokens[:-1]

        city_index = None
        for idx in range(len(text_tokens) - 1, -1, -1):
            if CITY_CODE_RE.fullmatch(text_tokens[idx]):
                city_index = idx
                break
        if city_index is None:
            raise ValueError(f"Unable to locate city code in line: {line}")

        city_code = text_tokens[city_index]
        notes_tokens = text_tokens[city_index + 1 :] if city_index + 1 < len(text_tokens) else []
        pre_city_tokens = text_tokens[:city_index]

        return RawProjectRow(
            county_group_name=county_group,
            text_tokens=text_tokens,
            number_tokens=number_tokens,
            type_code=type_code,
            city_code=city_code,
            notes_tokens=notes_tokens,
            pre_city_tokens=pre_city_tokens,
        )

    def _finalize_project_rows(self, raw_rows: Sequence[RawProjectRow]) -> List[ProjectEntry]:
        developer_frequency: Counter[Tuple[str, ...]] = Counter()
        for row in raw_rows:
            tokens = row.pre_city_tokens
            max_len = min(3, len(tokens))
            for n in range(1, max_len + 1):
                developer_frequency[tuple(tokens[-n:])] += 1

        projects: List[ProjectEntry] = []
        for row in raw_rows:
            project_name, developer_name = self._split_project_and_developer(row.pre_city_tokens, developer_frequency)
            notes = " ".join(row.notes_tokens) if row.notes_tokens else None
            metrics = self._map_numbers_to_metrics(row.number_tokens)
            projects.append(
                ProjectEntry(
                    county_group_name=row.county_group_name,
                    project_name=project_name,
                    developer_name=developer_name,
                    city_code=row.city_code,
                    product_type_code=row.type_code,
                    notes=notes,
                    metrics=metrics,
                )
            )
        return projects

    def _split_project_and_developer(
        self,
        tokens: Sequence[str],
        frequency: Counter[Tuple[str, ...]],
    ) -> Tuple[str, str]:
        if not tokens:
            raise ValueError("Project tokens empty; cannot determine names")

        max_len = min(3, len(tokens) - 1) if len(tokens) > 1 else 1
        if max_len < 1:
            max_len = 1

        best_suffix: Optional[Tuple[str, ...]] = None
        best_score: Tuple[int, int] = (-1, -1)
        for n in range(1, max_len + 1):
            candidate = tuple(tokens[-n:])
            score = (frequency.get(candidate, 0), n)
            if score > best_score:
                best_score = score
                best_suffix = candidate

        if best_suffix is None:
            best_suffix = (tokens[-1],)

        developer_tokens = list(best_suffix)
        if len(tokens) == len(developer_tokens):
            project_tokens = tokens[:-1]
            developer_tokens = [tokens[-1]]
        else:
            project_tokens = tokens[: -len(developer_tokens)]

        project_name = " ".join(project_tokens).strip()
        developer_name = " ".join(developer_tokens).strip()

        if not project_name:
            project_name = developer_name
        if not developer_name:
            developer_name = tokens[-1]

        return project_name, developer_name

    def _map_numbers_to_metrics(self, number_tokens: Sequence[str]) -> ProjectMetrics:
        # Convert tokens to Decimals, treating N/A and TSO as None
        numbers: List[Optional[Decimal]] = []
        for token in number_tokens:
            if token in ["N/A", "TSO"]:
                numbers.append(None)
            else:
                numbers.append(Decimal(token))
        
        if len(numbers) < 9:
            raise ValueError(f"Unexpected number of numeric columns ({len(numbers)}) in project row: {number_tokens}")

        cancellations = None
        if len(numbers) >= 11:
            cancellations = int(numbers[6]) if numbers[6] is not None else None
            sold_to_date = int(numbers[7]) if numbers[7] is not None and len(numbers) > 7 else None
            sold_ytd = int(numbers[8]) if numbers[8] is not None and len(numbers) > 8 else None
            avg_week = numbers[9] if numbers[9] is not None and len(numbers) > 9 else None
            avg_ytd = numbers[10] if numbers[10] is not None and len(numbers) > 10 else None
        else:
            sold_to_date = int(numbers[6]) if numbers[6] is not None and len(numbers) > 6 else None
            sold_ytd = int(numbers[7]) if numbers[7] is not None and len(numbers) > 7 else None
            avg_week = numbers[8] if numbers[8] is not None and len(numbers) > 8 else None
            avg_ytd = numbers[9] if numbers[9] is not None and len(numbers) > 9 else None

        return ProjectMetrics(
            units_total=int(numbers[0]) if numbers[0] is not None and len(numbers) > 0 else None,
            units_new_released=int(numbers[1]) if numbers[1] is not None and len(numbers) > 1 else None,
            units_released_to_date=int(numbers[2]) if numbers[2] is not None and len(numbers) > 2 else None,
            units_remaining=int(numbers[3]) if numbers[3] is not None and len(numbers) > 3 else None,
            traffic=int(numbers[4]) if numbers[4] is not None and len(numbers) > 4 else None,
            sales_this_week=int(numbers[5]) if numbers[5] is not None and len(numbers) > 5 else None,
            cancellations_this_week=cancellations,
            sold_to_date=sold_to_date,
            sold_year_to_date=sold_ytd,
            average_sales_per_week=avg_week,
            average_sales_per_week_ytd=avg_ytd,
        )

    # ------------------------------------------------------------------
    # Aggregates
    # ------------------------------------------------------------------
    def _build_county_aggregates(self, projects: Sequence[ProjectEntry]) -> List[CountyAggregate]:
        totals: Dict[str, Dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
        ytd_values: Dict[str, List[Decimal]] = defaultdict(list)

        for project in projects:
            metrics = project.metrics
            county = project.county_group_name
            totals[county]["projects"] += 1
            if metrics.traffic is not None:
                totals[county]["traffic"] += Decimal(metrics.traffic)
            if metrics.sales_this_week is not None:
                totals[county]["sales"] += Decimal(metrics.sales_this_week)
            if metrics.cancellations_this_week is not None:
                totals[county]["cancellations"] += Decimal(metrics.cancellations_this_week)
            if metrics.net_sales_this_week is not None:
                totals[county]["net_sales"] += Decimal(metrics.net_sales_this_week)
            if metrics.average_sales_per_week_ytd is not None:
                ytd_values[county].append(metrics.average_sales_per_week_ytd)

        aggregates: List[CountyAggregate] = []
        for county, values in totals.items():
            projects_reporting = int(values["projects"])
            traffic = int(values.get("traffic", Decimal()))
            sales = int(values.get("sales", Decimal()))
            cancellations = int(values.get("cancellations", Decimal()))
            net_sales = int(values.get("net_sales", Decimal()))

            average_sales = None
            if projects_reporting:
                average_sales = Decimal(sales) / Decimal(projects_reporting) if sales else Decimal(0)
            per_project_avg_traffic = None
            if projects_reporting and traffic:
                per_project_avg_traffic = Decimal(traffic) / Decimal(projects_reporting)
            per_project_avg_sales = None
            if projects_reporting and sales:
                per_project_avg_sales = Decimal(sales) / Decimal(projects_reporting)
            per_project_avg_cancels = None
            if projects_reporting and cancellations:
                per_project_avg_cancels = Decimal(cancellations) / Decimal(projects_reporting)
            per_project_avg_net_sales = None
            if projects_reporting and net_sales:
                per_project_avg_net_sales = Decimal(net_sales) / Decimal(projects_reporting)

            ytd_avg = None
            if ytd_values[county]:
                ytd_avg = sum(ytd_values[county]) / Decimal(len(ytd_values[county]))

            traffic_to_sales_ratio = None
            if sales:
                traffic_to_sales_ratio = (
                    Decimal(traffic) / Decimal(sales) if traffic else Decimal(0)
                )

            aggregates.append(
                CountyAggregate(
                    county_group_name=county,
                    projects_reporting=projects_reporting,
                    traffic=traffic,
                    sales=sales,
                    cancellations=cancellations,
                    net_sales=net_sales,
                    average_sales=average_sales,
                    average_sales_year_to_date=ytd_avg,
                    traffic_to_sales_ratio=traffic_to_sales_ratio,
                    per_project_avg_traffic=per_project_avg_traffic,
                    per_project_avg_sales=per_project_avg_sales,
                    per_project_avg_cancellations=per_project_avg_cancels,
                    per_project_avg_net_sales=per_project_avg_net_sales,
                )
            )

        return aggregates

    # ------------------------------------------------------------------
    # Financial news
    # ------------------------------------------------------------------
    def _parse_financial_news(self, lines: Sequence[str]) -> Optional[FinancialNews]:
        try:
            start_idx = next(i for i, line in enumerate(lines) if line.strip() == "WEEKLY FINANCIAL NEWS")
        except StopIteration:
            return None

        headline = ""
        rates: Dict[str, RateSnapshot] = {}
        body_lines: List[str] = []
        author: Optional[str] = None
        source: Optional[str] = None

        i = start_idx + 1
        if i < len(lines):
            headline = lines[i].strip()
            i += 1

        while i < len(lines) and lines[i].strip().upper() != "RATE APR":
            if lines[i].strip():
                body_lines.append(lines[i].strip())
            i += 1

        if i < len(lines) and lines[i].strip().upper() == "RATE APR":
            i += 1
            while i < len(lines):
                line = lines[i].strip()
                if not line:
                    i += 1
                    continue
                if PERCENT_RE.search(line) is None:
                    break
                tokens = line.split()
                name_tokens: List[str] = []
                rate_value: Optional[Decimal] = None
                apr_value: Optional[Decimal] = None
                for token in tokens:
                    percent_match = PERCENT_RE.fullmatch(token)
                    if percent_match and rate_value is None:
                        rate_value = Decimal(percent_match.group(1))
                        continue
                    if percent_match and rate_value is not None:
                        apr_value = Decimal(percent_match.group(1))
                        continue
                    name_tokens.append(token)
                name = " ".join(name_tokens)
                rates[name] = RateSnapshot(name=name, rate=rate_value, apr=apr_value)
                i += 1

        narrative_lines: List[str] = []
        seen_source = False
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue
            if line.startswith("Source:"):
                source = line.replace("Source:", "").strip()
                seen_source = True
                i += 1
                continue
            if seen_source and author is None and not line.startswith("Week"):
                author = line
                i += 1
                continue
            if line.startswith("Week"):
                i += 1
                break
            narrative_lines.append(line)
            i += 1

        body_text = "\n".join(body_lines + narrative_lines).strip()

        return FinancialNews(
            headline=headline,
            body=body_text,
            author=author,
            source=source,
            rates=rates,
        )


__all__ = ["RynessParser"]

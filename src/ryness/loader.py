"""Database loader for parsed Ryness weekly reports."""

from __future__ import annotations

import re
from typing import Dict, Optional, Sequence

import psycopg
from psycopg.rows import dict_row

from .models import CountyAggregate, FinancialNews, ParsedReport, ProjectEntry, ProjectMetrics, YearlySummaryEntry


SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


def load_report(
    report: ParsedReport,
    *,
    dsn: Optional[str] = None,
    connection: Optional[psycopg.Connection] = None,
) -> None:
    """Load a :class:`ParsedReport` into Postgres.

    Either ``dsn`` or ``connection`` must be provided. When ``dsn`` is used the
    loader will manage the connection lifecycle; otherwise the provided
    connection will not be closed by this function.
    """

    if dsn is None and connection is None:
        raise ValueError("Provide either a DSN or an open psycopg connection")

    manage_connection = connection is None
    if manage_connection:
        connection = psycopg.connect(dsn, row_factory=dict_row)

    assert connection is not None  # for type-checkers

    try:
        loader = _Loader(connection)
        loader.load(report)
    finally:
        if manage_connection:
            connection.close()


class _Loader:
    def __init__(self, connection: psycopg.Connection):
        self.connection = connection
        self._product_type_cache: set[str] = set()
        self._developer_cache: Dict[str, int] = {}
        self._city_code_cache: Dict[str, str] = {}
        self._county_cache: Dict[str, int] = {}

    # ------------------------------------------------------------------
    def load(self, report: ParsedReport) -> None:
        with self.connection.transaction():
            region_id = self._ensure_region(report.region_name)
            report_week_id = self._ensure_report_week(
                region_id=region_id,
                week_end_date=report.week_end_date,
                week_label=report.week_label,
                source_pdf=report.source_pdf,
            )

            self._ensure_county_groups(region_id, report.projects, report.county_aggregates)
            self._upsert_yearly_summary(region_id, report.yearly_summary)
            self._upsert_projects(region_id, report_week_id, report.projects)
            self._upsert_county_metrics(report_week_id, report.county_aggregates)
            if report.financial_news:
                self._upsert_financial_news(report_week_id, report.financial_news)

    # ------------------------------------------------------------------
    # Region / county helpers
    # ------------------------------------------------------------------
    def _ensure_region(self, name: str) -> int:
        slug = slugify(name)
        with self.connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO regions (name, slug)
                VALUES (%s, %s)
                ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name
                RETURNING region_id
                """,
                (name, slug),
            )
            return cur.fetchone()[0]

    def _ensure_report_week(
        self,
        *,
        region_id: int,
        week_end_date,
        week_label: Optional[str],
        source_pdf: Optional[str],
    ) -> int:
        with self.connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO report_weeks (region_id, week_end_date, week_label, source_pdf)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (region_id, week_end_date)
                DO UPDATE SET
                    week_label = COALESCE(EXCLUDED.week_label, report_weeks.week_label),
                    source_pdf = COALESCE(EXCLUDED.source_pdf, report_weeks.source_pdf)
                RETURNING report_week_id
                """,
                (region_id, week_end_date, week_label, source_pdf),
            )
            return cur.fetchone()[0]

    def _ensure_county_groups(
        self,
        region_id: int,
        projects: Sequence[ProjectEntry],
        aggregates: Sequence[CountyAggregate],
    ) -> None:
        names = {project.county_group_name for project in projects}
        names.update(aggregate.county_group_name for aggregate in aggregates)
        for name in sorted(names):
            if name in self._county_cache:
                continue
            with self.connection.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO county_groups (region_id, name, display_name)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (region_id, name)
                    DO UPDATE SET display_name = EXCLUDED.display_name
                    RETURNING county_group_id
                    """,
                    (region_id, name, name),
                )
                county_id = cur.fetchone()[0]
                self._county_cache[name] = county_id

    # ------------------------------------------------------------------
    # Dimensional helpers
    # ------------------------------------------------------------------
    def _ensure_product_type(self, code: str) -> None:
        if code in self._product_type_cache:
            return
        with self.connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO product_types (product_type_code, description)
                VALUES (%s, %s)
                ON CONFLICT (product_type_code) DO NOTHING
                """,
                (code, code),
            )
        self._product_type_cache.add(code)

    def _ensure_developer(self, name: str) -> int:
        if name in self._developer_cache:
            return self._developer_cache[name]
        with self.connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO developers (name)
                VALUES (%s)
                ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
                RETURNING developer_id
                """,
                (name,),
            )
            developer_id = cur.fetchone()[0]
            self._developer_cache[name] = developer_id
            return developer_id

    def _ensure_city_code(self, code: str, region_id: int, county_group_id: int) -> None:
        if code in self._city_code_cache:
            return
        with self.connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO city_codes (city_code, name, region_id, county_group_id)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (city_code) DO UPDATE
                    SET region_id = COALESCE(EXCLUDED.region_id, city_codes.region_id),
                        county_group_id = COALESCE(EXCLUDED.county_group_id, city_codes.county_group_id),
                        name = COALESCE(EXCLUDED.name, city_codes.name)
                """,
                (code, code, region_id, county_group_id),
            )
        self._city_code_cache[code] = code

    # ------------------------------------------------------------------
    # Project + fact loading
    # ------------------------------------------------------------------
    def _upsert_projects(
        self,
        region_id: int,
        report_week_id: int,
        projects: Sequence[ProjectEntry],
    ) -> None:
        for project in projects:
            county_group_id = self._county_cache[project.county_group_name]
            self._ensure_product_type(project.product_type_code)
            developer_id = self._ensure_developer(project.developer_name)
            self._ensure_city_code(project.city_code, region_id, county_group_id)

            project_id = self._upsert_project_record(
                county_group_id=county_group_id,
                name=project.project_name,
                developer_id=developer_id,
                city_code=project.city_code,
                product_type_code=project.product_type_code,
                notes=project.notes,
                report_week_id=report_week_id,
            )

            self._upsert_project_weekly_stats(project_id, report_week_id, project.metrics)

    def _upsert_project_record(
        self,
        *,
        county_group_id: int,
        name: str,
        developer_id: int,
        city_code: str,
        product_type_code: str,
        notes: Optional[str],
        report_week_id: int,
    ) -> int:
        with self.connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO projects (
                    county_group_id,
                    name,
                    developer_id,
                    city_code,
                    product_type_code,
                    notes,
                    first_report_week_id,
                    last_report_week_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (county_group_id, name) DO UPDATE
                SET
                    developer_id = EXCLUDED.developer_id,
                    city_code = COALESCE(EXCLUDED.city_code, projects.city_code),
                    product_type_code = EXCLUDED.product_type_code,
                    notes = COALESCE(EXCLUDED.notes, projects.notes),
                    last_report_week_id = GREATEST(
                        COALESCE(projects.last_report_week_id, 0),
                        EXCLUDED.last_report_week_id
                    ),
                    first_report_week_id = COALESCE(projects.first_report_week_id, EXCLUDED.first_report_week_id)
                RETURNING project_id
                """,
                (
                    county_group_id,
                    name,
                    developer_id,
                    city_code,
                    product_type_code,
                    notes,
                    report_week_id,
                    report_week_id,
                ),
            )
            project_id = cur.fetchone()[0]
            return project_id

    def _upsert_project_weekly_stats(
        self,
        project_id: int,
        report_week_id: int,
        metrics: ProjectMetrics,
    ) -> None:
        with self.connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO project_weekly_stats (
                    project_id,
                    report_week_id,
                    units_total,
                    units_new_released,
                    units_released_to_date,
                    units_remaining,
                    traffic,
                    sales_this_week,
                    cancellations_this_week,
                    sold_to_date,
                    sold_year_to_date,
                    average_sales_per_week,
                    average_sales_per_week_ytd
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (project_id, report_week_id) DO UPDATE SET
                    units_total = EXCLUDED.units_total,
                    units_new_released = EXCLUDED.units_new_released,
                    units_released_to_date = EXCLUDED.units_released_to_date,
                    units_remaining = EXCLUDED.units_remaining,
                    traffic = EXCLUDED.traffic,
                    sales_this_week = EXCLUDED.sales_this_week,
                    cancellations_this_week = EXCLUDED.cancellations_this_week,
                    sold_to_date = EXCLUDED.sold_to_date,
                    sold_year_to_date = EXCLUDED.sold_year_to_date,
                    average_sales_per_week = EXCLUDED.average_sales_per_week,
                    average_sales_per_week_ytd = EXCLUDED.average_sales_per_week_ytd
                """,
                (
                    project_id,
                    report_week_id,
                    metrics.units_total,
                    metrics.units_new_released,
                    metrics.units_released_to_date,
                    metrics.units_remaining,
                    metrics.traffic,
                    metrics.sales_this_week,
                    metrics.cancellations_this_week,
                    metrics.sold_to_date,
                    metrics.sold_year_to_date,
                    metrics.average_sales_per_week,
                    metrics.average_sales_per_week_ytd,
                ),
            )

    # ------------------------------------------------------------------
    # Aggregates & auxiliary tables
    # ------------------------------------------------------------------
    def _upsert_county_metrics(
        self,
        report_week_id: int,
        aggregates: Sequence[CountyAggregate],
    ) -> None:
        for aggregate in aggregates:
            county_group_id = self._county_cache[aggregate.county_group_name]
            with self.connection.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO county_weekly_metrics (
                        county_group_id,
                        report_week_id,
                        projects_reporting,
                        traffic,
                        sales,
                        cancellations,
                        net_sales,
                        average_sales,
                        average_sales_year_to_date,
                        avg_sales_year_to_date_delta,
                        average_sales_prev_13_weeks,
                        avg_sales_prev_13_delta,
                        traffic_to_sales_ratio,
                        per_project_avg_traffic,
                        per_project_avg_sales,
                        per_project_avg_cancellations,
                        per_project_avg_net_sales
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (county_group_id, report_week_id) DO UPDATE SET
                        projects_reporting = EXCLUDED.projects_reporting,
                        traffic = EXCLUDED.traffic,
                        sales = EXCLUDED.sales,
                        cancellations = EXCLUDED.cancellations,
                        net_sales = EXCLUDED.net_sales,
                        average_sales = EXCLUDED.average_sales,
                        average_sales_year_to_date = EXCLUDED.average_sales_year_to_date,
                        avg_sales_year_to_date_delta = EXCLUDED.avg_sales_year_to_date_delta,
                        average_sales_prev_13_weeks = EXCLUDED.average_sales_prev_13_weeks,
                        avg_sales_prev_13_delta = EXCLUDED.avg_sales_prev_13_delta,
                        traffic_to_sales_ratio = EXCLUDED.traffic_to_sales_ratio,
                        per_project_avg_traffic = EXCLUDED.per_project_avg_traffic,
                        per_project_avg_sales = EXCLUDED.per_project_avg_sales,
                        per_project_avg_cancellations = EXCLUDED.per_project_avg_cancellations,
                        per_project_avg_net_sales = EXCLUDED.per_project_avg_net_sales
                    """,
                    (
                        county_group_id,
                        report_week_id,
                        aggregate.projects_reporting,
                        aggregate.traffic,
                        aggregate.sales,
                        aggregate.cancellations,
                        aggregate.net_sales,
                        aggregate.average_sales,
                        aggregate.average_sales_year_to_date,
                        aggregate.avg_sales_year_to_date_delta,
                        aggregate.average_sales_prev_13_weeks,
                        aggregate.avg_sales_prev_13_delta,
                        aggregate.traffic_to_sales_ratio,
                        aggregate.per_project_avg_traffic,
                        aggregate.per_project_avg_sales,
                        aggregate.per_project_avg_cancellations,
                        aggregate.per_project_avg_net_sales,
                    ),
                )

    def _upsert_yearly_summary(
        self,
        region_id: int,
        summaries: Sequence[YearlySummaryEntry],
    ) -> None:
        for summary in summaries:
            with self.connection.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO region_yearly_summary (
                        region_id,
                        calendar_year,
                        avg_weekly_projects,
                        avg_weekly_traffic,
                        avg_weekly_sales,
                        avg_weekly_cancels,
                        avg_project_sales,
                        year_end_avg_project_sales
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (region_id, calendar_year) DO UPDATE SET
                        avg_weekly_projects = EXCLUDED.avg_weekly_projects,
                        avg_weekly_traffic = EXCLUDED.avg_weekly_traffic,
                        avg_weekly_sales = EXCLUDED.avg_weekly_sales,
                        avg_weekly_cancels = EXCLUDED.avg_weekly_cancels,
                        avg_project_sales = EXCLUDED.avg_project_sales,
                        year_end_avg_project_sales = EXCLUDED.year_end_avg_project_sales
                    """,
                    (
                        region_id,
                        summary.calendar_year,
                        summary.avg_weekly_projects,
                        summary.avg_weekly_traffic,
                        summary.avg_weekly_sales,
                        summary.avg_weekly_cancels,
                        summary.avg_project_sales,
                        summary.year_end_avg_project_sales,
                    ),
                )

    def _upsert_financial_news(self, report_week_id: int, news: FinancialNews) -> None:
        body_text = self._format_financial_body(news)
        with self.connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO weekly_financial_news (
                    report_week_id,
                    headline,
                    author,
                    source,
                    body
                )
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (report_week_id) DO UPDATE SET
                    headline = EXCLUDED.headline,
                    author = EXCLUDED.author,
                    source = EXCLUDED.source,
                    body = EXCLUDED.body
                """,
                (
                    report_week_id,
                    news.headline,
                    news.author,
                    news.source,
                    body_text,
                ),
            )

    def _format_financial_body(self, news: FinancialNews) -> str:
        rate_lines = []
        for rate in news.rates.values():
            parts = []
            if rate.rate is not None:
                parts.append(f"Rate: {rate.rate}%")
            if rate.apr is not None:
                parts.append(f"APR: {rate.apr}%")
            rate_lines.append(f"{rate.name}: {', '.join(parts)}")
        body_sections = []
        if rate_lines:
            body_sections.append("Rates:\n" + "\n".join(rate_lines))
        if news.body:
            body_sections.append(news.body)
        return "\n\n".join(body_sections).strip()


def slugify(value: str) -> str:
    slug = SLUG_PATTERN.sub("-", value.lower()).strip("-")
    return slug or "region"


__all__ = ["load_report", "slugify"]

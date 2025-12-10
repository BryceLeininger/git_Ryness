"""End-to-end ingestion test for the Ryness parser and loader."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from testcontainers.postgres import PostgresContainer

from ryness import RynessParser, load_report

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "db" / "migrations" / "0001_initial_schema.sql"
SEEDS = ROOT / "db" / "seeds" / "reference_data.sql"
SAMPLE_TEXT = ROOT / "113025 NorCal Ryness Report_SAMPLE.txt"


def _run_sql_script(connection: psycopg.Connection, path: Path) -> None:
    script = path.read_text(encoding="utf-8")
    with connection.cursor() as cur:
        cur.execute(script)
    connection.commit()


def test_round_trip_ingest(tmp_path: Path) -> None:  # noqa: D103 - pytest style
    parser = RynessParser()
    text = SAMPLE_TEXT.read_text(encoding="utf-8")
    parsed = parser.parse_text(text, source_pdf="113025 NorCal Ryness Report_SAMPLE.pdf")

    with PostgresContainer("postgres:16-alpine") as postgres:
        conn = psycopg.connect(postgres.get_connection_url(driver=None), row_factory=dict_row)
        _run_sql_script(conn, MIGRATION)
        _run_sql_script(conn, SEEDS)

        load_report(parsed, connection=conn)
        load_report(parsed, connection=conn)  # idempotency check

        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS c FROM projects")
            project_count = cur.fetchone()["c"]
        assert project_count == len(parsed.projects)

        expected_traffic = sum((metric.traffic or 0) for metric in parsed.iter_project_metrics())
        expected_net_sales = sum(metric.net_sales_this_week for metric in parsed.iter_project_metrics())

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(SUM(traffic), 0) AS traffic,
                       COALESCE(SUM(net_sales_this_week), 0) AS net_sales
                FROM project_weekly_stats
                """
            )
            totals = cur.fetchone()
        assert totals["traffic"] == expected_traffic
        assert totals["net_sales"] == expected_net_sales

        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS c FROM county_weekly_metrics")
            county_metrics_count = cur.fetchone()["c"]
        assert county_metrics_count == len(parsed.county_aggregates)

        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS c FROM region_yearly_summary")
            yearly_count = cur.fetchone()["c"]
        assert yearly_count == len(parsed.yearly_summary)

        with conn.cursor() as cur:
            cur.execute("SELECT headline, body FROM weekly_financial_news")
            news = cur.fetchone()
        assert news is not None
        assert "Rates:" in news["body"]
        assert parsed.financial_news is None or news["headline"] == parsed.financial_news.headline

        conn.close()

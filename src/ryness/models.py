"""Pydantic models representing parsed Ryness report data."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Dict, Iterable, List, Optional

from pydantic import BaseModel, Field, computed_field


class YearlySummaryEntry(BaseModel):
    calendar_year: int
    avg_weekly_projects: Decimal = Field(..., alias="avg_weekly_projects")
    avg_weekly_traffic: Decimal
    avg_weekly_sales: Decimal
    avg_weekly_cancels: Decimal
    avg_project_sales: Decimal
    year_end_avg_project_sales: Decimal


class RateSnapshot(BaseModel):
    name: str
    rate: Optional[Decimal] = None
    apr: Optional[Decimal] = None


class FinancialNews(BaseModel):
    headline: str
    body: str
    author: Optional[str] = None
    source: Optional[str] = None
    rates: Dict[str, RateSnapshot] = Field(default_factory=dict)


class ProjectMetrics(BaseModel):
    units_total: Optional[int] = None
    units_new_released: Optional[int] = None
    units_released_to_date: Optional[int] = None
    units_remaining: Optional[int] = None
    traffic: Optional[int] = None
    sales_this_week: Optional[int] = None
    cancellations_this_week: Optional[int] = None
    sold_to_date: Optional[int] = None
    sold_year_to_date: Optional[int] = None
    average_sales_per_week: Optional[Decimal] = None
    average_sales_per_week_ytd: Optional[Decimal] = None

    @computed_field(return_type=int)
    def net_sales_this_week(self) -> int:
        sales = self.sales_this_week or 0
        cancels = self.cancellations_this_week or 0
        return sales - cancels


class ProjectEntry(BaseModel):
    county_group_name: str
    project_name: str
    developer_name: str
    city_code: str
    product_type_code: str
    notes: Optional[str] = None
    metrics: ProjectMetrics


class CountyAggregate(BaseModel):
    county_group_name: str
    projects_reporting: int
    traffic: int
    sales: int
    cancellations: int
    net_sales: int
    average_sales: Optional[Decimal] = None
    average_sales_year_to_date: Optional[Decimal] = None
    avg_sales_year_to_date_delta: Optional[Decimal] = None
    average_sales_prev_13_weeks: Optional[Decimal] = None
    avg_sales_prev_13_delta: Optional[Decimal] = None
    traffic_to_sales_ratio: Optional[Decimal] = None
    per_project_avg_traffic: Optional[Decimal] = None
    per_project_avg_sales: Optional[Decimal] = None
    per_project_avg_cancellations: Optional[Decimal] = None
    per_project_avg_net_sales: Optional[Decimal] = None


class CountySummaryRow(BaseModel):
    name: str
    projects_reporting: int
    traffic: int
    sales: int
    cancellations: int
    net_sales: int
    average_sales: Decimal
    average_sales_ytd: Decimal
    average_sales_ytd_delta_pct: Decimal
    average_sales_prev13: Decimal
    average_sales_prev13_delta_pct: Decimal


class ParsedReport(BaseModel):
    region_name: str
    week_end_date: date
    week_label: Optional[str] = None
    source_pdf: Optional[str] = None

    yearly_summary: List[YearlySummaryEntry] = Field(default_factory=list)
    county_summary_rows: List[CountySummaryRow] = Field(default_factory=list)
    projects: List[ProjectEntry] = Field(default_factory=list)
    county_aggregates: List[CountyAggregate] = Field(default_factory=list)
    financial_news: Optional[FinancialNews] = None

    def get_county_aggregate_map(self) -> Dict[str, CountyAggregate]:
        return {aggregate.county_group_name: aggregate for aggregate in self.county_aggregates}

    def iter_project_metrics(self) -> Iterable[ProjectMetrics]:
        for project in self.projects:
            yield project.metrics

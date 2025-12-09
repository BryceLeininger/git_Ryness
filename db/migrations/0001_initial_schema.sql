BEGIN;

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE regions (
    region_id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    slug TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE county_groups (
    county_group_id SERIAL PRIMARY KEY,
    region_id INTEGER NOT NULL REFERENCES regions(region_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    display_name TEXT NOT NULL,
    notes TEXT,
    display_order SMALLINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (region_id, name)
);

CREATE TABLE product_types (
    product_type_code TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    category TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE city_codes (
    city_code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    region_id INTEGER REFERENCES regions(region_id) ON DELETE SET NULL,
    county_group_id INTEGER REFERENCES county_groups(county_group_id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE developers (
    developer_id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE report_weeks (
    report_week_id BIGSERIAL PRIMARY KEY,
    region_id INTEGER NOT NULL REFERENCES regions(region_id) ON DELETE CASCADE,
    week_end_date DATE NOT NULL,
    week_of_year SMALLINT GENERATED ALWAYS AS (
        EXTRACT(WEEK FROM week_end_date)::SMALLINT
    ) STORED,
    calendar_year SMALLINT GENERATED ALWAYS AS (
        EXTRACT(YEAR FROM week_end_date)::SMALLINT
    ) STORED,
    week_start_date DATE GENERATED ALWAYS AS (
        week_end_date - INTERVAL '6 days'
    ) STORED,
    week_label TEXT,
    source_pdf TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (region_id, week_end_date)
);

CREATE TABLE projects (
    project_id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    developer_id INTEGER NOT NULL REFERENCES developers(developer_id) ON DELETE RESTRICT,
    county_group_id INTEGER NOT NULL REFERENCES county_groups(county_group_id) ON DELETE RESTRICT,
    city_code TEXT REFERENCES city_codes(city_code) ON DELETE SET NULL,
    product_type_code TEXT NOT NULL REFERENCES product_types(product_type_code) ON DELETE RESTRICT,
    notes TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    first_report_week_id BIGINT,
    last_report_week_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (county_group_id, name)
);

ALTER TABLE projects
    ADD CONSTRAINT projects_first_week_fk FOREIGN KEY (first_report_week_id)
        REFERENCES report_weeks(report_week_id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE projects
    ADD CONSTRAINT projects_last_week_fk FOREIGN KEY (last_report_week_id)
        REFERENCES report_weeks(report_week_id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE project_weekly_stats (
    project_weekly_stats_id BIGSERIAL PRIMARY KEY,
    project_id BIGINT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    report_week_id BIGINT NOT NULL REFERENCES report_weeks(report_week_id) ON DELETE CASCADE,
    units_total INTEGER,
    units_new_released INTEGER,
    units_released_to_date INTEGER,
    units_remaining INTEGER,
    traffic INTEGER,
    sales_this_week INTEGER,
    cancellations_this_week INTEGER,
    sold_to_date INTEGER,
    sold_year_to_date INTEGER,
    average_sales_per_week NUMERIC(8,2),
    average_sales_per_week_ytd NUMERIC(8,2),
    net_sales_this_week INTEGER GENERATED ALWAYS AS (
        COALESCE(sales_this_week, 0) - COALESCE(cancellations_this_week, 0)
    ) STORED,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (project_id, report_week_id),
    CHECK (units_total IS NULL OR units_total >= 0),
    CHECK (units_new_released IS NULL OR units_new_released >= 0),
    CHECK (units_released_to_date IS NULL OR units_released_to_date >= 0),
    CHECK (units_remaining IS NULL OR units_remaining >= 0),
    CHECK (traffic IS NULL OR traffic >= 0),
    CHECK (sales_this_week IS NULL OR sales_this_week >= 0),
    CHECK (cancellations_this_week IS NULL OR cancellations_this_week >= 0),
    CHECK (sold_to_date IS NULL OR sold_to_date >= 0),
    CHECK (sold_year_to_date IS NULL OR sold_year_to_date >= 0)
);

CREATE TABLE county_weekly_metrics (
    county_weekly_metrics_id BIGSERIAL PRIMARY KEY,
    county_group_id INTEGER NOT NULL REFERENCES county_groups(county_group_id) ON DELETE CASCADE,
    report_week_id BIGINT NOT NULL REFERENCES report_weeks(report_week_id) ON DELETE CASCADE,
    projects_reporting INTEGER,
    traffic INTEGER,
    sales INTEGER,
    cancellations INTEGER,
    net_sales INTEGER,
    average_sales NUMERIC(8,2),
    average_sales_year_to_date NUMERIC(8,2),
    avg_sales_year_to_date_delta NUMERIC(8,2),
    average_sales_prev_13_weeks NUMERIC(8,2),
    avg_sales_prev_13_delta NUMERIC(8,2),
    traffic_to_sales_ratio NUMERIC(8,2),
    per_project_avg_traffic NUMERIC(10,2),
    per_project_avg_sales NUMERIC(8,2),
    per_project_avg_cancellations NUMERIC(8,2),
    per_project_avg_net_sales NUMERIC(8,2),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (county_group_id, report_week_id)
);

CREATE TABLE region_yearly_summary (
    region_yearly_summary_id BIGSERIAL PRIMARY KEY,
    region_id INTEGER NOT NULL REFERENCES regions(region_id) ON DELETE CASCADE,
    calendar_year SMALLINT NOT NULL,
    avg_weekly_projects NUMERIC(8,2),
    avg_weekly_traffic NUMERIC(10,2),
    avg_weekly_sales NUMERIC(8,2),
    avg_weekly_cancels NUMERIC(8,2),
    avg_project_sales NUMERIC(8,2),
    year_end_avg_project_sales NUMERIC(8,2),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (region_id, calendar_year)
);

CREATE TABLE weekly_financial_news (
    weekly_financial_news_id BIGSERIAL PRIMARY KEY,
    report_week_id BIGINT NOT NULL REFERENCES report_weeks(report_week_id) ON DELETE CASCADE,
    headline TEXT NOT NULL,
    author TEXT,
    source TEXT,
    body TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_county_groups_region ON county_groups(region_id);
CREATE INDEX idx_city_codes_region ON city_codes(region_id);
CREATE INDEX idx_projects_county ON projects(county_group_id);
CREATE INDEX idx_projects_product_type ON projects(product_type_code);
CREATE INDEX idx_project_weekly_stats_report_week ON project_weekly_stats(report_week_id);
CREATE INDEX idx_project_weekly_stats_project ON project_weekly_stats(project_id);
CREATE INDEX idx_county_weekly_metrics_report_week ON county_weekly_metrics(report_week_id);
CREATE INDEX idx_region_yearly_summary_year ON region_yearly_summary(region_id, calendar_year);

COMMIT;

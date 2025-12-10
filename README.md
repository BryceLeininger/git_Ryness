# Ryness Weekly Sales Database

This repository provides tools for parsing Ryness weekly sales reports (PDF format) and loading the data into a PostgreSQL database for analysis and reporting.

## Overview

The Ryness reports track residential development sales across Northern California regions (Sacramento, Bay Area). This project:

1. Extracts structured data from PDF reports
2. Stores data in a normalized PostgreSQL schema
3. Enables querying and analysis of sales trends, traffic patterns, and market metrics

## Quick Start

### Prerequisites

- Python 3.9 or higher
- PostgreSQL 12 or higher
- A PostgreSQL database instance (e.g., Neon, local PostgreSQL, Docker)

### Installation

1. Clone the repository:
```bash
git clone https://github.com/BryceLeininger/git_Ryness.git
cd git_Ryness
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

### Database Setup

1. Create a `.env` file with your database connection string:
```bash
cp .env.example .env
# Edit .env and set your DATABASE_URL
```

The `DATABASE_URL` should follow this format:
```
DATABASE_URL=postgresql://username:password@host:port/database_name
```

For Neon or other cloud providers, use their provided connection string.

2. Run the database setup script:
```bash
python scripts/setup_database.py
```

This script will:
- Create all necessary tables (regions, projects, developers, etc.)
- Load reference data (product types, city codes, county groups)
- Prepare the database for data ingestion

### Ingesting Data

Once the database is set up, you can parse and load weekly reports:

1. Extract text from a PDF report:
```bash
python scripts/extract_pdf_text.py "path/to/report.pdf" > report.txt
```

2. Parse and load the data:
```bash
python -m ryness.parser report.txt
```

## Database Schema

The database uses a star schema design with:

- **Dimension tables**: `regions`, `county_groups`, `city_codes`, `product_types`, `developers`, `projects`
- **Fact tables**: `project_weekly_stats`, `county_weekly_metrics`, `region_yearly_summary`
- **Supporting tables**: `report_weeks`, `weekly_financial_news`

See [`docs/data_model.md`](docs/data_model.md) for detailed schema documentation.

## Documentation

- [`docs/data_model.md`](docs/data_model.md) - Complete database schema documentation
- [`docs/ingestion_workflow.md`](docs/ingestion_workflow.md) - Step-by-step data loading guide
- [`.env.example`](.env.example) - Example environment configuration

## Testing

Run the test suite to verify everything is working:

```bash
pytest
```

The tests use testcontainers to spin up a temporary PostgreSQL instance, apply migrations, and validate the complete ingestion workflow.

## Project Structure

```
git_Ryness/
├── db/
│   ├── migrations/          # Database schema migrations
│   └── seeds/              # Reference data (regions, product types, etc.)
├── docs/                   # Documentation
├── scripts/                # Utility scripts
│   ├── extract_pdf_text.py    # PDF to text converter
│   └── setup_database.py      # Database initialization script
├── src/ryness/            # Python package for parsing and loading
├── tests/                 # Test suite
└── requirements.txt       # Python dependencies
```

## Example Queries

Find top-performing projects in Sacramento for November 2025:

```sql
SELECT p.name,
       cg.display_name AS county,
       stats.average_sales_per_week,
       stats.traffic
FROM project_weekly_stats stats
JOIN projects p ON p.project_id = stats.project_id
JOIN report_weeks rw ON rw.report_week_id = stats.report_week_id
JOIN county_groups cg ON cg.county_group_id = p.county_group_id
JOIN regions r ON r.region_id = rw.region_id
WHERE r.slug = 'sacramento'
  AND rw.week_end_date BETWEEN '2025-11-01' AND '2025-11-30'
ORDER BY stats.average_sales_per_week DESC
LIMIT 10;
```

Calculate traffic-to-sales conversion by county:

```sql
SELECT cg.display_name,
       SUM(stats.traffic) AS total_traffic,
       SUM(stats.sales_this_week) AS total_sales,
       ROUND(SUM(stats.traffic)::NUMERIC / NULLIF(SUM(stats.sales_this_week), 0), 2) AS conversion_ratio
FROM project_weekly_stats stats
JOIN projects p ON p.project_id = stats.project_id
JOIN county_groups cg ON cg.county_group_id = p.county_group_id
JOIN report_weeks rw ON rw.report_week_id = stats.report_week_id
WHERE rw.week_end_date = '2025-11-30'
GROUP BY cg.display_name
ORDER BY conversion_ratio;
```

## Contributing

Contributions are welcome! Please ensure:

1. Tests pass: `pytest`
2. Code follows existing style conventions
3. Documentation is updated for new features

## License

See LICENSE file for details.

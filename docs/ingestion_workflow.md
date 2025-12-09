# Weekly Ingestion Workflow

The repository provides a reproducible path for turning PDF reports into a relational dataset that your Neon project (`neon_Ryness`) can host. The steps below assume you have cloned the repo, created a virtual environment, and are ready to ingest the **Week Ending 30 November 2025** sample file.

1. **Extract PDF text** (one-time per incoming file). The helper script in `scripts/extract_pdf_text.py` converts the PDF into UTF-8 text while preserving page delineation.
2. **Run the parser** (`ryness.parser`). It identifies regions, county blocks, project rows, and footer metadata. Output is a structured JSON payload aligned with the schema in `docs/data_model.md`.
3. **Load into Postgres** using `ryness.loader`. The loader performs the following operations inside a single transaction:
   - upserts regions, county groups, city codes, product types, and developers referenced by the batch;
   - creates or re-uses `projects` records;
   - inserts weekly facts into `project_weekly_stats` and optional aggregates into `county_weekly_metrics`/`region_yearly_summary`;
   - records the financing commentary if present.
4. **Verify** using the supplied pytest suite (`tests/test_ingest_roundtrip.py`). The test spins up a disposable Postgres 16 container, applies migration `0001`, runs the reference seed script, loads the JSON fixture, and checks the main KPI counts. This mirrors the Neon deployment path.

Because everything runs within migrations/seeds + Python scripts, the process is CI/CD friendly: run migrations, execute loader, and publish results.

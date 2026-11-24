.PHONY: up down data run trigger psql test logs local-setup local-data local-run local-test

# ------------------------------------------------------------ Docker (Airflow)
up:            ## start warehouse + Airflow (UI: http://localhost:8080, admin/admin)
	@grep -q AIRFLOW_UID .env 2>/dev/null || echo "AIRFLOW_UID=$$(id -u)" >> .env
	docker compose up -d --build

down:          ## stop everything (add -v manually to also delete the data volumes)
	docker compose down

data:          ## generate ~100k rows of dirty sample data into data/raw/
	docker compose exec airflow-scheduler python -m etl.generate_data

trigger:       ## trigger the DAG from the CLI (or use the UI)
	docker compose exec airflow-scheduler airflow dags trigger retail_etl

psql:          ## open a SQL shell on the warehouse (or: make psql < sql/analytics.sql)
	docker compose exec -T warehouse-db psql -U warehouse -d retail_dw

test:          ## run the test-suite inside the container
	docker compose exec airflow-scheduler python -m pytest -q /opt/airflow/tests

logs:
	docker compose logs -f airflow-scheduler

# ------------------------------------------- Local Python (no Airflow needed)
# Needs only the warehouse DB:  docker compose up -d warehouse-db
local-setup:
	python -m venv .venv && .venv/bin/pip install -r requirements.txt

local-data:
	.venv/bin/python -m etl.generate_data

local-run:
	.venv/bin/python -m etl.run_pipeline

local-test:
	.venv/bin/python -m pytest -q

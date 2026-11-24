FROM apache/airflow:2.9.3-python3.11

# Airflow's image already ships pandas, SQLAlchemy and psycopg2 (pinned by Airflow's
# constraints). Only add what it lacks.
RUN pip install --no-cache-dir "pyarrow>=14" pytest

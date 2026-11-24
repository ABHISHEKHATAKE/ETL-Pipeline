"""Airflow DAG: daily batch ETL for retail orders.

    extract >> transform >> validate >> load >> cleanup

Each task hands the next one a parquet file in a per-run staging folder (never
data through XCom). The load is idempotent, so retries and re-runs are safe.
"""
from datetime import datetime, timedelta

from airflow import DAG
from airflow.exceptions import AirflowFailException
from airflow.operators.python import PythonOperator

from etl import pipeline
from etl.validate import DataQualityError


def _on_failure(context):
    """Record the failure in etl_run_log once retries are exhausted."""
    pipeline.task_mark_failed(context["run_id"], str(context.get("exception")))


def _validate(run_id: str):
    try:
        return pipeline.task_validate(run_id)
    except DataQualityError as exc:
        # Retrying won't fix bad data, so fail immediately without retries.
        raise AirflowFailException(str(exc))


with DAG(
    dag_id="retail_etl",
    description="Extract retail orders, clean + validate them, load a star schema",
    start_date=datetime(2026, 1, 1),
    schedule="@daily",
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "data-eng",
        "retries": 2,
        "retry_delay": timedelta(minutes=1),
        "on_failure_callback": _on_failure,
    },
    tags=["etl", "retail", "postgres"],
) as dag:
    run_id = "{{ run_id }}"  # templated by Airflow at runtime

    extract = PythonOperator(
        task_id="extract", python_callable=pipeline.task_extract, op_kwargs={"run_id": run_id})
    transform = PythonOperator(
        task_id="transform", python_callable=pipeline.task_transform, op_kwargs={"run_id": run_id})
    validate = PythonOperator(
        task_id="validate", python_callable=_validate, op_kwargs={"run_id": run_id})
    load = PythonOperator(
        task_id="load", python_callable=pipeline.task_load, op_kwargs={"run_id": run_id})
    cleanup = PythonOperator(
        task_id="cleanup", python_callable=pipeline.cleanup, op_kwargs={"run_id": run_id})

    extract >> transform >> validate >> load >> cleanup

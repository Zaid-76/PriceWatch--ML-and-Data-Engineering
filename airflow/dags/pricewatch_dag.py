from datetime import timedelta, timezone, datetime
import pendulum
from airflow.sdk import dag, task, Variable
import pickle


@dag(
    dag_id="pricewatch_daily_ingestion_dag",
    description="Ingest, validate, predict and monitor daily stock prices in Postgres and Drift check weekly",
    start_date=pendulum.datetime(2026, 9, 7, tz="America/New_York"),
    schedule="0 19 * * 1-5",
    catchup=False,
    max_active_runs=1,
    tags=["pricewatch", "ingestion", "validation","prediction","monitoring","Drift check"],
)
def pricewatch_daily_ingestion_dag():

    @task(retries=2, retry_delay=timedelta(minutes=5))
    def ingestion():
        from ingestion import run_ingestion
        run_ingestion()

    @task(retries=2, retry_delay=timedelta(minutes=5))
    def validation():
        from validation import validate_market_data
        validate_market_data()

    @task(retries=2, retry_delay=timedelta(minutes=5))
    def prediction():
        from prediction import run_prediction
        run_prediction()

    @task(retries=2, retry_delay=timedelta(minutes=5))
    def monitoring():
        from monitoring import monitor_predictions
        monitor_predictions()

    @task.short_circuit(retries=2, retry_delay=timedelta(minutes=5))
    def drift_is_due():
        with open("/opt/airflow/project/model.pkl", "rb") as f:
            model_run_id = pickle.load(f)["model_run_id"]

        variable_name = f"pricewatch_drift_last_success_{model_run_id}"
        last_success = Variable.get(variable_name, default=None)

        if last_success is None:
            return True

        last_success_time = datetime.fromisoformat(last_success)
        return (
                datetime.now(timezone.utc) - last_success_time
                >= timedelta(days=7)
        )

    @task(retries=2, retry_delay=timedelta(minutes=5))
    def drift_check():
        from drifting import drift_monitoring
        checked_model_run_id = drift_monitoring()

        # Record the time only after drift monitoring succeeds.
        Variable.set(
            f"pricewatch_drift_last_success_{checked_model_run_id}",
            datetime.now(timezone.utc).isoformat()
        )

    ingestion_task = ingestion()
    validation_task = validation()
    prediction_task = prediction()
    monitoring_task = monitoring()

    ingestion_task >> validation_task >> prediction_task >> monitoring_task >> drift_is_due() >> drift_check()


pricewatch_daily_ingestion_dag()
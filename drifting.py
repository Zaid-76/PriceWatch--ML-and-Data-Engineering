from dotenv import load_dotenv
import os
import psycopg2
import pandas as pd
from evidently import Report
from evidently.presets import DataDriftPreset
from features import calculate_features
from pathlib import Path
import pickle
import mlflow
from datetime import datetime, timezone


def drift_monitoring():
    load_dotenv()
    connection = None
    cursor = None
    model_path = Path(__file__).resolve().parent / "model.pkl"
    with open(model_path, "rb") as f:
        saved_data = pickle.load(f)
        feature_columns = saved_data["feature_columns"]
    try:
        connection = psycopg2.connect(database=os.getenv('DATABASE_NAME'), user=os.getenv('DATABASE_USERNAME'),
                                      password=os.getenv('DATABASE_PASSWORD'),
                                      host=os.getenv('DATABASE_HOST'), port=os.getenv('DATABASE_PORT'))
        cursor = connection.cursor()
        cursor.execute('''SELECT company_id, price_date,
                                    open_price, high_price, low_price, close_price, volume
                                    FROM stock_prices''')
        dataframe = pd.DataFrame.from_records(cursor.fetchall())
        dataframe.columns = ['company_id', 'price_date', 'open_price', 'high_price', 'low_price', 'close_price',
                             'volume']

        dataframe = calculate_features(dataframe)
        dataframe = dataframe.groupby(['company_id']).tail(30)
        dataframe = dataframe[feature_columns].astype(float)
        model_run_id= saved_data["model_run_id"]
        file_path=mlflow.artifacts.download_artifacts(artifact_path="training_reference.csv",run_id=model_run_id,dst_path=str(Path(__file__).resolve().parent / "temp"))
        reference_dataframe=pd.read_csv(file_path)

        #driftcheck

        report = Report(
            [DataDriftPreset(method="wasserstein", threshold=0.1)]
        )
        result = report.run(
            current_data=dataframe[feature_columns],
            reference_data=reference_dataframe[feature_columns],
        )
        # Save each report with a unique UTC timestamp.
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        report_path = Path(__file__).resolve().parent / "temp" / f"drift_report_{timestamp}.html"
        result.save_html(str(report_path))

        # Extract the feature scores already calculated by Evidently.
        drift_metrics = {}
        for metric in result.dict()["metrics"]:
            if metric["metric_name"].startswith("ValueDrift("):
                feature = metric["config"]["column"]
                drift_metrics[f"drift_{feature}"] = float(metric["value"])

        mlflow.log_artifact(
            str(report_path),
            artifact_path="drift_reports",
            run_id=model_run_id
        )

        mlflow.log_metrics(
            drift_metrics,
            run_id=model_run_id
        )

        print("Drift report and scores logged to MLflow.")
        return model_run_id
        #print(file_path)


    except (Exception, psycopg2.DatabaseError) as error:
        print(error)
        raise

    finally:
        if cursor is not None:
            cursor.close()
            print("Cursor closed.")

        if connection is not None:
            connection.close()
            print("Database connection closed.")


if __name__ == '__main__':
    drift_monitoring()
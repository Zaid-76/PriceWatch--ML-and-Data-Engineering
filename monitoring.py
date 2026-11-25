from dotenv import load_dotenv
import os
import psycopg2
import pandas as pd
import mlflow


def monitor_predictions():
    load_dotenv()
    connection = None
    cursor = None
    try:
        connection = psycopg2.connect(database=os.getenv('DATABASE_NAME'), user=os.getenv('DATABASE_USERNAME'),
                                      password=os.getenv('DATABASE_PASSWORD'),
                                      host=os.getenv('DATABASE_HOST'), port=os.getenv('DATABASE_PORT'))
        cursor = connection.cursor()
        cursor.execute("""
                    SELECT spd.predicted_return, spd.model_run_id, spr1.close_price as feature_close, spr2.close_price as target_close  FROM stock_predictions spd JOIN stock_prices spr1 ON spd.company_id = spr1.company_id AND  spd.feature_date = spr1.price_date
                    JOIN  stock_prices spr2 ON spd.company_id = spr2.company_id AND  spd.target_date = spr2.price_date;
                       """)

        dataframe = pd.DataFrame.from_records(
            cursor.fetchall(),
            columns=["predicted_return", "model_run_id", "feature_close", "target_close"]
        )
        print(dataframe)
        if dataframe.empty:
            print("No predictions available for evaluation")
            return
        dataframe[["predicted_return", "feature_close", "target_close"]]= dataframe[["predicted_return", "feature_close", "target_close"]].astype(float)
        dataframe["actual_return"] = ((dataframe["target_close"] / dataframe["feature_close"]) - 1)*100
        dataframe["absolute_prediction_error"] = abs(dataframe["actual_return"] - dataframe["predicted_return"])
        dataframe["baseline_absolute_error"] = dataframe["actual_return"].abs()

        summary_dataframe = dataframe.groupby("model_run_id", as_index=False).agg(
            mae=("absolute_prediction_error", "mean"),
            baseline_mae=("baseline_absolute_error", "mean"),
            prediction_count=("absolute_prediction_error", "count")
        )
        for _, row in summary_dataframe.iterrows():
            mlflow.log_metrics(
                {
                    "monitoring_mae": float(row["mae"]),
                    "monitoring_baseline_mae": float(row["baseline_mae"]),
                    "monitoring_prediction_count": int(row["prediction_count"])
                },
                run_id=row["model_run_id"]
            )

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
    monitor_predictions()
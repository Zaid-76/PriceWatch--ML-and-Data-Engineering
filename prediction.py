import pickle
from features import calculate_features
from dotenv import load_dotenv
import os
import pandas as pd
import psycopg2
from datetime import timedelta
import pandas_market_calendars as mcal
from pathlib import Path


def run_prediction():

    model_path = Path(__file__).resolve().parent / "model.pkl"
    with open(model_path, "rb") as f:
        saved_data = pickle.load(f)
        model = saved_data["model"]
        feature_columns = saved_data["feature_columns"]
        run_id = saved_data["model_run_id"]
    load_dotenv()
    connection = None
    cursor = None
    try:
        connection = psycopg2.connect(
            database=os.getenv("DATABASE_NAME"),
            user=os.getenv("DATABASE_USERNAME"),
            password=os.getenv("DATABASE_PASSWORD"),
            host=os.getenv("DATABASE_HOST"),
            port=os.getenv("DATABASE_PORT"),
        )
        cursor = connection.cursor()
        cursor.execute('''SELECT company_id, price_date,
                                    open_price, high_price, low_price, close_price, volume
                                    FROM stock_prices''')
        dataframe = pd.DataFrame.from_records(cursor.fetchall())
        dataframe.columns = ['company_id', 'price_date', 'open_price', 'high_price', 'low_price', 'close_price',
                             'volume']
        dataframe = calculate_features(dataframe)
        latest_rows = dataframe.groupby('company_id').tail(1).sort_values(by=['company_id', 'price_date'], ascending=[True, True])
        dataframe=latest_rows[feature_columns].astype(float)

        # missing feature check
        if(dataframe.isnull().values.any()):
            raise ValueError('missing data in the latest rows')


        latest_rows['predicted_return']=model.predict(dataframe)

        nasdaq = mcal.get_calendar("NASDAQ")
        target_dates = []

        for feature_date in latest_rows["price_date"]:
            schedule = nasdaq.schedule(
                start_date=feature_date + timedelta(days=1),
                end_date=feature_date + timedelta(days=14)
            )

            if schedule.empty:
                raise ValueError(f"No trading session found after {feature_date}")

            target_dates.append(schedule.index[0].date())

        latest_rows["target_date"] = target_dates

        print(latest_rows[
                  ["company_id", "price_date", "target_date", "predicted_return"]
              ])

        for _,i in latest_rows.iterrows():
            cursor.execute(
                """
                INSERT INTO stock_predictions (
                    company_id,
                    feature_date,
                    target_date,
                    predicted_return,
                    model_run_id
                )
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (company_id, feature_date, model_run_id)
                DO NOTHING
                """,
                (
                    int(i["company_id"]),
                    i["price_date"],
                    i["target_date"],
                    float(i["predicted_return"]),
                    run_id
                ),
            )
        connection.commit()

    except Exception:
        if connection is not None:
            connection.rollback()
        raise


    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()


if __name__ == '__main__':
    run_prediction()
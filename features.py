import psycopg2
from dotenv import load_dotenv
import os
import pandas as pd
import numpy as np
#from sklearn.ensemble import RandomForestRegressor
import xgboost as xgb
import pickle
import json
import mlflow
from pathlib import Path
import shutil


def calculate_features(dataframe):
    # Sort within each company before calculating returns and rolling features.
    dataframe.sort_values(by=['company_id', 'price_date'], inplace=True, ascending=[True, True])
    dataframe['daily_return'] = dataframe.groupby('company_id')['close_price'].shift(1)
    dataframe['daily_return'] = ((dataframe['close_price'] / dataframe['daily_return']) - 1) * 100
    dataframe['return_mean_5'] = dataframe.groupby('company_id')['daily_return'].transform(
        lambda x: x.rolling(5).mean())
    dataframe['return_std_5'] = dataframe.groupby('company_id')['daily_return'].transform(lambda x: x.rolling(5).std())
    dataframe['intraday_return'] = ((dataframe['close_price'] / dataframe['open_price']) - 1) * 100
    return dataframe

def feature_eng():
    load_dotenv()
    mlflow.set_experiment('PriceWatch')
    connection=None
    cursor=None
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
        dataframe.columns=['company_id', 'price_date', 'open_price', 'high_price', 'low_price', 'close_price','volume']

        dataframe = calculate_features(dataframe)
        # The next row's return is the target, not an input feature.
        dataframe['target_return'] = dataframe.groupby('company_id')['daily_return'].shift(-1)
        # Keep complete historical rows for training and latest rows for future prediction.
        training_dataframe=dataframe.copy()
        training_dataframe=training_dataframe.dropna(subset=['daily_return','target_return','return_mean_5','return_std_5','intraday_return'])
        training_dataframe['target_return']=training_dataframe['target_return'].astype(float)
        latest_records=dataframe.groupby(['company_id']).tail(1)

        # Choose chronological 70/15/15 boundaries shared by all companies.
        unique_dates=training_dataframe['price_date'].unique()
        unique_dates.sort()
        total_no_unique_dates=training_dataframe['price_date'].nunique()
        earliest_date=unique_dates[0]
        latest_date=unique_dates[-1]
        train_dates= int(total_no_unique_dates * 0.7)
        val_dates = int(total_no_unique_dates * 0.15)
        test_dates = int(total_no_unique_dates * 0.15)
        test_dates += int((total_no_unique_dates-train_dates-val_dates-test_dates))
        first_validation_date=unique_dates[train_dates]
        first_testing_date=unique_dates[train_dates+val_dates]

        train_set=training_dataframe[training_dataframe['price_date']<first_validation_date]
        validation_set=training_dataframe[training_dataframe['price_date'].between(first_validation_date,first_testing_date,inclusive='left')]
        test_set=training_dataframe[training_dataframe['price_date']>=first_testing_date]

        # Exclude the latest date in each earlier split for the next-session target gap.
        train_set = train_set[train_set["price_date"] < train_set["price_date"].max()].copy()
        validation_set = validation_set[validation_set["price_date"] < validation_set["price_date"].max()].copy()

        feature_columns = [
            "daily_return",
            "return_mean_5",
            "return_std_5",
            "intraday_return",
        ]

        X_train = train_set[feature_columns].astype(float).copy()
        Y_train = train_set["target_return"].copy()

        X_val = validation_set[feature_columns].astype(float).copy()
        Y_val = validation_set["target_return"].copy()

        X_test = test_set[feature_columns].astype(float).copy()
        Y_test = test_set["target_return"].copy()


        with mlflow.start_run(run_name="PriceWatch") as run:
            # Train the selected model.
            candidate_model = xgb.XGBRegressor(
                n_estimators=300,  # Number of boosting rounds
                max_depth=6,  # Maximum tree depth
                learning_rate=0.01,  # Shrinkage factor (eta)
                subsample=0.8,  # Row subsampling ratio
                colsample_bytree=0.8,  # Feature subsampling ratio
                random_state=42,
                eval_metric= 'mae',
                early_stopping_rounds=50
            )
            mlflow.log_params(candidate_model.get_params())
            candidate_model.fit(X_train, Y_train, eval_set=[(X_val, Y_val)])

            # Compare against the zero-return baseline on the test set.
            baseline_test_mae = np.mean(np.abs(Y_test))
            candidate_model_test_pred = candidate_model.predict(X_test)
            candidate_model_test_mae = np.mean(np.abs(Y_test - candidate_model_test_pred))

            #comparing the candidate model with the current model
            model_path = Path(__file__).resolve().parent / "model.pkl"
            old_model_test_mae = None

            if model_path.is_file():
                with open(model_path, "rb") as f:
                    old_model = pickle.load(f)["model"]

                old_predictions = old_model.predict(X_test)
                old_model_test_mae = float(np.mean(np.abs(Y_test - old_predictions)))
            if old_model_test_mae is not None:
                mlflow.log_metric("old_model_test_mae", old_model_test_mae)

            # print("Baseline test MAE:", baseline_test_mae)
            # print("XGB Regressor test MAE:", model_test_mae)
            mlflow.log_metric('baseline_test_mae', baseline_test_mae)
            mlflow.log_metric('model_test_mae', candidate_model_test_mae)

            if old_model_test_mae is None or (
                    candidate_model_test_mae < old_model_test_mae
                    and candidate_model_test_mae < baseline_test_mae
            ):
                candidate_path = model_path.parent / "candidate_model.pkl"
                reference_path = model_path.parent / "training_reference.csv"
                evaluation_path = model_path.parent / "evaluation.json"

                # Save the candidate separately
                with open(candidate_path, "wb") as f:
                    pickle.dump({
                        "model": candidate_model,
                        "feature_columns": feature_columns,
                        "model_run_id": run.info.run_id
                    }, f)

                X_train.to_csv(reference_path, index=False)

                with open(evaluation_path, "w") as f:
                    json.dump({
                        "baseline_test_mae": float(baseline_test_mae),
                        "model_test_mae": float(candidate_model_test_mae),
                        "old_model_test_mae": old_model_test_mae
                    }, f, indent=2)

                # Finish all uploads before replacing model.pkl.
                mlflow.log_artifact(str(candidate_path))
                mlflow.log_artifact(str(evaluation_path))
                mlflow.log_artifact(str(reference_path))

                shutil.copyfile(candidate_path, model_path)

    except Exception:
        if connection is not None:
            connection.rollback()
        raise

    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    feature_eng()
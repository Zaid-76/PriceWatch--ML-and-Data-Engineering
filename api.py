from fastapi import FastAPI, HTTPException, status
from dotenv import load_dotenv
import os
import psycopg2
import pprint
from pydantic import BaseModel
from datetime import date

class PredictionResponse(BaseModel):
    symbol: str
    feature_date: date
    target_date: date
    predicted_return: float
    model_run_id: str

app = FastAPI()


@app.get("/health")
async def root():
    return {"message": "OK"}

@app.get("/predictions/{symbol}", response_model=PredictionResponse)
def prediction(symbol: str):
    symbol = symbol.upper()

    load_dotenv()
    connection = None
    cursor = None
    try:
        connection = psycopg2.connect(database=os.getenv('DATABASE_NAME'), user=os.getenv('DATABASE_USERNAME'),
                                      password=os.getenv('DATABASE_PASSWORD'),
                                      host=os.getenv('DATABASE_HOST'), port=os.getenv('DATABASE_PORT'))
        cursor = connection.cursor()
        cursor.execute('''SELECT c.symbol, s.feature_date, s.target_date, s.predicted_return, s.model_run_id
                       FROM stock_predictions s JOIN companies c ON s.company_id = c.company_id
                       WHERE c.symbol= %s
                       ORDER BY s.feature_date DESC,
                                s.predicted_at DESC,
                                s.prediction_id DESC
                       LIMIT(1)
                       ''', (symbol,))
        result = cursor.fetchone()
        if(result == None):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Prediction not found"
            )
        else:
            return {
                "symbol": result[0],
                "feature_date": result[1],
                "target_date": result[2],
                "predicted_return": result[3],
                "model_run_id": result[4],
            }


    except (Exception, psycopg2.DatabaseError) as error:
        print(error)
        raise

    finally:
        if cursor is not None:
            cursor.close()
            #print("Cursor closed.")

        if connection is not None:
            connection.close()
            #print("Database connection closed.")

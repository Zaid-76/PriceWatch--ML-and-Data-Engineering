"""
Fetch daily stock prices and upsert company metadata and prices
into PostgreSQL.
"""

import os
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pandas_market_calendars as mcal
import psycopg2
import requests
from dotenv import load_dotenv


pre_defined_symbollist = ["AAPL", "MSFT", "NVDA"]
HISTORICAL_START_DATE = date(2021, 9, 1)


def get_latest_completed_session():
    now = datetime.now(ZoneInfo("America/New_York"))
    publication_buffer = timedelta(minutes=60)

    calendar = mcal.get_calendar("NASDAQ")
    schedule = calendar.schedule(
        start_date=(now - timedelta(days=30)).date(),
        end_date=now.date(),
    )

    eligible_sessions = schedule[
        schedule["market_close"] + publication_buffer <= now
    ]

    if eligible_sessions.empty:
        raise ValueError("Could not determine the latest completed session.")

    return eligible_sessions.index[-1].date()


def run_ingestion(full_refresh=False):
    load_dotenv()

    api_key = os.getenv("API_KEY")
    if not api_key:
        raise ValueError("API_KEY is missing.")

    end_date = get_latest_completed_session()

    for symbol in pre_defined_symbollist:
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

            # These three configured stocks use the NASDAQ calendar.
            cursor.execute(
                """
                SELECT MAX(s.price_date)
                FROM companies c
                JOIN stock_prices s ON s.company_id = c.company_id
                WHERE c.symbol = %s;
                """,
                (symbol,),
            )
            latest_stored_date = cursor.fetchone()[0]

            if full_refresh or latest_stored_date is None:
                start_date = HISTORICAL_START_DATE
            else:
                # Re-fetch the last stored session as well.
                start_date = latest_stored_date

            if start_date > end_date:
                raise ValueError(
                    f"{symbol}: start date {start_date} is after "
                    f"the latest completed session {end_date}."
                )

            print(f"{symbol}: fetching {start_date} through {end_date}")

            response = requests.get(
                "https://api.twelvedata.com/time_series",
                params={
                    "apikey": api_key,
                    "symbol": symbol,
                    "interval": "1day",
                    "format": "JSON",
                    "type": "stock",
                    "timezone": "UTC",
                    "order": "asc",
                    "start_date": start_date.isoformat(),
                    "end_date": f"{end_date.isoformat()}T23:59:59",
                },
                timeout=60,
            )

            # Avoid including the API-key-bearing URL in an HTTP error.
            if response.status_code != 200:
                raise RuntimeError(
                    f"{symbol}: API returned HTTP {response.status_code}."
                )

            data = response.json()

            if data.get("status") == "error":
                raise ValueError(
                    f"{symbol}: API error: {data.get('message', 'Unknown error')}"
                )

            if not data.get("meta") or not data.get("values"):
                raise ValueError(
                    f"{symbol}: API returned no usable data "
                    f"for {start_date} through {end_date}."
                )

            meta = data["meta"]

            cursor.execute(
                """
                INSERT INTO companies (
                    symbol,
                    currency,
                    exchange,
                    exchange_timezone,
                    mic_code,
                    type
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol, exchange)
                DO UPDATE SET
                    currency = EXCLUDED.currency,
                    exchange_timezone = EXCLUDED.exchange_timezone,
                    mic_code = EXCLUDED.mic_code,
                    type = EXCLUDED.type,
                    meta_data_fetched_at = NOW()
                RETURNING company_id;
                """,
                (
                    meta["symbol"],
                    meta["currency"],
                    meta["exchange"],
                    meta["exchange_timezone"],
                    meta["mic_code"],
                    meta["type"],
                ),
            )

            company_id = cursor.fetchone()[0]

            for row in data["values"]:
                price_date = date.fromisoformat(row["datetime"])

                if not start_date <= price_date <= end_date:
                    raise ValueError(
                        f"{symbol}: API returned an out-of-range date: "
                        f"{price_date}."
                    )

                cursor.execute(
                    """
                    INSERT INTO stock_prices (
                        company_id,
                        price_date,
                        open_price,
                        high_price,
                        low_price,
                        close_price,
                        volume
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (company_id, price_date)
                    DO UPDATE SET
                        open_price = EXCLUDED.open_price,
                        high_price = EXCLUDED.high_price,
                        low_price = EXCLUDED.low_price,
                        close_price = EXCLUDED.close_price,
                        volume = EXCLUDED.volume,
                        ingested_at = NOW();
                    """,
                    (
                        company_id,
                        price_date,
                        Decimal(row["open"]),
                        Decimal(row["high"]),
                        Decimal(row["low"]),
                        Decimal(row["close"]),
                        int(row["volume"]) if row.get("volume") else None,
                    ),
                )

            connection.commit()
            print(
                f"{symbol}: successfully upserted "
                f"{len(data['values'])} price records."
            )

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
    run_ingestion()
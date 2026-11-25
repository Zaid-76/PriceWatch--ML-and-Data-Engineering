from dotenv import load_dotenv
import os
import psycopg2
import ingestion
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas_market_calendars as mcal

symbol_list=ingestion.pre_defined_symbollist.copy()


def validate_market_data():
    load_dotenv()
    connection = None
    cursor = None
    try:
        connection = psycopg2.connect(database=os.getenv('DATABASE_NAME'), user=os.getenv('DATABASE_USERNAME'),
                                      password=os.getenv('DATABASE_PASSWORD'),
                                      host=os.getenv('DATABASE_HOST'), port=os.getenv('DATABASE_PORT'))
        cursor = connection.cursor()

        #check-1
        cursor.execute('''SELECT
                        c.symbol,
                        COUNT(s.price_date) AS total_rows
                        FROM companies c
                        LEFT JOIN stock_prices s ON c.company_id = s.company_id
                        GROUP BY c.company_id, c.symbol
                        ORDER BY c.symbol;''')
        result = cursor.fetchall()
        for i in symbol_list:
            flag=0
            for j in result:
                if j[0] == i and j[1] >= 1:
                    flag=1
                    break
            if flag==0:
                raise ValueError(f'{i} company hasnt been ingested or if it has , no data is present for that company in the database!')


        #check-2
        cursor.execute('''SELECT company_id, price_date,
                            open_price, high_price, low_price, close_price
                            FROM stock_prices
                            WHERE open_price IS NULL
                            OR high_price IS NULL
                            OR low_price IS NULL
                            OR close_price IS NULL
                            OR low_price <= 0
                            OR high_price < low_price
                            OR open_price NOT BETWEEN low_price AND high_price
                            OR close_price NOT BETWEEN low_price AND high_price;''')
        result=cursor.fetchall()
        if(result != []):
            print(result)
            raise ValueError('missing price or invalid OHLC relationship after ingestion')

        #check-3
        cursor.execute('''SELECT company_id, price_date, COUNT(*) AS row_count
                            FROM stock_prices
                            GROUP BY company_id, price_date
                            HAVING COUNT(*) > 1;''')
        result=cursor.fetchall()
        if (result != []):
            print(result)
            raise ValueError('duplicate company or date records')

        #check-4
        now = datetime.now(ZoneInfo("America/New_York"))

        # Example allowance, not a guaranteed Twelve Data publication time.
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
            raise ValueError("Could not determine the expected trading date.")

        expected_date = eligible_sessions.index[-1].date()

        cursor.execute("""
            SELECT c.symbol, MAX(s.price_date)
            FROM companies c
            LEFT JOIN stock_prices s ON s.company_id = c.company_id
            GROUP BY c.symbol;
        """)

        latest_dates = dict(cursor.fetchall())
        errors = []

        for symbol in symbol_list:
            latest_date = latest_dates.get(symbol)

            if latest_date is None:
                errors.append(f"{symbol}: no price data found.")

            elif latest_date < expected_date:
                errors.append(
                    f"{symbol}: stale data; latest={latest_date}, "
                    f"expected={expected_date}."
                )

            elif latest_date > expected_date:
                errors.append(
                    f"{symbol}: latest={latest_date} is newer than the expected "
                    f"completed session={expected_date}; check for an unfinished "
                    "daily candle or an invalid date."
                )

        if errors:
            raise ValueError("Freshness validation failed:\n" + "\n".join(errors))

        print(f"Freshness check passed. Expected trading date: {expected_date}")



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


if __name__ == "__main__":
    validate_market_data()
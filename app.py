from flask import Flask, request, render_template, jsonify
import yfinance as yf
from openai import OpenAI
import redis
import time
import json
import os
import logging
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
print(api_key)
app = Flask(__name__)


if not app.debug:
    file_handler = RotatingFileHandler('logs/flaskapp.log', maxBytes=10240, backupCount=10)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)

    app.logger.setLevel(logging.INFO)
    app.logger.info('Flask App startup')

if os.environ.get('FLASK_ENV') == 'production':
    app.config.from_object('config.ProductionConfig')
else:
    app.config.from_object('config.DevelopmentConfig')

# Initialize Flask app


# Connect to Redis
r = redis.StrictRedis(host='localhost', port=6379, db=0, decode_responses=True)

# Cache expiration time in seconds (e.g., 24 hours = 86400 seconds)
CACHE_EXPIRATION_TIME = 86400  # 24 hours

def stock_analysis_prompt(company_a, company_b):
    format_instruction = """
    <h2>Stock Analysis: Company A vs. Company B</h2>

    <h3>Market Capitalization</h3>
    <p>[Brief description of market capitalization comparison]</p>

    <h3>Price-to-Earnings (P/E) Ratios</h3>
    <p>[Comparison of trailing and forward P/E ratios]</p>

    <h3>PEG Ratio</h3>
    <p>[Comparison of PEG ratios]</p>

    <h3>Price-to-Sales and Price-to-Book Ratios</h3>
    <p>[Analysis of price-to-sales and price-to-book ratios]</p>

    <h3>Performance Indicators</h3>
    <p>[Discussion of 52-week range and performance indicators]</p>

    <h3>Average Stock Prices</h3>
    <p>[Analysis of fifty-day and two-hundred-day averages]</p>

    <h3>Conclusion</h3>
    <p>[Final summary and investor guidance]</p>

    <h3>What to do next</h3>
    <p>[suggest how to continue research. Give specific suggestions in the context of what was said in this doc.  Incorporate my aphliate link to https://www.tradingview.com -  https://www.tradingview.com/?aff_id=142766]</p>"""
    return f"Compare the stocks of {company_a} and {company_b}.\n{format_instruction}"

# Function to get stock data from Redis cache or fetch from yfinance
def get_stock_info(ticker):
    # Check if the data is in Redis
    stock_data = r.get(ticker)

    if stock_data:
        # Parse JSON data if available in Redis
        return json.loads(stock_data)

    # If not in Redis, fetch from yfinance
    stock = yf.Ticker(ticker)
    try:
        stock_info = stock.info
        data = {
            'longName': stock_info.get('longName', 'N/A'),
            'marketCap': stock_info.get('marketCap', 'N/A'),
            'enterpriseValue': stock_info.get('enterpriseValue', 'N/A'),
            'trailingPE': stock_info.get('trailingPE', 'N/A'),
            'forwardPE': stock_info.get('forwardPE', 'N/A'),
            'pegRatio': stock_info.get('pegRatio', 'N/A'),
            'priceToSalesTrailing12Months': stock_info.get('priceToSalesTrailing12Months', 'N/A'),
            'priceToBook': stock_info.get('priceToBook', 'N/A'),
            'enterpriseToRevenue': stock_info.get('enterpriseToRevenue', 'N/A'),
            'enterpriseToEbitda': stock_info.get('enterpriseToEbitda', 'N/A'),
            'fiftyTwoWeekHigh': stock_info.get('fiftyTwoWeekHigh', 'N/A'),
            'fiftyTwoWeekLow': stock_info.get('fiftyTwoWeekLow', 'N/A'),
            'fiftyDayAverage': stock_info.get('fiftyDayAverage', 'N/A'),
            'twoHundredDayAverage': stock_info.get('twoHundredDayAverage', 'N/A')
        }

        # Store in Redis cache as a JSON string
        r.setex(ticker, CACHE_EXPIRATION_TIME, json.dumps(data))
        return data
    except Exception as e:
        return {"error": f"Failed to retrieve stock data: {str(e)}"}

def get_sorted_stock_key(ticker1, ticker2):
    # Sort tickers alphabetically to avoid duplication (AAPL vs MSFT is same as MSFT vs AAPL)
    sorted_tickers = sorted([ticker1, ticker2])
    return f"{sorted_tickers[0]}_{sorted_tickers[1]}"

# Function to check if GPT response is cached
def get_cached_gpt_response(ticker1, ticker2):
    stock_pair_key = get_sorted_stock_key(ticker1, ticker2)
    gpt_response = r.get(stock_pair_key)
    if gpt_response:
        return gpt_response
    return None

# Cache GPT response
def cache_gpt_response(ticker1, ticker2, response):
    stock_pair_key = get_sorted_stock_key(ticker1, ticker2)
    r.setex(stock_pair_key, CACHE_EXPIRATION_TIME, response)

@app.route('/definitions')
def definitions():
    return render_template('def.html')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    ticker_symbol1 = request.form['ticker1']
    ticker_symbol2 = request.form['ticker2']

    # Get stock info from cache or fetch from yfinance
    fundamental_data1 = get_stock_info(ticker_symbol1)
    fundamental_data2 = get_stock_info(ticker_symbol2)

    prompt = stock_analysis_prompt(ticker_symbol1, ticker_symbol2)

    # Format numbers
    for data in [fundamental_data1, fundamental_data2]:
        for key, value in data.items():
            if isinstance(value, (int, float)):
                data[key] = f"{value:,.2f}"

    # Check if GPT response is already cached
    cached_gpt_response = get_cached_gpt_response(ticker_symbol1, ticker_symbol2)
    if cached_gpt_response:
        # If cached, use the cached response
        analysis_html = cached_gpt_response
    else:
        message = prompt + str(fundamental_data1) + str(fundamental_data2)
        client = OpenAI()
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful stock market assistant."},
                {"role": "user", "content": message}
            ]
        )
        analysis_html = completion.choices[0].message.content
        # Cache the GPT response
        cache_gpt_response(ticker_symbol1, ticker_symbol2, analysis_html)

    return render_template('result.html', data1=fundamental_data1, data2=fundamental_data2, analysis=analysis_html)

if __name__ == '__main__':
    app.run(debug=True)

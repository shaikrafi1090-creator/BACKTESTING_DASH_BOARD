import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

st.set_page_config(page_title="Momentum Builder & Backtester", layout="wide")
st.title("📈 Quantitative Momentum System")

# Universe (Aap apne hisaab se 50-100 stocks add kar sakte hain, yahan top liquid examples hain)
TICKERS = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS", 
    "HAL.NS", "BEL.NS", "TATASTEEL.NS", "ITC.NS", "LT.NS", 
    "ZOMATO.NS", "TATAMOTORS.NS", "M&M.NS", "BAJFINANCE.NS", "AXISBANK.NS",
    "SUNPHARMA.NS", "MARUTI.NS", "BHARTIARTL.NS", "SBIN.NS", "ASIANPAINT.NS"
]
BENCHMARK = "^NSEI" # Nifty 50 index

# Create Tabs in Streamlit
tab1, tab2 = st.tabs(["🔴 Live Momentum Scanner", "📊 Historical Equity Curve (Backtest)"])

# ----------------- TAB 1: LIVE SCANNER -----------------
with tab1:
    st.header("Current Month Selection")
    top_n = st.slider("Select Top N Stocks for Portfolio", min_value=3, max_value=10, value=5, key='live_n')
    
    if st.button("Run Live Scanner"):
        with st.spinner("Fetching latest data..."):
            end_date = datetime.today()
            start_date = end_date - timedelta(days=200)
            data = yf.download(TICKERS, start=start_date, end=end_date)['Close']
            
            results = []
            for t in TICKERS:
                if t in data.columns and len(data[t].dropna()) >= 126:
                    series = data[t].dropna()
                    roc = ((series.iloc[-1] - series.iloc[-126]) / series.iloc[-126]) * 100
                    vol = series.pct_change().dropna().std() * np.sqrt(252) * 100
                    score = roc / vol if vol > 0 else 0
                    
                    results.append({'Stock': t.replace('.NS', ''), '6M Return %': round(roc, 2), 
                                    'Volatility %': round(vol, 2), 'Momentum Score': round(score, 2)})
            
            df = pd.DataFrame(results).sort_values(by='Momentum Score', ascending=False).reset_index(drop=True)
            df.index += 1
            
            st.success(f"Top {top_n} Stocks to Buy & Hold right now:")
            st.dataframe(df.head(top_n), use_container_width=True)


# ----------------- TAB 2: BACKTEST & EQUITY CURVE -----------------
with tab2:
    st.header("Momentum Strategy vs Nifty 50 (Last 3 Years)")
    st.markdown("Yeh backtest har mahine ke end mein 6-month momentum calculate karke Top N stocks mein equal capital reallocate karta hai.")
    
    bt_top_n = st.slider("Stocks to hold in Backtest", min_value=3, max_value=10, value=5, key='bt_n')
    
    if st.button("Run Backtest & Plot Equity Curve"):
        with st.spinner("Simulating monthly rebalancing for the last 3 years. Please wait..."):
            # Fetch 3.5 years of data (0.5 year is for initial 6-month lookback)
            end = datetime.today()
            start = end - timedelta(days=365 * 3.5)
            
            all_tickers = TICKERS + [BENCHMARK]
            # Download daily data
            df_daily = yf.download(all_tickers, start=start, end=end)['Close']
            
            # Resample to get Month-End dates for rebalancing
            monthly_dates = df_daily.resample('ME').last().index
            
            portfolio_returns = []
            benchmark_returns = []
            dates_tracked = []
            
            # Start loop from month 6 (to have enough data for 6M ROC)
            for i in range(6, len(monthly_dates) - 1):
                eval_date = monthly_dates[i]
                start_lookback = monthly_dates[i-6]
                next_rebalance_date = monthly_dates[i+1]
                
                # 1. Calculate Momentum Score at eval_date
                scores = {}
                for t in TICKERS:
                    if t in df_daily.columns:
                        p_eval = df_daily[t].loc[:eval_date].dropna()
                        p_start = df_daily[t].loc[:start_lookback].dropna()
                        
                        if len(p_eval) > 0 and len(p_start) > 0:
                            curr_price = p_eval.iloc[-1]
                            old_price = p_start.iloc[-1]
                            
                            roc = (curr_price - old_price) / old_price
                            
                            # Calculate volatility over the 6 months
                            past_6m = df_daily[t].loc[start_lookback:eval_date].dropna()
                            if len(past_6m) > 20:
                                vol = past_6m.pct_change().std() * np.sqrt(252)
                                score = roc / vol if vol > 0 else 0
                                scores[t] = score
                
                # 2. Pick Top N Stocks
                if not scores: continue
                ranked_stocks = sorted(scores, key=scores.get, reverse=True)[:bt_top_n]
                
                # 3. Calculate 1-Month Forward Return for selected stocks
                port_month_ret = 0
                for t in ranked_stocks:
                    try:
                        buy_price = df_daily[t].loc[:eval_date].dropna().iloc[-1]
                        sell_price = df_daily[t].loc[:next_rebalance_date].dropna().iloc[-1]
                        stock_ret = (sell_price - buy_price) / buy_price
                        port_month_ret += stock_ret
                    except:
                        pass
                
                # Equal Weight Return
                port_month_ret = port_month_ret / bt_top_n
                portfolio_returns.append(port_month_ret)
                
                # 4. Calculate Benchmark Return (Nifty 50)
                try:
                    bench_buy = df_daily[BENCHMARK].loc[:eval_date].dropna().iloc[-1]
                    bench_sell = df_daily[BENCHMARK].loc[:next_rebalance_date].dropna().iloc[-1]
                    bench_ret = (bench_sell - bench_buy) / bench_buy
                except:
                    bench_ret = 0
                benchmark_returns.append(bench_ret)
                
                dates_tracked.append(next_rebalance_date)

            # --- Calculate Cumulative Equity Curve (Starting with ₹100) ---
            equity_df = pd.DataFrame(index=dates_tracked)
            equity_df['Momentum Strategy'] = 100 * (1 + pd.Series(portfolio_returns)).cumprod().values
            equity_df['Nifty 50 (Benchmark)'] = 100 * (1 + pd.Series(benchmark_returns)).cumprod().values
            
            # Show the Chart
            st.line_chart(equity_df, height=400)
            
            # Show Final Stats
            final_port_value = equity_df['Momentum Strategy'].iloc[-1]
            final_bench_value = equity_df['Nifty 50 (Benchmark)'].iloc[-1]
            
            col1, col2 = st.columns(2)
            col1.metric("Strategy Total Return", f"{round((final_port_value - 100), 2)} %")
            col2.metric("Nifty 50 Total Return", f"{round((final_bench_value - 100), 2)} %")
            
            st.info("Note: Backtest does not include slippage, taxes (STCG), and brokerage charges. Actual returns might slightly vary.")

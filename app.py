import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Momentum Builder & Backtester", layout="wide")
st.title("📈 Quantitative Momentum System")

# --- LOAD SYMBOLS FROM CSV ---
@st.cache_data
def load_symbols():
    # Check for the exact filename you uploaded, or fallback to 'symbols.csv'
    file_path = "STOCK SYMBOLS (3).csv"
    if not os.path.exists(file_path):
        file_path = "symbols.csv"
        
    if os.path.exists(file_path):
        df_symbols = pd.read_csv(file_path)
        # Adding '.NS' to all symbols for Yahoo Finance India
        ticker_list = []
        for sym in df_symbols['Symbol'].dropna():
            sym_str = str(sym).strip()
            if not sym_str.endswith('.NS'):
                sym_str += '.NS'
            ticker_list.append(sym_str)
        return ticker_list
    else:
        st.warning("CSV file not found! Please upload 'STOCK SYMBOLS (1).csv'. Running with fallback tickers.")
        return ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS"]

# Load Universe
TICKERS = load_symbols()
BENCHMARK = "^NSEI" # Nifty 50 index

st.sidebar.success(f"✅ Loaded {len(TICKERS)} stocks from CSV")

# Create Tabs
tab1, tab2 = st.tabs(["🔴 Live Momentum Scanner", "📊 Historical Equity Curve (Backtest)"])

# ==========================================
# TAB 1: LIVE SCANNER
# ==========================================
with tab1:
    st.header("Current Month Selection")
    top_n = st.slider("Select Top N Stocks for Portfolio", min_value=3, max_value=20, value=10, key='live_n')
    
    if st.button("Run Live Scanner"):
        with st.spinner(f"Fetching latest data for {len(TICKERS)} stocks. This might take a minute..."):
            end_date = datetime.today()
            start_date = end_date - timedelta(days=250) # Buffer to ensure 126 trading days
            
            # Download data quietly
            data = yf.download(TICKERS, start=start_date, end=end_date, progress=False)['Close']
            
            results = []
            for t in TICKERS:
                if t in data.columns:
                    series = data[t].dropna()
                    if len(series) >= 126: # Need approx 6 months of data
                        curr_price = series.iloc[-1]
                        price_6m_ago = series.iloc[-126]
                        
                        # 6 Month Return
                        roc = ((curr_price - price_6m_ago) / price_6m_ago) * 100
                        # Annualized Volatility
                        vol = series.pct_change().dropna().std() * np.sqrt(252) * 100
                        # Risk Adjusted Momentum
                        score = roc / vol if vol > 0 else 0
                        
                        results.append({
                            'Stock': t.replace('.NS', ''), 
                            'Current Price (₹)': round(curr_price, 2),
                            '6M Return (%)': round(roc, 2), 
                            'Volatility (%)': round(vol, 2), 
                            'Momentum Score': round(score, 2)
                        })
            
            if results:
                df = pd.DataFrame(results).sort_values(by='Momentum Score', ascending=False).reset_index(drop=True)
                df.index += 1
                
                st.success(f"🏆 Top {top_n} Stocks to Buy & Hold right now:")
                st.dataframe(df.head(top_n), use_container_width=True)
                
                st.info(f"💡 **Action:** Allocate {round(100/top_n, 2)}% of your capital to each of these {top_n} stocks.")
            else:
                st.error("Not enough data to calculate momentum.")

# ==========================================
# ==========================================
# TAB 2: BACKTEST & EQUITY CURVE
# ==========================================
with tab2:
    st.header("Momentum Strategy vs Nifty 50 (Last 3 Years)")
    st.markdown("Yeh system pichle 3 saalo mein har mahine Top N stocks ko automatically rebalance karke test karta hai.")
    
    # UI controls for Backtest
    col1, col2 = st.columns(2)
    with col1:
        bt_top_n = st.slider("Stocks to hold in Backtest", min_value=3, max_value=20, value=10, key='bt_n')
    with col2:
        # Naya feature: Transaction Cost (%)
        txn_cost_pct = st.number_input("Transaction Cost per Trade (%)", min_value=0.0, max_value=5.0, value=1.0, step=0.1, help="Total % deducted per round-trip trade (Buy + Sell charges & slippage). Example: 1.0 means 1% is lost to charges.")
    
    if st.button("Run Backtest & Plot Equity Curve"):
        with st.spinner("Simulating monthly rebalancing with transaction costs. Please wait..."):
            
            end = datetime.today()
            start = end - timedelta(days=365 * 3.5) # 3 years + 6 months lookback
            
            all_tickers = TICKERS + [BENCHMARK]
            df_daily = yf.download(all_tickers, start=start, end=end, progress=False)['Close']
            
            monthly_dates = df_daily.resample('ME').last().index
            
            portfolio_returns = []
            benchmark_returns = []
            dates_tracked = []
            
            # Decimal value for calculation (e.g., 1.0% -> 0.01)
            txn_cost_decimal = txn_cost_pct / 100.0
            
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
                            
                            past_6m = df_daily[t].loc[start_lookback:eval_date].dropna()
                            if len(past_6m) > 20:
                                vol = past_6m.pct_change().std() * np.sqrt(252)
                                score = roc / vol if vol > 0 else 0
                                scores[t] = score
                
                if not scores: continue
                
                # 2. Pick Top N Stocks
                ranked_stocks = sorted(scores, key=scores.get, reverse=True)[:bt_top_n]
                
                # 3. Calculate 1-Month Forward Return WITH TRANSACTION COSTS
                port_month_ret = 0
                valid_stocks = 0
                for t in ranked_stocks:
                    try:
                        buy_price = df_daily[t].loc[:eval_date].dropna().iloc[-1]
                        sell_price = df_daily[t].loc[:next_rebalance_date].dropna().iloc[-1]
                        
                        # Gross Return
                        gross_ret = (sell_price - buy_price) / buy_price
                        
                        # Net Return (Gross me se 1% deduction)
                        net_ret = gross_ret - txn_cost_decimal
                        
                        port_month_ret += net_ret
                        valid_stocks += 1
                    except Exception:
                        pass
                
                if valid_stocks > 0:
                    port_month_ret = port_month_ret / valid_stocks
                portfolio_returns.append(port_month_ret)
                
                # 4. Calculate Benchmark Return (No transaction cost on index)
                try:
                    bench_buy = df_daily[BENCHMARK].loc[:eval_date].dropna().iloc[-1]
                    bench_sell = df_daily[BENCHMARK].loc[:next_rebalance_date].dropna().iloc[-1]
                    bench_ret = (bench_sell - bench_buy) / bench_buy
                except Exception:
                    bench_ret = 0
                benchmark_returns.append(bench_ret)
                
                dates_tracked.append(next_rebalance_date)

            # --- Calculate Equity Curve ---
            if portfolio_returns:
                equity_df = pd.DataFrame(index=dates_tracked)
                equity_df['Momentum Strategy (Net of Costs)'] = 100 * (1 + pd.Series(portfolio_returns)).cumprod().values
                equity_df['Nifty 50 (Benchmark)'] = 100 * (1 + pd.Series(benchmark_returns)).cumprod().values
                
                st.line_chart(equity_df, height=400)
                
                # Display Final Returns
                final_port_value = equity_df['Momentum Strategy (Net of Costs)'].iloc[-1]
                final_bench_value = equity_df['Nifty 50 (Benchmark)'].iloc[-1]
                
                col1, col2 = st.columns(2)
                col1.metric(f"Strategy Net Return (After {txn_cost_pct}% Costs)", f"{round((final_port_value - 100), 2)} %")
                col2.metric("Nifty 50 Cumulative Return", f"{round((final_bench_value - 100), 2)} %")
                
                st.info(f"✅ Backtest applies a strict {txn_cost_pct}% capital penalty on every monthly rotation to simulate real-world trading friction.")
            else:
                st.error("Backtest failed. Not enough historical data.")

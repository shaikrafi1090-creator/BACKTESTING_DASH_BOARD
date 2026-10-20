import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Pro Quant Momentum System", layout="wide")
st.title("📈 Quantitative Momentum System")

# --- LOAD SYMBOLS FROM CSV ---
@st.cache_data
def load_symbols():
    file_path = "STOCK SYMBOLS (1).csv"
    if not os.path.exists(file_path):
        file_path = "symbols.csv"
        
    if os.path.exists(file_path):
        df_symbols = pd.read_csv(file_path)
        ticker_list = []
        for sym in df_symbols['Symbol'].dropna():
            sym_str = str(sym).strip()
            if not sym_str.endswith('.NS'):
                sym_str += '.NS'
            ticker_list.append(sym_str)
        return ticker_list
    else:
        st.warning("CSV file not found! Please upload 'STOCK SYMBOLS (1).csv'. Running with fallback tickers.")
        return ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS", "ITC.NS", "LT.NS"]

TICKERS = load_symbols()
BENCHMARK = "^NSEI" # Nifty 50 index

st.sidebar.success(f"✅ Loaded {len(TICKERS)} stocks from CSV")

# Create Tabs
tab1, tab2 = st.tabs(["🔴 Live Momentum Scanner", "📊 15-Year Backtest & Analytics"])

# ==========================================
# TAB 1: LIVE SCANNER
# ==========================================
with tab1:
    st.header("Current Month Selection")
    top_n = st.slider("Select Top N Stocks for Portfolio", min_value=3, max_value=20, value=10, key='live_n')
    
    if st.button("Run Live Scanner"):
        with st.spinner(f"Fetching latest data for {len(TICKERS)} stocks. This might take a minute..."):
            end_date = datetime.today()
            start_date = end_date - timedelta(days=250) # Buffer for 126 trading days
            
            data = yf.download(TICKERS, start=start_date, end=end_date, progress=False)['Close']
            
            results = []
            for t in TICKERS:
                if t in data.columns:
                    series = data[t].dropna()
                    if len(series) >= 126: 
                        curr_price = series.iloc[-1]
                        price_6m_ago = series.iloc[-126]
                        
                        # Pure Absolute Momentum 
                        roc = ((curr_price - price_6m_ago) / price_6m_ago) * 100
                        
                        results.append({
                            'Stock': t.replace('.NS', ''), 
                            'Current Price (₹)': round(curr_price, 2),
                            '6M Return (%)': round(roc, 2), 
                            'Momentum Score': round(roc, 2)
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
# TAB 2: BACKTEST & EQUITY CURVE
# ==========================================
with tab2:
    st.header("Momentum Strategy vs Nifty 50 (15-Year Engine)")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        bt_top_n = st.slider("Stocks to hold in Backtest", min_value=3, max_value=20, value=10, key='bt_n')
    with col2:
        txn_cost_pct = st.number_input("Transaction Cost per Trade (%)", min_value=0.0, max_value=5.0, value=1.0, step=0.1)
    with col3:
        rebalance_freq = st.selectbox("Rebalance Frequency", ["Monthly", "Quarterly"])
    
    if st.button("Run Backtest & Plot Analytics"):
        with st.spinner(f"Simulating {rebalance_freq} rebalancing for the LAST 15 YEARS. Fetching heavy data..."):
            
            end = datetime.today()
            start = end - timedelta(days=365 * 15.5) 
            
            all_tickers = TICKERS + [BENCHMARK]
            df_daily = yf.download(all_tickers, start=start, end=end, progress=False)['Close']
            
            monthly_dates = df_daily.resample('ME').last().index
            
            portfolio_returns = []
            benchmark_returns = []
            dates_tracked = []
            
            txn_cost_decimal = txn_cost_pct / 100.0
            
            previous_ranked_stocks = []
            active_positions = {}
            completed_trades = []
            
            step = 1 if rebalance_freq == "Monthly" else 3
            
            for i in range(6, len(monthly_dates) - step, step):
                eval_date = monthly_dates[i]
                start_lookback = monthly_dates[i-6]
                next_rebalance_date = monthly_dates[i+step]
                
                # 1. Calculate Pure Momentum Score
                scores = {}
                for t in TICKERS:
                    if t in df_daily.columns:
                        p_eval = df_daily[t].loc[:eval_date].dropna()
                        p_start = df_daily[t].loc[:start_lookback].dropna()
                        
                        if len(p_eval) > 0 and len(p_start) > 0:
                            curr_price = p_eval.iloc[-1]
                            old_price = p_start.iloc[-1]
                            roc = (curr_price - old_price) / old_price
                            scores[t] = roc
                
                if not scores: continue
                ranked_stocks = sorted(scores, key=scores.get, reverse=True)[:bt_top_n]
                
                # --- TRADE LOGIC (Exits) ---
                for t in list(active_positions.keys()):
                    if t not in ranked_stocks:
                        try:
                            entry_date = active_positions[t]['entry_date']
                            entry_price = active_positions[t]['entry_price']
                            exit_price = df_daily[t].loc[:eval_date].dropna().iloc[-1]
                            
                            days_held = (eval_date - entry_date).days
                            net_ret = ((exit_price - entry_price) / entry_price) - txn_cost_decimal
                            
                            completed_trades.append({
                                'Stock': t,
                                'Entry Date': entry_date.strftime('%Y-%m-%d'),
                                'Exit Date': eval_date.strftime('%Y-%m-%d'),
                                'Holding Days': days_held,
                                'Net Return (%)': round(net_ret * 100, 2)
                            })
                        except Exception:
                            pass
                        del active_positions[t]
                
                # --- TRADE LOGIC (Entries) ---
                for t in ranked_stocks:
                    if t not in active_positions:
                        try:
                            entry_price = df_daily[t].loc[:eval_date].dropna().iloc[-1]
                            active_positions[t] = {'entry_date': eval_date, 'entry_price': entry_price}
                        except Exception:
                            pass

                # --- PORTFOLIO RETURN LOGIC ---
                port_period_ret = 0
                valid_stocks = 0
                for t in ranked_stocks:
                    try:
                        buy_price = df_daily[t].loc[:eval_date].dropna().iloc[-1]
                        sell_price = df_daily[t].loc[:next_rebalance_date].dropna().iloc[-1]
                        gross_ret = (sell_price - buy_price) / buy_price
                        
                        if t not in previous_ranked_stocks:
                            net_ret = gross_ret - txn_cost_decimal
                        else:
                            net_ret = gross_ret
                            
                        port_period_ret += net_ret
                        valid_stocks += 1
                    except Exception:
                        pass
                
                if valid_stocks > 0:
                    port_period_ret = port_period_ret / valid_stocks
                portfolio_returns.append(port_period_ret)
                
                try:
                    bench_buy = df_daily[BENCHMARK].loc[:eval_date].dropna().iloc[-1]
                    bench_sell = df_daily[BENCHMARK].loc[:next_rebalance_date].dropna().iloc[-1]
                    benchmark_returns.append((bench_sell - bench_buy) / bench_buy)
                except Exception:
                    benchmark_returns.append(0)
                
                dates_tracked.append(next_rebalance_date)
                previous_ranked_stocks = ranked_stocks

            # Close Open Trades for Metric Calculation
            if dates_tracked:
                final_date = dates_tracked[-1]
                for t in list(active_positions.keys()):
                    try:
                        entry_date = active_positions[t]['entry_date']
                        entry_price = active_positions[t]['entry_price']
                        exit_price = df_daily[t].loc[:final_date].dropna().iloc[-1]
                        
                        days_held = (final_date - entry_date).days
                        net_ret = ((exit_price - entry_price) / entry_price) - txn_cost_decimal
                        
                        completed_trades.append({
                            'Stock': t,
                            'Entry Date': entry_date.strftime('%Y-%m-%d'),
                            'Exit Date': final_date.strftime('%Y-%m-%d') + " (Active)",
                            'Holding Days': days_held,
                            'Net Return (%)': round(net_ret * 100, 2)
                        })
                    except Exception:
                        pass

            # --- RENDER CHARTS AND ADVANCED METRICS ---
            if portfolio_returns and len(dates_tracked) > 1:
                equity_df = pd.DataFrame(index=dates_tracked)
                equity_df['Momentum Strategy (Net)'] = 100 * (1 + pd.Series(portfolio_returns)).cumprod().values
                equity_df['Nifty 50 Benchmark'] = 100 * (1 + pd.Series(benchmark_returns)).cumprod().values
                
                st.line_chart(equity_df, height=400)
                
                final_port_val = equity_df['Momentum Strategy (Net)'].iloc[-1]
                final_bench_val = equity_df['Nifty 50 Benchmark'].iloc[-1]
                
                # Accurate CAGR
                days_total = (dates_tracked[-1] - dates_tracked[0]).days
                years = days_total / 365.25 if days_total > 0 else 1
                
                cagr = ((final_port_val / 100) ** (1 / years)) - 1
                bench_cagr = ((final_bench_val / 100) ** (1 / years)) - 1
                
                # --- DRAWDOWN & RECOVERY CALCULATIONS ---
                roll_max = equity_df['Momentum Strategy (Net)'].cummax()
                drawdown = (equity_df['Momentum Strategy (Net)'] - roll_max) / roll_max
                max_dd = drawdown.min() * 100
                
                # Recovery Days (Runner-Up) for Strategy
                drawdown_duration = []
                current_duration = 0
                for dd in drawdown:
                    if dd < 0:
                        current_duration += 1
                    else:
                        drawdown_duration.append(current_duration)
                        current_duration = 0
                longest_dd_duration = max(drawdown_duration) if drawdown_duration else 0
                
                bench_roll_max = equity_df['Nifty 50 Benchmark'].cummax()
                bench_drawdown = (equity_df['Nifty 50 Benchmark'] - bench_roll_max) / bench_roll_max
                bench_max_dd = bench_drawdown.min() * 100
                
                # Recovery Days (Runner-Up) for Benchmark
                bench_dd_duration = []
                b_current_duration = 0
                for dd in bench_drawdown:
                    if dd < 0:
                        b_current_duration += 1
                    else:
                        bench_dd_duration.append(b_current_duration)
                        b_current_duration = 0
                bench_longest_duration = max(bench_dd_duration) if bench_dd_duration else 0
                
                # Sharpe Ratio
                rf_rate = 0.06
                port_returns_series = pd.Series(portfolio_returns)
                if port_returns_series.std() != 0:
                    annual_factor = np.sqrt(12) if rebalance_freq == "Monthly" else np.sqrt(4)
                    sharpe_ratio = (cagr - rf_rate) / (port_returns_series.std() * annual_factor)
                else:
                    sharpe_ratio = 0

                # Trade Stats
                trades_df = pd.DataFrame(completed_trades)
                if not trades_df.empty:
                    avg_holding_days = int(trades_df['Holding Days'].mean())
                    avg_trade_ret = trades_df['Net Return (%)'].mean()
                    median_trade_ret = trades_df['Net Return (%)'].median()
                    winning_trades = trades_df[trades_df['Net Return (%)'] > 0]
                    win_rate = (len(winning_trades) / len(trades_df)) * 100
                    best_trade = trades_df['Net Return (%)'].max()
                    worst_trade = trades_df['Net Return (%)'].min()
                else:
                    avg_holding_days = avg_trade_ret = median_trade_ret = 0
                    win_rate = best_trade = worst_trade = 0
                
                # Display 3 Rows of Analytics
                st.subheader(f"📈 15-Year Performance Analytics ({rebalance_freq})")
                
                st.markdown("**1. Return & Risk Profile**")
                r1_c1, r1_c2, r1_c3, r1_c4, r1_c5 = st.columns(5)
                r1_c1.metric("🚀 Strategy CAGR", f"{round(cagr * 100, 2)} %")
                r1_c2.metric("📉 Max Drawdown", f"{round(max_dd, 2)} %")
                r1_c3.metric("📊 Sharpe Ratio", f"{round(sharpe_ratio, 2)}")
                r1_c4.metric("📈 Nifty 50 CAGR", f"{round(bench_cagr * 100, 2)} %")
                r1_c5.metric("📉 Nifty Max DD", f"{round(bench_max_dd, 2)} %")
                
                st.markdown("**2. Floating Drawdown & Recovery Time**")
                rx_c1, rx_c2, rx_c3, rx_c4 = st.columns(4)
                rx_c1.metric("⏱️ Strategy Recovery", f"{longest_dd_duration} Periods", help="Longest time taken to recover a previous high (Runner-up).")
                rx_c2.metric("⚠️ Strategy Floating DD", f"{round(drawdown.iloc[-1] * 100, 2)} %", help="Current active drawdown from the last peak.")
                rx_c3.metric("⏱️ Nifty 50 Recovery", f"{bench_longest_duration} Periods")
                rx_c4.metric("⚠️ Nifty Floating DD", f"{round(bench_drawdown.iloc[-1] * 100, 2)} %")
                
                st.markdown("**3. Trade Execution Stats**")
                r2_c1, r2_c2, r2_c3, r2_c4, r2_c5 = st.columns(5)
                r2_c1.metric("🎯 Win Rate", f"{round(win_rate, 1)} %")
                r2_c2.metric("💰 Avg Return", f"{round(avg_trade_ret, 2)} %")
                r2_c3.metric("⚖️ Median Return", f"{round(median_trade_ret, 2)} %")
                r2_c4.metric("🏆 Best Trade", f"+{round(best_trade, 2)} %")
                r2_c5.metric("💔 Worst Trade", f"{round(worst_trade, 2)} %")
                
                st.markdown("---")
                st.subheader("📝 Per Script Total Returns & Trade Log")
                with st.expander("Click to View Complete Trade History"):
                    st.dataframe(trades_df.sort_values(by='Entry Date', ascending=False), use_container_width=True)
            else:
                st.error("Backtest failed. Not enough historical data. Ensure your CSV contains valid Yahoo Finance tickers.")

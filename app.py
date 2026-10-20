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
tab1, tab2 = st.tabs(["🔴 Live Momentum Scanner", "📊 Backtest & Analytics Engine"])

# ==========================================
# TAB 1: LIVE SCANNER
# ==========================================
with tab1:
    st.header("Current Month Selection")
    top_n = st.slider("Select Top N Stocks for Portfolio", min_value=3, max_value=20, value=10, key='live_n')
    
    if st.button("Run Live Scanner"):
        with st.spinner(f"Fetching latest data for {len(TICKERS)} stocks. This might take a minute..."):
            end_date = datetime.today()
            start_date = end_date - timedelta(days=250) 
            
            data = yf.download(TICKERS, start=start_date, end=end_date, progress=False)['Close']
            
            results = []
            for t in TICKERS:
                if t in data.columns:
                    series = data[t].dropna()
                    if len(series) >= 126: 
                        curr_price = series.iloc[-1]
                        price_6m_ago = series.iloc[-126]
                        
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
    
    # 5 Columns for Advanced UI Controls
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        bt_top_n = st.slider("Stocks to hold", min_value=3, max_value=20, value=10, key='bt_n')
    with col2:
        txn_cost_pct = st.number_input("Txn Cost (%)", min_value=0.0, max_value=5.0, value=1.0, step=0.1)
    with col3:
        rebalance_freq = st.selectbox("Rebalance", ["Monthly", "Quarterly"])
    with col4:
        backtest_period = st.selectbox("Test Duration", ["3 Years", "5 Years", "10 Years", "15 Years"], index=3)
    with col5:
        # NAYA FEATURE: Rolling Returns Period Option
        rolling_period = st.selectbox("Rolling Period", ["1 Year", "3 Years", "5 Years"])
    
    st.header(f"Momentum Strategy vs Nifty 50 ({backtest_period} Engine)")
    
    if st.button("Run Backtest & Plot Analytics"):
        with st.spinner(f"Simulating {rebalance_freq} rebalancing for the LAST {backtest_period.upper()}. Fetching data..."):
            
            years_map = {"3 Years": 3, "5 Years": 5, "10 Years": 10, "15 Years": 15}
            selected_years = years_map[backtest_period]
            
            end = datetime.today()
            start = end - timedelta(days=(365 * selected_years) + 182) 
            
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
                
                # Exits
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
                                'Entry Price (₹)': round(entry_price, 2),
                                'Exit Date': eval_date.strftime('%Y-%m-%d'),
                                'Exit Price (₹)': round(exit_price, 2),
                                'Holding Days': days_held,
                                'Net Return (%)': round(net_ret * 100, 2)
                            })
                        except Exception:
                            pass
                        del active_positions[t]
                
                # Entries
                for t in ranked_stocks:
                    if t not in active_positions:
                        try:
                            entry_price = df_daily[t].loc[:eval_date].dropna().iloc[-1]
                            active_positions[t] = {'entry_date': eval_date, 'entry_price': entry_price}
                        except Exception:
                            pass

                # Monthly Returns
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

            # Final Close
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
                            'Entry Price (₹)': round(entry_price, 2),
                            'Exit Date': final_date.strftime('%Y-%m-%d') + " (Active)",
                            'Exit Price (₹)': round(exit_price, 2),
                            'Holding Days': days_held,
                            'Net Return (%)': round(net_ret * 100, 2)
                        })
                    except Exception:
                        pass

            # --- METRICS & PLOTS ---
            if portfolio_returns and len(dates_tracked) > 1:
                equity_df = pd.DataFrame(index=dates_tracked)
                equity_df['Momentum Strategy (Net)'] = 100 * (1 + pd.Series(portfolio_returns)).cumprod().values
                equity_df['Nifty 50 Benchmark'] = 100 * (1 + pd.Series(benchmark_returns)).cumprod().values
                
                st.line_chart(equity_df, height=400)
                
                # Base Stats
                final_port_val = equity_df['Momentum Strategy (Net)'].iloc[-1]
                final_bench_val = equity_df['Nifty 50 Benchmark'].iloc[-1]
                days_total = (dates_tracked[-1] - dates_tracked[0]).days
                years = days_total / 365.25 if days_total > 0 else 1
                cagr = ((final_port_val / 100) ** (1 / years)) - 1
                bench_cagr = ((final_bench_val / 100) ** (1 / years)) - 1
                
                # Drawdown
                roll_max = equity_df['Momentum Strategy (Net)'].cummax()
                drawdown = (equity_df['Momentum Strategy (Net)'] - roll_max) / roll_max
                max_dd = drawdown.min() * 100
                
                bench_roll_max = equity_df['Nifty 50 Benchmark'].cummax()
                bench_drawdown = (equity_df['Nifty 50 Benchmark'] - bench_roll_max) / bench_roll_max
                bench_max_dd = bench_drawdown.min() * 100
                
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
                
                # -------------------------------------------------------------
                # 🔄 ROLLING RETURNS CALCULATION
                # -------------------------------------------------------------
                r_years = int(rolling_period.split()[0])
                periods_per_year = 12 if rebalance_freq == "Monthly" else 4
                rolling_window = r_years * periods_per_year
                
                st.markdown("---")
                if len(equity_df) > rolling_window:
                    st.subheader(f"🔄 {rolling_period} Rolling Returns (Strategy vs Nifty)")
                    
                    # (Current / Price N-periods ago) - 1
                    roll_strat = (equity_df['Momentum Strategy (Net)'] / equity_df['Momentum Strategy (Net)'].shift(rolling_window)) - 1
                    roll_bench = (equity_df['Nifty 50 Benchmark'] / equity_df['Nifty 50 Benchmark'].shift(rolling_window)) - 1
                    
                    rolling_df = pd.DataFrame({
                        f'Strategy {rolling_period} Return (%)': roll_strat * 100,
                        f'Nifty 50 {rolling_period} Return (%)': roll_bench * 100
                    }).dropna()
                    
                    # Plot Rolling Returns Curve
                 # Same colors yahan bhi apply karenge
                    st.line_chart(rolling_df, height=300, color=["#00C853", "#FFA500"])
                    
                    # Rolling Return Metrics
                    st_avg_roll = rolling_df.iloc[:, 0].mean()
                    bench_avg_roll = rolling_df.iloc[:, 1].mean()
                    
                    st_positive = (rolling_df.iloc[:, 0] > 0).mean() * 100
                    bench_positive = (rolling_df.iloc[:, 1] > 0).mean() * 100
                    
                    st_beat_nifty = (rolling_df.iloc[:, 0] > rolling_df.iloc[:, 1]).mean() * 100
                    
                    st.markdown(f"**{rolling_period} Rolling Statistics:**")
                    rc1, rc2, rc3, rc4 = st.columns(4)
                    rc1.metric(f"📈 Avg {rolling_period} Ret", f"{round(st_avg_roll, 2)} %")
                    rc2.metric(f"📉 Nifty Avg {rolling_period} Ret", f"{round(bench_avg_roll, 2)} %")
                    rc3.metric(f"🎯 Win Rate (Positive Returns)", f"{round(st_positive, 2)} %")
                    rc4.metric(f"🏆 Beaten Nifty (% of times)", f"{round(st_beat_nifty, 2)} %")
                else:
                    st.warning(f"⚠️ Your Backtest period ({backtest_period}) is too short to calculate a {rolling_period} rolling return window. Please increase Test Duration or decrease Rolling Period.")
                
                st.markdown("---")
                
                # --- METRICS UI ---
                st.subheader(f"📈 Core Performance Analytics")
                r1_c1, r1_c2, r1_c3, r1_c4, r1_c5 = st.columns(5)
                r1_c1.metric("🚀 Strategy CAGR", f"{round(cagr * 100, 2)} %")
                r1_c2.metric("📉 Max Drawdown", f"{round(max_dd, 2)} %")
                r1_c3.metric("🎯 Win Rate", f"{round(win_rate, 1)} %")
                r1_c4.metric("📈 Nifty 50 CAGR", f"{round(bench_cagr * 100, 2)} %")
                r1_c5.metric("📉 Nifty Max DD", f"{round(bench_max_dd, 2)} %")
                
                r2_c1, r2_c2, r2_c3, r2_c4, r2_c5 = st.columns(5)
                r2_c1.metric("💰 Avg Return (Trade)", f"{round(avg_trade_ret, 2)} %")
                r2_c2.metric("⚖️ Median Return", f"{round(median_trade_ret, 2)} %")
                r2_c3.metric("🏆 Best Trade", f"+{round(best_trade, 2)} %")
                r2_c4.metric("💔 Worst Trade", f"{round(worst_trade, 2)} %")
                r2_c5.metric("⚠️ Floating Drawdown", f"{round(drawdown.iloc[-1] * 100, 2)} %")
                
                st.markdown("---")
                st.subheader("📝 Per Script Total Returns & Trade Log")
                with st.expander("Click to View Complete Trade History"):
                    st.dataframe(trades_df.sort_values(by='Entry Date', ascending=False), use_container_width=True)
            else:
                st.error("Backtest failed. Not enough historical data.")

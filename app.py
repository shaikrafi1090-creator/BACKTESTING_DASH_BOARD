# UI Controls
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        bt_top_n = st.slider("Stocks to hold", min_value=3, max_value=20, value=10, key='bt_n')
    with col2:
        txn_cost_pct = st.number_input("Txn Cost (%)", min_value=0.0, max_value=5.0, value=1.0, step=0.1)
    with col3:
        rebalance_freq = st.selectbox("Rebalance", ["Monthly", "Quarterly"])
    with col4:
        backtest_period = st.selectbox("Test Duration", ["3 Years", "5 Years", "9 Years", "10 Years", "15 Years"], index=2)
    with col5:
        chunk_years = st.slider("Split Breakdown (Yrs)", min_value=1, max_value=5, value=3)

    # NEW: Advanced Strategy Overlays
    col6, col7 = st.columns(2)
    with col6:
        use_regime_filter = st.checkbox("🛡️ Enable Market Regime Filter (Exit to Cash if Nifty < 200 DMA)", value=True)
    with col7:
        use_cash_yield = st.checkbox("💵 Apply 5% Annual Liquid Fund Yield on Cash", value=False)
    
    st.header(f"Momentum Strategy vs Nifty 50 ({backtest_period} Engine)")
    
    if st.button("Run Backtest & Plot Analytics"):
        with st.spinner(f"Simulating {rebalance_freq} rebalancing for the LAST {backtest_period.upper()}. Fetching data..."):
            
            years_map = {"3 Years": 3, "5 Years": 5, "9 Years": 9, "10 Years": 10, "15 Years": 15}
            selected_years = years_map[backtest_period]
            
            # Fetch extra data for the 200 DMA calculation
            end = datetime.today()
            start = end - timedelta(days=(365 * selected_years) + 365) 
            
            all_tickers = TICKERS + [BENCHMARK]
            df_daily = yf.download(all_tickers, start=start, end=end, progress=False)['Close']
            
            # Calculate Nifty 200 DMA
            if BENCHMARK in df_daily.columns:
                df_daily['NIFTY_200_DMA'] = df_daily[BENCHMARK].rolling(window=200).mean()
            
            monthly_dates = pd.DatetimeIndex(df_daily.index.to_series().groupby(df_daily.index.to_period('M')).first().values)
            
            portfolio_returns = []
            benchmark_returns = []
            dates_tracked = []
            
            txn_cost_decimal = txn_cost_pct / 100.0
            cash_yield_monthly = (0.05 / 12) if use_cash_yield else 0.0
            previous_ranked_stocks = []
            active_positions = {}
            completed_trades = []
            
            step = 1 if rebalance_freq == "Monthly" else 3
            periods_per_year = 12 if rebalance_freq == "Monthly" else 4
            
            # Start loop after 200 days to ensure DMA is populated
            start_index = 12 
            
            for i in range(start_index, len(monthly_dates) - step, step):
                eval_date = monthly_dates[i]
                start_lookback = monthly_dates[i-6]
                next_rebalance_date = monthly_dates[i+step]
                
                # --- MARKET REGIME FILTER LOGIC ---
                is_bull_regime = True
                if use_regime_filter:
                    try:
                        current_nifty = df_daily[BENCHMARK].loc[:eval_date].dropna().iloc[-1]
                        current_dma = df_daily['NIFTY_200_DMA'].loc[:eval_date].dropna().iloc[-1]
                        if current_nifty < current_dma:
                            is_bull_regime = False
                    except:
                        pass
                
                scores = {}
                ranked_stocks = []
                
                if is_bull_regime:
                    for t in TICKERS:
                        if t in df_daily.columns and t != 'NIFTY_200_DMA':
                            p_eval = df_daily[t].loc[:eval_date].dropna()
                            p_start = df_daily[t].loc[:start_lookback].dropna()
                            
                            if len(p_eval) > 0 and len(p_start) > 0:
                                curr_price = p_eval.iloc[-1]
                                old_price = p_start.iloc[-1]
                                roc = (curr_price - old_price) / old_price
                                scores[t] = roc
                    
                    if scores:
                        ranked_stocks = sorted(scores, key=scores.get, reverse=True)[:bt_top_n]
                
                # Close positions no longer in top N (or if in Bear Regime)
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
                
                # Open new positions
                for t in ranked_stocks:
                    if t not in active_positions:
                        try:
                            entry_price = df_daily[t].loc[:eval_date].dropna().iloc[-1]
                            active_positions[t] = {'entry_date': eval_date, 'entry_price': entry_price}
                        except Exception:
                            pass

                # Calculate Portfolio Return for the Period
                port_period_ret = 0
                if is_bull_regime:
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
                else:
                    # Bear Regime: Portfolio is in Cash
                    port_period_ret = cash_yield_monthly * step

                portfolio_returns.append(port_period_ret)
                
                try:
                    bench_buy = df_daily[BENCHMARK].loc[:eval_date].dropna().iloc[-1]
                    bench_sell = df_daily[BENCHMARK].loc[:next_rebalance_date].dropna().iloc[-1]
                    benchmark_returns.append((bench_sell - bench_buy) / bench_buy)
                except Exception:
                    benchmark_returns.append(0)
                
                dates_tracked.append(next_rebalance_date)
                previous_ranked_stocks = ranked_stocks

            # ... (Rest of the metric calculation code remains the same) ...

            # NEW: Add Kelly Criterion to Insight Section
            # Add this right after calculating Win Rate and Payoff Ratio in the metrics block
            if win_rate > 0 and payoff_ratio > 0:
                win_prob = win_rate / 100.0
                kelly_fraction = win_prob - ((1 - win_prob) / payoff_ratio)
                kelly_pct = max(0, round(kelly_fraction * 100, 2))
                half_kelly = round(kelly_pct / 2, 2)
            else:
                kelly_pct = 0
                half_kelly = 0

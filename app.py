"""
Bitget Trading Analytics Dashboard
Groups opens + partial closes into positions
Correctly calculates P&L including fees and funding
Supports USDT-M and USDC-M file uploads
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import io
import base64

st.set_page_config(
    page_title="Bitget Trading Dashboard",
    page_icon="📊",
    layout="wide"
)


class BitgetAnalyzer:
    def __init__(self, df):
        self.df = df
        self.trades = []
        self.parse_trades()

    @staticmethod
    def load_csv(uploaded_file):
        content = uploaded_file.getvalue().decode('utf-8-sig')
        df = pd.read_csv(io.StringIO(content))
        df.columns = [col.strip() for col in df.columns]

        # Strip leading tabs/whitespace from the Order column
        if 'Order' in df.columns:
            df['Order'] = df['Order'].astype(str).str.strip()

        df['Date'] = pd.to_datetime(df['Date'].str.strip())
        df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce').fillna(0)
        df['Fee'] = pd.to_numeric(df['Fee'], errors='coerce').fillna(0)

        # Detect market type from Coin column
        if 'Coin' in df.columns:
            coin_val = df['Coin'].str.strip().iloc[0] if len(df) > 0 else ''
            if coin_val == 'USDC':
                df['Market'] = 'USDC-M'
            else:
                df['Market'] = 'USDT-M'
        else:
            df['Market'] = 'Unknown'

        return df

    @staticmethod
    def merge_dataframes(dfs):
        """Merge multiple DataFrames from different uploads."""
        if len(dfs) == 1:
            return dfs[0]
        combined = pd.concat(dfs, ignore_index=True)
        # Deduplicate by Order ID in case of overlapping exports
        if 'Order' in combined.columns:
            combined = combined.drop_duplicates(subset='Order', keep='first')
        combined = combined.sort_values('Date').reset_index(drop=True)
        return combined

    def get_funding_fees_for_position(self, symbol, open_date, close_date):
        """Calculate total funding fees for a position between open and close dates."""
        funding_df = self.df[
            (self.df['Futures'] == symbol) &
            (self.df['Type'] == 'contract_margin_settle_fee') &
            (self.df['Date'] >= open_date) &
            (self.df['Date'] <= close_date)
        ]
        return funding_df['Amount'].sum()

    def parse_trades(self):
        """
        Group opens and closes into positions per symbol.

        A position starts when we see an open (open_long/open_short) with no
        active position. It accumulates subsequent opens (adding to position)
        and closes (partial/full). The position ends when a NEW open appears
        AFTER at least one close has occurred, or at end of data.

        P&L = sum(close_amounts) + sum(close_fees) + sum(open_fees) + funding_fees
        (fees are negative values = costs, so adding them subtracts from P&L)
        """
        trade_types_open = {'open_short', 'open_long'}
        trade_types_close = {'close_short', 'close_long'}

        for symbol in self.df['Futures'].unique():
            symbol_df = self.df[self.df['Futures'] == symbol].sort_values('Date')

            # Detect market type for this symbol
            market = symbol_df['Market'].iloc[0] if 'Market' in symbol_df.columns else 'Unknown'

            positions = []
            current = None  # Current position being built

            for _, row in symbol_df.iterrows():
                txn_type = row['Type']

                if txn_type in trade_types_open:
                    if current is not None and current['has_close']:
                        # Previous position had closes → finalize it, start new
                        positions.append(current)
                        current = None

                    if current is None:
                        current = {
                            'direction': txn_type,
                            'open_date': row['Date'],
                            'open_fees': [],
                            'close_amounts': [],
                            'close_fees': [],
                            'close_dates': [],
                            'has_close': False,
                        }

                    current['open_fees'].append(row['Fee'])

                elif txn_type in trade_types_close:
                    if current is None:
                        # Orphan close (no matching open in data) — create minimal position
                        current = {
                            'direction': 'open_long' if txn_type == 'close_long' else 'open_short',
                            'open_date': row['Date'],
                            'open_fees': [],
                            'close_amounts': [],
                            'close_fees': [],
                            'close_dates': [],
                            'has_close': False,
                        }

                    current['has_close'] = True
                    current['close_amounts'].append(row['Amount'])
                    current['close_fees'].append(row['Fee'])
                    current['close_dates'].append(row['Date'])

            # Don't forget the last position
            if current is not None and current['has_close']:
                positions.append(current)

            # Convert positions to trade records
            for pos in positions:
                close_date = max(pos['close_dates'])
                open_date = pos['open_date']

                # Realized P&L from price movement
                realized_pnl = sum(pos['close_amounts'])

                # Fees (all negative = costs)
                total_close_fees = sum(pos['close_fees'])
                total_open_fees = sum(pos['open_fees'])

                # Funding fees during position lifetime
                funding_fees = self.get_funding_fees_for_position(
                    symbol, open_date, close_date
                )

                # Net P&L: realized + fees (negative) + funding
                net_pnl = realized_pnl + total_close_fees + total_open_fees + funding_fees

                is_win = net_pnl > 0
                holding_hours = (close_date - open_date).total_seconds() / 3600

                direction_label = 'Long' if 'long' in pos['direction'] else 'Short'

                self.trades.append({
                    'symbol': symbol,
                    'market': market,
                    'open_date': open_date,
                    'close_date': close_date,
                    'direction': direction_label,
                    'realized_pnl': realized_pnl,
                    'open_fees': total_open_fees,
                    'close_fees': total_close_fees,
                    'funding_fees': funding_fees,
                    'net_pnl': net_pnl,
                    'is_win': is_win,
                    'holding_hours': holding_hours,
                    'is_liquidation': False,
                    'num_closes': len(pos['close_amounts']),
                })

            # Handle liquidations separately
            liquidation_rows = symbol_df[
                symbol_df['Type'].str.contains('burst_close', na=False)
            ]
            for _, row in liquidation_rows.iterrows():
                pnl = row['Amount']
                fee = row['Fee']
                net_pnl = pnl + fee  # fee is negative

                direction_label = 'Short' if 'short' in row['Type'] else 'Long'

                self.trades.append({
                    'symbol': symbol,
                    'market': market,
                    'open_date': row['Date'],
                    'close_date': row['Date'],
                    'direction': direction_label,
                    'realized_pnl': pnl,
                    'open_fees': 0,
                    'close_fees': fee,
                    'funding_fees': 0,
                    'net_pnl': net_pnl,
                    'is_win': False,
                    'holding_hours': 0,
                    'is_liquidation': True,
                    'num_closes': 1,
                })

        self.trades.sort(key=lambda x: x['close_date'])

    def get_summary_stats(self):
        if not self.trades:
            return {}

        total_trades = len(self.trades)
        liquidation_count = sum(1 for t in self.trades if t['is_liquidation'])
        normal_count = total_trades - liquidation_count

        winning_trades = sum(1 for t in self.trades if t['is_win'])
        losing_trades = total_trades - winning_trades
        win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0

        total_pnl = sum(t['net_pnl'] for t in self.trades)
        gross_profit = sum(t['net_pnl'] for t in self.trades if t['net_pnl'] > 0)
        gross_loss = abs(sum(t['net_pnl'] for t in self.trades if t['net_pnl'] < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

        total_funding_fees = sum(t['funding_fees'] for t in self.trades)
        total_open_fees = sum(t['open_fees'] for t in self.trades)
        total_close_fees = sum(t['close_fees'] for t in self.trades)
        total_trading_fees = total_open_fees + total_close_fees

        avg_win = (
            sum(t['net_pnl'] for t in self.trades if t['net_pnl'] > 0) / winning_trades
            if winning_trades > 0 else 0
        )
        avg_loss = (
            sum(t['net_pnl'] for t in self.trades if t['net_pnl'] < 0) / losing_trades
            if losing_trades > 0 else 0
        )

        best_trade = max(self.trades, key=lambda x: x['net_pnl']) if self.trades else None
        worst_trade = min(self.trades, key=lambda x: x['net_pnl']) if self.trades else None

        returns = [t['net_pnl'] for t in self.trades]
        sharpe = (
            (np.mean(returns) / np.std(returns)) * np.sqrt(252)
            if np.std(returns) > 0 else 0
        )

        cumulative = np.cumsum(returns)
        running_max = np.maximum.accumulate(cumulative)
        drawdown = cumulative - running_max
        max_drawdown = np.min(drawdown) if len(drawdown) > 0 else 0

        expectancy = total_pnl / total_trades if total_trades > 0 else 0

        holding_hours = [t['holding_hours'] for t in self.trades if t['holding_hours'] > 0]
        avg_holding = np.mean(holding_hours) if holding_hours else 0

        return {
            'total_trades': total_trades,
            'normal_trades': normal_count,
            'liquidation_trades': liquidation_count,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'gross_profit': gross_profit,
            'gross_loss': gross_loss,
            'profit_factor': profit_factor,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'best_trade': best_trade,
            'worst_trade': worst_trade,
            'sharpe_ratio': sharpe,
            'max_drawdown': max_drawdown,
            'expectancy': expectancy,
            'avg_holding_hours': avg_holding,
            'total_funding_fees': total_funding_fees,
            'total_trading_fees': total_trading_fees,
            'total_open_fees': total_open_fees,
            'total_close_fees': total_close_fees,
        }

    def get_symbol_breakdown(self):
        symbol_stats = {}
        for trade in self.trades:
            sym = trade['symbol']
            if sym not in symbol_stats:
                symbol_stats[sym] = {
                    'trades': 0,
                    'wins': 0,
                    'total_pnl': 0,
                    'total_funding_fees': 0,
                    'liquidations': 0,
                    'liquidation_pnl': 0,
                    'market': trade.get('market', ''),
                }
            symbol_stats[sym]['trades'] += 1
            if trade['is_win']:
                symbol_stats[sym]['wins'] += 1
            symbol_stats[sym]['total_pnl'] += trade['net_pnl']
            symbol_stats[sym]['total_funding_fees'] += trade['funding_fees']
            if trade['is_liquidation']:
                symbol_stats[sym]['liquidations'] += 1
                symbol_stats[sym]['liquidation_pnl'] += trade['net_pnl']

        for sym in symbol_stats:
            s = symbol_stats[sym]
            s['win_rate'] = (s['wins'] / s['trades']) * 100 if s['trades'] > 0 else 0
            s['avg_pnl'] = s['total_pnl'] / s['trades'] if s['trades'] > 0 else 0

        return symbol_stats

    def get_time_series_data(self):
        if not self.trades:
            return pd.DataFrame()

        dates = [t['close_date'] for t in self.trades]
        cumulative_pnl = np.cumsum([t['net_pnl'] for t in self.trades])
        rolling_winrate = []
        liquidation_flags = [1 if t['is_liquidation'] else 0 for t in self.trades]

        for i in range(len(self.trades)):
            window = self.trades[max(0, i - 19):i + 1]
            winrate = (sum(1 for t in window if t['is_win']) / len(window)) * 100
            rolling_winrate.append(winrate)

        return pd.DataFrame({
            'date': dates,
            'pnl': [t['net_pnl'] for t in self.trades],
            'cumulative_pnl': cumulative_pnl,
            'rolling_winrate': rolling_winrate,
            'trade_number': range(1, len(self.trades) + 1),
            'is_liquidation': liquidation_flags,
        })

    def get_trades_df(self):
        return pd.DataFrame(self.trades)


def main():
    st.title("📊 Bitget Trading Analytics Dashboard")
    st.markdown("### Analyze your USDT-M / USDC-M Futures trading performance")
    st.markdown(
        "**✅ Position-based P&L · Partial closes grouped correctly · "
        "Funding fees included · Multi-file support**"
    )

    with st.sidebar:
        st.header("📁 Upload Data")
        st.markdown(
            "Upload one or both Bitget CSV transaction exports. "
            "The files will be merged automatically."
        )

        uploaded_files = st.file_uploader(
            "Upload Bitget CSV Export(s)",
            type=['csv'],
            accept_multiple_files=True,
            help="You can upload both USDT-M and USDC-M transaction exports at once.",
        )

        st.markdown("---")
        st.markdown("### How It Works")
        st.markdown(
            "- Opens and partial closes are **grouped into positions**\n"
            "- Funding fees are included for each position's lifetime\n"
            "- Trading fees (open + close) are subtracted\n"
            "- Liquidations are tracked separately\n"
            "- USDT-M and USDC-M files are merged if both uploaded"
        )

    if not uploaded_files:
        st.info("👈 Upload your Bitget CSV file(s) to begin")
        return

    with st.spinner("Analyzing your trades..."):
        try:
            dfs = []
            file_names = []
            for f in uploaded_files:
                df = BitgetAnalyzer.load_csv(f)
                dfs.append(df)
                file_names.append(f.name)

            combined_df = BitgetAnalyzer.merge_dataframes(dfs)
            analyzer = BitgetAnalyzer(combined_df)
            stats = analyzer.get_summary_stats()

            if not analyzer.trades:
                st.warning("No completed trades found in the uploaded data.")
                return

            market_info = ", ".join(
                sorted(combined_df['Market'].unique())
            )
            st.success(
                f"✅ **{len(analyzer.trades)} positions** analyzed from "
                f"**{len(uploaded_files)} file(s)** ({market_info})"
            )

        except Exception as e:
            st.error(f"Error: {str(e)}")
            import traceback
            st.code(traceback.format_exc())
            return

    # ── Summary metrics ──────────────────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Positions", stats['total_trades'])
        st.metric("Wins / Losses", f"{stats['winning_trades']} / {stats['losing_trades']}")

    with col2:
        win_icon = "🟢" if stats['win_rate'] >= 50 else "🔴"
        st.metric("Win Rate", f"{win_icon} {stats['win_rate']:.1f}%")
        st.metric("Profit Factor", f"{stats['profit_factor']:.2f}")

    with col3:
        pnl_icon = "🟢" if stats['total_pnl'] >= 0 else "🔴"
        st.metric("Total Net P&L", f"{pnl_icon} ${stats['total_pnl']:.2f}")
        st.metric("Max Drawdown", f"${stats['max_drawdown']:.2f}")

    with col4:
        st.metric("Liquidations", stats['liquidation_trades'])
        st.metric("Expectancy", f"${stats['expectancy']:.2f}")

    # ── Cumulative P&L chart ─────────────────────────────────────────
    ts_data = analyzer.get_time_series_data()
    if not ts_data.empty:
        st.subheader("📈 Cumulative P&L")
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=ts_data['date'],
            y=ts_data['cumulative_pnl'],
            mode='lines+markers',
            name='Cumulative P&L',
            line=dict(color='#00cc96', width=2),
            marker=dict(size=4),
        ))
        # Mark liquidations
        liq_data = ts_data[ts_data['is_liquidation'] == 1]
        if not liq_data.empty:
            fig.add_trace(go.Scatter(
                x=liq_data['date'],
                y=liq_data['cumulative_pnl'],
                mode='markers',
                name='Liquidation',
                marker=dict(color='red', size=10, symbol='x'),
            ))
        fig.update_layout(
            xaxis_title='Date',
            yaxis_title='Cumulative P&L ($)',
            template='plotly_dark',
            height=400,
        )
        st.plotly_chart(fig, use_container_width=True)

    # ── Fee breakdown ────────────────────────────────────────────────
    with st.expander("💰 Fee Breakdown"):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Open Fees", f"${stats['total_open_fees']:.4f}")
        with col2:
            st.metric("Close Fees", f"${stats['total_close_fees']:.4f}")
        with col3:
            st.metric("Total Trading Fees", f"${stats['total_trading_fees']:.4f}")
        with col4:
            st.metric("Total Funding Fees", f"${stats['total_funding_fees']:.4f}")

    # ── Advanced stats ───────────────────────────────────────────────
    with st.expander("📐 Advanced Stats"):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Avg Win", f"${stats['avg_win']:.2f}")
        with col2:
            st.metric("Avg Loss", f"${stats['avg_loss']:.2f}")
        with col3:
            st.metric("Sharpe Ratio", f"{stats['sharpe_ratio']:.2f}")
        with col4:
            st.metric("Avg Holding", f"{stats['avg_holding_hours']:.1f}h")

        if stats['best_trade']:
            st.markdown(
                f"**Best trade:** {stats['best_trade']['symbol']} → "
                f"${stats['best_trade']['net_pnl']:.2f}"
            )
        if stats['worst_trade']:
            st.markdown(
                f"**Worst trade:** {stats['worst_trade']['symbol']} → "
                f"${stats['worst_trade']['net_pnl']:.2f}"
            )

    # ── Symbol breakdown ─────────────────────────────────────────────
    st.subheader("📊 Performance by Symbol")
    symbol_stats = analyzer.get_symbol_breakdown()
    if symbol_stats:
        symbol_df = pd.DataFrame([
            {
                'Symbol': sym,
                'Market': data['market'],
                'Positions': data['trades'],
                'Wins': data['wins'],
                'Win Rate': f"{data['win_rate']:.1f}%",
                'Total P&L': round(data['total_pnl'], 2),
                'Avg P&L': round(data['avg_pnl'], 2),
                'Funding Fees': round(data['total_funding_fees'], 4),
                'Liquidations': data['liquidations'],
            }
            for sym, data in symbol_stats.items()
        ]).sort_values('Total P&L', ascending=False)

        st.dataframe(symbol_df, use_container_width=True, hide_index=True)

        # P&L by symbol bar chart
        fig_bar = go.Figure()
        colors = ['#00cc96' if v >= 0 else '#ef553b' for v in symbol_df['Total P&L']]
        fig_bar.add_trace(go.Bar(
            x=symbol_df['Symbol'],
            y=symbol_df['Total P&L'],
            marker_color=colors,
            text=[f"${v:.2f}" for v in symbol_df['Total P&L']],
            textposition='outside',
        ))
        fig_bar.update_layout(
            title='P&L by Symbol',
            yaxis_title='P&L ($)',
            template='plotly_dark',
            height=350,
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    # ── All positions ────────────────────────────────────────────────
    st.subheader("📋 All Positions")
    trades_df = analyzer.get_trades_df()
    if not trades_df.empty:
        display_df = trades_df.copy()
        display_df['open_date'] = pd.to_datetime(display_df['open_date']).dt.strftime('%Y-%m-%d %H:%M')
        display_df['close_date'] = pd.to_datetime(display_df['close_date']).dt.strftime('%Y-%m-%d %H:%M')
        display_df['net_pnl_fmt'] = display_df['net_pnl'].apply(lambda x: f"${x:.2f}")
        display_df['funding_fmt'] = display_df['funding_fees'].apply(lambda x: f"${x:.4f}")
        display_df['result'] = display_df.apply(
            lambda r: "⚠️ LIQUIDATION" if r['is_liquidation'] else ("✅ Win" if r['is_win'] else "❌ Loss"),
            axis=1,
        )
        display_df['holding'] = display_df['holding_hours'].apply(
            lambda x: f"{x:.1f}h" if x > 0 else "Instant"
        )

        st.dataframe(
            display_df[[
                'open_date', 'close_date', 'symbol', 'market', 'direction',
                'net_pnl_fmt', 'funding_fmt', 'result', 'holding', 'num_closes',
            ]].rename(columns={
                'open_date': 'Opened',
                'close_date': 'Closed',
                'symbol': 'Symbol',
                'market': 'Market',
                'direction': 'Direction',
                'net_pnl_fmt': 'Net P&L',
                'funding_fmt': 'Funding',
                'result': 'Result',
                'holding': 'Holding',
                'num_closes': 'Fills',
            }),
            use_container_width=True,
            hide_index=True,
        )

        # Download
        csv = trades_df.to_csv(index=False)
        b64 = base64.b64encode(csv.encode()).decode()
        st.markdown(
            f'<a href="data:file/csv;base64,{b64}" download="bitget_positions.csv">'
            f'📥 Download Positions CSV</a>',
            unsafe_allow_html=True,
        )


if __name__ == "__main__":
    main()

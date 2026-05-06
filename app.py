"""
Bitget Trading Analytics Dashboard
Streamlit app for analyzing Bitget USDT-M/USDC-M Futures trades
INCLUDES liquidations in P&L calculations
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from datetime import datetime
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
        self.liquidations = []
        self.parse_trades()
    
    @staticmethod
    def load_csv(uploaded_file):
        content = uploaded_file.getvalue().decode('utf-8')
        lines = content.split('\n')
        
        header_row = 0
        if lines and 'Order' in lines[0] and 'Date' not in lines[0]:
            header_row = 1
        
        df = pd.read_csv(io.StringIO(content), skiprows=header_row)
        df.columns = [col.strip() for col in df.columns]
        
        df['Date'] = pd.to_datetime(df['Date'])
        df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce')
        df['Fee'] = pd.to_numeric(df['Fee'], errors='coerce')
        
        return df
    
    def _group_by_time(self, transactions, time_window_seconds=60):
        if not transactions:
            return []
        
        groups = []
        current_group = [transactions[0]]
        
        for txn in transactions[1:]:
            time_diff = (txn['Date'] - current_group[0]['Date']).total_seconds()
            if time_diff <= time_window_seconds:
                current_group.append(txn)
            else:
                groups.append(current_group)
                current_group = [txn]
        
        if current_group:
            groups.append(current_group)
        
        return groups
    
    def parse_trades(self):
        """Parse open/close pairs AND liquidations into complete trades"""
        
        for symbol in self.df['Futures'].unique():
            symbol_df = self.df[self.df['Futures'] == symbol].sort_values('Date')
            
            # FIRST: Handle liquidations as individual trades
            liquidation_rows = symbol_df[symbol_df['Type'].str.contains('burst_close', na=False)]
            for _, row in liquidation_rows.iterrows():
                pnl = row['Amount'] if pd.notna(row['Amount']) else 0
                fee = row['Fee'] if pd.notna(row['Fee']) else 0
                net_pnl = pnl - fee  # Fee is already negative for liquidations usually
                
                self.liquidations.append({
                    'symbol': symbol,
                    'close_date': row['Date'],
                    'type': row['Type'],
                    'pnl': pnl,
                    'fee': fee,
                    'net_pnl': net_pnl,
                    'is_win': net_pnl > 0,
                    'is_liquidation': True
                })
                
                # Also add to main trades list
                self.trades.append({
                    'symbol': symbol,
                    'open_date': row['Date'],  # No open date for liquidations
                    'close_date': row['Date'],
                    'type': row['Type'],
                    'pnl': pnl,
                    'fee_paid': fee,
                    'fee_credit': 0,
                    'net_pnl': net_pnl,
                    'is_win': net_pnl > 0,
                    'holding_hours': 0,
                    'is_liquidation': True,
                    'partial_opens': 0,
                    'partial_closes': 1
                })
            
            # SECOND: Parse normal open/close pairs (excluding liquidations)
            normal_rows = symbol_df[~symbol_df['Type'].str.contains('burst_close', na=False)]
            
            # Separate opens and closes
            opens = []
            closes = []
            
            for _, row in normal_rows.iterrows():
                txn_type = row['Type']
                if txn_type in ['open_short', 'open_long']:
                    opens.append(row)
                elif txn_type in ['close_short', 'close_long']:
                    closes.append(row)
            
            # Group opens and closes within 60 seconds
            grouped_opens = self._group_by_time(opens)
            grouped_closes = self._group_by_time(closes)
            
            # Match groups (assume 1:1 matching in FIFO order)
            for open_group, close_group in zip(grouped_opens, grouped_closes):
                total_fee_credit = sum(abs(row['Fee']) for row in open_group if pd.notna(row['Fee']))
                total_pnl = sum(row['Amount'] for row in close_group if pd.notna(row['Amount']))
                total_fee_paid = sum(row['Fee'] for row in close_group if pd.notna(row['Fee']))
                
                net_pnl = total_pnl - total_fee_paid + total_fee_credit
                is_win = net_pnl > 0
                
                open_date = open_group[0]['Date']
                close_date = close_group[-1]['Date']
                holding_hours = (close_date - open_date).total_seconds() / 3600
                
                self.trades.append({
                    'symbol': symbol,
                    'open_date': open_date,
                    'close_date': close_date,
                    'type': open_group[0]['Type'],
                    'close_type': close_group[0]['Type'],
                    'pnl': total_pnl,
                    'fee_paid': total_fee_paid,
                    'fee_credit': total_fee_credit,
                    'net_pnl': net_pnl,
                    'is_win': is_win,
                    'holding_hours': holding_hours,
                    'is_liquidation': False,
                    'partial_opens': len(open_group),
                    'partial_closes': len(close_group)
                })
        
        # Sort all trades by close date
        self.trades.sort(key=lambda x: x['close_date'])
    
    def get_summary_stats(self):
        """Calculate summary statistics INCLUDING liquidations"""
        if not self.trades:
            return {}
        
        total_trades = len(self.trades)
        liquidation_count = sum(1 for t in self.trades if t.get('is_liquidation', False))
        normal_count = total_trades - liquidation_count
        
        winning_trades = sum(1 for t in self.trades if t['is_win'])
        losing_trades = total_trades - winning_trades
        win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0
        
        total_pnl = sum(t['net_pnl'] for t in self.trades)
        gross_profit = sum(t['net_pnl'] for t in self.trades if t['net_pnl'] > 0)
        gross_loss = abs(sum(t['net_pnl'] for t in self.trades if t['net_pnl'] < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        avg_win = sum(t['net_pnl'] for t in self.trades if t['net_pnl'] > 0) / winning_trades if winning_trades > 0 else 0
        avg_loss = sum(t['net_pnl'] for t in self.trades if t['net_pnl'] < 0) / losing_trades if losing_trades > 0 else 0
        
        # Best and worst trades (NOW INCLUDING LIQUIDATIONS)
        best_trade = max(self.trades, key=lambda x: x['net_pnl']) if self.trades else None
        worst_trade = min(self.trades, key=lambda x: x['net_pnl']) if self.trades else None
        
        # Separate best/worst by type
        best_normal = max([t for t in self.trades if not t.get('is_liquidation', False)], 
                         key=lambda x: x['net_pnl']) if normal_count > 0 else None
        worst_normal = min([t for t in self.trades if not t.get('is_liquidation', False)], 
                          key=lambda x: x['net_pnl']) if normal_count > 0 else None
        
        best_liquidation = max([t for t in self.trades if t.get('is_liquidation', False)], 
                              key=lambda x: x['net_pnl']) if liquidation_count > 0 else None
        worst_liquidation = min([t for t in self.trades if t.get('is_liquidation', False)], 
                               key=lambda x: x['net_pnl']) if liquidation_count > 0 else None
        
        # Calculate Sharpe Ratio
        returns = [t['net_pnl'] for t in self.trades]
        sharpe = (np.mean(returns) / np.std(returns)) * np.sqrt(252) if np.std(returns) > 0 else 0
        
        # Max drawdown
        cumulative = np.cumsum(returns)
        running_max = np.maximum.accumulate(cumulative)
        drawdown = cumulative - running_max
        max_drawdown = np.min(drawdown) if len(drawdown) > 0 else 0
        
        # Expectancy
        expectancy = total_pnl / total_trades if total_trades > 0 else 0
        
        # Average holding time
        avg_holding = np.mean([t['holding_hours'] for t in self.trades if t['holding_hours'] > 0]) if self.trades else 0
        
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
            'best_normal': best_normal,
            'worst_normal': worst_normal,
            'best_liquidation': best_liquidation,
            'worst_liquidation': worst_liquidation,
            'sharpe_ratio': sharpe,
            'max_drawdown': max_drawdown,
            'expectancy': expectancy,
            'avg_holding_hours': avg_holding
        }
    
    def get_symbol_breakdown(self):
        """Get performance by symbol"""
        symbol_stats = {}
        for trade in self.trades:
            sym = trade['symbol']
            if sym not in symbol_stats:
                symbol_stats[sym] = {
                    'trades': 0, 
                    'wins': 0, 
                    'total_pnl': 0,
                    'liquidations': 0,
                    'liquidation_pnl': 0
                }
            
            symbol_stats[sym]['trades'] += 1
            if trade['is_win']:
                symbol_stats[sym]['wins'] += 1
            symbol_stats[sym]['total_pnl'] += trade['net_pnl']
            
            if trade.get('is_liquidation', False):
                symbol_stats[sym]['liquidations'] += 1
                symbol_stats[sym]['liquidation_pnl'] += trade['net_pnl']
        
        for sym in symbol_stats:
            symbol_stats[sym]['win_rate'] = (symbol_stats[sym]['wins'] / symbol_stats[sym]['trades']) * 100 if symbol_stats[sym]['trades'] > 0 else 0
            symbol_stats[sym]['avg_pnl'] = symbol_stats[sym]['total_pnl'] / symbol_stats[sym]['trades'] if symbol_stats[sym]['trades'] > 0 else 0
        
        return symbol_stats
    
    def get_time_series_data(self):
        """Get time series data for charts"""
        if not self.trades:
            return pd.DataFrame()
        
        dates = [t['close_date'] for t in self.trades]
        cumulative_pnl = np.cumsum([t['net_pnl'] for t in self.trades])
        rolling_winrate = []
        liquidation_flags = [1 if t.get('is_liquidation', False) else 0 for t in self.trades]
        
        for i in range(len(self.trades)):
            window = self.trades[max(0, i-19):i+1]
            winrate = (sum(1 for t in window if t['is_win']) / len(window)) * 100
            rolling_winrate.append(winrate)
        
        return pd.DataFrame({
            'date': dates,
            'pnl': [t['net_pnl'] for t in self.trades],
            'cumulative_pnl': cumulative_pnl,
            'rolling_winrate': rolling_winrate,
            'trade_number': range(1, len(self.trades) + 1),
            'is_liquidation': liquidation_flags
        })
    
    def get_daily_pnl(self):
        """Aggregate P&L by day"""
        if not self.trades:
            return pd.DataFrame()
        
        daily = {}
        for trade in self.trades:
            if isinstance(trade['close_date'], pd.Timestamp):
                day = trade['close_date'].date()
            elif isinstance(trade['close_date'], datetime):
                day = trade['close_date'].date()
            else:
                day = pd.to_datetime(trade['close_date']).date()
            
            if day not in daily:
                daily[day] = {'pnl': 0, 'trades': 0, 'wins': 0, 'liquidations': 0}
            
            daily[day]['pnl'] += trade['net_pnl']
            daily[day]['trades'] += 1
            if trade['is_win']:
                daily[day]['wins'] += 1
            if trade.get('is_liquidation', False):
                daily[day]['liquidations'] += 1
        
        df_daily = pd.DataFrame([
            {'date': pd.Timestamp(day), 
             'pnl': data['pnl'], 
             'trades': data['trades'], 
             'wins': data['wins'],
             'liquidations': data['liquidations']}
            for day, data in daily.items()
        ]).sort_values('date')
        
        if not df_daily.empty:
            df_daily['win_rate'] = (df_daily['wins'] / df_daily['trades']) * 100
            df_daily['cumulative_pnl'] = df_daily['pnl'].cumsum()
        
        return df_daily
    
    def get_trades_df(self):
        """Get trades as DataFrame"""
        return pd.DataFrame(self.trades)

def main():
    st.title("📊 Bitget Trading Analytics Dashboard")
    st.markdown("### Analyze your USDT-M/USDC-M Futures trading performance")
    st.markdown("**⚠️ Includes liquidations (burst_close) in calculations**")
    
    with st.sidebar:
        st.header("📁 Data Source")
        uploaded_file = st.file_uploader(
            "Upload Bitget CSV Export",
            type=['csv'],
            help="Export your transaction history from Bitget as CSV"
        )
        
        st.markdown("---")
        st.markdown("### 📖 Instructions")
        st.markdown("""
        1. Export your USDT-M or USDC-M Futures transactions from Bitget
        2. Upload the CSV file here
        3. Explore your trading metrics
        """)
        
        st.markdown("---")
        st.markdown("### ⚠️ Important")
        st.markdown("""
        - **Liquidations (burst_close) are included** in all calculations
        - Partial fills within 60 seconds are grouped as one trade
        - Funding fees are tracked separately
        """)
        
        st.markdown("---")
        st.markdown("Made with ❤️ for Bitget traders")
    
    if uploaded_file is None:
        st.info("👈 Please upload your Bitget CSV file to get started")
        return
    
    with st.spinner("Loading and analyzing your trades..."):
        try:
            df = BitgetAnalyzer.load_csv(uploaded_file)
            analyzer = BitgetAnalyzer(df)
            stats = analyzer.get_summary_stats()
            
            if not analyzer.trades:
                st.warning("No trades found. Make sure your CSV has open/close transactions or liquidations.")
                return
            
            st.success(f"✅ Loaded {len(df)} transactions → {len(analyzer.trades)} trades (including {stats['liquidation_trades']} liquidations)")
            
        except Exception as e:
            st.error(f"Error: {str(e)}")
            return
    
    # Display summary metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Trades", stats['total_trades'])
        st.metric("Normal / Liquidation", f"{stats['normal_trades']} / {stats['liquidation_trades']}")
    
    with col2:
        win_color = "🟢" if stats['win_rate'] >= 50 else "🔴"
        st.metric("Win Rate", f"{win_color} {stats['win_rate']:.1f}%")
        st.metric("Profit Factor", f"{stats['profit_factor']:.2f}")
    
    with col3:
        pnl_color = "🟢" if stats['total_pnl'] >= 0 else "🔴"
        st.metric("Total Net P&L", f"{pnl_color} ${stats['total_pnl']:.2f}")
        st.metric("Expectancy", f"${stats['expectancy']:.2f}")
    
    with col4:
        st.metric("Sharpe Ratio", f"{stats['sharpe_ratio']:.2f}")
        st.metric("Max Drawdown", f"${stats['max_drawdown']:.2f}")
    
    # Best and Worst Trades (NOW INCLUDING LIQUIDATIONS)
    st.subheader("🏆 Best & Worst Trades")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**Best Trade Overall**")
        if stats['best_trade']:
            best = stats['best_trade']
            badge = "⚠️ LIQUIDATION" if best.get('is_liquidation', False) else "✅ NORMAL"
            st.info(f"""
            - **Symbol:** {best['symbol']}
            - **P&L:** ${best['net_pnl']:.2f}
            - **Date:** {best['close_date'].strftime('%Y-%m-%d %H:%M')}
            - **Type:** {best['type']}
            - **{badge}**
            """)
        
        if stats['best_normal']:
            st.markdown("**Best Normal Trade**")
            best_n = stats['best_normal']
            st.info(f"{best_n['symbol']} +${best_n['net_pnl']:.2f}")
        
        if stats['best_liquidation']:
            st.markdown("**Best Liquidation** (least bad)")
            best_l = stats['best_liquidation']
            color = "🟢" if best_l['net_pnl'] > 0 else "🔴"
            st.info(f"{color} {best_l['symbol']} ${best_l['net_pnl']:.2f}")
    
    with col2:
        st.markdown("**Worst Trade Overall**")
        if stats['worst_trade']:
            worst = stats['worst_trade']
            badge = "⚠️ LIQUIDATION" if worst.get('is_liquidation', False) else "❌ NORMAL"
            st.error(f"""
            - **Symbol:** {worst['symbol']}
            - **P&L:** ${worst['net_pnl']:.2f}
            - **Date:** {worst['close_date'].strftime('%Y-%m-%d %H:%M')}
            - **Type:** {worst['type']}
            - **{badge}**
            """)
        
        if stats['worst_normal']:
            st.markdown("**Worst Normal Trade**")
            worst_n = stats['worst_normal']
            st.error(f"{worst_n['symbol']} ${worst_n['net_pnl']:.2f}")
        
        if stats['worst_liquidation']:
            st.markdown("**Worst Liquidation**")
            worst_l = stats['worst_liquidation']
            st.error(f"⚠️ {worst_l['symbol']} ${worst_l['net_pnl']:.2f}")
    
    # Cumulative P&L Chart with liquidation markers
    st.subheader("📈 Cumulative P&L Over Time")
    ts_data = analyzer.get_time_series_data()
    if not ts_data.empty:
        fig = go.Figure()
        
        # Main equity line
        fig.add_trace(go.Scatter(
            x=ts_data['trade_number'],
            y=ts_data['cumulative_pnl'],
            mode='lines',
            name='Equity Curve',
            line=dict(color='#00ff00', width=2)
        ))
        
        # Mark liquidations
        liquidation_points = ts_data[ts_data['is_liquidation'] == 1]
        if not liquidation_points.empty:
            fig.add_trace(go.Scatter(
                x=liquidation_points['trade_number'],
                y=liquidation_points['cumulative_pnl'],
                mode='markers',
                name='Liquidations',
                marker=dict(color='red', size=10, symbol='x')
            ))
        
        fig.update_layout(height=450, xaxis_title="Trade Number", yaxis_title="Cumulative P&L (USDT)")
        fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
        st.plotly_chart(fig, use_container_width=True)
    
    # P&L Distribution by Trade Type
    st.subheader("📊 P&L Distribution")
    trades_df = analyzer.get_trades_df()
    if not trades_df.empty:
        trades_df['type_category'] = trades_df['is_liquidation'].apply(lambda x: 'Liquidation' if x else 'Normal')
        
        fig = px.histogram(
            trades_df,
            x='net_pnl',
            color='type_category',
            nbins=40,
            title="Trade P&L Distribution by Type",
            labels={'net_pnl': 'P&L (USDT)', 'count': 'Number of Trades'},
            color_discrete_map={'Normal': '#00ff00', 'Liquidation': '#ff4b4b'},
            barmode='overlay'
        )
        fig.add_vline(x=0, line_dash="dash", line_color="red")
        fig.update_layout(height=450)
        st.plotly_chart(fig, use_container_width=True)
    
    # Symbol Performance
    st.subheader("📈 Performance by Symbol")
    symbol_stats = analyzer.get_symbol_breakdown()
    
    if symbol_stats:
        symbol_df = pd.DataFrame([
            {
                'Symbol': sym,
                'Trades': data['trades'],
                'Wins': data['wins'],
                'Win Rate': f"{data['win_rate']:.1f}%",
                'Total P&L': f"${data['total_pnl']:.2f}",
                'Avg P&L': f"${data['avg_pnl']:.2f}",
                'Liquidations': data['liquidations'],
                'Liquidation P&L': f"${data['liquidation_pnl']:.2f}"
            }
            for sym, data in symbol_stats.items()
        ]).sort_values('Total P&L', ascending=False)
        
        st.dataframe(symbol_df, use_container_width=True, hide_index=True)
        
        # Bar chart with liquidation highlighting
        fig = go.Figure()
        symbols = list(symbol_stats.keys())
        total_pnls = [symbol_stats[s]['total_pnl'] for s in symbols]
        liq_pnls = [symbol_stats[s]['liquidation_pnl'] for s in symbols]
        
        fig.add_trace(go.Bar(
            name='Normal Trades',
            x=symbols,
            y=[total_pnls[i] - liq_pnls[i] for i in range(len(symbols))],
            marker_color='#00ff00'
        ))
        fig.add_trace(go.Bar(
            name='Liquidations',
            x=symbols,
            y=liq_pnls,
            marker_color='#ff4b4b'
        ))
        
        fig.update_layout(
            title="P&L Breakdown by Symbol (Normal vs Liquidations)",
            xaxis_title="Symbol",
            yaxis_title="P&L (USDT)",
            barmode='stack',
            height=450
        )
        st.plotly_chart(fig, use_container_width=True)
    
    # Trades Table
    st.subheader("📋 All Trades")
    if not trades_df.empty:
        display_df = trades_df.copy()
        display_df['close_date'] = pd.to_datetime(display_df['close_date']).dt.strftime('%Y-%m-%d %H:%M')
        display_df['net_pnl'] = display_df['net_pnl'].apply(lambda x: f"${x:.2f}")
        display_df['is_win'] = display_df['is_win'].apply(lambda x: "✅ Win" if x else "❌ Loss")
        display_df['is_liquidation'] = display_df['is_liquidation'].apply(lambda x: "⚠️ LIQUIDATION" if x else "Normal")
        display_df['holding_hours'] = display_df['holding_hours'].apply(lambda x: f"{x:.1f}h" if x > 0 else "Instant")
        
        st.dataframe(
            display_df[['close_date', 'symbol', 'is_liquidation', 'net_pnl', 'is_win', 'holding_hours']],
            use_container_width=True,
            hide_index=True,
            column_config={
                'is_liquidation': st.column_config.Column('Type'),
                'net_pnl': st.column_config.Column('P&L'),
                'is_win': st.column_config.Column('Result'),
            }
        )
        
        # Download button
        csv = trades_df.to_csv(index=False)
        b64 = base64.b64encode(csv.encode()).decode()
        st.markdown(f'<a href="data:file/csv;base64,{b64}" download="bitget_trades_with_liquidations.csv">📥 Download CSV (Includes Liquidations)</a>', unsafe_allow_html=True)
        
        # Risk Warning
        if stats['liquidation_trades'] > 0:
            st.warning(f"⚠️ **Risk Alert:** You have {stats['liquidation_trades']} liquidation(s) totaling ${stats['gross_loss']:.2f} in losses. Consider reviewing position sizing and stop-loss strategies.")

if __name__ == "__main__":
    main()

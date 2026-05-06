"""
Bitget Trading Analytics Dashboard
Streamlit app for analyzing Bitget USDT-M Futures trades
Groups partial fills into single trades
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

# Page configuration
st.set_page_config(
    page_title="Bitget Trading Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: nowrap;
        gap: 8px;
    }
    .profit-text {
        color: #00ff00;
        font-weight: bold;
    }
    .loss-text {
        color: #ff4b4b;
        font-weight: bold;
    }
    .big-metric {
        font-size: 2rem;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

class BitgetAnalyzer:
    def __init__(self, df):
        """Initialize with Bitget CSV data"""
        self.df = df
        self.trades = []
        self.parse_trades()
    
    @staticmethod
    def load_csv(uploaded_file):
        """Load and parse uploaded CSV"""
        content = uploaded_file.getvalue().decode('utf-8')
        lines = content.split('\n')
        
        # Find the actual header row (skip the first "Order" line if present)
        header_row = 0
        if lines and 'Order' in lines[0] and 'Date' not in lines[0]:
            header_row = 1
        
        df = pd.read_csv(io.StringIO(content), skiprows=header_row)
        df.columns = [col.strip() for col in df.columns]
        
        # Convert columns
        df['Date'] = pd.to_datetime(df['Date'])
        df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce')
        df['Fee'] = pd.to_numeric(df['Fee'], errors='coerce')
        df['Wallet balance'] = pd.to_numeric(df['Wallet balance'], errors='coerce')
        
        return df
    
    def _group_by_time(self, transactions, time_window_seconds=60):
        """Group transactions that occur within time_window_seconds of each other"""
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
        """Parse open/close pairs into complete trades, grouping partial fills by time window"""
        
        for symbol in self.df['Futures'].unique():
            symbol_df = self.df[self.df['Futures'] == symbol].sort_values('Date')
            
            # Separate opens and closes
            opens = []
            closes = []
            
            for _, row in symbol_df.iterrows():
                txn_type = row['Type']
                if txn_type in ['open_short', 'open_long']:
                    opens.append(row)
                elif txn_type in ['close_short', 'close_long']:
                    closes.append(row)
                # Ignore other transaction types (funding fees, transfers, etc.)
            
            # Group opens and closes within 60 seconds
            grouped_opens = self._group_by_time(opens)
            grouped_closes = self._group_by_time(closes)
            
            # Match groups (assume 1:1 matching in FIFO order)
            for open_group, close_group in zip(grouped_opens, grouped_closes):
                # Aggregate values from all partial fills
                total_fee_credit = sum(abs(row['Fee']) for row in open_group if pd.notna(row['Fee']))
                total_pnl = sum(row['Amount'] for row in close_group if pd.notna(row['Amount']))
                total_fee_paid = sum(row['Fee'] for row in close_group if pd.notna(row['Fee']))
                
                net_pnl = total_pnl - total_fee_paid + total_fee_credit
                is_win = net_pnl > 0
                
                # Dates - first open to last close
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
                    'partial_opens': len(open_group),
                    'partial_closes': len(close_group)
                })
        
        # Sort trades by close date
        self.trades.sort(key=lambda x: x['close_date'])
    
    def get_summary_stats(self):
        """Calculate summary statistics"""
        if not self.trades:
            return {}
        
        total_trades = len(self.trades)
        winning_trades = sum(1 for t in self.trades if t['is_win'])
        losing_trades = total_trades - winning_trades
        win_rate = (winning_trades / total_trades) * 100
        
        total_pnl = sum(t['net_pnl'] for t in self.trades)
        gross_profit = sum(t['net_pnl'] for t in self.trades if t['net_pnl'] > 0)
        gross_loss = abs(sum(t['net_pnl'] for t in self.trades if t['net_pnl'] < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        avg_win = sum(t['net_pnl'] for t in self.trades if t['net_pnl'] > 0) / winning_trades if winning_trades > 0 else 0
        avg_loss = sum(t['net_pnl'] for t in self.trades if t['net_pnl'] < 0) / losing_trades if losing_trades > 0 else 0
        
        best_trade = max(self.trades, key=lambda x: x['net_pnl']) if self.trades else None
        worst_trade = min(self.trades, key=lambda x: x['net_pnl']) if self.trades else None
        
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
        avg_holding = np.mean([t['holding_hours'] for t in self.trades]) if self.trades else 0
        
        return {
            'total_trades': total_trades,
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
            'avg_holding_hours': avg_holding
        }
    
    def get_symbol_breakdown(self):
        """Get performance by symbol"""
        symbol_stats = {}
        for trade in self.trades:
            sym = trade['symbol']
            if sym not in symbol_stats:
                symbol_stats[sym] = {'trades': 0, 'wins': 0, 'total_pnl': 0}
            
            symbol_stats[sym]['trades'] += 1
            if trade['is_win']:
                symbol_stats[sym]['wins'] += 1
            symbol_stats[sym]['total_pnl'] += trade['net_pnl']
        
        for sym in symbol_stats:
            symbol_stats[sym]['win_rate'] = (symbol_stats[sym]['wins'] / symbol_stats[sym]['trades']) * 100
            symbol_stats[sym]['avg_pnl'] = symbol_stats[sym]['total_pnl'] / symbol_stats[sym]['trades']
        
        return symbol_stats
    
    def get_time_series_data(self):
        """Get time series data for charts"""
        if not self.trades:
            return pd.DataFrame()
        
        dates = [t['close_date'] for t in self.trades]
        cumulative_pnl = np.cumsum([t['net_pnl'] for t in self.trades])
        rolling_winrate = []
        
        for i in range(len(self.trades)):
            window = self.trades[max(0, i-19):i+1]
            winrate = (sum(1 for t in window if t['is_win']) / len(window)) * 100
            rolling_winrate.append(winrate)
        
        return pd.DataFrame({
            'date': dates,
            'pnl': [t['net_pnl'] for t in self.trades],
            'cumulative_pnl': cumulative_pnl,
            'rolling_winrate': rolling_winrate,
            'trade_number': range(1, len(self.trades) + 1)
        })
    
    def get_daily_pnl(self):
        """Aggregate P&L by day"""
        if not self.trades:
            return pd.DataFrame()
        
        daily = {}
        for trade in self.trades:
            day = trade['close_date'].date()
            if day not in daily:
                daily[day] = {'pnl': 0, 'trades': 0, 'wins': 0}
            
            daily[day]['pnl'] += trade['net_pnl']
            daily[day]['trades'] += 1
            if trade['is_win']:
                daily[day]['wins'] += 1
        
        df_daily = pd.DataFrame([
            {'date': day, 'pnl': data['pnl'], 'trades': data['trades'], 'wins': data['wins']}
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
    st.markdown("### Analyze your USDT-M Futures trading performance")
    
    # Sidebar
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
        1. Export your USDT-M Futures transactions from Bitget
        2. Upload the CSV file here
        3. Explore your trading metrics
        """)
        
        st.markdown("---")
        st.markdown("### 🎯 Metrics Explained")
        st.markdown("""
        - **Win Rate**: % of profitable trades
        - **Profit Factor**: Gross profit / Gross loss (>1.5 is good)
        - **Sharpe Ratio**: Risk-adjusted return (>1 is good)
        - **Expectancy**: Average P&L per trade
        """)
        
        st.markdown("---")
        st.markdown("Made with ❤️ for Bitget traders")
    
    # File upload handling
    if uploaded_file is None:
        st.info("👈 Please upload your Bitget CSV file to get started")
        
        with st.expander("📋 Expected CSV format"):
            st.markdown("""
            Your Bitget CSV should have:
            - `Date` - Transaction timestamp
            - `Futures` - Trading pair (e.g., BTCUSDT)
            - `Type` - Transaction type
            - `Amount` - P&L for closes
            - `Fee` - Trading fees
            - `Wallet balance` - Running balance
            """)
        return
    
    # Load and analyze
    with st.spinner("Loading and analyzing your trades..."):
        try:
            df = BitgetAnalyzer.load_csv(uploaded_file)
            analyzer = BitgetAnalyzer(df)
            stats = analyzer.get_summary_stats()
            
            if not analyzer.trades:
                st.warning("No closed trades found. Make sure you have both open and close transactions.")
                return
            
            st.success(f"✅ Loaded {len(df)} transactions → {len(analyzer.trades)} completed trades")
            
        except Exception as e:
            st.error(f"Error: {str(e)}")
            return
    
    # Tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📈 Overview", "💰 P&L Analysis", "📊 Trade Breakdown", "📅 Calendar View", "📋 Raw Data"
    ])
    
    # Tab 1: Overview
    with tab1:
        # Key metrics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Trades", stats['total_trades'])
            st.metric("Win / Loss", f"{stats['winning_trades']} / {stats['losing_trades']}")
        
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
            st.metric("Avg Holding", f"{stats['avg_holding_hours']:.1f}h")
        
        # Best/Worst trades
        if stats['best_trade']:
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("### 🏆 Best Trade")
                best = stats['best_trade']
                st.markdown(f"""
                - **Symbol:** {best['symbol']}
                - **P&L:** ${best['net_pnl']:.2f}
                - **Date:** {best['close_date'].strftime('%Y-%m-%d %H:%M')}
                - **Duration:** {best['holding_hours']:.1f}h
                """)
            
            with col2:
                st.markdown("### 💩 Worst Trade")
                worst = stats['worst_trade']
                st.markdown(f"""
                - **Symbol:** {worst['symbol']}
                - **P&L:** ${worst['net_pnl']:.2f}
                - **Date:** {worst['close_date'].strftime('%Y-%m-%d %H:%M')}
                - **Duration:** {worst['holding_hours']:.1f}h
                """)
        
        # Cumulative P&L Chart
        st.markdown("### 📈 Cumulative P&L Over Time")
        ts_data = analyzer.get_time_series_data()
        if not ts_data.empty:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=ts_data['trade_number'],
                y=ts_data['cumulative_pnl'],
                mode='lines+markers',
                name='Cumulative P&L',
                line=dict(color='#00ff00', width=2),
                marker=dict(size=8, color='#00ff00')
            ))
            fig.update_layout(
                height=450,
                title="Equity Curve",
                xaxis_title="Trade Number",
                yaxis_title="Cumulative P&L (USDT)",
                hovermode='x unified'
            )
            # Add zero line
            fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
            st.plotly_chart(fig, use_container_width=True)
        
        # Rolling Win Rate
        st.markdown("### 🎯 Rolling Win Rate (20 trades)")
        if not ts_data.empty:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=ts_data['trade_number'],
                y=ts_data['rolling_winrate'],
                mode='lines',
                name='Win Rate',
                line=dict(color='#ff9900', width=2),
                fill='tozeroy',
                fillcolor='rgba(255, 153, 0, 0.2)'
            ))
            fig.add_hline(y=50, line_dash="dash", line_color="red", 
                         annotation_text="Breakeven", annotation_position="bottom right")
            fig.update_layout(
                height=350,
                title="Rolling Win Rate",
                xaxis_title="Trade Number",
                yaxis_title="Win Rate (%)",
                yaxis_range=[0, 100]
            )
            st.plotly_chart(fig, use_container_width=True)
    
    # Tab 2: P&L Analysis
    with tab2:
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### 📊 Win/Loss Distribution")
            fig = go.Figure(data=[go.Pie(
                labels=['Winning Trades', 'Losing Trades'],
                values=[stats['winning_trades'], stats['losing_trades']],
                marker_colors=['#00ff00', '#ff4b4b'],
                hole=0.4,
                textinfo='label+percent'
            )])
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            st.markdown("### 💰 Average Trade")
            fig = go.Figure(data=[
                go.Bar(name='Average Win', x=['Win'], y=[stats['avg_win']], 
                      marker_color='#00ff00', text=f"${stats['avg_win']:.2f}", textposition='auto'),
                go.Bar(name='Average Loss', x=['Loss'], y=[abs(stats['avg_loss'])], 
                      marker_color='#ff4b4b', text=f"${abs(stats['avg_loss']):.2f}", textposition='auto')
            ])
            fig.update_layout(height=400, yaxis_title="USDT", showlegend=True)
            st.plotly_chart(fig, use_container_width=True)
        
        # P&L Histogram
        st.markdown("### 📊 P&L Distribution")
        trades_df = analyzer.get_trades_df()
        if not trades_df.empty:
            fig = px.histogram(
                trades_df, 
                x='net_pnl', 
                nbins=30,
                title="Distribution of Trade Outcomes",
                labels={'net_pnl': 'P&L (USDT)', 'count': 'Number of Trades'},
                color_discrete_sequence=['#00ff00']
            )
            fig.add_vline(x=0, line_dash="dash", line_color="red", annotation_text="Breakeven")
            fig.update_layout(height=450)
            st.plotly_chart(fig, use_container_width=True)
        
        # P&L by Holding Time
        st.markdown("### ⏱️ P&L vs Holding Time")
        if not trades_df.empty:
            fig = px.scatter(
                trades_df,
                x='holding_hours',
                y='net_pnl',
                color='is_win',
                title="Trade P&L by Duration",
                labels={'holding_hours': 'Holding Time (hours)', 'net_pnl': 'P&L (USDT)'},
                color_discrete_map={True: '#00ff00', False: '#ff4b4b'}
            )
            fig.update_layout(height=450)
            st.plotly_chart(fig, use_container_width=True)
    
    # Tab 3: Trade Breakdown by Symbol
    with tab3:
        symbol_stats = analyzer.get_symbol_breakdown()
        
        if symbol_stats:
            st.markdown("### 📈 Performance by Symbol")
            
            # Create DataFrame
            symbol_df = pd.DataFrame([
                {
                    'Symbol': sym,
                    'Trades': data['trades'],
                    'Wins': data['wins'],
                    'Win Rate': f"{data['win_rate']:.1f}%",
                    'Total P&L': f"${data['total_pnl']:.2f}",
                    'Avg P&L': f"${data['avg_pnl']:.2f}"
                }
                for sym, data in symbol_stats.items()
            ]).sort_values('Total P&L', ascending=False)
            
            st.dataframe(symbol_df, use_container_width=True, hide_index=True)
            
            # Bar chart
            col1, col2 = st.columns(2)
            
            with col1:
                fig = go.Figure()
                symbols = list(symbol_stats.keys())
                pnls = [symbol_stats[s]['total_pnl'] for s in symbols]
                colors = ['#00ff00' if p > 0 else '#ff4b4b' for p in pnls]
                
                fig.add_trace(go.Bar(
                    x=symbols,
                    y=pnls,
                    marker_color=colors,
                    text=[f'${p:.2f}' for p in pnls],
                    textposition='auto'
                ))
                fig.update_layout(
                    title="Total P&L by Symbol",
                    xaxis_title="Symbol",
                    yaxis_title="Total P&L (USDT)",
                    height=400
                )
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                fig = go.Figure()
                win_rates = [symbol_stats[s]['win_rate'] for s in symbols]
                
                fig.add_trace(go.Bar(
                    x=symbols,
                    y=win_rates,
                    marker_color='#ff9900',
                    text=[f'{wr:.1f}%' for wr in win_rates],
                    textposition='auto'
                ))
                fig.add_hline(y=50, line_dash="dash", line_color="red")
                fig.update_layout(
                    title="Win Rate by Symbol",
                    xaxis_title="Symbol",
                    yaxis_title="Win Rate (%)",
                    yaxis_range=[0, 100],
                    height=400
                )
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No symbol data available")
    
    # Tab 4: Calendar View
    with tab4:
        daily_df = analyzer.get_daily_pnl()
        
        if not daily_df.empty and len(daily_df) > 0:
            st.markdown("### 📅 Daily Performance")
            
            # Daily P&L Chart
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=daily_df['date'],
                y=daily_df['pnl'],
                name="Daily P&L",
                marker_color=['#00ff00' if x > 0 else '#ff4b4b' for x in daily_df['pnl']],
                text=[f'${x:.2f}' for x in daily_df['pnl']],
                textposition='outside'
            ))
            fig.update_layout(
                height=450,
                title="Daily Profit & Loss",
                xaxis_title="Date",
                yaxis_title="P&L (USDT)"
            )
            fig.add_hline(y=0, line_dash="dash", line_color="gray")
            st.plotly_chart(fig, use_container_width=True)
            
            # Daily Stats Table
            st.markdown("### 📊 Daily Summary")
            daily_display = daily_df.copy()
            daily_display['date'] = daily_display['date'].dt.strftime('%Y-%m-%d')
            daily_display['pnl'] = daily_display['pnl'].apply(lambda x: f"${x:.2f}")
            daily_display['win_rate'] = daily_display['win_rate'].apply(lambda x: f"{x:.1f}%")
            daily_display = daily_display.rename(columns={
                'date': 'Date',
                'pnl': 'P&L',
                'trades': 'Trades',
                'wins': 'Wins',
                'win_rate': 'Win Rate'
            })
            st.dataframe(daily_display, use_container_width=True, hide_index=True)
            
            # Best/Worst Days
            if len(daily_df) > 0:
                col1, col2 = st.columns(2)
                
                best_day = daily_df.loc[daily_df['pnl'].idxmax()]
                worst_day = daily_df.loc[daily_df['pnl'].idxmin()]
                
                with col1:
                    st.markdown("### 🌟 Best Day")
                    st.markdown(f"""
                    - **Date:** {best_day['date'].strftime('%Y-%m-%d')}
                    - **P&L:** ${best_day['pnl']:.2f}
                    - **Trades:** {best_day['trades']}
                    - **Win Rate:** {best_day['win_rate']:.1f}%
                    """)
                
                with col2:
                    st.markdown("### 📉 Worst Day")
                    st.markdown(f"""
                    - **Date:** {worst_day['date'].strftime('%Y-%m-%d')}
                    - **P&L:** ${worst_day['pnl']:.2f}
                    - **Trades:** {worst_day['trades']}
                    - **Win Rate:** {worst_day['win_rate']:.1f}%
                    """)
        else:
            st.info("Not enough daily data to display calendar view")
    
    # Tab 5: Raw Data
    with tab5:
        st.markdown("### 📋 All Trades")
        
        trades_df = analyzer.get_trades_df()
        if not trades_df.empty:
            # Format for display
            display_df = trades_df.copy()
            display_df['close_date'] = display_df['close_date'].dt.strftime('%Y-%m-%d %H:%M')
            display_df['open_date'] = display_df['open_date'].dt.strftime('%Y-%m-%d %H:%M')
            display_df['net_pnl'] = display_df['net_pnl'].apply(lambda x: f"${x:.2f}")
            display_df['is_win'] = display_df['is_win'].apply(lambda x: "✅ Win" if x else "❌ Loss")
            display_df['holding_hours'] = display_df['holding_hours'].apply(lambda x: f"{x:.1f}h")
            
            # Select and rename columns
            display_df = display_df[[
                'close_date', 'symbol', 'type', 'net_pnl', 'is_win', 
                'holding_hours', 'partial_opens', 'partial_closes'
            ]]
            display_df.columns = [
                'Close Date', 'Symbol', 'Type', 'P&L', 'Result', 
                'Holding Time', 'Partial Opens', 'Partial Closes'
            ]
            
            st.dataframe(display_df, use_container_width=True, hide_index=True)
            
            # Download button
            csv = trades_df.to_csv(index=False)
            b64 = base64.b64encode(csv.encode()).decode()
            href = f'<a href="data:file/csv;base64,{b64}" download="bitget_trades_export.csv" style="text-decoration: none; background: #00ff00; color: black; padding: 10px 20px; border-radius: 5px;">📥 Download Trades as CSV</a>'
            st.markdown(href, unsafe_allow_html=True)
            
            # Summary
            st.markdown("### 📊 Summary")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Trades", len(trades_df))
            with col2:
                st.metric("Winning Trades", len(trades_df[trades_df['is_win']]))
            with col3:
                st.metric("Losing Trades", len(trades_df[~trades_df['is_win']]))
        else:
            st.info("No trade data available")

if __name__ == "__main__":
    main()

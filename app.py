"""
Bitget Trading Analytics Dashboard
Streamlit app for analyzing Bitget USDT-M Futures trades
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
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
    .metric-card {
        padding: 15px;
        border-radius: 10px;
        background-color: #f0f2f6;
        text-align: center;
    }
    .profit-text {
        color: #00ff00;
        font-weight: bold;
    }
    .loss-text {
        color: #ff4b4b;
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
        
        header_row = 0
        if lines and 'Order' in lines[0] and 'Date' not in lines[0]:
            header_row = 1
        
        df = pd.read_csv(io.StringIO(content), skiprows=header_row)
        df.columns = [col.strip() for col in df.columns]
        
        df['Date'] = pd.to_datetime(df['Date'])
        df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce')
        df['Fee'] = pd.to_numeric(df['Fee'], errors='coerce')
        df['Wallet balance'] = pd.to_numeric(df['Wallet balance'], errors='coerce')
        
        return df
    
    def parse_trades(self):
        """Parse open/close pairs into complete trades"""
        for symbol in self.df['Futures'].unique():
            symbol_df = self.df[self.df['Futures'] == symbol].sort_values('Date')
            open_positions = []
            
            for _, row in symbol_df.iterrows():
                txn_type = row['Type']
                
                if txn_type in ['open_short', 'open_long']:
                    open_positions.append({
                        'open_date': row['Date'],
                        'type': txn_type,
                        'fee_credit': abs(row['Fee']) if pd.notna(row['Fee']) else 0,
                        'wallet_balance': row['Wallet balance']
                    })
                
                elif txn_type in ['close_short', 'close_long']:
                    if open_positions:
                        position = open_positions.pop(0)
                        pnl = row['Amount'] if pd.notna(row['Amount']) else 0
                        fee = row['Fee'] if pd.notna(row['Fee']) else 0
                        
                        is_win = pnl > 0
                        holding_hours = (row['Date'] - position['open_date']).total_seconds() / 3600
                        
                        self.trades.append({
                            'symbol': symbol,
                            'open_date': position['open_date'],
                            'close_date': row['Date'],
                            'type': position['type'],
                            'close_type': txn_type,
                            'pnl': pnl,
                            'fee_paid': fee,
                            'fee_credit': position['fee_credit'],
                            'net_pnl': pnl - fee + position['fee_credit'],
                            'is_win': is_win,
                            'holding_hours': holding_hours
                        })
    
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
        
        returns = [t['net_pnl'] for t in self.trades]
        sharpe = (np.mean(returns) / np.std(returns)) * np.sqrt(252) if np.std(returns) > 0 else 0
        
        cumulative = np.cumsum(returns)
        running_max = np.maximum.accumulate(cumulative)
        drawdown = cumulative - running_max
        max_drawdown = np.min(drawdown) if len(drawdown) > 0 else 0
        
        expectancy = total_pnl / total_trades if total_trades > 0 else 0
        
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
            'avg_holding_hours': np.mean([t['holding_hours'] for t in self.trades]) if self.trades else 0,
            'max_drawdown': max_drawdown,
            'expectancy': expectancy
        }
    
    def get_symbol_breakdown(self):
        """Get performance by symbol"""
        symbol_stats = {}
        for trade in self.trades:
            sym = trade['symbol']
            if sym not in symbol_stats:
                symbol_stats[sym] = {'trades': 0, 'wins': 0, 'total_pnl': 0, 'pnl_list': []}
            
            symbol_stats[sym]['trades'] += 1
            if trade['is_win']:
                symbol_stats[sym]['wins'] += 1
            symbol_stats[sym]['total_pnl'] += trade['net_pnl']
            symbol_stats[sym]['pnl_list'].append(trade['net_pnl'])
        
        for sym in symbol_stats:
            symbol_stats[sym]['win_rate'] = (symbol_stats[sym]['wins'] / symbol_stats[sym]['trades']) * 100
            symbol_stats[sym]['avg_pnl'] = symbol_stats[sym]['total_pnl'] / symbol_stats[sym]['trades']
        
        return symbol_stats
    
    def get_time_series_data(self):
        """Get time series data for charts"""
        if not self.trades:
            return pd.DataFrame()
        
        trades_sorted = sorted(self.trades, key=lambda x: x['close_date'])
        
        dates = []
        for t in trades_sorted:
            close_date = t['close_date']
            if isinstance(close_date, str):
                close_date = pd.to_datetime(close_date)
            dates.append(close_date)
        
        cumulative_pnl = np.cumsum([t['net_pnl'] for t in trades_sorted])
        rolling_winrate = []
        
        for i in range(len(trades_sorted)):
            window = trades_sorted[max(0, i-19):i+1]
            winrate = (sum(1 for t in window if t['is_win']) / len(window)) * 100
            rolling_winrate.append(winrate)
        
        return pd.DataFrame({
            'date': dates,
            'pnl': [t['net_pnl'] for t in trades_sorted],
            'cumulative_pnl': cumulative_pnl,
            'rolling_winrate': rolling_winrate
        })
    
    def get_daily_pnl(self):
        """Aggregate P&L by day"""
        if not self.trades:
            return pd.DataFrame()
        
        daily = {}
        for trade in self.trades:
            close_date = trade['close_date']
            if isinstance(close_date, str):
                close_date = pd.to_datetime(close_date)
            day = close_date.date()
            
            if day not in daily:
                daily[day] = {'pnl': 0, 'trades': 0, 'wins': 0}
            
            daily[day]['pnl'] += trade['net_pnl']
            daily[day]['trades'] += 1
            if trade['is_win']:
                daily[day]['wins'] += 1
        
        df_daily = pd.DataFrame([
            {'date': pd.to_datetime(day), 'pnl': data['pnl'], 'trades': data['trades'], 'wins': data['wins']}
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
        3. Explore your trading metrics and charts
        """)
        
        st.markdown("---")
        st.markdown("### 🎯 Metrics Explained")
        st.markdown("""
        - **Win Rate**: Percentage of profitable trades
        - **Profit Factor**: Gross profit / Gross loss (>1.5 is good)
        - **Sharpe Ratio**: Risk-adjusted return (>1 is good)
        - **Max Drawdown**: Largest peak-to-trough decline
        - **Expectancy**: Average P&L per trade
        """)
        
        st.markdown("---")
        st.markdown("Made with ❤️ for Bitget traders")
    
    if uploaded_file is None:
        st.info("👈 Please upload your Bitget CSV file to get started")
        
        with st.expander("📋 See expected CSV format"):
            st.markdown("""
            Your Bitget CSV should have these columns:
            - `Date` - Transaction timestamp
            - `Futures` - Trading pair (e.g., BTCUSDT)
            - `Type` - Transaction type (open_long, close_short, etc.)
            - `Amount` - P&L amount for closes
            - `Fee` - Trading fees
            - `Wallet balance` - Running balance
            
            **Supported transaction types:**
            - `open_long` / `open_short` - Opening positions
            - `close_long` / `close_short` - Closing positions
            """)
        return
    
    with st.spinner("Loading and analyzing your trades..."):
        try:
            df = BitgetAnalyzer.load_csv(uploaded_file)
            analyzer = BitgetAnalyzer(df)
            stats = analyzer.get_summary_stats()
            
            if not analyzer.trades:
                st.warning("No closed trades found in the CSV file.")
                return
            
            st.success(f"✅ Loaded {len(df)} transactions and parsed {len(analyzer.trades)} completed trades")
            
        except Exception as e:
            st.error(f"Error parsing CSV: {str(e)}")
            return
    
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📈 Overview", "💰 P&L Analysis", "📊 Trade Breakdown", "📅 Calendar View", "📋 Raw Data"
    ])
    
    with tab1:
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Trades", stats['total_trades'])
            st.metric("Win / Loss", f"{stats['winning_trades']} / {stats['losing_trades']}")
        
        with col2:
            st.metric("Win Rate", f"{stats['win_rate']:.1f}%")
            st.metric("Profit Factor", f"{stats['profit_factor']:.2f}")
        
        with col3:
            total_pnl_color = "🟢" if stats['total_pnl'] >= 0 else "🔴"
            st.metric("Total Net P&L", f"{total_pnl_color} ${stats['total_pnl']:.4f}")
            st.metric("Expectancy", f"${stats['expectancy']:.4f}")
        
        with col4:
            st.metric("Sharpe Ratio", f"{stats['sharpe_ratio']:.2f}")
            st.metric("Max Drawdown", f"${stats['max_drawdown']:.4f}")
        
        if stats['best_trade']:
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("### 🏆 Best Trade")
                best = stats['best_trade']
                st.markdown(f"""
                - **Symbol:** {best['symbol']}
                - **P&L:** ${best['net_pnl']:.4f}
                - **Holding:** {best['holding_hours']:.1f}h
                """)
            
            with col2:
                st.markdown("### 💩 Worst Trade")
                worst = stats['worst_trade']
                st.markdown(f"""
                - **Symbol:** {worst['symbol']}
                - **P&L:** ${worst['net_pnl']:.4f}
                - **Holding:** {worst['holding_hours']:.1f}h
                """)
        
        ts_data = analyzer.get_time_series_data()
        if not ts_data.empty:
            st.markdown("### 📈 Cumulative P&L Over Time")
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=ts_data['date'],
                y=ts_data['cumulative_pnl'],
                mode='lines+markers',
                name='Cumulative P&L',
                line=dict(color='#00ff00', width=2)
            ))
            fig.update_layout(height=400, xaxis_title="Date", yaxis_title="Cumulative P&L (USDT)")
            st.plotly_chart(fig, use_container_width=True)
    
    with tab2:
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### 📊 Win/Loss Distribution")
            fig = go.Figure(data=[go.Pie(
                labels=['Winning Trades', 'Losing Trades'],
                values=[stats['winning_trades'], stats['losing_trades']],
                marker_colors=['#00ff00', '#ff4b4b'],
                hole=0.4
            )])
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            st.markdown("### 💰 Average Trade")
            fig = go.Figure(data=[
                go.Bar(name='Win', x=['Win'], y=[stats['avg_win']], marker_color='#00ff00'),
                go.Bar(name='Loss', x=['Loss'], y=[abs(stats['avg_loss'])], marker_color='#ff4b4b')
            ])
            fig.update_layout(height=400, yaxis_title="USDT")
            st.plotly_chart(fig, use_container_width=True)
        
        trades_df = analyzer.get_trades_df()
        if not trades_df.empty:
            fig = px.histogram(
                trades_df, x='net_pnl', nbins=30,
                title="P&L Distribution",
                color_discrete_sequence=['#00ff00']
            )
            fig.add_vline(x=0, line_dash="dash", line_color="red")
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)
    
    with tab3:
        symbol_stats = analyzer.get_symbol_breakdown()
        if symbol_stats:
            symbol_df = pd.DataFrame([
                {'Symbol': sym, 'Trades': data['trades'], 'Wins': data['wins'],
                 'Win Rate': f"{data['win_rate']:.1f}%", 'Total P&L': f"${data['total_pnl']:.4f}"}
                for sym, data in symbol_stats.items()
            ]).sort_values('Total P&L', ascending=False)
            st.dataframe(symbol_df, use_container_width=True)
    
    with tab4:
        daily_df = analyzer.get_daily_pnl()
        if not daily_df.empty and len(daily_df) > 1:
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=daily_df['date'], y=daily_df['pnl'],
                name="Daily P&L",
                marker_color=['#00ff00' if x > 0 else '#ff4b4b' for x in daily_df['pnl']]
            ))
            fig.update_layout(height=400, title="Daily P&L", xaxis_title="Date", yaxis_title="USDT")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Not enough daily data")
    
    with tab5:
        trades_df = analyzer.get_trades_df()
        if not trades_df.empty:
            display_df = trades_df.copy()
            display_df['close_date'] = pd.to_datetime(display_df['close_date']).dt.strftime('%Y-%m-%d %H:%M')
            display_df['net_pnl'] = display_df['net_pnl'].apply(lambda x: f"${x:.4f}")
            display_df['is_win'] = display_df['is_win'].apply(lambda x: "✅ Win" if x else "❌ Loss")
            st.dataframe(display_df[['close_date', 'symbol', 'net_pnl', 'is_win', 'holding_hours']], 
                        use_container_width=True)

if __name__ == "__main__":
    main()

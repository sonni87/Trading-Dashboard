"""
Bitget Trading Analytics Dashboard
Correctly matches opens with closes chronologically
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
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
    
    def parse_trades(self):
        """
        Match opens with closes chronologically
        Each close is matched with the most recent open before it
        """
        
        for symbol in self.df['Futures'].unique():
            symbol_df = self.df[self.df['Futures'] == symbol].sort_values('Date')
            
            # Collect all opens and closes as dictionaries with scalar values
            opens = []
            closes = []
            
            for _, row in symbol_df.iterrows():
                txn_type = row['Type']
                if txn_type in ['open_short', 'open_long']:
                    opens.append({
                        'date': row['Date'],
                        'type': txn_type,
                        'fee': row['Fee'] if pd.notna(row['Fee']) else 0,
                        'amount': row['Amount'] if pd.notna(row['Amount']) else 0
                    })
                elif txn_type in ['close_short', 'close_long']:
                    closes.append({
                        'date': row['Date'],
                        'type': txn_type,
                        'fee': row['Fee'] if pd.notna(row['Fee']) else 0,
                        'amount': row['Amount'] if pd.notna(row['Amount']) else 0
                    })
            
            # Make a copy of opens to work with (FIFO queue)
            opens_queue = opens.copy()
            
            # Process each close in chronological order
            for close in closes:
                # Find the most recent open BEFORE this close
                matching_open = None
                matching_index = -1
                
                for i in range(len(opens_queue) - 1, -1, -1):
                    if opens_queue[i]['date'] < close['date']:
                        matching_open = opens_queue[i]
                        matching_index = i
                        break
                
                if matching_open:
                    fee_credit = abs(matching_open['fee']) if pd.notna(matching_open['fee']) else 0
                    pnl = close['amount'] if pd.notna(close['amount']) else 0
                    fee_paid = close['fee'] if pd.notna(close['fee']) else 0
                    
                    net_pnl = pnl - fee_paid + fee_credit
                    is_win = net_pnl > 0
                    
                    holding_hours = (close['date'] - matching_open['date']).total_seconds() / 3600
                    
                    self.trades.append({
                        'symbol': symbol,
                        'open_date': matching_open['date'],
                        'close_date': close['date'],
                        'type': matching_open['type'],
                        'close_type': close['type'],
                        'pnl': pnl,
                        'fee_paid': fee_paid,
                        'fee_credit': fee_credit,
                        'net_pnl': net_pnl,
                        'is_win': is_win,
                        'holding_hours': holding_hours,
                        'is_liquidation': False
                    })
                    
                    opens_queue.pop(matching_index)
            
            # Handle liquidations
            liquidation_rows = symbol_df[symbol_df['Type'].str.contains('burst_close', na=False)]
            for _, row in liquidation_rows.iterrows():
                pnl = row['Amount'] if pd.notna(row['Amount']) else 0
                fee = row['Fee'] if pd.notna(row['Fee']) else 0
                net_pnl = pnl - fee
                
                self.trades.append({
                    'symbol': symbol,
                    'open_date': row['Date'],
                    'close_date': row['Date'],
                    'type': row['Type'],
                    'pnl': pnl,
                    'fee_paid': fee,
                    'fee_credit': 0,
                    'net_pnl': net_pnl,
                    'is_win': False,
                    'holding_hours': 0,
                    'is_liquidation': True
                })
        
        self.trades.sort(key=lambda x: x['close_date'])
    
    def get_summary_stats(self):
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
        
        best_trade = max(self.trades, key=lambda x: x['net_pnl']) if self.trades else None
        worst_trade = min(self.trades, key=lambda x: x['net_pnl']) if self.trades else None
        
        returns = [t['net_pnl'] for t in self.trades]
        sharpe = (np.mean(returns) / np.std(returns)) * np.sqrt(252) if np.std(returns) > 0 else 0
        
        cumulative = np.cumsum(returns)
        running_max = np.maximum.accumulate(cumulative)
        drawdown = cumulative - running_max
        max_drawdown = np.min(drawdown) if len(drawdown) > 0 else 0
        
        expectancy = total_pnl / total_trades if total_trades > 0 else 0
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
            'sharpe_ratio': sharpe,
            'max_drawdown': max_drawdown,
            'expectancy': expectancy,
            'avg_holding_hours': avg_holding
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
    
    def get_trades_df(self):
        return pd.DataFrame(self.trades)

def main():
    st.title("📊 Bitget Trading Analytics Dashboard")
    st.markdown("### Analyze your USDT-M/USDC-M Futures trading performance")
    
    with st.sidebar:
        st.header("📁 Data Source")
        uploaded_file = st.file_uploader(
            "Upload Bitget CSV Export",
            type=['csv']
        )
        
        st.markdown("---")
        st.markdown("### How It Works")
        st.markdown("""
        - Each close is matched with the most recent open before it
        - Works correctly for all symbols
        - Includes liquidations
        """)
    
    if uploaded_file is None:
        st.info("👈 Upload your Bitget CSV file to begin")
        return
    
    with st.spinner("Analyzing your trades..."):
        try:
            df = BitgetAnalyzer.load_csv(uploaded_file)
            analyzer = BitgetAnalyzer(df)
            stats = analyzer.get_summary_stats()
            
            if not analyzer.trades:
                st.warning("No trades found")
                return
            
            st.success(f"✅ {len(analyzer.trades)} trades analyzed")
            
        except Exception as e:
            st.error(f"Error: {str(e)}")
            return
    
    # Summary
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Trades", stats['total_trades'])
        st.metric("Wins / Losses", f"{stats['winning_trades']} / {stats['losing_trades']}")
    
    with col2:
        st.metric("Win Rate", f"{stats['win_rate']:.1f}%")
        st.metric("Profit Factor", f"{stats['profit_factor']:.2f}")
    
    with col3:
        pnl_color = "🟢" if stats['total_pnl'] >= 0 else "🔴"
        st.metric("Total Net P&L", f"{pnl_color} ${stats['total_pnl']:.2f}")
    
    with col4:
        st.metric("Liquidations", stats['liquidation_trades'])
        st.metric("Max Drawdown", f"${stats['max_drawdown']:.2f}")
    
    # Symbol table
    st.subheader("📊 Performance by Symbol")
    symbol_stats = analyzer.get_symbol_breakdown()
    
    if symbol_stats:
        symbol_df = pd.DataFrame([
            {
                'Symbol': sym,
                'Trades': data['trades'],
                'Wins': data['wins'],
                'Win Rate': f"{data['win_rate']:.1f}%",
                'Total P&L': f"${data['total_pnl']:.2f}",
                'Liquidations': data['liquidations']
            }
            for sym, data in symbol_stats.items()
        ]).sort_values('Total P&L', ascending=False)
        
        st.dataframe(symbol_df, use_container_width=True, hide_index=True)
    
    # All trades
    st.subheader("📋 All Trades")
    trades_df = analyzer.get_trades_df()
    
    if not trades_df.empty:
        display_df = trades_df.copy()
        display_df['close_date'] = pd.to_datetime(display_df['close_date']).dt.strftime('%Y-%m-%d %H:%M')
        display_df['net_pnl'] = display_df['net_pnl'].apply(lambda x: f"${x:.2f}")
        display_df['is_win'] = display_df['is_win'].apply(lambda x: "✅ Win" if x else "❌ Loss")
        display_df['holding_hours'] = display_df['holding_hours'].apply(lambda x: f"{x:.1f}h" if x > 0 else "Liquidation")
        
        st.dataframe(
            display_df[['close_date', 'symbol', 'net_pnl', 'is_win', 'holding_hours']],
            use_container_width=True,
            hide_index=True
        )

if __name__ == "__main__":
    main()

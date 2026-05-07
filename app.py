"""
Bitget Trading Analytics Dashboard
Position-based P&L · Multi-account · Bitget-style dark UI
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
import io
import base64

# ─── Page config & theme ────────────────────────────────────────────
st.set_page_config(
    page_title="Trading Dashboard",
    page_icon="📊",
    layout="wide",
)

# ─── Bitget-style CSS ───────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.stApp { background-color: #0D1117; color: #E6EDF3; }
header[data-testid="stHeader"] { background: #0D1117; }

section[data-testid="stSidebar"] {
    background: #161B22; border-right: 1px solid #21262D;
}
section[data-testid="stSidebar"] .stMarkdown p,
section[data-testid="stSidebar"] .stMarkdown li,
section[data-testid="stSidebar"] label { color: #8B949E; }
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 { color: #E6EDF3; }

div[data-testid="stMetric"] {
    background: #161B22; border: 1px solid #21262D;
    border-radius: 12px; padding: 16px 20px;
}
div[data-testid="stMetric"] label { color: #8B949E !important; font-size: 13px; }
div[data-testid="stMetric"] [data-testid="stMetricValue"] {
    color: #E6EDF3 !important; font-size: 22px; font-weight: 600;
}

div[data-testid="stExpander"] {
    background: #161B22; border: 1px solid #21262D; border-radius: 12px;
}
button[data-baseweb="tab"] { color: #8B949E !important; font-weight: 500; }
button[data-baseweb="tab"][aria-selected="true"] { color: #00E5A0 !important; }
div[data-baseweb="tab-highlight"] { background-color: #00E5A0 !important; }

div[data-testid="stDataFrame"] {
    border: 1px solid #21262D; border-radius: 12px; overflow: hidden;
}
div[data-baseweb="select"] > div {
    background-color: #161B22 !important; border-color: #30363D !important;
}

.dash-header {
    color: #E6EDF3; font-size: 18px; font-weight: 600;
    margin: 28px 0 12px 0; padding-bottom: 8px; border-bottom: 1px solid #21262D;
}
.account-card {
    background: #161B22; border: 1px solid #21262D;
    border-radius: 14px; padding: 24px; margin-bottom: 16px;
}
.account-card h3 { margin: 0 0 16px 0; font-size: 16px; }
.account-card .big-pnl { font-size: 32px; font-weight: 700; }
.block-container { padding-top: 2rem; }
</style>
""", unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════════════
# ANALYZER CLASS
# ═════════════════════════════════════════════════════════════════════

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
        if 'Order' in df.columns:
            df['Order'] = df['Order'].astype(str).str.strip()
        df['Date'] = pd.to_datetime(df['Date'].str.strip())
        df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce').fillna(0)
        df['Fee'] = pd.to_numeric(df['Fee'], errors='coerce').fillna(0)
        if 'Coin' in df.columns:
            coin = df['Coin'].str.strip().iloc[0] if len(df) > 0 else ''
            df['Market'] = 'USDC-M' if coin == 'USDC' else 'USDT-M'
        else:
            df['Market'] = 'Unknown'
        return df

    @staticmethod
    def merge_dataframes(dfs):
        if len(dfs) == 1:
            return dfs[0]
        combined = pd.concat(dfs, ignore_index=True)
        if 'Order' in combined.columns:
            combined = combined.drop_duplicates(subset='Order', keep='first')
        return combined.sort_values('Date').reset_index(drop=True)

    def get_funding_fees(self, symbol, open_date, close_date):
        f = self.df[
            (self.df['Futures'] == symbol)
            & (self.df['Type'] == 'contract_margin_settle_fee')
            & (self.df['Date'] >= open_date)
            & (self.df['Date'] <= close_date)
        ]
        return f['Amount'].sum()

    def parse_trades(self):
        open_types = {'open_short', 'open_long'}
        close_types = {'close_short', 'close_long'}
        valid = self.df[
            self.df['Futures'].notna()
            & (self.df['Futures'].astype(str).str.strip() != '')
            & (self.df['Futures'].astype(str) != 'nan')
        ]

        for symbol in valid['Futures'].unique():
            sdf = valid[valid['Futures'] == symbol].sort_values('Date')
            if sdf.empty:
                continue
            market = sdf['Market'].iloc[0] if 'Market' in sdf.columns else '?'

            positions, cur = [], None
            for _, r in sdf.iterrows():
                t = r['Type']
                if t in open_types:
                    if cur and cur['has_close']:
                        positions.append(cur)
                        cur = None
                    if cur is None:
                        cur = dict(
                            direction=t, open_date=r['Date'],
                            open_fees=[], close_amounts=[], close_fees=[],
                            close_dates=[], has_close=False,
                        )
                    cur['open_fees'].append(r['Fee'])
                elif t in close_types:
                    if cur is None:
                        cur = dict(
                            direction='open_long' if t == 'close_long' else 'open_short',
                            open_date=r['Date'],
                            open_fees=[], close_amounts=[], close_fees=[],
                            close_dates=[], has_close=False,
                        )
                    cur['has_close'] = True
                    cur['close_amounts'].append(r['Amount'])
                    cur['close_fees'].append(r['Fee'])
                    cur['close_dates'].append(r['Date'])
            if cur and cur['has_close']:
                positions.append(cur)

            for p in positions:
                cd = max(p['close_dates'])
                od = p['open_date']
                realized = sum(p['close_amounts'])
                cf = sum(p['close_fees'])
                of_ = sum(p['open_fees'])
                ff = self.get_funding_fees(symbol, od, cd)
                net = realized + cf + of_ + ff
                self.trades.append(dict(
                    symbol=symbol, market=market,
                    open_date=od, close_date=cd,
                    direction='Long' if 'long' in p['direction'] else 'Short',
                    realized_pnl=realized,
                    open_fees=of_, close_fees=cf, funding_fees=ff,
                    net_pnl=net, is_win=net > 0,
                    holding_hours=(cd - od).total_seconds() / 3600,
                    is_liquidation=False,
                    num_closes=len(p['close_amounts']),
                ))

            for _, r in sdf[sdf['Type'].str.contains('burst_close', na=False)].iterrows():
                net = r['Amount'] + r['Fee']
                self.trades.append(dict(
                    symbol=symbol, market=market,
                    open_date=r['Date'], close_date=r['Date'],
                    direction='Long' if 'long' in r['Type'] else 'Short',
                    realized_pnl=r['Amount'],
                    open_fees=0, close_fees=r['Fee'], funding_fees=0,
                    net_pnl=net, is_win=False,
                    holding_hours=0, is_liquidation=True, num_closes=1,
                ))

        self.trades.sort(key=lambda x: x['close_date'])

    def stats(self, market_filter=None):
        trades = self.trades
        if market_filter:
            trades = [t for t in trades if t['market'] == market_filter]
        if not trades:
            return None
        n = len(trades)
        wins = sum(1 for t in trades if t['is_win'])
        losses = n - wins
        liqs = sum(1 for t in trades if t['is_liquidation'])
        total_pnl = sum(t['net_pnl'] for t in trades)
        gp = sum(t['net_pnl'] for t in trades if t['net_pnl'] > 0)
        gl = abs(sum(t['net_pnl'] for t in trades if t['net_pnl'] < 0))
        pf = gp / gl if gl > 0 else float('inf')
        ff = sum(t['funding_fees'] for t in trades)
        tf = sum(t['open_fees'] + t['close_fees'] for t in trades)
        rets = [t['net_pnl'] for t in trades]
        sharpe = (np.mean(rets) / np.std(rets)) * np.sqrt(252) if np.std(rets) > 0 else 0
        cum = np.cumsum(rets)
        dd = cum - np.maximum.accumulate(cum)
        mdd = np.min(dd) if len(dd) > 0 else 0
        best = max(trades, key=lambda x: x['net_pnl'])
        worst = min(trades, key=lambda x: x['net_pnl'])
        hh = [t['holding_hours'] for t in trades if t['holding_hours'] > 0]
        return dict(
            trades=n, wins=wins, losses=losses, liqs=liqs,
            win_rate=wins / n * 100, total_pnl=total_pnl,
            gross_profit=gp, gross_loss=gl, profit_factor=pf,
            avg_win=gp / wins if wins else 0, avg_loss=-gl / losses if losses else 0,
            funding_fees=ff, trading_fees=tf,
            sharpe=sharpe, max_drawdown=mdd,
            expectancy=total_pnl / n,
            avg_holding=np.mean(hh) if hh else 0,
            best=best, worst=worst,
        )

    def symbol_breakdown(self, market_filter=None):
        trades = self.trades
        if market_filter:
            trades = [t for t in trades if t['market'] == market_filter]
        out = {}
        for t in trades:
            s = t['symbol']
            if s not in out:
                out[s] = dict(trades=0, wins=0, pnl=0, funding=0, liqs=0, market=t['market'])
            out[s]['trades'] += 1
            if t['is_win']:
                out[s]['wins'] += 1
            out[s]['pnl'] += t['net_pnl']
            out[s]['funding'] += t['funding_fees']
            if t['is_liquidation']:
                out[s]['liqs'] += 1
        for s in out:
            out[s]['win_rate'] = out[s]['wins'] / out[s]['trades'] * 100 if out[s]['trades'] else 0
        return out

    def cumulative_series(self, market_filter=None):
        trades = self.trades
        if market_filter:
            trades = [t for t in trades if t['market'] == market_filter]
        if not trades:
            return pd.DataFrame()
        cum = np.cumsum([t['net_pnl'] for t in trades])
        return pd.DataFrame(dict(
            date=[t['close_date'] for t in trades],
            pnl=[t['net_pnl'] for t in trades],
            cumulative=cum,
            is_liq=[t['is_liquidation'] for t in trades],
        ))


# ═════════════════════════════════════════════════════════════════════
# UI COMPONENTS
# ═════════════════════════════════════════════════════════════════════

def render_metrics(stats, currency='$'):
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("Positions", stats['trades'])
    with c2:
        icon = "🟢" if stats['win_rate'] >= 50 else "🔴"
        st.metric("Win Rate", f"{icon} {stats['win_rate']:.1f}%")
    with c3:
        sign = '+' if stats['total_pnl'] >= 0 else ''
        st.metric("Net P&L", f"{sign}{stats['total_pnl']:,.2f} {currency}")
    with c4:
        st.metric("Profit Factor", f"{stats['profit_factor']:.2f}")
    with c5:
        st.metric("Liquidations", stats['liqs'])


def render_cumulative_chart(series, title="Cumulative P&L"):
    if series.empty:
        return
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=series['date'], y=series['cumulative'],
        mode='lines', name='P&L',
        line=dict(color='#00E5A0', width=2),
        fill='tozeroy', fillcolor='rgba(0,229,160,0.08)',
    ))
    liqs = series[series['is_liq']]
    if not liqs.empty:
        fig.add_trace(go.Scatter(
            x=liqs['date'], y=liqs['cumulative'],
            mode='markers', name='Liquidation',
            marker=dict(color='#F6465D', size=8, symbol='x'),
        ))
    fig.update_layout(
        template='plotly_dark',
        paper_bgcolor='#0D1117', plot_bgcolor='#0D1117',
        height=360, margin=dict(l=0, r=0, t=30, b=0),
        title=dict(text=title, font=dict(size=14, color='#8B949E')),
        xaxis=dict(gridcolor='#21262D', showgrid=False),
        yaxis=dict(gridcolor='#21262D', title='P&L'),
        legend=dict(bgcolor='rgba(0,0,0,0)'),
        hovermode='x unified',
    )
    st.plotly_chart(fig, use_container_width=True)


def render_symbol_bars(sym_stats, title="P&L by Symbol"):
    if not sym_stats:
        return
    df = pd.DataFrame([
        dict(symbol=s, pnl=d['pnl']) for s, d in sym_stats.items()
    ]).sort_values('pnl', ascending=True)
    colors = ['#00E5A0' if v >= 0 else '#F6465D' for v in df['pnl']]
    fig = go.Figure(go.Bar(
        y=df['symbol'], x=df['pnl'], orientation='h',
        marker_color=colors,
        text=[f"{v:+,.0f}" for v in df['pnl']],
        textposition='outside', textfont=dict(size=11),
    ))
    fig.update_layout(
        template='plotly_dark',
        paper_bgcolor='#0D1117', plot_bgcolor='#0D1117',
        height=max(280, len(df) * 28),
        margin=dict(l=0, r=60, t=30, b=0),
        title=dict(text=title, font=dict(size=14, color='#8B949E')),
        xaxis=dict(gridcolor='#21262D', title='P&L'),
        yaxis=dict(gridcolor='#21262D'),
    )
    st.plotly_chart(fig, use_container_width=True)


def render_positions_table(trades, market_filter=None):
    if not trades:
        st.info("No positions to display.")
        return
    data = trades if not market_filter else [t for t in trades if t['market'] == market_filter]
    if not data:
        st.info("No positions for this filter.")
        return

    df = pd.DataFrame(data)

    # ── Filters ──
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        syms = ['All'] + sorted(df['symbol'].unique().tolist())
        sel_sym = st.selectbox("Symbol", syms, key=f"sym_{market_filter}")
    with c2:
        sel_dir = st.selectbox("Direction", ['All', 'Long', 'Short'], key=f"dir_{market_filter}")
    with c3:
        sel_res = st.selectbox("Result", ['All', 'Win', 'Loss', 'Liquidation'], key=f"res_{market_filter}")
    with c4:
        sort_map = {
            'Close date ↓': ('close_date', False),
            'Close date ↑': ('close_date', True),
            'P&L best ↓': ('net_pnl', False),
            'P&L worst ↓': ('net_pnl', True),
            'Holding longest ↓': ('holding_hours', False),
            'Holding shortest ↓': ('holding_hours', True),
        }
        sel_sort = st.selectbox("Sort", list(sort_map.keys()), key=f"sort_{market_filter}")

    if sel_sym != 'All':
        df = df[df['symbol'] == sel_sym]
    if sel_dir != 'All':
        df = df[df['direction'] == sel_dir]
    if sel_res == 'Win':
        df = df[(df['is_win']) & (~df['is_liquidation'])]
    elif sel_res == 'Loss':
        df = df[(~df['is_win']) & (~df['is_liquidation'])]
    elif sel_res == 'Liquidation':
        df = df[df['is_liquidation']]

    sort_col, asc = sort_map[sel_sort]
    df = df.sort_values(sort_col, ascending=asc)

    if df.empty:
        st.info("No positions match filters.")
        return

    display = pd.DataFrame({
        'Opened': df['open_date'].dt.strftime('%Y-%m-%d %H:%M'),
        'Closed': df['close_date'].dt.strftime('%Y-%m-%d %H:%M'),
        'Symbol': df['symbol'],
        'Dir': df['direction'],
        'Net P&L': df['net_pnl'].round(2),
        'Funding': df['funding_fees'].round(4),
        'Result': df.apply(
            lambda r: '⚠️ LIQ' if r['is_liquidation'] else ('✅ Win' if r['is_win'] else '❌ Loss'), axis=1
        ),
        'Holding': df['holding_hours'].apply(lambda h: f"{h:.1f}h" if h > 0 else '—'),
        'Fills': df['num_closes'].astype(int),
    })

    st.caption(f"{len(display)} of {len(data)} positions")

    st.dataframe(
        display, use_container_width=True, hide_index=True,
        height=min(600, 38 + len(display) * 35),
        column_config={
            'Net P&L': st.column_config.NumberColumn('Net P&L', format="%.2f"),
            'Funding': st.column_config.NumberColumn('Funding', format="%.4f"),
            'Fills': st.column_config.NumberColumn('Fills', format="%d"),
        },
    )

    csv_out = df.to_csv(index=False)
    st.download_button("📥 Download CSV", csv_out, "positions.csv", "text/csv", key=f"dl_{market_filter}")


# ═════════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════════

def main():
    st.markdown("""
    <div style="display:flex; align-items:center; gap:12px; margin-bottom:4px;">
        <span style="font-size:28px;">📊</span>
        <span style="font-size:26px; font-weight:700; color:#E6EDF3;">Trading Dashboard</span>
    </div>
    <p style="color:#8B949E; margin-top:0; font-size:14px;">
        Bitget Futures · Position-based P&L · Multi-account analysis
    </p>
    """, unsafe_allow_html=True)

    with st.sidebar:
        st.markdown("### 📁 Upload Data")
        uploaded_files = st.file_uploader(
            "Bitget CSV Transaction Exports",
            type=['csv'], accept_multiple_files=True,
            help="Upload USDT-M and/or USDC-M transaction CSVs",
        )
        st.markdown("---")
        st.markdown(
            "**How it works**\n\n"
            "Opens & partial closes are grouped into positions. "
            "P&L includes trading fees and funding fees."
        )

    if not uploaded_files:
        st.markdown("""
        <div style="text-align:center; padding:80px 20px; color:#8B949E;">
            <p style="font-size:48px; margin-bottom:16px;">📁</p>
            <p style="font-size:18px;">Upload your Bitget CSV export(s) to get started</p>
            <p style="font-size:14px; margin-top:8px;">
                Supports USDT-M and USDC-M · Multiple files merged automatically
            </p>
        </div>
        """, unsafe_allow_html=True)
        return

    with st.spinner("Analyzing positions..."):
        try:
            dfs = [BitgetAnalyzer.load_csv(f) for f in uploaded_files]
            combined = BitgetAnalyzer.merge_dataframes(dfs)
            analyzer = BitgetAnalyzer(combined)
            if not analyzer.trades:
                st.warning("No completed positions found.")
                return
        except Exception as e:
            st.error(f"Error: {e}")
            import traceback
            st.code(traceback.format_exc())
            return

    markets = sorted(set(t['market'] for t in analyzer.trades))
    has_both = len(markets) > 1

    # ── Account comparison ──
    if has_both:
        st.markdown('<div class="dash-header">⚖️ Account Comparison</div>', unsafe_allow_html=True)
        cols = st.columns(len(markets))
        for i, m in enumerate(markets):
            s = analyzer.stats(m)
            if not s:
                continue
            currency = 'USDC' if 'USDC' in m else 'USDT'
            pnl_color = '#00E5A0' if s['total_pnl'] >= 0 else '#F6465D'
            sign = '+' if s['total_pnl'] >= 0 else ''
            with cols[i]:
                st.markdown(f"""
                <div class="account-card">
                    <h3 style="color:#8B949E;">{m}</h3>
                    <div class="big-pnl" style="color:{pnl_color};">{sign}{s['total_pnl']:,.2f} {currency}</div>
                    <div style="margin-top:16px; display:grid; grid-template-columns:1fr 1fr; gap:8px; font-size:14px;">
                        <div><span style="color:#8B949E;">Positions</span><br><b>{s['trades']}</b></div>
                        <div><span style="color:#8B949E;">Win Rate</span><br><b>{s['win_rate']:.1f}%</b></div>
                        <div><span style="color:#8B949E;">Profit Factor</span><br><b>{s['profit_factor']:.2f}</b></div>
                        <div><span style="color:#8B949E;">Liquidations</span><br><b style="color:#F6465D;">{s['liqs']}</b></div>
                        <div><span style="color:#8B949E;">Trading Fees</span><br><b>{s['trading_fees']:,.2f}</b></div>
                        <div><span style="color:#8B949E;">Funding Fees</span><br><b>{s['funding_fees']:,.2f}</b></div>
                        <div><span style="color:#8B949E;">Best Trade</span><br><b style="color:#00E5A0;">+{s['best']['net_pnl']:,.2f}</b></div>
                        <div><span style="color:#8B949E;">Worst Trade</span><br><b style="color:#F6465D;">{s['worst']['net_pnl']:,.2f}</b></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

        ts = analyzer.stats()
        st.markdown(f"""
        <div style="text-align:center; padding:12px; background:#161B22; border:1px solid #21262D; border-radius:12px; margin-bottom:20px;">
            <span style="color:#8B949E; font-size:14px;">Combined Net P&L</span><br>
            <span style="font-size:28px; font-weight:700; color:{'#00E5A0' if ts['total_pnl']>=0 else '#F6465D'};">
                {'+' if ts['total_pnl']>=0 else ''}{ts['total_pnl']:,.2f}
            </span>
            <span style="color:#8B949E;"> across {ts['trades']} positions</span>
        </div>
        """, unsafe_allow_html=True)

    # ── Tabs ──
    tab_labels = (markets + ['Combined']) if has_both else markets
    tabs = st.tabs(tab_labels)

    for idx, label in enumerate(tab_labels):
        with tabs[idx]:
            mf = None if label == 'Combined' else label
            s = analyzer.stats(mf)
            if not s:
                st.info("No data.")
                continue
            currency = 'USDC' if mf and 'USDC' in mf else ('USDT' if mf and 'USDT' in mf else '$')

            render_metrics(s, currency)

            series = analyzer.cumulative_series(mf)
            render_cumulative_chart(series, f"Cumulative P&L ({label})")

            with st.expander("📐 Detailed Stats & Fee Breakdown"):
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    st.metric("Avg Win", f"{s['avg_win']:,.2f}")
                    st.metric("Trading Fees", f"{s['trading_fees']:,.2f}")
                with c2:
                    st.metric("Avg Loss", f"{s['avg_loss']:,.2f}")
                    st.metric("Funding Fees", f"{s['funding_fees']:,.2f}")
                with c3:
                    st.metric("Sharpe Ratio", f"{s['sharpe']:.2f}")
                    st.metric("Max Drawdown", f"{s['max_drawdown']:,.2f}")
                with c4:
                    st.metric("Expectancy", f"{s['expectancy']:,.2f}")
                    st.metric("Avg Holding", f"{s['avg_holding']:.1f}h")
                st.markdown(
                    f"**Best:** {s['best']['symbol']} → "
                    f"**+{s['best']['net_pnl']:,.2f}** &nbsp;|&nbsp; "
                    f"**Worst:** {s['worst']['symbol']} → "
                    f"**{s['worst']['net_pnl']:,.2f}**"
                )

            st.markdown('<div class="dash-header">📊 Performance by Symbol</div>', unsafe_allow_html=True)
            sym = analyzer.symbol_breakdown(mf)
            if sym:
                sym_df = pd.DataFrame([
                    dict(Symbol=k, Positions=v['trades'], Wins=v['wins'],
                         WinRate=round(v['win_rate'],1), PnL=round(v['pnl'],2),
                         Funding=round(v['funding'],2), Liqs=v['liqs'])
                    for k, v in sym.items()
                ]).sort_values('PnL', ascending=False)
                st.dataframe(sym_df, use_container_width=True, hide_index=True,
                    column_config={
                        'WinRate': st.column_config.NumberColumn('Win %', format="%.1f%%"),
                        'PnL': st.column_config.NumberColumn('P&L', format="%.2f"),
                        'Funding': st.column_config.NumberColumn('Funding', format="%.2f"),
                    })
                render_symbol_bars(sym, f"P&L by Symbol ({label})")

            st.markdown('<div class="dash-header">📋 All Positions</div>', unsafe_allow_html=True)
            render_positions_table(analyzer.trades, mf)


if __name__ == "__main__":
    main()

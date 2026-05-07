"""
Bitget Trading Analytics Dashboard
Position-based P&L · Multi-account · Legacy import · Bitget-style dark UI
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import io

st.set_page_config(page_title="Trading Dashboard", page_icon="📊", layout="wide")

# ─── CSS ────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Albert+Sans:wght@400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Albert Sans', sans-serif; }
.stApp { background-color: #0D1117; color: #D0D7DE; }
header[data-testid="stHeader"] { background: #0D1117; }

section[data-testid="stSidebar"] {
    background: #161B22; border-right: 1px solid #21262D;
}
section[data-testid="stSidebar"] .stMarkdown p,
section[data-testid="stSidebar"] .stMarkdown li { color: #9DA5AE; }
section[data-testid="stSidebar"] label { color: #C9D1D9 !important; }
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 { color: #E6EDF3; }

div[data-testid="stMetric"] {
    background: #161B22; border: 1px solid #21262D;
    border-radius: 12px; padding: 16px 20px;
}
div[data-testid="stMetric"] label { color: #9DA5AE !important; font-size: 13px; }
div[data-testid="stMetric"] [data-testid="stMetricValue"] {
    color: #E6EDF3 !important; font-size: 22px; font-weight: 600;
}

div[data-testid="stExpander"] {
    background: #161B22; border: 1px solid #21262D; border-radius: 12px;
}
button[data-baseweb="tab"] { color: #9DA5AE !important; font-weight: 500; }
button[data-baseweb="tab"][aria-selected="true"] { color: #00E5A0 !important; }
div[data-baseweb="tab-highlight"] { background-color: #00E5A0 !important; }

/* Table / dataframe: slightly lighter bg for contrast */
div[data-testid="stDataFrame"] {
    border: 1px solid #21262D; border-radius: 12px; overflow: hidden;
}
div[data-testid="stDataFrame"] > div { background-color: #171D24 !important; }

/* Selectbox / filters */
div[data-baseweb="select"] > div {
    background-color: #1C2330 !important; border-color: #30363D !important;
    color: #D0D7DE !important;
}
label { color: #C9D1D9 !important; }
p, span, li { color: #D0D7DE; }

/* Captions more visible */
div[data-testid="stCaptionContainer"] p { color: #9DA5AE !important; }

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
# ANALYZER
# ═════════════════════════════════════════════════════════════════════

class BitgetAnalyzer:
    def __init__(self, df):
        self.df = df
        self.trades = []
        self.parse_trades()

    # ── Loaders ──────────────────────────────────────────────────────

    @staticmethod
    def detect_format(content):
        """Return 'bitget' or 'legacy' based on CSV header."""
        first_line = content.split('\n')[0]
        if 'From Wallet' in first_line or 'Description;;;' in first_line:
            return 'legacy'
        return 'bitget'

    @staticmethod
    def load_csv(uploaded_file):
        content = uploaded_file.getvalue().decode('utf-8-sig')
        fmt = BitgetAnalyzer.detect_format(content)
        if fmt == 'legacy':
            return BitgetAnalyzer._load_legacy(content)
        return BitgetAnalyzer._load_bitget(content)

    @staticmethod
    def _load_bitget(content):
        df = pd.read_csv(io.StringIO(content))
        df.columns = [c.strip() for c in df.columns]
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
    def _load_legacy(content):
        """Convert portfolio-tracker format to standard Bitget format."""
        raw = pd.read_csv(io.StringIO(content))
        raw.columns = [c.strip() for c in raw.columns]

        # Find description column (has ;;; suffix sometimes)
        desc_col = [c for c in raw.columns if 'Description' in c][0]
        raw['bitget_type'] = raw[desc_col].astype(str).str.strip()
        raw['date'] = pd.to_datetime(raw['Date (UTC)'])
        raw['from_amt'] = pd.to_numeric(raw['From Amount'], errors='coerce').fillna(0)
        raw['to_amt'] = pd.to_numeric(raw['To Amount'], errors='coerce').fillna(0)
        raw['tag'] = raw['Tag'].astype(str).str.strip()
        raw['txtype'] = raw['Type'].astype(str).str.strip()

        rows = []
        for _, r in raw.iterrows():
            bt = r['bitget_type']
            if bt == 'nan' or bt == '':
                continue

            if r['tag'] == 'margin_fee':
                if bt == 'contract_margin_settle_fee':
                    # Funding fee (paid) → Amount negative, Fee 0
                    rows.append(dict(
                        Order=r.get('ID (read-only)', ''),
                        Date=r['date'], Coin='USDT', Futures='LEGACY',
                        Type=bt, Amount=-r['from_amt'], Fee=0, Market='Legacy',
                    ))
                else:
                    # Trading fee → Amount 0, Fee negative
                    rows.append(dict(
                        Order=r.get('ID (read-only)', ''),
                        Date=r['date'], Coin='USDT', Futures='LEGACY',
                        Type=bt, Amount=0, Fee=-r['from_amt'], Market='Legacy',
                    ))
            elif r['tag'] == 'realized_gain':
                if r['txtype'] == 'deposit':
                    # Profit
                    rows.append(dict(
                        Order=r.get('ID (read-only)', ''),
                        Date=r['date'], Coin='USDT', Futures='LEGACY',
                        Type=bt, Amount=r['to_amt'], Fee=0, Market='Legacy',
                    ))
                else:
                    # Loss (withdrawal)
                    rows.append(dict(
                        Order=r.get('ID (read-only)', ''),
                        Date=r['date'], Coin='USDT', Futures='LEGACY',
                        Type=bt, Amount=-r['from_amt'], Fee=0, Market='Legacy',
                    ))

        df = pd.DataFrame(rows)
        if df.empty:
            return df
        df['Order'] = df['Order'].astype(str)
        return df

    @staticmethod
    def merge_dataframes(dfs):
        if len(dfs) == 1:
            return dfs[0]
        combined = pd.concat(dfs, ignore_index=True)
        if 'Order' in combined.columns:
            combined = combined.drop_duplicates(subset='Order', keep='first')
        return combined.sort_values('Date').reset_index(drop=True)

    # ── Funding lookup ───────────────────────────────────────────────

    def get_funding(self, symbol, od, cd):
        f = self.df[
            (self.df['Futures'] == symbol)
            & (self.df['Type'] == 'contract_margin_settle_fee')
            & (self.df['Date'] >= od) & (self.df['Date'] <= cd)
        ]
        return f['Amount'].sum()

    # ── Parse trades ─────────────────────────────────────────────────

    def parse_trades(self):
        open_t = {'open_short', 'open_long'}
        close_t = {'close_short', 'close_long', 'force_close_long', 'force_close_short'}
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
                if t in open_t:
                    if cur and cur['hc']:
                        positions.append(cur)
                        cur = None
                    if cur is None:
                        cur = dict(d=t, od=r['Date'], of=[], ca=[], cf=[], cd=[], hc=False)
                    cur['of'].append(r['Fee'])
                elif t in close_t:
                    if cur is None:
                        cur = dict(
                            d='open_long' if 'long' in t else 'open_short',
                            od=r['Date'], of=[], ca=[], cf=[], cd=[], hc=False,
                        )
                    cur['hc'] = True
                    cur['ca'].append(r['Amount'])
                    cur['cf'].append(r['Fee'])
                    cur['cd'].append(r['Date'])
            if cur and cur['hc']:
                positions.append(cur)

            for p in positions:
                cd = max(p['cd'])
                od = p['od']
                real = sum(p['ca'])
                cf = sum(p['cf'])
                of = sum(p['of'])
                ff = self.get_funding(symbol, od, cd)
                net = real + cf + of + ff
                self.trades.append(dict(
                    symbol=symbol, market=market, open_date=od, close_date=cd,
                    direction='Long' if 'long' in p['d'] else 'Short',
                    realized_pnl=real, open_fees=of, close_fees=cf,
                    funding_fees=ff, net_pnl=net, is_win=net > 0,
                    holding_hours=(cd - od).total_seconds() / 3600,
                    is_liquidation=False, num_closes=len(p['ca']),
                ))

            # Liquidations
            for _, r in sdf[sdf['Type'].str.contains('burst_close', na=False)].iterrows():
                net = r['Amount'] + r['Fee']
                self.trades.append(dict(
                    symbol=symbol, market=market,
                    open_date=r['Date'], close_date=r['Date'],
                    direction='Long' if 'long' in r['Type'] else 'Short',
                    realized_pnl=r['Amount'], open_fees=0, close_fees=r['Fee'],
                    funding_fees=0, net_pnl=net, is_win=False,
                    holding_hours=0, is_liquidation=True, num_closes=1,
                ))

        self.trades.sort(key=lambda x: x['close_date'])

    # ── Stats ────────────────────────────────────────────────────────

    def stats(self, mf=None):
        tr = [t for t in self.trades if not mf or t['market'] == mf]
        if not tr:
            return None
        n = len(tr)
        w = sum(1 for t in tr if t['is_win'])
        l = n - w
        lq = sum(1 for t in tr if t['is_liquidation'])
        tp = sum(t['net_pnl'] for t in tr)
        gp = sum(t['net_pnl'] for t in tr if t['net_pnl'] > 0)
        gl = abs(sum(t['net_pnl'] for t in tr if t['net_pnl'] < 0))
        pf = gp / gl if gl > 0 else float('inf')
        ff = sum(t['funding_fees'] for t in tr)
        tf = sum(t['open_fees'] + t['close_fees'] for t in tr)
        rets = [t['net_pnl'] for t in tr]
        sh = (np.mean(rets) / np.std(rets)) * np.sqrt(252) if np.std(rets) > 0 else 0
        cum = np.cumsum(rets)
        dd = cum - np.maximum.accumulate(cum)
        mdd = float(np.min(dd)) if len(dd) > 0 else 0
        b = max(tr, key=lambda x: x['net_pnl'])
        wo = min(tr, key=lambda x: x['net_pnl'])
        hh = [t['holding_hours'] for t in tr if t['holding_hours'] > 0]
        return dict(
            trades=n, wins=w, losses=l, liqs=lq,
            win_rate=w / n * 100, total_pnl=tp,
            gross_profit=gp, gross_loss=gl, profit_factor=pf,
            avg_win=gp / w if w else 0, avg_loss=-gl / l if l else 0,
            funding_fees=ff, trading_fees=tf,
            sharpe=sh, max_drawdown=mdd,
            expectancy=tp / n, avg_holding=np.mean(hh) if hh else 0,
            best=b, worst=wo,
        )

    def symbol_breakdown(self, mf=None):
        tr = [t for t in self.trades if not mf or t['market'] == mf]
        out = {}
        for t in tr:
            s = t['symbol']
            if s not in out:
                out[s] = dict(trades=0, wins=0, pnl=0, funding=0, liqs=0, market=t['market'])
            out[s]['trades'] += 1
            if t['is_win']: out[s]['wins'] += 1
            out[s]['pnl'] += t['net_pnl']
            out[s]['funding'] += t['funding_fees']
            if t['is_liquidation']: out[s]['liqs'] += 1
        for s in out:
            out[s]['win_rate'] = out[s]['wins'] / out[s]['trades'] * 100 if out[s]['trades'] else 0
        return out

    def cumulative(self, mf=None):
        tr = [t for t in self.trades if not mf or t['market'] == mf]
        if not tr:
            return pd.DataFrame()
        cum = np.cumsum([t['net_pnl'] for t in tr])
        return pd.DataFrame(dict(
            date=[t['close_date'] for t in tr], pnl=[t['net_pnl'] for t in tr],
            cumulative=cum, is_liq=[t['is_liquidation'] for t in tr],
        ))


# ═════════════════════════════════════════════════════════════════════
# UI COMPONENTS
# ═════════════════════════════════════════════════════════════════════

def render_metrics(s, cur='$'):
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1: st.metric("Positions", s['trades'])
    with c2:
        ic = "🟢" if s['win_rate'] >= 50 else "🔴"
        st.metric("Win Rate", f"{ic} {s['win_rate']:.1f}%")
    with c3:
        sg = '+' if s['total_pnl'] >= 0 else ''
        st.metric("Net P&L", f"{sg}{s['total_pnl']:,.2f} {cur}")
    with c4: st.metric("Profit Factor", f"{s['profit_factor']:.2f}")
    with c5: st.metric("Liquidations", s['liqs'])


def render_chart(series, title="Cumulative P&L"):
    if series.empty:
        return
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=series['date'], y=series['cumulative'],
        mode='lines', name='P&L',
        line=dict(color='#00E5A0', width=2),
        fill='tozeroy', fillcolor='rgba(0,229,160,0.08)',
    ))
    lq = series[series['is_liq']]
    if not lq.empty:
        fig.add_trace(go.Scatter(
            x=lq['date'], y=lq['cumulative'],
            mode='markers', name='Liquidation',
            marker=dict(color='#F6465D', size=8, symbol='x'),
        ))
    fig.update_layout(
        template='plotly_dark',
        paper_bgcolor='#0D1117', plot_bgcolor='#0D1117',
        height=360, margin=dict(l=0, r=0, t=30, b=0),
        title=dict(text=title, font=dict(size=14, color='#9DA5AE')),
        xaxis=dict(gridcolor='#21262D', showgrid=False),
        yaxis=dict(gridcolor='#21262D', title='P&L'),
        legend=dict(bgcolor='rgba(0,0,0,0)'),
        font=dict(family='Albert Sans'), hovermode='x unified',
    )
    st.plotly_chart(fig, use_container_width=True)


def render_bars(sym, title="P&L by Symbol"):
    if not sym:
        return
    df = pd.DataFrame([dict(symbol=s, pnl=d['pnl']) for s, d in sym.items()]).sort_values('pnl', ascending=True)
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
        title=dict(text=title, font=dict(size=14, color='#9DA5AE')),
        xaxis=dict(gridcolor='#21262D', title='P&L'),
        yaxis=dict(gridcolor='#21262D'),
        font=dict(family='Albert Sans'),
    )
    st.plotly_chart(fig, use_container_width=True)


def render_positions(trades, mf=None):
    data = [t for t in trades if not mf or t['market'] == mf]
    if not data:
        st.info("No positions to display.")
        return
    df = pd.DataFrame(data)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        syms = ['All'] + sorted(df['symbol'].unique().tolist())
        sel_sym = st.selectbox("Symbol", syms, key=f"s_{mf}")
    with c2:
        sel_dir = st.selectbox("Direction", ['All', 'Long', 'Short'], key=f"d_{mf}")
    with c3:
        sel_res = st.selectbox("Result", ['All', 'Win', 'Loss', 'Liquidation'], key=f"r_{mf}")
    with c4:
        sort_map = {
            'Close date ↓': ('close_date', False),
            'Close date ↑': ('close_date', True),
            'P&L best ↓': ('net_pnl', False),
            'P&L worst ↓': ('net_pnl', True),
            'Holding longest ↓': ('holding_hours', False),
        }
        sel_sort = st.selectbox("Sort", list(sort_map.keys()), key=f"o_{mf}")

    if sel_sym != 'All': df = df[df['symbol'] == sel_sym]
    if sel_dir != 'All': df = df[df['direction'] == sel_dir]
    if sel_res == 'Win': df = df[(df['is_win']) & (~df['is_liquidation'])]
    elif sel_res == 'Loss': df = df[(~df['is_win']) & (~df['is_liquidation'])]
    elif sel_res == 'Liquidation': df = df[df['is_liquidation']]

    sc, asc = sort_map[sel_sort]
    df = df.sort_values(sc, ascending=asc)

    if df.empty:
        st.info("No positions match filters.")
        return

    disp = pd.DataFrame({
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

    st.caption(f"{len(disp)} of {len(data)} positions")
    st.dataframe(disp, use_container_width=True, hide_index=True,
        height=min(600, 38 + len(disp) * 35),
        column_config={
            'Net P&L': st.column_config.NumberColumn('Net P&L', format="%.2f"),
            'Funding': st.column_config.NumberColumn('Funding', format="%.4f"),
            'Fills': st.column_config.NumberColumn('Fills', format="%d"),
        })
    st.download_button("📥 Download CSV", df.to_csv(index=False),
                        "positions.csv", "text/csv", key=f"dl_{mf}")


# ═════════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════════

def main():
    st.markdown("""
    <div style="display:flex; align-items:center; gap:12px; margin-bottom:4px;">
        <span style="font-size:28px;">📊</span>
        <span style="font-size:26px; font-weight:700; color:#E6EDF3;">Trading Dashboard</span>
    </div>
    <p style="color:#9DA5AE; margin-top:0; font-size:14px;">
        Bitget Futures · Position-based P&L · Multi-account analysis
    </p>
    """, unsafe_allow_html=True)

    with st.sidebar:
        st.markdown("### 📁 Upload Data")
        uploaded = st.file_uploader(
            "Bitget CSV Transaction Exports",
            type=['csv'], accept_multiple_files=True,
            help="Supports: Bitget USDT-M, USDC-M, and legacy portfolio-tracker exports",
        )
        st.markdown("---")
        st.markdown(
            "**Supported formats**\n\n"
            "- Bitget USDT-M / USDC-M transaction exports\n"
            "- Legacy portfolio-tracker CSV (auto-detected)\n\n"
            "Upload multiple files — they merge automatically."
        )

    if not uploaded:
        st.markdown("""
        <div style="text-align:center; padding:80px 20px; color:#9DA5AE;">
            <p style="font-size:48px; margin-bottom:16px;">📁</p>
            <p style="font-size:18px; color:#D0D7DE;">Upload your Bitget CSV export(s) to get started</p>
            <p style="font-size:14px; margin-top:8px;">
                USDT-M · USDC-M · Legacy accounts · Multiple files merged automatically
            </p>
        </div>
        """, unsafe_allow_html=True)
        return

    with st.spinner("Analyzing positions..."):
        try:
            dfs = []
            for f in uploaded:
                df = BitgetAnalyzer.load_csv(f)
                if not df.empty:
                    dfs.append(df)
                    market = df['Market'].iloc[0] if 'Market' in df.columns else '?'
                    st.sidebar.caption(f"✓ {f.name} → {market} ({len(df)} rows)")
            if not dfs:
                st.warning("No valid data found.")
                return
            combined = BitgetAnalyzer.merge_dataframes(dfs)
            az = BitgetAnalyzer(combined)
            if not az.trades:
                st.warning("No completed positions found.")
                return
        except Exception as e:
            st.error(f"Error: {e}")
            import traceback
            st.code(traceback.format_exc())
            return

    markets = sorted(set(t['market'] for t in az.trades))
    has_multi = len(markets) > 1

    # ── Account comparison ──
    if has_multi:
        st.markdown('<div class="dash-header">⚖️ Account Comparison</div>', unsafe_allow_html=True)
        cols = st.columns(len(markets))
        for i, m in enumerate(markets):
            s = az.stats(m)
            if not s: continue
            cur = 'USDC' if 'USDC' in m else 'USDT'
            pc = '#00E5A0' if s['total_pnl'] >= 0 else '#F6465D'
            sg = '+' if s['total_pnl'] >= 0 else ''
            with cols[i]:
                st.markdown(f"""
                <div class="account-card">
                    <h3 style="color:#9DA5AE;">{m}</h3>
                    <div class="big-pnl" style="color:{pc};">{sg}{s['total_pnl']:,.2f} {cur}</div>
                    <div style="margin-top:16px; display:grid; grid-template-columns:1fr 1fr; gap:8px; font-size:14px; color:#D0D7DE;">
                        <div><span style="color:#9DA5AE;">Positions</span><br><b>{s['trades']}</b></div>
                        <div><span style="color:#9DA5AE;">Win Rate</span><br><b>{s['win_rate']:.1f}%</b></div>
                        <div><span style="color:#9DA5AE;">Profit Factor</span><br><b>{s['profit_factor']:.2f}</b></div>
                        <div><span style="color:#9DA5AE;">Liquidations</span><br><b style="color:#F6465D;">{s['liqs']}</b></div>
                        <div><span style="color:#9DA5AE;">Trading Fees</span><br><b>{s['trading_fees']:,.2f}</b></div>
                        <div><span style="color:#9DA5AE;">Funding Fees</span><br><b>{s['funding_fees']:,.2f}</b></div>
                        <div><span style="color:#9DA5AE;">Best Trade</span><br><b style="color:#00E5A0;">+{s['best']['net_pnl']:,.2f}</b></div>
                        <div><span style="color:#9DA5AE;">Worst Trade</span><br><b style="color:#F6465D;">{s['worst']['net_pnl']:,.2f}</b></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

        ts = az.stats()
        st.markdown(f"""
        <div style="text-align:center; padding:12px; background:#161B22; border:1px solid #21262D;
                    border-radius:12px; margin-bottom:20px;">
            <span style="color:#9DA5AE; font-size:14px;">Combined Net P&L</span><br>
            <span style="font-size:28px; font-weight:700; color:{'#00E5A0' if ts['total_pnl']>=0 else '#F6465D'};">
                {'+' if ts['total_pnl']>=0 else ''}{ts['total_pnl']:,.2f}
            </span>
            <span style="color:#9DA5AE;"> across {ts['trades']} positions</span>
        </div>
        """, unsafe_allow_html=True)

    # ── Tabs ──
    labels = (markets + ['Combined']) if has_multi else markets
    tabs = st.tabs(labels)

    for idx, label in enumerate(labels):
        with tabs[idx]:
            mf = None if label == 'Combined' else label
            s = az.stats(mf)
            if not s:
                st.info("No data.")
                continue
            cur = 'USDC' if mf and 'USDC' in mf else ('USDT' if mf and 'USDT' in mf else '$')

            render_metrics(s, cur)
            render_chart(az.cumulative(mf), f"Cumulative P&L ({label})")

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
            sym = az.symbol_breakdown(mf)
            if sym:
                sdf = pd.DataFrame([
                    dict(Symbol=k, Positions=v['trades'], Wins=v['wins'],
                         WinRate=round(v['win_rate'], 1), PnL=round(v['pnl'], 2),
                         Funding=round(v['funding'], 2), Liqs=v['liqs'])
                    for k, v in sym.items()
                ]).sort_values('PnL', ascending=False)
                st.dataframe(sdf, use_container_width=True, hide_index=True,
                    column_config={
                        'WinRate': st.column_config.NumberColumn('Win %', format="%.1f%%"),
                        'PnL': st.column_config.NumberColumn('P&L', format="%.2f"),
                        'Funding': st.column_config.NumberColumn('Funding', format="%.2f"),
                    })
                render_bars(sym, f"P&L by Symbol ({label})")

            st.markdown('<div class="dash-header">📋 All Positions</div>', unsafe_allow_html=True)
            render_positions(az.trades, mf)


if __name__ == "__main__":
    main()

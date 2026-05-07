"""
Bitget Trading Analytics Dashboard
Position-based P&L · Trading Journal · Multi-account · Bitget-style dark UI
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import io
import json
import hashlib
from datetime import datetime

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

div[data-testid="stDataFrame"] {
    border: 1px solid #21262D; border-radius: 12px; overflow: hidden;
}
div[data-testid="stDataFrame"] > div { background-color: #171D24 !important; }

div[data-baseweb="select"] > div {
    background-color: #1C2330 !important; border-color: #30363D !important;
    color: #D0D7DE !important;
}
label { color: #C9D1D9 !important; }
p, span, li { color: #D0D7DE; }
div[data-testid="stCaptionContainer"] p { color: #9DA5AE !important; }

/* Text areas & inputs */
textarea, input[type="text"], input[type="number"] {
    background-color: #1C2330 !important; border-color: #30363D !important;
    color: #D0D7DE !important;
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

/* Journal cards */
.journal-card {
    background: #161B22; border: 1px solid #21262D;
    border-radius: 12px; padding: 20px; margin-bottom: 12px;
}
.journal-card .trade-info { color: #9DA5AE; font-size: 13px; margin-bottom: 8px; }
.journal-card .journal-notes { color: #D0D7DE; font-size: 14px; line-height: 1.6; }
.tag-pill {
    display: inline-block; padding: 3px 10px; border-radius: 20px;
    font-size: 12px; font-weight: 500; margin-right: 6px; margin-bottom: 4px;
}
.tag-strategy { background: #1F3A2F; color: #00E5A0; }
.tag-mistake { background: #3A1F1F; color: #F6465D; }
.tag-emotion { background: #1F2D3A; color: #58A6FF; }
</style>
""", unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═════════════════════════════════════════════════════════════════════

STRATEGIES = [
    '', 'Trend Following', 'Breakout', 'Mean Reversion', 'Scalp',
    'Swing', 'News/Event', 'Support/Resistance', 'DCA/Grid', 'Other',
]
EMOTIONS = ['', 'Calm & Focused', 'Confident', 'Anxious', 'FOMO', 'Greedy', 'Fearful', 'Revenge', 'Bored', 'Euphoric']
MISTAKES = [
    'No stop loss', 'Moved stop loss', 'Oversize position', 'FOMO entry',
    'Revenge trade', 'Ignored plan', 'Exited too early', 'Held too long',
    'Wrong direction bias', 'Traded against trend',
]
TIMEFRAMES = ['', '1m', '5m', '15m', '1h', '4h', '1D', '1W']


# ═════════════════════════════════════════════════════════════════════
# JOURNAL MANAGER
# ═════════════════════════════════════════════════════════════════════

class JournalManager:
    """Manages journal entries in session_state with JSON export/import."""

    @staticmethod
    def init():
        if 'journal' not in st.session_state:
            st.session_state.journal = {}

    @staticmethod
    def get(trade_id):
        return st.session_state.journal.get(trade_id, {})

    @staticmethod
    def save(trade_id, entry):
        st.session_state.journal[trade_id] = entry

    @staticmethod
    def delete(trade_id):
        st.session_state.journal.pop(trade_id, None)

    @staticmethod
    def export_json():
        return json.dumps(st.session_state.journal, indent=2, default=str)

    @staticmethod
    def import_json(content):
        data = json.loads(content)
        st.session_state.journal.update(data)
        return len(data)

    @staticmethod
    def count():
        return len(st.session_state.journal)

    @staticmethod
    def all_entries():
        return st.session_state.journal


def make_trade_id(t):
    """Create a stable unique ID for a trade based on its key attributes."""
    key = f"{t['symbol']}_{t['open_date']}_{t['close_date']}_{t['direction']}_{t['net_pnl']:.4f}"
    return hashlib.md5(key.encode()).hexdigest()[:12]


# ═════════════════════════════════════════════════════════════════════
# ANALYZER
# ═════════════════════════════════════════════════════════════════════

class BitgetAnalyzer:
    def __init__(self, df):
        self.df = df
        self.trades = []
        self.parse_trades()

    @staticmethod
    def detect_format(content):
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
        raw = pd.read_csv(io.StringIO(content))
        raw.columns = [c.strip() for c in raw.columns]
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
            if bt in ('nan', ''): continue
            if r['tag'] == 'margin_fee':
                if bt == 'contract_margin_settle_fee':
                    rows.append(dict(Order=r.get('ID (read-only)', ''), Date=r['date'],
                                     Coin='USDT', Futures='LEGACY', Type=bt,
                                     Amount=-r['from_amt'], Fee=0, Market='Legacy'))
                else:
                    rows.append(dict(Order=r.get('ID (read-only)', ''), Date=r['date'],
                                     Coin='USDT', Futures='LEGACY', Type=bt,
                                     Amount=0, Fee=-r['from_amt'], Market='Legacy'))
            elif r['tag'] == 'realized_gain':
                amt = r['to_amt'] if r['txtype'] == 'deposit' else -r['from_amt']
                rows.append(dict(Order=r.get('ID (read-only)', ''), Date=r['date'],
                                 Coin='USDT', Futures='LEGACY', Type=bt,
                                 Amount=amt, Fee=0, Market='Legacy'))
        df = pd.DataFrame(rows)
        if not df.empty:
            df['Order'] = df['Order'].astype(str)
        return df

    @staticmethod
    def merge_dataframes(dfs):
        if len(dfs) == 1: return dfs[0]
        combined = pd.concat(dfs, ignore_index=True)
        if 'Order' in combined.columns:
            combined = combined.drop_duplicates(subset='Order', keep='first')
        return combined.sort_values('Date').reset_index(drop=True)

    def get_funding(self, symbol, od, cd):
        f = self.df[
            (self.df['Futures'] == symbol) & (self.df['Type'] == 'contract_margin_settle_fee')
            & (self.df['Date'] >= od) & (self.df['Date'] <= cd)
        ]
        return f['Amount'].sum()

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
            if sdf.empty: continue
            market = sdf['Market'].iloc[0] if 'Market' in sdf.columns else '?'
            positions, cur = [], None
            for _, r in sdf.iterrows():
                t = r['Type']
                if t in open_t:
                    if cur and cur['hc']:
                        positions.append(cur); cur = None
                    if cur is None:
                        cur = dict(d=t, od=r['Date'], of=[], ca=[], cf=[], cd=[], hc=False)
                    cur['of'].append(r['Fee'])
                elif t in close_t:
                    if cur is None:
                        cur = dict(d='open_long' if 'long' in t else 'open_short',
                                   od=r['Date'], of=[], ca=[], cf=[], cd=[], hc=False)
                    cur['hc'] = True
                    cur['ca'].append(r['Amount']); cur['cf'].append(r['Fee']); cur['cd'].append(r['Date'])
            if cur and cur['hc']: positions.append(cur)

            for p in positions:
                cd = max(p['cd']); od = p['od']
                real = sum(p['ca']); cf = sum(p['cf']); of = sum(p['of'])
                ff = self.get_funding(symbol, od, cd)
                net = real + cf + of + ff
                trade = dict(
                    symbol=symbol, market=market, open_date=od, close_date=cd,
                    direction='Long' if 'long' in p['d'] else 'Short',
                    realized_pnl=real, open_fees=of, close_fees=cf,
                    funding_fees=ff, net_pnl=net, is_win=net > 0,
                    holding_hours=(cd - od).total_seconds() / 3600,
                    is_liquidation=False, num_closes=len(p['ca']),
                )
                trade['id'] = make_trade_id(trade)
                self.trades.append(trade)

            for _, r in sdf[sdf['Type'].str.contains('burst_close', na=False)].iterrows():
                net = r['Amount'] + r['Fee']
                trade = dict(
                    symbol=symbol, market=market, open_date=r['Date'], close_date=r['Date'],
                    direction='Long' if 'long' in r['Type'] else 'Short',
                    realized_pnl=r['Amount'], open_fees=0, close_fees=r['Fee'],
                    funding_fees=0, net_pnl=net, is_win=False,
                    holding_hours=0, is_liquidation=True, num_closes=1,
                )
                trade['id'] = make_trade_id(trade)
                self.trades.append(trade)

        self.trades.sort(key=lambda x: x['close_date'])

    def stats(self, mf=None):
        tr = [t for t in self.trades if not mf or t['market'] == mf]
        if not tr: return None
        n = len(tr)
        w = sum(1 for t in tr if t['is_win']); l = n - w
        lq = sum(1 for t in tr if t['is_liquidation'])
        tp = sum(t['net_pnl'] for t in tr)
        gp = sum(t['net_pnl'] for t in tr if t['net_pnl'] > 0)
        gl = abs(sum(t['net_pnl'] for t in tr if t['net_pnl'] < 0))
        pf = gp / gl if gl > 0 else float('inf')
        ff = sum(t['funding_fees'] for t in tr)
        tf = sum(t['open_fees'] + t['close_fees'] for t in tr)
        rets = [t['net_pnl'] for t in tr]
        sh = (np.mean(rets) / np.std(rets)) * np.sqrt(252) if np.std(rets) > 0 else 0
        cum = np.cumsum(rets); dd = cum - np.maximum.accumulate(cum)
        mdd = float(np.min(dd)) if len(dd) > 0 else 0
        b = max(tr, key=lambda x: x['net_pnl']); wo = min(tr, key=lambda x: x['net_pnl'])
        hh = [t['holding_hours'] for t in tr if t['holding_hours'] > 0]
        return dict(trades=n, wins=w, losses=l, liqs=lq, win_rate=w/n*100, total_pnl=tp,
                    gross_profit=gp, gross_loss=gl, profit_factor=pf,
                    avg_win=gp/w if w else 0, avg_loss=-gl/l if l else 0,
                    funding_fees=ff, trading_fees=tf, sharpe=sh, max_drawdown=mdd,
                    expectancy=tp/n, avg_holding=np.mean(hh) if hh else 0, best=b, worst=wo)

    def symbol_breakdown(self, mf=None):
        tr = [t for t in self.trades if not mf or t['market'] == mf]
        out = {}
        for t in tr:
            s = t['symbol']
            if s not in out:
                out[s] = dict(trades=0, wins=0, pnl=0, funding=0, liqs=0, market=t['market'])
            out[s]['trades'] += 1
            if t['is_win']: out[s]['wins'] += 1
            out[s]['pnl'] += t['net_pnl']; out[s]['funding'] += t['funding_fees']
            if t['is_liquidation']: out[s]['liqs'] += 1
        for s in out:
            out[s]['win_rate'] = out[s]['wins']/out[s]['trades']*100 if out[s]['trades'] else 0
        return out

    def cumulative(self, mf=None):
        tr = [t for t in self.trades if not mf or t['market'] == mf]
        if not tr: return pd.DataFrame()
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
    with c2: st.metric("Win Rate", f"{'🟢' if s['win_rate']>=50 else '🔴'} {s['win_rate']:.1f}%")
    with c3: st.metric("Net P&L", f"{'+' if s['total_pnl']>=0 else ''}{s['total_pnl']:,.2f} {cur}")
    with c4: st.metric("Profit Factor", f"{s['profit_factor']:.2f}")
    with c5: st.metric("Liquidations", s['liqs'])


def render_chart(series, title="Cumulative P&L"):
    if series.empty: return
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=series['date'], y=series['cumulative'], mode='lines', name='P&L',
        line=dict(color='#00E5A0', width=2), fill='tozeroy', fillcolor='rgba(0,229,160,0.08)'))
    lq = series[series['is_liq']]
    if not lq.empty:
        fig.add_trace(go.Scatter(x=lq['date'], y=lq['cumulative'], mode='markers', name='Liquidation',
            marker=dict(color='#F6465D', size=8, symbol='x')))
    fig.update_layout(template='plotly_dark', paper_bgcolor='#0D1117', plot_bgcolor='#0D1117',
        height=360, margin=dict(l=0, r=0, t=30, b=0),
        title=dict(text=title, font=dict(size=14, color='#9DA5AE')),
        xaxis=dict(gridcolor='#21262D', showgrid=False),
        yaxis=dict(gridcolor='#21262D', title='P&L'),
        legend=dict(bgcolor='rgba(0,0,0,0)'), font=dict(family='Albert Sans'), hovermode='x unified')
    st.plotly_chart(fig, use_container_width=True)


def render_bars(sym, title="P&L by Symbol"):
    if not sym: return
    df = pd.DataFrame([dict(symbol=s, pnl=d['pnl']) for s, d in sym.items()]).sort_values('pnl', ascending=True)
    colors = ['#00E5A0' if v >= 0 else '#F6465D' for v in df['pnl']]
    fig = go.Figure(go.Bar(y=df['symbol'], x=df['pnl'], orientation='h', marker_color=colors,
        text=[f"{v:+,.0f}" for v in df['pnl']], textposition='outside', textfont=dict(size=11)))
    fig.update_layout(template='plotly_dark', paper_bgcolor='#0D1117', plot_bgcolor='#0D1117',
        height=max(280, len(df)*28), margin=dict(l=0, r=60, t=30, b=0),
        title=dict(text=title, font=dict(size=14, color='#9DA5AE')),
        xaxis=dict(gridcolor='#21262D', title='P&L'), yaxis=dict(gridcolor='#21262D'),
        font=dict(family='Albert Sans'))
    st.plotly_chart(fig, use_container_width=True)


def render_positions(trades, mf=None):
    data = [t for t in trades if not mf or t['market'] == mf]
    if not data:
        st.info("No positions to display."); return
    df = pd.DataFrame(data)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        sel_sym = st.selectbox("Symbol", ['All'] + sorted(df['symbol'].unique().tolist()), key=f"s_{mf}")
    with c2:
        sel_dir = st.selectbox("Direction", ['All', 'Long', 'Short'], key=f"d_{mf}")
    with c3:
        sel_res = st.selectbox("Result", ['All', 'Win', 'Loss', 'Liquidation'], key=f"r_{mf}")
    with c4:
        sort_map = {'Close date ↓': ('close_date', False), 'Close date ↑': ('close_date', True),
                    'P&L best ↓': ('net_pnl', False), 'P&L worst ↓': ('net_pnl', True),
                    'Holding longest ↓': ('holding_hours', False)}
        sel_sort = st.selectbox("Sort", list(sort_map.keys()), key=f"o_{mf}")

    if sel_sym != 'All': df = df[df['symbol'] == sel_sym]
    if sel_dir != 'All': df = df[df['direction'] == sel_dir]
    if sel_res == 'Win': df = df[(df['is_win']) & (~df['is_liquidation'])]
    elif sel_res == 'Loss': df = df[(~df['is_win']) & (~df['is_liquidation'])]
    elif sel_res == 'Liquidation': df = df[df['is_liquidation']]
    sc, asc = sort_map[sel_sort]
    df = df.sort_values(sc, ascending=asc)
    if df.empty:
        st.info("No positions match filters."); return

    # Check for journal entries
    journal = st.session_state.get('journal', {})
    disp = pd.DataFrame({
        'Opened': df['open_date'].dt.strftime('%Y-%m-%d %H:%M'),
        'Closed': df['close_date'].dt.strftime('%Y-%m-%d %H:%M'),
        'Symbol': df['symbol'], 'Dir': df['direction'],
        'Net P&L': df['net_pnl'].round(2),
        'Funding': df['funding_fees'].round(4),
        'Result': df.apply(lambda r: '⚠️ LIQ' if r['is_liquidation'] else ('✅ Win' if r['is_win'] else '❌ Loss'), axis=1),
        'Holding': df['holding_hours'].apply(lambda h: f"{h:.1f}h" if h > 0 else '—'),
        'Fills': df['num_closes'].astype(int),
        '📓': df['id'].apply(lambda x: '✏️' if x in journal else ''),
    })
    st.caption(f"{len(disp)} of {len(data)} positions")
    st.dataframe(disp, use_container_width=True, hide_index=True,
        height=min(600, 38 + len(disp) * 35),
        column_config={
            'Net P&L': st.column_config.NumberColumn('Net P&L', format="%.2f"),
            'Funding': st.column_config.NumberColumn('Funding', format="%.4f"),
            'Fills': st.column_config.NumberColumn('Fills', format="%d"),
            '📓': st.column_config.TextColumn('📓', width='small'),
        })
    st.download_button("📥 Download CSV", df.to_csv(index=False), "positions.csv", "text/csv", key=f"dl_{mf}")


# ═════════════════════════════════════════════════════════════════════
# JOURNAL UI
# ═════════════════════════════════════════════════════════════════════

def render_journal_tab(trades):
    """Full journal tab: entry form, recent entries, analytics."""
    journal = st.session_state.journal

    # ── Import/Export in sidebar area ──
    st.markdown('<div class="dash-header">📓 Trading Journal</div>', unsafe_allow_html=True)

    j_col1, j_col2, j_col3 = st.columns([2, 1, 1])
    with j_col1:
        st.caption(f"{len(journal)} journal entries recorded")
    with j_col2:
        if journal:
            st.download_button("📥 Export Journal", JournalManager.export_json(),
                               "trading_journal.json", "application/json", key="j_export")
    with j_col3:
        j_file = st.file_uploader("📤 Import", type=['json'], key="j_import", label_visibility="collapsed")
        if j_file:
            try:
                n = JournalManager.import_json(j_file.getvalue().decode('utf-8'))
                st.success(f"Imported {n} entries")
                st.rerun()
            except Exception as e:
                st.error(f"Import error: {e}")

    st.markdown("---")

    # ── Trade selector ──
    trade_options = []
    for t in sorted(trades, key=lambda x: x['close_date'], reverse=True):
        pnl_str = f"+{t['net_pnl']:.2f}" if t['net_pnl'] >= 0 else f"{t['net_pnl']:.2f}"
        has_entry = '✏️ ' if t['id'] in journal else ''
        label = f"{has_entry}{t['close_date'].strftime('%Y-%m-%d %H:%M')} | {t['symbol']} {t['direction']} | {pnl_str}"
        trade_options.append((label, t))

    if not trade_options:
        st.info("No trades to journal.")
        return

    selected_label = st.selectbox(
        "Select a trade to journal",
        [o[0] for o in trade_options],
        key="j_trade_select",
    )
    selected_trade = next(o[1] for o in trade_options if o[0] == selected_label)
    tid = selected_trade['id']
    existing = JournalManager.get(tid)

    # ── Trade summary ──
    pnl_color = '#00E5A0' if selected_trade['net_pnl'] >= 0 else '#F6465D'
    result = '⚠️ Liquidation' if selected_trade['is_liquidation'] else ('✅ Win' if selected_trade['is_win'] else '❌ Loss')
    st.markdown(f"""
    <div class="journal-card">
        <div style="display:grid; grid-template-columns:repeat(5,1fr); gap:12px; font-size:14px;">
            <div><span style="color:#9DA5AE;">Symbol</span><br><b>{selected_trade['symbol']}</b></div>
            <div><span style="color:#9DA5AE;">Direction</span><br><b>{selected_trade['direction']}</b></div>
            <div><span style="color:#9DA5AE;">Net P&L</span><br><b style="color:{pnl_color};">{'+' if selected_trade['net_pnl']>=0 else ''}{selected_trade['net_pnl']:,.2f}</b></div>
            <div><span style="color:#9DA5AE;">Holding</span><br><b>{selected_trade['holding_hours']:.1f}h</b></div>
            <div><span style="color:#9DA5AE;">Result</span><br><b>{result}</b></div>
        </div>
        <div style="margin-top:8px; font-size:13px; color:#9DA5AE;">
            {selected_trade['open_date'].strftime('%Y-%m-%d %H:%M')} → {selected_trade['close_date'].strftime('%Y-%m-%d %H:%M')}
            &nbsp;|&nbsp; {selected_trade['market']}
            &nbsp;|&nbsp; Fees: {selected_trade['open_fees']+selected_trade['close_fees']:.2f}
            &nbsp;|&nbsp; Funding: {selected_trade['funding_fees']:.4f}
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Journal form ──
    with st.form(key=f"journal_form_{tid}"):
        c1, c2, c3 = st.columns(3)
        with c1:
            strategy = st.selectbox("Strategy / Setup", STRATEGIES,
                index=STRATEGIES.index(existing.get('strategy', '')) if existing.get('strategy', '') in STRATEGIES else 0)
        with c2:
            emotion = st.selectbox("Emotional State (entry)", EMOTIONS,
                index=EMOTIONS.index(existing.get('emotion', '')) if existing.get('emotion', '') in EMOTIONS else 0)
        with c3:
            confidence = st.slider("Confidence (1-5)", 1, 5, existing.get('confidence', 3))

        c4, c5 = st.columns(2)
        with c4:
            timeframe = st.selectbox("Timeframe", TIMEFRAMES,
                index=TIMEFRAMES.index(existing.get('timeframe', '')) if existing.get('timeframe', '') in TIMEFRAMES else 0)
        with c5:
            rating = st.slider("Trade Execution Rating (1-5)", 1, 5, existing.get('rating', 3),
                               help="How well did you execute the plan?")

        mistakes = st.multiselect("Mistakes Made", MISTAKES, default=existing.get('mistakes', []))

        setup_notes = st.text_area("Setup & Entry Reason",
            value=existing.get('setup_notes', ''), height=80,
            placeholder="Why did you enter this trade? What was the setup?")

        exit_notes = st.text_area("Exit Notes",
            value=existing.get('exit_notes', ''), height=80,
            placeholder="Why did you exit? Was it planned or reactive?")

        lessons = st.text_area("Lessons Learned",
            value=existing.get('lessons', ''), height=80,
            placeholder="What did you learn? What would you do differently?")

        bc1, bc2 = st.columns([4, 1])
        with bc1:
            submitted = st.form_submit_button("💾 Save Journal Entry", use_container_width=True)
        with bc2:
            delete = st.form_submit_button("🗑️ Delete", use_container_width=True)

    if submitted:
        entry = dict(
            strategy=strategy, emotion=emotion, confidence=confidence,
            timeframe=timeframe, rating=rating, mistakes=mistakes,
            setup_notes=setup_notes, exit_notes=exit_notes, lessons=lessons,
            symbol=selected_trade['symbol'], direction=selected_trade['direction'],
            net_pnl=selected_trade['net_pnl'], close_date=str(selected_trade['close_date']),
            saved_at=str(datetime.now()),
        )
        JournalManager.save(tid, entry)
        st.success("Journal entry saved!")
        st.rerun()

    if delete:
        JournalManager.delete(tid)
        st.info("Journal entry deleted.")
        st.rerun()

    # ── Recent entries ──
    st.markdown('<div class="dash-header">📝 Recent Journal Entries</div>', unsafe_allow_html=True)
    if not journal:
        st.caption("No journal entries yet. Select a trade above and save your first entry.")
    else:
        entries_with_data = []
        for t in sorted(trades, key=lambda x: x['close_date'], reverse=True):
            if t['id'] in journal:
                entries_with_data.append((t, journal[t['id']]))

        for t, e in entries_with_data[:10]:
            pnl_c = '#00E5A0' if t['net_pnl'] >= 0 else '#F6465D'
            tags_html = ''
            if e.get('strategy'):
                tags_html += f'<span class="tag-pill tag-strategy">{e["strategy"]}</span>'
            if e.get('emotion'):
                tags_html += f'<span class="tag-pill tag-emotion">{e["emotion"]}</span>'
            for m in e.get('mistakes', []):
                tags_html += f'<span class="tag-pill tag-mistake">{m}</span>'

            notes_parts = []
            if e.get('setup_notes'): notes_parts.append(f"<b>Setup:</b> {e['setup_notes']}")
            if e.get('exit_notes'): notes_parts.append(f"<b>Exit:</b> {e['exit_notes']}")
            if e.get('lessons'): notes_parts.append(f"<b>Lessons:</b> {e['lessons']}")
            notes_html = '<br>'.join(notes_parts)

            st.markdown(f"""
            <div class="journal-card">
                <div class="trade-info">
                    {t['close_date'].strftime('%Y-%m-%d %H:%M')} · {t['symbol']} · {t['direction']} ·
                    <span style="color:{pnl_c}; font-weight:600;">{'+' if t['net_pnl']>=0 else ''}{t['net_pnl']:,.2f}</span>
                    &nbsp;· Confidence: {'⭐' * e.get('confidence', 0)} · Execution: {'⭐' * e.get('rating', 0)}
                </div>
                <div style="margin:6px 0;">{tags_html}</div>
                <div class="journal-notes">{notes_html}</div>
            </div>
            """, unsafe_allow_html=True)

    # ── Journal Analytics ──
    if len(journal) >= 3:
        st.markdown('<div class="dash-header">📊 Journal Analytics</div>', unsafe_allow_html=True)
        render_journal_analytics(trades, journal)


def render_journal_analytics(trades, journal):
    """Analyze patterns from journal entries."""
    trade_map = {t['id']: t for t in trades}
    records = []
    for tid, entry in journal.items():
        if tid in trade_map:
            t = trade_map[tid]
            records.append({**entry, 'net_pnl': t['net_pnl'], 'is_win': t['is_win'],
                           'holding_hours': t['holding_hours'], 'trade_id': tid})
    if not records:
        return
    jdf = pd.DataFrame(records)

    c1, c2 = st.columns(2)

    # ── By Strategy ──
    with c1:
        if 'strategy' in jdf.columns:
            strat_df = jdf[jdf['strategy'] != ''].groupby('strategy').agg(
                Trades=('net_pnl', 'count'),
                AvgPnL=('net_pnl', 'mean'),
                TotalPnL=('net_pnl', 'sum'),
                WinRate=('is_win', 'mean'),
            ).round(2)
            strat_df['WinRate'] = (strat_df['WinRate'] * 100).round(1)
            if not strat_df.empty:
                st.markdown("**Performance by Strategy**")
                st.dataframe(strat_df.sort_values('TotalPnL', ascending=False),
                             use_container_width=True,
                             column_config={
                                 'WinRate': st.column_config.NumberColumn('Win %', format="%.1f%%"),
                                 'AvgPnL': st.column_config.NumberColumn('Avg P&L', format="%.2f"),
                                 'TotalPnL': st.column_config.NumberColumn('Total P&L', format="%.2f"),
                             })

    # ── By Emotional State ──
    with c2:
        if 'emotion' in jdf.columns:
            emo_df = jdf[jdf['emotion'] != ''].groupby('emotion').agg(
                Trades=('net_pnl', 'count'),
                AvgPnL=('net_pnl', 'mean'),
                TotalPnL=('net_pnl', 'sum'),
                WinRate=('is_win', 'mean'),
            ).round(2)
            emo_df['WinRate'] = (emo_df['WinRate'] * 100).round(1)
            if not emo_df.empty:
                st.markdown("**Performance by Emotional State**")
                st.dataframe(emo_df.sort_values('TotalPnL', ascending=False),
                             use_container_width=True,
                             column_config={
                                 'WinRate': st.column_config.NumberColumn('Win %', format="%.1f%%"),
                                 'AvgPnL': st.column_config.NumberColumn('Avg P&L', format="%.2f"),
                                 'TotalPnL': st.column_config.NumberColumn('Total P&L', format="%.2f"),
                             })

    # ── Confidence vs P&L ──
    if 'confidence' in jdf.columns and jdf['confidence'].nunique() > 1:
        conf_df = jdf.groupby('confidence').agg(
            Trades=('net_pnl', 'count'),
            AvgPnL=('net_pnl', 'mean'),
            WinRate=('is_win', 'mean'),
        ).round(2)
        conf_df['WinRate'] = (conf_df['WinRate'] * 100).round(1)
        fig = go.Figure()
        fig.add_trace(go.Bar(x=conf_df.index, y=conf_df['AvgPnL'], name='Avg P&L',
            marker_color=['#00E5A0' if v >= 0 else '#F6465D' for v in conf_df['AvgPnL']],
            text=[f"{v:.0f}" for v in conf_df['AvgPnL']], textposition='outside'))
        fig.update_layout(template='plotly_dark', paper_bgcolor='#0D1117', plot_bgcolor='#0D1117',
            height=280, margin=dict(l=0, r=0, t=30, b=0),
            title=dict(text='Avg P&L by Confidence Level', font=dict(size=14, color='#9DA5AE')),
            xaxis=dict(title='Confidence (1-5)', dtick=1),
            yaxis=dict(gridcolor='#21262D', title='Avg P&L'), font=dict(family='Albert Sans'))
        st.plotly_chart(fig, use_container_width=True)

    # ── Top Mistakes ──
    all_mistakes = []
    for r in records:
        for m in r.get('mistakes', []):
            all_mistakes.append({'mistake': m, 'net_pnl': r['net_pnl']})
    if all_mistakes:
        mdf = pd.DataFrame(all_mistakes)
        mistake_stats = mdf.groupby('mistake').agg(
            Count=('net_pnl', 'count'),
            AvgPnL=('net_pnl', 'mean'),
            TotalPnL=('net_pnl', 'sum'),
        ).round(2).sort_values('Count', ascending=False)

        st.markdown("**Most Frequent Mistakes & Their Cost**")
        st.dataframe(mistake_stats, use_container_width=True,
                     column_config={
                         'AvgPnL': st.column_config.NumberColumn('Avg P&L', format="%.2f"),
                         'TotalPnL': st.column_config.NumberColumn('Total Cost', format="%.2f"),
                     })

    # ── Execution Rating vs P&L ──
    if 'rating' in jdf.columns and jdf['rating'].nunique() > 1:
        rat_df = jdf.groupby('rating').agg(
            Trades=('net_pnl', 'count'), AvgPnL=('net_pnl', 'mean'), WinRate=('is_win', 'mean'),
        ).round(2)
        rat_df['WinRate'] = (rat_df['WinRate'] * 100).round(1)
        fig2 = go.Figure()
        fig2.add_trace(go.Bar(x=rat_df.index, y=rat_df['WinRate'], name='Win Rate %',
            marker_color='#58A6FF', text=[f"{v:.0f}%" for v in rat_df['WinRate']], textposition='outside'))
        fig2.update_layout(template='plotly_dark', paper_bgcolor='#0D1117', plot_bgcolor='#0D1117',
            height=280, margin=dict(l=0, r=0, t=30, b=0),
            title=dict(text='Win Rate by Execution Rating', font=dict(size=14, color='#9DA5AE')),
            xaxis=dict(title='Execution Rating (1-5)', dtick=1),
            yaxis=dict(gridcolor='#21262D', title='Win Rate %'), font=dict(family='Albert Sans'))
        st.plotly_chart(fig2, use_container_width=True)


# ═════════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════════

def main():
    JournalManager.init()

    st.markdown("""
    <div style="display:flex; align-items:center; gap:12px; margin-bottom:4px;">
        <span style="font-size:28px;">📊</span>
        <span style="font-size:26px; font-weight:700; color:#E6EDF3;">Trading Dashboard</span>
    </div>
    <p style="color:#9DA5AE; margin-top:0; font-size:14px;">
        Bitget Futures · Position-based P&L · Trading Journal · Multi-account
    </p>
    """, unsafe_allow_html=True)

    with st.sidebar:
        st.markdown("### 📁 Upload Data")
        uploaded = st.file_uploader("Bitget CSV Transaction Exports", type=['csv'],
            accept_multiple_files=True, help="Supports Bitget USDT-M, USDC-M, and legacy exports")
        st.markdown("---")
        st.markdown(
            "**Supported formats**\n\n"
            "- Bitget USDT-M / USDC-M exports\n"
            "- Legacy portfolio-tracker CSV\n\n"
            "Multiple files merge automatically."
        )
        st.markdown("---")
        st.markdown("### 📓 Journal Data")
        j_count = JournalManager.count()
        st.caption(f"{j_count} journal entries")
        if j_count > 0:
            st.download_button("📥 Export Journal JSON", JournalManager.export_json(),
                               "trading_journal.json", "application/json", key="sidebar_j_export")
        j_import = st.file_uploader("Import Journal JSON", type=['json'], key="sidebar_j_import")
        if j_import:
            try:
                n = JournalManager.import_json(j_import.getvalue().decode('utf-8'))
                st.success(f"Imported {n} entries")
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

    if not uploaded:
        st.markdown("""
        <div style="text-align:center; padding:80px 20px; color:#9DA5AE;">
            <p style="font-size:48px; margin-bottom:16px;">📁</p>
            <p style="font-size:18px; color:#D0D7DE;">Upload your Bitget CSV export(s) to get started</p>
            <p style="font-size:14px; margin-top:8px;">
                USDT-M · USDC-M · Legacy accounts · Trading Journal
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
                st.warning("No valid data found."); return
            combined = BitgetAnalyzer.merge_dataframes(dfs)
            az = BitgetAnalyzer(combined)
            if not az.trades:
                st.warning("No completed positions found."); return
        except Exception as e:
            st.error(f"Error: {e}")
            import traceback; st.code(traceback.format_exc()); return

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

    # ── Tabs: Markets + Journal ──
    labels = (markets + ['Combined', '📓 Journal']) if has_multi else (markets + ['📓 Journal'])
    tabs = st.tabs(labels)

    for idx, label in enumerate(labels):
        with tabs[idx]:
            if label == '📓 Journal':
                render_journal_tab(az.trades)
                continue

            mf = None if label == 'Combined' else label
            s = az.stats(mf)
            if not s:
                st.info("No data."); continue
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
                    f"**Best:** {s['best']['symbol']} → **+{s['best']['net_pnl']:,.2f}** &nbsp;|&nbsp; "
                    f"**Worst:** {s['worst']['symbol']} → **{s['worst']['net_pnl']:,.2f}**")

            st.markdown('<div class="dash-header">📊 Performance by Symbol</div>', unsafe_allow_html=True)
            sym = az.symbol_breakdown(mf)
            if sym:
                sdf = pd.DataFrame([
                    dict(Symbol=k, Positions=v['trades'], Wins=v['wins'],
                         WinRate=round(v['win_rate'],1), PnL=round(v['pnl'],2),
                         Funding=round(v['funding'],2), Liqs=v['liqs'])
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

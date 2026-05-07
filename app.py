"""
Bitget Trading Analytics Dashboard + Trade Republic Portfolio
Position-based P&L · Trading Journal · Multi-account · Bitget-style dark UI
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
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
    background-color: #1C2330 !important; border-color: #30363D !important; color: #D0D7DE !important;
}
label { color: #C9D1D9 !important; }
p, span, li { color: #D0D7DE; }
div[data-testid="stCaptionContainer"] p { color: #9DA5AE !important; }
textarea, input[type="text"], input[type="number"] {
    background-color: #1C2330 !important; border-color: #30363D !important; color: #D0D7DE !important;
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

STRATEGIES = ['', 'Trend Following', 'Breakout', 'Mean Reversion', 'Scalp',
              'Swing', 'News/Event', 'Support/Resistance', 'DCA/Grid', 'Other']
EMOTIONS = ['', 'Calm & Focused', 'Confident', 'Anxious', 'FOMO', 'Greedy', 'Fearful', 'Revenge', 'Bored', 'Euphoric']
MISTAKES = ['No stop loss', 'Moved stop loss', 'Oversize position', 'FOMO entry',
            'Revenge trade', 'Ignored plan', 'Exited too early', 'Held too long',
            'Wrong direction bias', 'Traded against trend']
TIMEFRAMES = ['', '1m', '5m', '15m', '1h', '4h', '1D', '1W']


# ═════════════════════════════════════════════════════════════════════
# JOURNAL
# ═════════════════════════════════════════════════════════════════════

class JournalManager:
    @staticmethod
    def init():
        if 'journal' not in st.session_state:
            st.session_state.journal = {}

    @staticmethod
    def get(tid): return st.session_state.journal.get(tid, {})

    @staticmethod
    def save(tid, entry): st.session_state.journal[tid] = entry

    @staticmethod
    def delete(tid): st.session_state.journal.pop(tid, None)

    @staticmethod
    def export_json(): return json.dumps(st.session_state.journal, indent=2, default=str)

    @staticmethod
    def import_json(content):
        data = json.loads(content)
        st.session_state.journal.update(data)
        return len(data)

    @staticmethod
    def count(): return len(st.session_state.journal)


def make_trade_id(t):
    key = f"{t['symbol']}_{t['open_date']}_{t['close_date']}_{t['direction']}_{t['net_pnl']:.4f}"
    return hashlib.md5(key.encode()).hexdigest()[:12]


# ═════════════════════════════════════════════════════════════════════
# BITGET ANALYZER
# ═════════════════════════════════════════════════════════════════════

class BitgetAnalyzer:
    def __init__(self, df):
        self.df = df; self.trades = []; self.parse_trades()

    @staticmethod
    def detect_format(content):
        first = content.split('\n')[0]
        if 'From Wallet' in first or 'Description;;;' in first: return 'legacy'
        return 'bitget'

    @staticmethod
    def load_csv(f):
        content = f.getvalue().decode('utf-8-sig')
        return BitgetAnalyzer._load_legacy(content) if BitgetAnalyzer.detect_format(content) == 'legacy' else BitgetAnalyzer._load_bitget(content)

    @staticmethod
    def _load_bitget(content):
        df = pd.read_csv(io.StringIO(content)); df.columns = [c.strip() for c in df.columns]
        if 'Order' in df.columns: df['Order'] = df['Order'].astype(str).str.strip()
        df['Date'] = pd.to_datetime(df['Date'].str.strip())
        df['Amount'] = pd.to_numeric(df['Amount'], errors='coerce').fillna(0)
        df['Fee'] = pd.to_numeric(df['Fee'], errors='coerce').fillna(0)
        if 'Coin' in df.columns:
            coin = df['Coin'].str.strip().iloc[0] if len(df) > 0 else ''
            df['Market'] = 'USDC-M' if coin == 'USDC' else 'USDT-M'
        else: df['Market'] = 'Unknown'
        return df

    @staticmethod
    def _load_legacy(content):
        raw = pd.read_csv(io.StringIO(content)); raw.columns = [c.strip() for c in raw.columns]
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
                    rows.append(dict(Order=r.get('ID (read-only)', ''), Date=r['date'], Coin='USDT', Futures='LEGACY', Type=bt, Amount=-r['from_amt'], Fee=0, Market='Legacy'))
                else:
                    rows.append(dict(Order=r.get('ID (read-only)', ''), Date=r['date'], Coin='USDT', Futures='LEGACY', Type=bt, Amount=0, Fee=-r['from_amt'], Market='Legacy'))
            elif r['tag'] == 'realized_gain':
                amt = r['to_amt'] if r['txtype'] == 'deposit' else -r['from_amt']
                rows.append(dict(Order=r.get('ID (read-only)', ''), Date=r['date'], Coin='USDT', Futures='LEGACY', Type=bt, Amount=amt, Fee=0, Market='Legacy'))
        df = pd.DataFrame(rows)
        if not df.empty: df['Order'] = df['Order'].astype(str)
        return df

    @staticmethod
    def merge_dataframes(dfs):
        if len(dfs) == 1: return dfs[0]
        c = pd.concat(dfs, ignore_index=True)
        if 'Order' in c.columns: c = c.drop_duplicates(subset='Order', keep='first')
        return c.sort_values('Date').reset_index(drop=True)

    def get_funding(self, sym, od, cd):
        return self.df[(self.df['Futures'] == sym) & (self.df['Type'] == 'contract_margin_settle_fee') & (self.df['Date'] >= od) & (self.df['Date'] <= cd)]['Amount'].sum()

    def parse_trades(self):
        """
        Build closed Bitget positions from ledger rows.

        This keeps separate open Long/Short buckets per symbol instead of using a
        single current position. It is more robust when a file contains partial
        closes, alternating long/short trades, force closes, or multiple market
        exports merged together.
        """
        open_t = {'open_short', 'open_long'}
        close_t = {'close_short', 'close_long', 'force_close_long', 'force_close_short'}
        liquidation_t = {'burst_close_long', 'burst_close_short'}

        valid = self.df[
            self.df['Futures'].notna()
            & (self.df['Futures'].astype(str).str.strip() != '')
            & (self.df['Futures'].astype(str) != 'nan')
        ].copy()

        if valid.empty:
            return

        valid['Type'] = valid['Type'].astype(str).str.strip()

        def direction_from_type(t):
            return 'Long' if 'long' in str(t) else 'Short'

        for sym in valid['Futures'].unique():
            sdf = valid[valid['Futures'] == sym].sort_values('Date')
            if sdf.empty:
                continue

            market = sdf['Market'].iloc[0] if 'Market' in sdf.columns else '?'
            current = {'Long': None, 'Short': None}
            positions = []

            for _, r in sdf.iterrows():
                t = str(r['Type']).strip()
                direction = direction_from_type(t)

                if t in open_t:
                    cur = current[direction]
                    if cur is None:
                        cur = dict(
                            d=t, direction=direction, od=r['Date'],
                            of=[], ca=[], cf=[], cd=[], hc=False,
                            is_liquidation=False
                        )
                        current[direction] = cur
                    cur['of'].append(float(r.get('Fee', 0) or 0))

                elif t in close_t:
                    cur = current[direction]
                    if cur is None:
                        # Missing open leg in the export. Keep the close so it is visible.
                        cur = dict(
                            d='open_long' if direction == 'Long' else 'open_short',
                            direction=direction, od=r['Date'],
                            of=[], ca=[], cf=[], cd=[], hc=False,
                            is_liquidation=('force_close' in t)
                        )
                        current[direction] = cur

                    cur['hc'] = True
                    cur['ca'].append(float(r.get('Amount', 0) or 0))
                    cur['cf'].append(float(r.get('Fee', 0) or 0))
                    cur['cd'].append(r['Date'])
                    if 'force_close' in t:
                        cur['is_liquidation'] = True

                    # For Bitget transaction exports there is usually no reliable size
                    # in this normalized ledger. We therefore close a position when a
                    # close event appears after an open bucket, and keep additional
                    # same-direction close fills in that bucket until the next open.
                    positions.append(cur)
                    current[direction] = None

                elif t in liquidation_t:
                    net = float(r.get('Amount', 0) or 0) + float(r.get('Fee', 0) or 0)
                    trade = dict(
                        symbol=sym, market=market,
                        open_date=r['Date'], close_date=r['Date'],
                        direction=direction,
                        realized_pnl=float(r.get('Amount', 0) or 0),
                        open_fees=0,
                        close_fees=float(r.get('Fee', 0) or 0),
                        funding_fees=0,
                        net_pnl=net,
                        is_win=False,
                        holding_hours=0,
                        is_liquidation=True,
                        num_closes=1
                    )
                    trade['id'] = make_trade_id(trade)
                    self.trades.append(trade)

            for p in positions:
                if not p.get('hc') or not p.get('cd'):
                    continue
                cd = max(p['cd'])
                od = p['od']
                real = sum(p['ca'])
                cf = sum(p['cf'])
                of = sum(p['of'])
                ff = self.get_funding(sym, od, cd)
                net = real + cf + of + ff
                trade = dict(
                    symbol=sym, market=market,
                    open_date=od, close_date=cd,
                    direction=p['direction'],
                    realized_pnl=real,
                    open_fees=of,
                    close_fees=cf,
                    funding_fees=ff,
                    net_pnl=net,
                    is_win=net > 0,
                    holding_hours=(cd - od).total_seconds() / 3600,
                    is_liquidation=bool(p.get('is_liquidation')),
                    num_closes=len(p['ca'])
                )
                trade['id'] = make_trade_id(trade)
                self.trades.append(trade)

        # De-duplicate defensively when the same export is uploaded twice.
        deduped = {}
        for t in self.trades:
            deduped[t['id']] = t
        self.trades = sorted(deduped.values(), key=lambda x: x['close_date'])

    def stats(self, mf=None):
        tr = [t for t in self.trades if not mf or t['market'] == mf]
        if not tr: return None
        n = len(tr); w = sum(1 for t in tr if t['is_win']); l = n - w
        lq = sum(1 for t in tr if t['is_liquidation']); tp = sum(t['net_pnl'] for t in tr)
        gp = sum(t['net_pnl'] for t in tr if t['net_pnl'] > 0); gl = abs(sum(t['net_pnl'] for t in tr if t['net_pnl'] < 0))
        pf = gp / gl if gl > 0 else float('inf'); ff = sum(t['funding_fees'] for t in tr)
        tf = sum(t['open_fees'] + t['close_fees'] for t in tr); rets = [t['net_pnl'] for t in tr]
        sh = (np.mean(rets) / np.std(rets)) * np.sqrt(252) if np.std(rets) > 0 else 0
        cum = np.cumsum(rets); dd = cum - np.maximum.accumulate(cum); mdd = float(np.min(dd)) if len(dd) > 0 else 0
        b = max(tr, key=lambda x: x['net_pnl']); wo = min(tr, key=lambda x: x['net_pnl'])
        hh = [t['holding_hours'] for t in tr if t['holding_hours'] > 0]
        return dict(trades=n, wins=w, losses=l, liqs=lq, win_rate=w/n*100, total_pnl=tp, gross_profit=gp, gross_loss=gl,
                    profit_factor=pf, avg_win=gp/w if w else 0, avg_loss=-gl/l if l else 0, funding_fees=ff, trading_fees=tf,
                    sharpe=sh, max_drawdown=mdd, expectancy=tp/n, avg_holding=np.mean(hh) if hh else 0, best=b, worst=wo)

    def symbol_breakdown(self, mf=None):
        tr = [t for t in self.trades if not mf or t['market'] == mf]; out = {}
        for t in tr:
            s = t['symbol']
            if s not in out: out[s] = dict(trades=0, wins=0, pnl=0, funding=0, liqs=0, market=t['market'])
            out[s]['trades'] += 1
            if t['is_win']: out[s]['wins'] += 1
            out[s]['pnl'] += t['net_pnl']; out[s]['funding'] += t['funding_fees']
            if t['is_liquidation']: out[s]['liqs'] += 1
        for s in out: out[s]['win_rate'] = out[s]['wins'] / out[s]['trades'] * 100 if out[s]['trades'] else 0
        return out

    def cumulative(self, mf=None):
        tr = [t for t in self.trades if not mf or t['market'] == mf]
        if not tr: return pd.DataFrame()
        cum = np.cumsum([t['net_pnl'] for t in tr])
        return pd.DataFrame(dict(date=[t['close_date'] for t in tr], pnl=[t['net_pnl'] for t in tr], cumulative=cum, is_liq=[t['is_liquidation'] for t in tr]))


# ═════════════════════════════════════════════════════════════════════
# TRADE REPUBLIC ANALYZER
# ═════════════════════════════════════════════════════════════════════


class TradeRepublicAnalyzer:
    """
    Trade Republic CSV analyzer with FIFO lot matching.

    Design goals:
    - Use symbol/ISIN as the asset key instead of display name.
    - Build buy lots including buy fees in cost basis.
    - Close lots FIFO for SELL, WARRANT_EXERCISE and transfers out.
    - Treat sell fees/taxes as cash deductions in net P&L.
    - Handle stock dividends and corrections as zero-cost lots.
    - Handle paired SPLIT / REVERSE_SPLIT rows as cost-preserving lot transfers.
    """

    EPS = 1e-9

    def __init__(self, df):
        self.df = df.copy()
        self.closed_positions = []
        self.open_positions = []
        self.data_quality_issues = []
        self.unmatched_closures = []
        self.lots_by_key = {}
        self.meta_by_key = {}
        self.analyze()

    @staticmethod
    def load_csv(f):
        content = f.getvalue().decode('utf-8-sig')
        df = pd.read_csv(io.StringIO(content))

        # Ensure all expected columns exist; TR exports can change slightly.
        defaults = {
            'datetime': pd.NaT, 'date': pd.NaT, 'category': '', 'type': '',
            'asset_class': '', 'name': '', 'symbol': '', 'shares': 0,
            'price': 0, 'amount': 0, 'fee': 0, 'tax': 0, 'currency': 'EUR',
            'description': '', 'transaction_id': ''
        }
        for col, default in defaults.items():
            if col not in df.columns:
                df[col] = default

        for col in ['amount', 'fee', 'tax', 'shares', 'price']:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

        df['datetime'] = pd.to_datetime(df['datetime'], errors='coerce', utc=True)
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        df['type'] = df['type'].astype(str).str.strip()
        df['category'] = df['category'].astype(str).str.strip()
        df['asset_class'] = df['asset_class'].fillna('').astype(str).str.strip()
        df['name'] = df['name'].fillna('').astype(str).str.strip()
        df['symbol'] = df['symbol'].fillna('').astype(str).str.strip()
        df['description'] = df['description'].fillna('').astype(str)

        return df.sort_values(['datetime', 'transaction_id']).reset_index(drop=True)

    @staticmethod
    def is_tr_file(f):
        content = f.getvalue().decode('utf-8-sig')
        f.seek(0)
        first = content.splitlines()[0] if content else ''
        return 'account_type' in first and 'asset_class' in first

    @staticmethod
    def _signed_number(x):
        try:
            return float(x)
        except Exception:
            return 0.0

    def _key(self, row):
        symbol = str(row.get('symbol', '') or '').strip()
        name = str(row.get('name', '') or '').strip()
        asset_class = str(row.get('asset_class', '') or '').strip()
        if symbol:
            return symbol
        if name:
            return f"NAME::{name}"
        return f"UNKNOWN::{asset_class}"

    def _update_meta(self, key, row):
        if key not in self.meta_by_key:
            self.meta_by_key[key] = dict(
                symbol=str(row.get('symbol', '') or '').strip(),
                name=str(row.get('name', '') or '').strip(),
                asset_class=str(row.get('asset_class', '') or '').strip(),
            )
        else:
            m = self.meta_by_key[key]
            for field in ['symbol', 'name', 'asset_class']:
                val = str(row.get(field, '') or '').strip()
                if val:
                    m[field] = val

    def _lots(self, key):
        return self.lots_by_key.setdefault(key, [])

    def _add_lot(self, key, shares, total_cost, row, source='BUY'):
        shares = float(shares or 0)
        total_cost = float(total_cost or 0)
        if shares <= self.EPS:
            return
        self._update_meta(key, row)
        self._lots(key).append(dict(
            key=key,
            shares=shares,
            total_cost=total_cost,
            unit_cost=total_cost / shares if shares else 0,
            open_date=row.get('datetime'),
            source=source,
            txid=row.get('transaction_id', ''),
        ))

    def _pop_fifo_cost(self, key, qty, row, close_type):
        """
        Remove qty from FIFO lots and return matched chunks:
        [{shares, cost_basis, first_buy, lot_source}]
        """
        qty = float(abs(qty or 0))
        lots = self._lots(key)
        matched = []

        while qty > self.EPS and lots:
            lot = lots[0]
            take = min(qty, lot['shares'])
            unit_cost = lot['total_cost'] / lot['shares'] if lot['shares'] else 0
            cost = unit_cost * take
            matched.append(dict(
                shares=take,
                cost_basis=cost,
                first_buy=lot.get('open_date'),
                lot_source=lot.get('source', 'BUY'),
            ))

            lot['shares'] -= take
            lot['total_cost'] -= cost
            qty -= take

            if lot['shares'] <= self.EPS:
                lots.pop(0)

        if qty > 1e-6:
            meta = self.meta_by_key.get(key, {})
            self.unmatched_closures.append(dict(
                datetime=row.get('datetime'),
                name=meta.get('name') or row.get('name', ''),
                symbol=meta.get('symbol') or row.get('symbol', ''),
                missing_shares=qty,
                close_type=close_type,
                type=row.get('type', ''),
                transaction_id=row.get('transaction_id', ''),
            ))
            self.data_quality_issues.append(
                f"{close_type}: {qty:.8f} shares could not be matched for {meta.get('symbol') or key}"
            )

        return matched

    def _close_lots(self, key, qty, gross_proceeds, close_fee, close_tax, row, close_type='SELL'):
        qty = float(abs(qty or 0))
        if qty <= self.EPS:
            return

        self._update_meta(key, row)
        matched = self._pop_fifo_cost(key, qty, row, close_type)
        if not matched:
            return

        total_matched = sum(m['shares'] for m in matched)
        total_cost = sum(m['cost_basis'] for m in matched)
        gross_proceeds = float(gross_proceeds or 0)
        close_fee = float(close_fee or 0)
        close_tax = float(close_tax or 0)

        # Allocate proceeds/fee/tax to matched shares if only a partial close was possible.
        allocation = total_matched / qty if qty else 1
        proceeds_alloc = gross_proceeds * allocation
        fee_alloc = close_fee * allocation
        tax_alloc = close_tax * allocation

        meta = self.meta_by_key.get(key, {})
        realized_pnl = proceeds_alloc - total_cost
        net_pnl = proceeds_alloc + fee_alloc + tax_alloc - total_cost

        first_buy_values = [m['first_buy'] for m in matched if pd.notna(m['first_buy'])]
        first_buy = min(first_buy_values) if first_buy_values else row.get('datetime')
        avg_buy_price = total_cost / total_matched if total_matched else 0
        avg_sell_price = proceeds_alloc / total_matched if total_matched else 0

        self.closed_positions.append(dict(
            name=meta.get('name') or row.get('name', ''),
            symbol=meta.get('symbol') or key,
            asset_class=meta.get('asset_class') or row.get('asset_class', ''),
            shares_sold=total_matched,
            avg_buy_price=avg_buy_price,
            avg_sell_price=avg_sell_price,
            realized_pnl=realized_pnl,
            fees=abs(fee_alloc),
            taxes=abs(tax_alloc),
            net_pnl=net_pnl,
            first_buy=first_buy,
            last_sell=row.get('datetime'),
            num_buys=len(set(m.get('first_buy') for m in matched)),
            num_sells=1,
            close_type=close_type,
            transaction_id=row.get('transaction_id', ''),
        ))

    def _find_tilg_for_exercise(self, row, used_tilg_ids):
        symbol = str(row.get('symbol', '') or '').strip()
        if not symbol:
            return 0.0, 0.0

        candidates = self.df[
            (self.df['type'] == 'TILG') &
            (self.df['symbol'].astype(str).str.strip() == symbol)
        ].copy()

        if candidates.empty:
            return 0.0, 0.0

        # Prefer the nearest unused TILG after the exercise; fall back to nearest.
        candidates['time_diff'] = (candidates['datetime'] - row.get('datetime')).dt.total_seconds()
        after = candidates[candidates['time_diff'] >= -60].sort_values('time_diff')
        ordered = pd.concat([after, candidates.assign(time_diff_abs=candidates['time_diff'].abs()).sort_values('time_diff_abs')])

        for _, c in ordered.iterrows():
            txid = c.get('transaction_id', '')
            if txid not in used_tilg_ids:
                used_tilg_ids.add(txid)
                return float(c.get('amount', 0) or 0), float(c.get('tax', 0) or 0)

        return 0.0, 0.0

    def _handle_split_group(self, group):
        """
        Handles paired TR split rows:
        old instrument negative shares, new instrument positive shares.
        Cost basis is transferred proportionally from old lots to new lots.
        """
        negatives = group[group['shares'] < -self.EPS]
        positives = group[group['shares'] > self.EPS]

        if negatives.empty or positives.empty:
            # If the export contains a one-sided split, record it and continue.
            for _, r in group.iterrows():
                self.data_quality_issues.append(
                    f"One-sided {r['type']} ignored for {r.get('symbol','') or r.get('name','')}"
                )
            return

        # This covers common one-old-to-one-new TR split rows.
        neg_total = abs(negatives['shares'].sum())
        pos_total = positives['shares'].sum()
        if neg_total <= self.EPS or pos_total <= self.EPS:
            return

        # Pull cost from negative instruments.
        transferred_chunks = []
        for _, r in negatives.iterrows():
            old_key = self._key(r)
            self._update_meta(old_key, r)
            transferred_chunks.extend(self._pop_fifo_cost(old_key, abs(r['shares']), r, r['type']))

        total_cost = sum(c['cost_basis'] for c in transferred_chunks)
        first_buy = min([c['first_buy'] for c in transferred_chunks if pd.notna(c['first_buy'])], default=group['datetime'].iloc[0])

        # Add cost-preserving lots to positive instrument(s).
        for _, r in positives.iterrows():
            new_key = self._key(r)
            self._update_meta(new_key, r)
            share_ratio = float(r['shares']) / pos_total if pos_total else 0
            self._add_lot(
                new_key,
                float(r['shares']),
                total_cost * share_ratio,
                {**r.to_dict(), 'datetime': first_buy},
                source=r['type']
            )

    def analyze(self):
        df = self.df.copy()
        used_tilg_ids = set()

        # Process split groups first, but in chronological order relative to other events.
        split_ids = set()
        for (_, _, dt), group in df[df['type'].isin(['SPLIT', 'REVERSE_SPLIT'])].groupby(['type', 'category', 'datetime'], dropna=False):
            split_ids.update(group.index.tolist())

        def event_priority(row):
            typ = row['type']
            if typ in ['SPLIT', 'REVERSE_SPLIT']:
                return 1
            if typ in ['BUY', 'STOCK_DIVIDEND', 'CORRECTION'] and float(row.get('shares', 0) or 0) > 0:
                return 0
            if typ in ['SELL', 'WARRANT_EXERCISE', 'FREE_DELIVERY'] or (typ == 'CORRECTION' and float(row.get('shares', 0) or 0) < 0):
                return 2
            return 3

        rows = df.sort_values(['datetime', 'transaction_id']).copy()
        rows['_priority'] = rows.apply(event_priority, axis=1)
        rows = rows.sort_values(['datetime', '_priority', 'transaction_id'])

        processed_split_groups = set()

        for idx, row in rows.iterrows():
            typ = row['type']
            category = row['category']

            if typ in ['SPLIT', 'REVERSE_SPLIT']:
                group_key = (typ, category, row['datetime'])
                if group_key not in processed_split_groups:
                    group = df[
                        (df['type'] == typ) &
                        (df['category'] == category) &
                        (df['datetime'] == row['datetime'])
                    ]
                    self._handle_split_group(group)
                    processed_split_groups.add(group_key)
                continue

            # Only asset-related rows are needed for FIFO.
            if not row.get('symbol', '') and not row.get('name', ''):
                continue

            key = self._key(row)
            self._update_meta(key, row)

            shares = float(row.get('shares', 0) or 0)
            amount = float(row.get('amount', 0) or 0)
            fee = float(row.get('fee', 0) or 0)
            tax = float(row.get('tax', 0) or 0)

            if category == 'TRADING' and typ == 'BUY':
                # Buy cost basis = cash paid including fees/taxes.
                total_cost = abs(amount + fee + tax)
                self._add_lot(key, abs(shares), total_cost, row, source='BUY')

            elif category == 'TRADING' and typ == 'SELL':
                # Sell amount is gross proceeds; fee/tax are usually negative cash flows.
                self._close_lots(key, abs(shares), amount, fee, tax, row, close_type='SELL')

            elif typ == 'WARRANT_EXERCISE':
                # Exercise removes derivative shares. TILG is the cash redemption.
                proceeds, tilg_tax = self._find_tilg_for_exercise(row, used_tilg_ids)
                self._close_lots(key, abs(shares), proceeds, 0.0, tilg_tax, row, close_type='KNOCKOUT')

            elif typ == 'FREE_DELIVERY':
                # Crypto transfer out; not a sale, but it closes the custody position at zero proceeds.
                self._close_lots(key, abs(shares), 0.0, fee, tax, row, close_type='TRANSFER')

            elif typ == 'CORRECTION':
                if shares > self.EPS:
                    # Tiny correction/inbound shares: zero-cost lot.
                    self._add_lot(key, shares, 0.0, row, source='CORRECTION')
                elif shares < -self.EPS:
                    self._close_lots(key, abs(shares), 0.0, fee, tax, row, close_type='CORRECTION')

            elif typ == 'STOCK_DIVIDEND' and shares > self.EPS:
                # Stock dividends add shares with zero cost basis.
                self._add_lot(key, shares, 0.0, row, source='STOCK_DIVIDEND')

        # Remaining FIFO lots are open positions. Aggregate by asset key so the
        # dashboard shows actual current positions, not one row per historical lot.
        for key, lots in self.lots_by_key.items():
            active_lots = [lot for lot in lots if lot['shares'] > 1e-8]
            if not active_lots:
                continue

            meta = self.meta_by_key.get(key, {})
            total_shares = sum(lot['shares'] for lot in active_lots)
            total_cost = sum(lot['total_cost'] for lot in active_lots)
            open_dates = [lot.get('open_date') for lot in active_lots if pd.notna(lot.get('open_date'))]
            sources = sorted(set(str(lot.get('source', 'BUY')) for lot in active_lots))

            self.open_positions.append(dict(
                name=meta.get('name') or key,
                symbol=meta.get('symbol') or key,
                asset_class=meta.get('asset_class', ''),
                shares=total_shares,
                avg_cost=total_cost / total_shares if total_shares else 0,
                total_cost=total_cost,
                first_buy=min(open_dates) if open_dates else pd.NaT,
                last_buy=max(open_dates) if open_dates else pd.NaT,
                num_lots=len(active_lots),
                lot_source=', '.join(sources),
            ))

        self.closed_positions.sort(key=lambda p: p['last_sell'] if pd.notna(p['last_sell']) else pd.Timestamp.min.tz_localize('UTC'))
        self.open_positions.sort(key=lambda p: p['total_cost'], reverse=True)

    def summary(self):
        cash = self.df[self.df['category'] == 'CASH']
        trading = self.df[self.df['category'] == 'TRADING']
        deposits = self.df[self.df['type'].isin(['CUSTOMER_INBOUND', 'TRANSFER_INBOUND'])]['amount'].sum()
        withdrawals = abs(self.df[self.df['type'].isin(['CUSTOMER_OUTBOUND_REQUEST', 'TRANSFER_OUTBOUND'])]['amount'].sum())
        dividends = self.df[self.df['type'] == 'DIVIDEND']['amount'].sum() + self.df[self.df['type'] == 'STOCK_DIVIDEND']['amount'].sum()
        interest = self.df[self.df['type'] == 'INTEREST_PAYMENT']['amount'].sum()
        total_fees = abs(trading['fee'].sum()) + abs(self.df[self.df['type'] == 'FEE']['fee'].sum())
        tilg_taxes = abs(self.df[(self.df['type'] == 'TILG')]['tax'].sum()) if 'tax' in self.df.columns else 0
        total_taxes = abs(trading['tax'].sum()) + tilg_taxes + abs(self.df[self.df['type'].isin(['DIVIDEND', 'INTEREST_PAYMENT'])]['tax'].sum())
        realized_pnl = sum(p['realized_pnl'] for p in self.closed_positions)
        net_pnl = sum(p['net_pnl'] for p in self.closed_positions)
        open_cost = sum(p['total_cost'] for p in self.open_positions)
        wins = sum(1 for p in self.closed_positions if p['net_pnl'] > 0)
        losses = len(self.closed_positions) - wins
        dmin = self.df['date'].min()
        dmax = self.df['date'].max()
        date_range = f"{dmin.strftime('%Y-%m-%d')} — {dmax.strftime('%Y-%m-%d')}" if pd.notna(dmin) and pd.notna(dmax) else "n/a"
        return dict(
            deposits=deposits, withdrawals=withdrawals, dividends=dividends,
            interest=interest, total_fees=total_fees, total_taxes=total_taxes,
            realized_pnl=realized_pnl, net_pnl=net_pnl, open_cost=open_cost,
            closed_count=len(self.closed_positions), open_count=len(self.open_positions),
            wins=wins, losses=losses, win_rate=wins / len(self.closed_positions) * 100 if self.closed_positions else 0,
            date_range=date_range,
            issues=len(self.data_quality_issues),
            unmatched=len(self.unmatched_closures),
        )

    def by_asset_class(self):
        out = {}
        for p in self.closed_positions:
            ac = p['asset_class'] or 'UNKNOWN'
            if ac not in out:
                out[ac] = dict(count=0, realized=0, fees=0, taxes=0, net=0, wins=0)
            out[ac]['count'] += 1
            out[ac]['realized'] += p['realized_pnl']
            out[ac]['fees'] += p['fees']
            out[ac]['taxes'] += p['taxes']
            out[ac]['net'] += p['net_pnl']
            if p['net_pnl'] > 0:
                out[ac]['wins'] += 1
        for ac in out:
            out[ac]['win_rate'] = out[ac]['wins'] / out[ac]['count'] * 100 if out[ac]['count'] else 0
        return out

    def diagnostics_df(self):
        rows = []
        for msg in self.data_quality_issues:
            rows.append(dict(kind='Issue', message=msg))
        for u in self.unmatched_closures:
            rows.append(dict(
                kind='Unmatched closure',
                message=f"{u.get('datetime')} · {u.get('symbol')} · missing {u.get('missing_shares'):.8f} shares · {u.get('close_type')}"
            ))
        return pd.DataFrame(rows)


# ═════════════════════════════════════════════════════════════════════
# BITGET UI COMPONENTS
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
        height=360, margin=dict(l=0, r=0, t=30, b=0), title=dict(text=title, font=dict(size=14, color='#9DA5AE')),
        xaxis=dict(gridcolor='#21262D', showgrid=False), yaxis=dict(gridcolor='#21262D', title='P&L'),
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
        xaxis=dict(gridcolor='#21262D', title='P&L'), yaxis=dict(gridcolor='#21262D'), font=dict(family='Albert Sans'))
    st.plotly_chart(fig, use_container_width=True)

def render_positions(trades, mf=None):
    data = [t for t in trades if not mf or t['market'] == mf]
    if not data: st.info("No positions."); return
    df = pd.DataFrame(data)
    c1, c2, c3, c4 = st.columns(4)
    with c1: sel_sym = st.selectbox("Symbol", ['All'] + sorted(df['symbol'].unique().tolist()), key=f"s_{mf}")
    with c2: sel_dir = st.selectbox("Direction", ['All', 'Long', 'Short'], key=f"d_{mf}")
    with c3: sel_res = st.selectbox("Result", ['All', 'Win', 'Loss', 'Liquidation'], key=f"r_{mf}")
    with c4:
        sort_map = {'Close date ↓': ('close_date', False), 'Close date ↑': ('close_date', True),
                    'P&L best ↓': ('net_pnl', False), 'P&L worst ↓': ('net_pnl', True), 'Holding longest ↓': ('holding_hours', False)}
        sel_sort = st.selectbox("Sort", list(sort_map.keys()), key=f"o_{mf}")
    if sel_sym != 'All': df = df[df['symbol'] == sel_sym]
    if sel_dir != 'All': df = df[df['direction'] == sel_dir]
    if sel_res == 'Win': df = df[(df['is_win']) & (~df['is_liquidation'])]
    elif sel_res == 'Loss': df = df[(~df['is_win']) & (~df['is_liquidation'])]
    elif sel_res == 'Liquidation': df = df[df['is_liquidation']]
    sc, asc = sort_map[sel_sort]; df = df.sort_values(sc, ascending=asc)
    if df.empty: st.info("No matches."); return
    journal = st.session_state.get('journal', {})
    disp = pd.DataFrame({
        'Opened': df['open_date'].dt.strftime('%Y-%m-%d %H:%M'), 'Closed': df['close_date'].dt.strftime('%Y-%m-%d %H:%M'),
        'Symbol': df['symbol'], 'Dir': df['direction'], 'Net P&L': df['net_pnl'].round(2), 'Funding': df['funding_fees'].round(4),
        'Result': df.apply(lambda r: '⚠️ LIQ' if r['is_liquidation'] else ('✅ Win' if r['is_win'] else '❌ Loss'), axis=1),
        'Holding': df['holding_hours'].apply(lambda h: f"{h:.1f}h" if h > 0 else '—'), 'Fills': df['num_closes'].astype(int),
        '📓': df['id'].apply(lambda x: '✏️' if x in journal else ''),
    })
    st.caption(f"{len(disp)} of {len(data)} positions")
    st.dataframe(disp, use_container_width=True, hide_index=True, height=min(600, 38 + len(disp)*35),
        column_config={'Net P&L': st.column_config.NumberColumn('Net P&L', format="%.2f"),
                       'Funding': st.column_config.NumberColumn('Funding', format="%.4f"),
                       'Fills': st.column_config.NumberColumn('Fills', format="%d"), '📓': st.column_config.TextColumn('📓', width='small')})
    st.download_button("📥 Download CSV", df.to_csv(index=False), "positions.csv", "text/csv", key=f"dl_{mf}")


# ═════════════════════════════════════════════════════════════════════
# TRADE REPUBLIC UI
# ═════════════════════════════════════════════════════════════════════

def render_tr_tab(tr: TradeRepublicAnalyzer):
    s = tr.summary()

    st.markdown('<div class="dash-header">📈 Trade Republic Overview</div>', unsafe_allow_html=True)
    st.caption(s['date_range'])

    # Key metrics
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1: st.metric("Deposits", f"{s['deposits']:,.0f} €")
    with c2: st.metric("Realized P&L", f"{s['realized_pnl']:+,.2f} €")
    with c3: st.metric("Net P&L (after fees & tax)", f"{s['net_pnl']:+,.2f} €")
    with c4: st.metric("Win Rate", f"{'🟢' if s['win_rate']>=50 else '🔴'} {s['win_rate']:.1f}%")
    with c5: st.metric("Closed / Open", f"{s['closed_count']} / {s['open_count']}")

    if s.get('issues', 0) or s.get('unmatched', 0):
        with st.expander(f"⚠️ Import diagnostics ({s.get('issues', 0)} issues / {s.get('unmatched', 0)} unmatched closures)"):
            diag = tr.diagnostics_df()
            if not diag.empty:
                st.dataframe(diag, use_container_width=True, hide_index=True)
            st.caption("These warnings usually indicate transfers, imported historical positions, one-sided split rows, or instruments that were closed before the uploaded CSV period started.")

    # Income
    with st.expander("💰 Cash Flow & Income"):
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1: st.metric("Dividends", f"{s['dividends']:,.2f} €")
        with c2: st.metric("Interest", f"{s['interest']:,.2f} €")
        with c3: st.metric("Trading Fees", f"-{s['total_fees']:,.2f} €")
        with c4: st.metric("Taxes Paid", f"-{s['total_taxes']:,.2f} €")
        with c5: st.metric("Open Positions Cost", f"{s['open_cost']:,.2f} €")

    # By asset class
    st.markdown('<div class="dash-header">📊 P&L by Asset Class</div>', unsafe_allow_html=True)
    ac_data = tr.by_asset_class()
    if ac_data:
        ac_names = {'STOCK': '🏢 Stocks', 'FUND': '📦 ETFs/Funds', 'DERIVATIVE': '📄 Derivatives', 'CRYPTO': '🪙 Crypto', 'SYNTHETIC': '🔀 Synthetic'}
        ac_df = pd.DataFrame([
            dict(Class=ac_names.get(k, k), Closed=v['count'], Wins=v['wins'],
                 WinRate=round(v['win_rate'], 1), Realized=round(v['realized'], 2),
                 Fees=round(v['fees'], 2), Taxes=round(v['taxes'], 2), Net=round(v['net'], 2))
            for k, v in ac_data.items()
        ]).sort_values('Net', ascending=False)
        st.dataframe(ac_df, use_container_width=True, hide_index=True,
            column_config={
                'WinRate': st.column_config.NumberColumn('Win %', format="%.1f%%"),
                'Realized': st.column_config.NumberColumn('Realized', format="%.2f"),
                'Fees': st.column_config.NumberColumn('Fees', format="%.2f"),
                'Taxes': st.column_config.NumberColumn('Taxes', format="%.2f"),
                'Net': st.column_config.NumberColumn('Net P&L', format="%.2f"),
            })

        # Bar chart
        colors = ['#00E5A0' if v['net'] >= 0 else '#F6465D' for v in ac_data.values()]
        fig = go.Figure(go.Bar(
            x=[ac_names.get(k, k) for k in ac_data.keys()],
            y=[v['net'] for v in ac_data.values()],
            marker_color=colors,
            text=[f"{v['net']:+,.0f}€" for v in ac_data.values()],
            textposition='outside',
        ))
        fig.update_layout(template='plotly_dark', paper_bgcolor='#0D1117', plot_bgcolor='#0D1117',
            height=300, margin=dict(l=0, r=0, t=30, b=0),
            title=dict(text='Net P&L by Asset Class', font=dict(size=14, color='#9DA5AE')),
            yaxis=dict(gridcolor='#21262D', title='P&L (EUR)'), font=dict(family='Albert Sans'))
        st.plotly_chart(fig, use_container_width=True)

    # Closed positions table
    st.markdown('<div class="dash-header">📋 Closed Positions</div>', unsafe_allow_html=True)
    if tr.closed_positions:
        cp_df = pd.DataFrame(tr.closed_positions)

        c1, c2, c3 = st.columns(3)
        with c1:
            ac_filter = st.selectbox("Asset Class", ['All'] + sorted(cp_df['asset_class'].unique().tolist()), key='tr_ac')
        with c2:
            tr_res = st.selectbox("Result", ['All', 'Win', 'Loss'], key='tr_res')
        with c3:
            tr_sort_map = {'P&L best ↓': ('realized_pnl', False), 'P&L worst ↓': ('realized_pnl', True),
                           'Last sell ↓': ('last_sell', False), 'Last sell ↑': ('last_sell', True)}
            tr_sort = st.selectbox("Sort", list(tr_sort_map.keys()), key='tr_sort')

        if ac_filter != 'All': cp_df = cp_df[cp_df['asset_class'] == ac_filter]
        if tr_res == 'Win': cp_df = cp_df[cp_df['realized_pnl'] > 0]
        elif tr_res == 'Loss': cp_df = cp_df[cp_df['realized_pnl'] <= 0]
        sc, asc = tr_sort_map[tr_sort]; cp_df = cp_df.sort_values(sc, ascending=asc)

        if not cp_df.empty:
            disp_cp = pd.DataFrame({
                'Buy Date': cp_df['first_buy'].dt.strftime('%Y-%m-%d'),
                'Sell Date': cp_df['last_sell'].dt.strftime('%Y-%m-%d'),
                'Name': cp_df['name'], 'Symbol': cp_df['symbol'], 'Class': cp_df['asset_class'],
                'Shares Sold': cp_df['shares_sold'].round(4),
                'Avg Buy': cp_df['avg_buy_price'].round(2), 'Avg Sell': cp_df['avg_sell_price'].round(2),
                'Realized P&L': cp_df['realized_pnl'].round(2), 'Fees': cp_df['fees'].round(2),
                'Taxes': cp_df['taxes'].round(2), 'Net P&L': cp_df['net_pnl'].round(2),
                'Result': cp_df['realized_pnl'].apply(lambda x: '✅' if x > 0 else '❌'),
                'How': cp_df.get('close_type', pd.Series(['SELL']*len(cp_df))).map(
                    {'SELL': '💰 Sold', 'KNOCKOUT': '💥 KO', 'TRANSFER': '📤 Transfer'}).fillna('💰 Sold'),
            })
            st.caption(f"{len(disp_cp)} closed positions")
            st.dataframe(disp_cp, use_container_width=True, hide_index=True,
                height=min(600, 38 + len(disp_cp)*35),
                column_config={
                    'Realized P&L': st.column_config.NumberColumn('Realized', format="%.2f"),
                    'Net P&L': st.column_config.NumberColumn('Net', format="%.2f"),
                    'Fees': st.column_config.NumberColumn('Fees', format="%.2f"),
                    'Taxes': st.column_config.NumberColumn('Tax', format="%.2f"),
                    'Avg Buy': st.column_config.NumberColumn('Avg Buy', format="%.2f"),
                    'Avg Sell': st.column_config.NumberColumn('Avg Sell', format="%.2f"),
                })
            st.download_button(
                "📥 Download closed TR positions CSV",
                cp_df.to_csv(index=False),
                "trade_republic_closed_positions_fifo.csv",
                "text/csv",
                key="tr_closed_download"
            )

    # Open positions
    if tr.open_positions:
        st.markdown('<div class="dash-header">📂 Open Positions</div>', unsafe_allow_html=True)
        op_df = pd.DataFrame(tr.open_positions).sort_values('total_cost', ascending=False)
        op_ac = st.selectbox(
            "Open Asset Class",
            ['All'] + sorted(op_df['asset_class'].fillna('UNKNOWN').unique().tolist()),
            key='tr_open_ac'
        )
        if op_ac != 'All':
            op_df = op_df[op_df['asset_class'] == op_ac]
        disp_op = pd.DataFrame({
            'First Buy': op_df['first_buy'].dt.strftime('%Y-%m-%d'),
            'Last Buy': op_df['last_buy'].dt.strftime('%Y-%m-%d') if 'last_buy' in op_df else op_df['first_buy'].dt.strftime('%Y-%m-%d'),
            'Name': op_df['name'], 'Symbol': op_df['symbol'], 'Class': op_df['asset_class'],
            'Shares': op_df['shares'].round(4), 'Avg Cost': op_df['avg_cost'].round(2),
            'Total Invested': op_df['total_cost'].round(2),
            'Lots': op_df['num_lots'].astype(int) if 'num_lots' in op_df else 1,
        })
        st.dataframe(disp_op, use_container_width=True, hide_index=True,
            column_config={
                'Avg Cost': st.column_config.NumberColumn('Avg Cost €', format="%.2f"),
                'Total Invested': st.column_config.NumberColumn('Invested €', format="%.2f"),
            })
        st.download_button(
            "📥 Download open TR positions CSV",
            op_df.to_csv(index=False),
            "trade_republic_open_positions_fifo.csv",
            "text/csv",
            key="tr_open_download"
        )

    # Dividend & interest timeline
    divs = tr.df[tr.df['type'] == 'DIVIDEND']
    interest = tr.df[tr.df['type'] == 'INTEREST_PAYMENT']
    if len(divs) + len(interest) > 0:
        st.markdown('<div class="dash-header">💵 Dividend & Interest Income</div>', unsafe_allow_html=True)
        income_data = []
        for _, r in divs.iterrows():
            income_data.append(dict(date=r['date'], type='Dividend', name=r['name'], amount=r['amount'], tax=r['tax']))
        for _, r in interest.iterrows():
            income_data.append(dict(date=r['date'], type='Interest', name='Cash', amount=r['amount'], tax=r['tax']))
        inc_df = pd.DataFrame(income_data).sort_values('date', ascending=False)
        inc_df['tax'] = inc_df['tax'].fillna(0)
        st.dataframe(pd.DataFrame({
            'Date': inc_df['date'].dt.strftime('%Y-%m-%d'), 'Type': inc_df['type'],
            'Name': inc_df['name'], 'Amount': inc_df['amount'].round(2), 'Tax': inc_df['tax'].round(2),
        }), use_container_width=True, hide_index=True,
            column_config={'Amount': st.column_config.NumberColumn('Amount €', format="%.2f"),
                           'Tax': st.column_config.NumberColumn('Tax €', format="%.2f")})


# ═════════════════════════════════════════════════════════════════════
# JOURNAL UI
# ═════════════════════════════════════════════════════════════════════

def render_journal_tab(trades):
    journal = st.session_state.journal
    st.markdown('<div class="dash-header">📓 Trading Journal</div>', unsafe_allow_html=True)
    j1, j2 = st.columns([3, 1])
    with j1: st.caption(f"{len(journal)} entries")
    with j2:
        j_file = st.file_uploader("Import JSON", type=['json'], key="j_imp", label_visibility="collapsed")
        if j_file:
            try: n = JournalManager.import_json(j_file.getvalue().decode('utf-8')); st.success(f"Imported {n}"); st.rerun()
            except Exception as e: st.error(str(e))
    st.markdown("---")
    opts = []
    for t in sorted(trades, key=lambda x: x['close_date'], reverse=True):
        pnl = f"+{t['net_pnl']:.2f}" if t['net_pnl'] >= 0 else f"{t['net_pnl']:.2f}"
        has = '✏️ ' if t['id'] in journal else ''
        opts.append((f"{has}{t['close_date'].strftime('%Y-%m-%d %H:%M')} | {t['symbol']} {t['direction']} | {pnl}", t))
    if not opts: st.info("No trades."); return
    sel = st.selectbox("Select trade", [o[0] for o in opts], key="j_sel")
    trade = next(o[1] for o in opts if o[0] == sel)
    tid = trade['id']; existing = JournalManager.get(tid)
    pc = '#00E5A0' if trade['net_pnl'] >= 0 else '#F6465D'
    res = '⚠️ Liquidation' if trade['is_liquidation'] else ('✅ Win' if trade['is_win'] else '❌ Loss')
    st.markdown(f"""<div class="journal-card"><div style="display:grid;grid-template-columns:repeat(5,1fr);gap:12px;font-size:14px;">
        <div><span style="color:#9DA5AE;">Symbol</span><br><b>{trade['symbol']}</b></div>
        <div><span style="color:#9DA5AE;">Direction</span><br><b>{trade['direction']}</b></div>
        <div><span style="color:#9DA5AE;">Net P&L</span><br><b style="color:{pc};">{'+' if trade['net_pnl']>=0 else ''}{trade['net_pnl']:,.2f}</b></div>
        <div><span style="color:#9DA5AE;">Holding</span><br><b>{trade['holding_hours']:.1f}h</b></div>
        <div><span style="color:#9DA5AE;">Result</span><br><b>{res}</b></div></div></div>""", unsafe_allow_html=True)
    with st.form(key=f"jf_{tid}"):
        c1, c2, c3 = st.columns(3)
        with c1: strategy = st.selectbox("Strategy", STRATEGIES, index=STRATEGIES.index(existing.get('strategy', '')) if existing.get('strategy', '') in STRATEGIES else 0)
        with c2: emotion = st.selectbox("Emotion", EMOTIONS, index=EMOTIONS.index(existing.get('emotion', '')) if existing.get('emotion', '') in EMOTIONS else 0)
        with c3: confidence = st.slider("Confidence", 1, 5, existing.get('confidence', 3))
        c4, c5 = st.columns(2)
        with c4: timeframe = st.selectbox("Timeframe", TIMEFRAMES, index=TIMEFRAMES.index(existing.get('timeframe', '')) if existing.get('timeframe', '') in TIMEFRAMES else 0)
        with c5: rating = st.slider("Execution Rating", 1, 5, existing.get('rating', 3))
        mistakes = st.multiselect("Mistakes", MISTAKES, default=existing.get('mistakes', []))
        setup = st.text_area("Setup & Entry Reason", value=existing.get('setup_notes', ''), height=80)
        exit_n = st.text_area("Exit Notes", value=existing.get('exit_notes', ''), height=80)
        lessons = st.text_area("Lessons Learned", value=existing.get('lessons', ''), height=80)
        b1, b2 = st.columns([4, 1])
        with b1: submitted = st.form_submit_button("💾 Save", use_container_width=True)
        with b2: delete = st.form_submit_button("🗑️ Delete", use_container_width=True)
    if submitted:
        JournalManager.save(tid, dict(strategy=strategy, emotion=emotion, confidence=confidence, timeframe=timeframe,
            rating=rating, mistakes=mistakes, setup_notes=setup, exit_notes=exit_n, lessons=lessons,
            symbol=trade['symbol'], direction=trade['direction'], net_pnl=trade['net_pnl'],
            close_date=str(trade['close_date']), saved_at=str(datetime.now())))
        st.success("Saved!"); st.rerun()
    if delete: JournalManager.delete(tid); st.info("Deleted."); st.rerun()

    # Recent entries
    if journal:
        st.markdown('<div class="dash-header">📝 Recent Entries</div>', unsafe_allow_html=True)
        for t in sorted(trades, key=lambda x: x['close_date'], reverse=True):
            if t['id'] not in journal: continue
            e = journal[t['id']]; pc = '#00E5A0' if t['net_pnl'] >= 0 else '#F6465D'
            tags = ''
            if e.get('strategy'): tags += f'<span class="tag-pill tag-strategy">{e["strategy"]}</span>'
            if e.get('emotion'): tags += f'<span class="tag-pill tag-emotion">{e["emotion"]}</span>'
            for m in e.get('mistakes', []): tags += f'<span class="tag-pill tag-mistake">{m}</span>'
            notes = '<br>'.join(filter(None, [
                f"<b>Setup:</b> {e['setup_notes']}" if e.get('setup_notes') else '',
                f"<b>Exit:</b> {e['exit_notes']}" if e.get('exit_notes') else '',
                f"<b>Lessons:</b> {e['lessons']}" if e.get('lessons') else '',
            ]))
            st.markdown(f"""<div class="journal-card"><div class="trade-info">{t['close_date'].strftime('%Y-%m-%d %H:%M')} · {t['symbol']} · {t['direction']} ·
                <span style="color:{pc};font-weight:600;">{'+' if t['net_pnl']>=0 else ''}{t['net_pnl']:,.2f}</span>
                · ⭐{'⭐'*(e.get('confidence',1)-1)} · Exec: {'⭐'*e.get('rating',1)}</div>
                <div style="margin:6px 0;">{tags}</div><div class="journal-notes">{notes}</div></div>""", unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════════

def main():
    JournalManager.init()
    st.markdown("""<div style="display:flex;align-items:center;gap:12px;margin-bottom:4px;">
        <span style="font-size:28px;">📊</span>
        <span style="font-size:26px;font-weight:700;color:#E6EDF3;">Trading Dashboard</span></div>
    <p style="color:#9DA5AE;margin-top:0;font-size:14px;">Bitget Futures · Trade Republic · Trading Journal</p>""", unsafe_allow_html=True)

    with st.sidebar:
        st.markdown("### 📁 Bitget Data")
        bitget_files = st.file_uploader("Bitget CSV Exports", type=['csv'], accept_multiple_files=True, key='bitget_up',
            help="USDT-M, USDC-M, or legacy exports")
        st.markdown("### 🏦 Trade Republic Data")
        tr_file = st.file_uploader("Trade Republic CSV Export", type=['csv'], key='tr_up',
            help="Transaktionsexport.csv from Trade Republic")
        st.markdown("---")
        st.markdown("### 📓 Journal")
        j_count = JournalManager.count()
        st.caption(f"{j_count} entries")
        if j_count > 0:
            st.download_button("📥 Export Journal", JournalManager.export_json(), "journal.json", "application/json", key="sj_exp")
        j_imp = st.file_uploader("Import Journal", type=['json'], key="sj_imp")
        if j_imp:
            try: JournalManager.import_json(j_imp.getvalue().decode('utf-8')); st.rerun()
            except: pass

    has_bitget = bitget_files and len(bitget_files) > 0
    has_tr = tr_file is not None

    if not has_bitget and not has_tr:
        st.markdown("""<div style="text-align:center;padding:80px 20px;color:#9DA5AE;">
            <p style="font-size:48px;margin-bottom:16px;">📁</p>
            <p style="font-size:18px;color:#D0D7DE;">Upload your trading data to get started</p>
            <p style="font-size:14px;margin-top:8px;">Bitget USDT-M · USDC-M · Legacy · Trade Republic</p></div>""", unsafe_allow_html=True)
        return

    az = None
    tr_analyzer = None

    # Load Bitget
    if has_bitget:
        try:
            dfs = []
            for f in bitget_files:
                df = BitgetAnalyzer.load_csv(f)
                if not df.empty: dfs.append(df)
            if dfs:
                combined = BitgetAnalyzer.merge_dataframes(dfs)
                az = BitgetAnalyzer(combined)
                if not az.trades: az = None
        except Exception as e:
            st.error(f"Bitget error: {e}")

    # Load Trade Republic
    if has_tr:
        try:
            tr_analyzer = TradeRepublicAnalyzer(TradeRepublicAnalyzer.load_csv(tr_file))
        except Exception as e:
            st.error(f"Trade Republic error: {e}")

    # Build tabs
    tab_labels = []
    if az:
        markets = sorted(set(t['market'] for t in az.trades))
        has_multi = len(markets) > 1
        if has_multi:
            # Account comparison header
            st.markdown('<div class="dash-header">⚖️ Bitget Account Comparison</div>', unsafe_allow_html=True)
            cols = st.columns(len(markets))
            for i, m in enumerate(markets):
                s = az.stats(m)
                if not s: continue
                cur = 'USDC' if 'USDC' in m else 'USDT'
                pc = '#00E5A0' if s['total_pnl'] >= 0 else '#F6465D'
                with cols[i]:
                    st.markdown(f"""<div class="account-card"><h3 style="color:#9DA5AE;">{m}</h3>
                        <div class="big-pnl" style="color:{pc};">{'+' if s['total_pnl']>=0 else ''}{s['total_pnl']:,.2f} {cur}</div>
                        <div style="margin-top:16px;display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:14px;color:#D0D7DE;">
                        <div><span style="color:#9DA5AE;">Positions</span><br><b>{s['trades']}</b></div>
                        <div><span style="color:#9DA5AE;">Win Rate</span><br><b>{s['win_rate']:.1f}%</b></div>
                        <div><span style="color:#9DA5AE;">Profit Factor</span><br><b>{s['profit_factor']:.2f}</b></div>
                        <div><span style="color:#9DA5AE;">Liquidations</span><br><b style="color:#F6465D;">{s['liqs']}</b></div></div></div>""", unsafe_allow_html=True)
            tab_labels = markets + ['Combined']
        else:
            tab_labels = markets
        tab_labels.append('📓 Journal')
    if tr_analyzer:
        tab_labels.append('🏦 Trade Republic')

    if not tab_labels:
        st.warning("No valid data found."); return

    tabs = st.tabs(tab_labels)
    tab_idx = 0

    # Bitget tabs
    if az:
        markets = sorted(set(t['market'] for t in az.trades))
        has_multi = len(markets) > 1
        bitget_labels = (markets + ['Combined']) if has_multi else markets
        for label in bitget_labels:
            with tabs[tab_idx]:
                mf = None if label == 'Combined' else label
                s = az.stats(mf)
                if not s: st.info("No data."); tab_idx += 1; continue
                cur = 'USDC' if mf and 'USDC' in mf else ('USDT' if mf and 'USDT' in mf else '$')
                render_metrics(s, cur)
                render_chart(az.cumulative(mf), f"Cumulative P&L ({label})")
                with st.expander("📐 Detailed Stats & Fee Breakdown"):
                    c1, c2, c3, c4 = st.columns(4)
                    with c1: st.metric("Avg Win", f"{s['avg_win']:,.2f}"); st.metric("Trading Fees", f"{s['trading_fees']:,.2f}")
                    with c2: st.metric("Avg Loss", f"{s['avg_loss']:,.2f}"); st.metric("Funding Fees", f"{s['funding_fees']:,.2f}")
                    with c3: st.metric("Sharpe Ratio", f"{s['sharpe']:.2f}"); st.metric("Max Drawdown", f"{s['max_drawdown']:,.2f}")
                    with c4: st.metric("Expectancy", f"{s['expectancy']:,.2f}"); st.metric("Avg Holding", f"{s['avg_holding']:.1f}h")
                    st.markdown(f"**Best:** {s['best']['symbol']} → **+{s['best']['net_pnl']:,.2f}** | **Worst:** {s['worst']['symbol']} → **{s['worst']['net_pnl']:,.2f}**")
                st.markdown('<div class="dash-header">📊 Performance by Symbol</div>', unsafe_allow_html=True)
                sym = az.symbol_breakdown(mf)
                if sym:
                    sdf = pd.DataFrame([dict(Symbol=k, Positions=v['trades'], Wins=v['wins'], WinRate=round(v['win_rate'],1),
                        PnL=round(v['pnl'],2), Funding=round(v['funding'],2), Liqs=v['liqs']) for k, v in sym.items()]).sort_values('PnL', ascending=False)
                    st.dataframe(sdf, use_container_width=True, hide_index=True,
                        column_config={'WinRate': st.column_config.NumberColumn('Win %', format="%.1f%%"),
                                       'PnL': st.column_config.NumberColumn('P&L', format="%.2f"),
                                       'Funding': st.column_config.NumberColumn('Funding', format="%.2f")})
                    render_bars(sym, f"P&L by Symbol ({label})")
                st.markdown('<div class="dash-header">📋 All Positions</div>', unsafe_allow_html=True)
                render_positions(az.trades, mf)
            tab_idx += 1

        # Journal tab
        with tabs[tab_idx]:
            render_journal_tab(az.trades)
        tab_idx += 1

    # Trade Republic tab
    if tr_analyzer:
        with tabs[tab_idx]:
            render_tr_tab(tr_analyzer)


if __name__ == "__main__":
    main()

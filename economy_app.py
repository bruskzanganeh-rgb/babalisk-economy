#!/usr/bin/env python3
"""
BRUSK EKONOMI — Personal Finance Dashboard
============================================
Complete economy tracker: net worth, Turkish stocks + screener,
budget, loans, crypto, instruments — all live.

Usage:
    pip install flask yfinance pandas
    python economy_app.py

Then open http://localhost:5001
"""

import json, os, time, threading, functools
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, render_template_string, jsonify, request, Response
import yfinance as yf
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

app = Flask(__name__)

# ══════════════════════════════════════════════════════════════
# AUTH — Set APP_PASSWORD env var to enable (optional locally)
# ══════════════════════════════════════════════════════════════
APP_PASSWORD = os.environ.get('APP_PASSWORD', '')  # empty = no auth (local dev)

def check_auth(password):
    return password == APP_PASSWORD

def auth_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not APP_PASSWORD:
            return f(*args, **kwargs)  # no password set = skip auth
        auth = request.authorization
        if not auth or not check_auth(auth.password):
            return Response('Logga in', 401, {'WWW-Authenticate': 'Basic realm="Brusk Ekonomi"'})
        return f(*args, **kwargs)
    return decorated

# ══════════════════════════════════════════════════════════════
# CONFIG — Edit my_economy.json to customize
# ══════════════════════════════════════════════════════════════
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'my_economy.json')
CACHE_DURATION = 900  # 15 min

# Default screener tickers — loaded from config, these are fallbacks
DEFAULT_BIST_SCREENER = [
    # ── BIST 30 (Blue Chips) ──
    "THYAO","GARAN","AKBNK","EREGL","FROTO","TUPRS","ASELS","BIMAS","ENKAI",
    "SAHOL","KCHOL","TCELL","PGSUS","SISE","TOASO","ARCLK","CCOLA","TTKOM",
    "YKBNK","HALKB","VAKBN","PETKM","ISCTR","SASA","TAVHL","EKGYO",
    "TKFEN","GUBRF","KRDMD",
    # ── BIST 50 (utöver BIST 30) ──
    "AEFES","MGROS","VESTL","OTKAR","DOAS","HEKTS","BRSAN","SOKM",
    "ULKER","TABGD","TTRAK","GOLTS","BTCIM","CIMSA","AKSA","ENJSA","DOHOL",
    "AGESA","ANSGR",
    # ── BIST 100 (utöver BIST 50) ──
    "RYGYO","RYSAS","GMTAS","TRGYO","MPARK","ASTOR","AGHOL","EUPWR","AKSEN",
    "TURSG","KONTR","KARSN","CANTE","GESAN","OYAKC","BERA","BUCIM","KLMSN",
    "EGEEN","MAVI","ALARK","LOGO","ASUZU","GLYHO","TKNSA","ISGYO","GOZDE",
    "TMSN","ALBRK","TSKB","INDES","GEDZA","KORDS","YATAS","NTHOL",
    "PRKME","ACSEL","KUYAS","OSMEN","MAGEN","TUKAS","KARTN","PENGD",
    "MIATK","AYEN","ISMEN","ADEL","OBAMS","PAPIL","PSDTC","RGYAS",
    # ── Populära utanför BIST 100 ──
    "ODAS","BIOEN","CEMAS","FENER","GSRAY","BJKAS","TBORG","DGATE","INTEM",
    "CLEBI","PKENT","RAYSG","VAKKO","SELEC","MEGAP","FORTE","FONET",
    "ARDYZ","ETILR","KENT","BFREN","DOCO","PENTA",
]

DEFAULT_SE_SCREENER = [
    # ── Large Cap (~100 bolag) ──
    "VOLV-B","ERIC-B","ATCO-A","ATCO-B","HM-B","INVE-B","SEB-A","SHB-A","SWED-A",
    "SAND","ASSA-B","ALFA","ABB","ESSITY-B","HEXA-B","NIBE-B","TELIA","SKF-B",
    "ELUX-B","GETI-B","EVO","KINV-B","LUND-B","SCA-B","SWEC-B","SAAB-B","BOL",
    "SINCH","SOBI","AZN","SSAB-A","SSAB-B","SECU-B","EMBRAC-B","BILL","HTRO",
    "AAK","AXFO","BALD-B","BILI-A","COOR","DOM","DUST","EKTA-B",
    "ELAN-B","HUFV-A","INTRUM","LATO-B","LOOMIS",
    "MTRS","NDA-SE","NOLA-B","PEAB-B","SAGA-B","SECT-B","STE-R",
    "TEL2-B","TIETOS","TREL-B","WALL-B","WIHL",
    # ── Mid Cap (~100 bolag) ──
    "BRAV","BUFAB","BULTEN","CLAS-B","CAST","CATE","DIOS",
    "FABG","HMS","HPOL-B","HUSQ-B","LAGR-B","LIFCO-B","THULE","TROAX",
    "BONAV-B","CINT","ELTEL","ENEA","FPAR-A",
    "G5EN","GENO","HANZA","INWI","ITAB","JM",
    "LIME","LUMI","MCOV-B","MIPS","MOMENT","NMAN",
    "NORB-B","NTEK-B","OEM-B","ORES","PNDX-B","PREV-B","PRIC-B",
    "RATO-B","SAVE","SEZI","SFAB","SOLT","STOR-B",
    "SUS","SVED-B","SYSR","TOBII","VIT-B","VNV","VOLCAR-B",
    # ── Small Cap (~100 bolag) ──
    "ACRI-B","AMBEA","ANOD-B","ARION-SDB","ARP","BEIA-B","BERG-B","BIOG-B",
    "BOOZT","BURE","CIBUS","CTT","DUNI","EGTX",
    "ENRO","FOUT","GIGSEK","GRNG","HLDX",
    "IMMNOV","ISR","KABE-B","KNOW","LAIR","LEO",
    "MEAB-B","MIDW-A","MILDEF","NAXS","NETI-B",
    "NP3","OX2","PLAZ-B","QLRO","QLINEA",
    "RROS","SANION","SBB-B","SBB-D","SDIP-PREF","SHOT","SIVE",
    "SYNT","TIGO-SDB","TRAD","TRUE-B","VESTUM","VIMIAN",
    "VITR","VPLAY-B","XANO-B","XBRANE",
]

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.economy_cache.json')

_cache = {'last_fetch': 0, 'prices': {}, 'fundamentals': {}, 'screener': [],
          'se_screener': [],
          'fx': {}, 'index': None, 'index_ch': None, 'crypto': {}}
_lock = threading.Lock()
_refreshing = False  # True while background refresh is running


def _save_cache_to_disk():
    """Persist cache to JSON file for instant startup."""
    try:
        with _lock:
            data = {k: v for k, v in _cache.items()}
        with open(CACHE_FILE, 'w') as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception as e:
        print(f"  [cache] Could not save: {e}")


def _load_cache_from_disk():
    """Load previously saved cache from disk."""
    global _cache
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE) as f:
                data = json.load(f)
            with _lock:
                _cache.update(data)
            age = time.time() - _cache.get('last_fetch', 0)
            print(f"  [cache] Loaded from disk (age: {age/60:.0f} min)")
            return True
    except Exception as e:
        print(f"  [cache] Could not load: {e}")
    return False


def load_config():
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except:
        return get_default_config()

def save_config(cfg):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

def _make_snapshot(d, today):
    """Build a snapshot dict with per-asset breakdown + individual items."""
    cfg = d.get('config', {})
    # Individual items dict: key -> SEK value
    items = {}
    # Bank accounts
    for b in cfg.get('bank_accounts', []):
        items['bank:' + b['name']] = round(b['sek'])
    # Stocks (SEK value)
    for row in d.get('stock_rows', []):
        items['stock:' + row['ticker']] = round(row.get('value_sek', 0))
    # Real estate
    for r in cfg.get('real_estate', []):
        items['re:' + r['name']] = round(r.get('value_sek', 0))
    # Crypto
    for c in d.get('crypto_rows', []):
        items['crypto:' + c['name']] = round(c.get('value_sek', 0))
    # Loans
    for l in cfg.get('loans', []):
        items['loan:' + l['name']] = round(-l['amount'])
    # Credits
    for c in cfg.get('credits', []):
        items['credit:' + c['name']] = round(-c['amount'])

    return {
        'date': today,
        'assets': round(d['total_assets']),
        'debts': round(d['total_debts']),
        'stocks_sek': round(d.get('stocks_sek', 0)),
        're_total': round(d.get('re_total', 0)),
        'bank_total': round(d.get('bank_total', 0)),
        'crypto_sek': round(d.get('crypto_sek', 0)),
        'gold_sek': round(d.get('gold_sek', 0)),
        'cash_sek': round(d.get('cash_sek', 0)),
        'items': items,
    }

def auto_snapshot():
    """Add monthly snapshot if last one is >25 days old."""
    cfg = load_config()
    history = cfg.get('networth_history', [])
    today = datetime.now().strftime('%Y-%m-%d')
    if history:
        last_date = history[-1].get('date', '')
        try:
            days_since = (datetime.now() - datetime.strptime(last_date, '%Y-%m-%d')).days
            if days_since < 25:
                return  # too recent
        except:
            pass
    refresh_data()
    d = compute_networth()
    history.append(_make_snapshot(d, today))
    cfg['networth_history'] = history
    save_config(cfg)


def get_default_config():
    return {
        "monthly_dca_try": 25000,
        "stocks": {
            "ARASE": {"shares":194,"cost":10507},
            "ANSGR": {"shares":1804,"cost":33771},
            "TUPRS": {"shares":282,"cost":39644},
            "AGESA": {"shares":465,"cost":19911},
            "DOAS": {"shares":373,"cost":73306},
            "TTRAK": {"shares":146,"cost":103488},
            "GOLTS": {"shares":272,"cost":98502},
            "TAVHL": {"shares":2405,"cost":530062},
            "CCOLA": {"shares":13407,"cost":660965},
            "AEFES": {"shares":5613,"cost":1063720},
            "RYSAS": {"shares":61073,"cost":776849},
            "RYGYO": {"shares":89659,"cost":1251640},
        },
        "real_estate": [
            {"name":"A-Plus 2+1 25e/mån","value_sek":531500,"rent_monthly":26000,"currency":"TRY"},
            {"name":"Ymsenvågen 8","value_sek":4540000},
        ],
        "bank_accounts": [
            {"name":"Montrose","sek":81000},
            {"name":"Avanza","sek":854000},
            {"name":"BABALISK AB","sek":134151},
            {"name":"Nordnet","sek":18300},
        ],
        "crypto": [
            {"name":"Bitcoin","symbol":"BTC-USD","amount":0.049},
            {"name":"Ethereum","symbol":"ETH-USD","amount":0.008},
        ],
        "cash": [
            {"name":"Ziraat Cash","try":44000},
        ],
        "gold": [
            {"name":"Gold Fysisk 7 gr","grams":7},
        ],
        "instruments": [
            {"name":"Gustav Prager","sek":8000},
            {"name":"A E Prager","sek":12000},
            {"name":"Emile Augusta Ouchard","usd":27000},
            {"name":"P Westerlund","sek":160000},
            {"name":"Pfretzschner Ellen","sek":15000},
            {"name":"China Viola","sek":5000},
            {"name":"Marc Laberte Bow","sek":20000},
            {"name":"Saz","sek":5000},
            {"name":"Longines","sek":20000},
            {"name":"Sonotronics Apollo","sek":15000},
            {"name":"Golf","sek":40000},
        ],
        "loans": [
            {"name":"Bostadslån 1","amount":1115201,"rate":0.027,"property":"Ymsenvågen 8"},
            {"name":"Bostadslån 2","amount":1046092,"rate":0.0133,"property":"Ymsenvågen 8"},
            {"name":"Bostadslån 3","amount":446071,"rate":0.0225,"property":"Ymsenvågen 8"},
            {"name":"Bostadslån 4","amount":330458,"rate":0.0412,"property":"Ymsenvågen 8"},
        ],
        "credits": [
            {"name":"Privatlån 7.45%","amount":48212,"rate":0.0745},
            {"name":"CSN Lån","amount":186751,"rate":0.006},
        ],
        "budget": {
            "income": [
                {"name":"Lön eft. skatt","sek":20000},
                {"name":"Hyra ut","sek":8000},
            ],
            "expenses": [
                {"name":"Bostadsavgift","sek":2948},
                {"name":"Amortering","sek":5160},
                {"name":"Räntekostnader","sek":5639},
                {"name":"Avanza","sek":15000},
                {"name":"Mat","sek":7000},
                {"name":"Unionens Akassa","sek":170},
                {"name":"Facket","sek":350},
                {"name":"Bensin","sek":1500},
                {"name":"Bilförsäkring","sek":500},
                {"name":"Parkering","sek":500},
                {"name":"Hemförsäkring","sek":170},
                {"name":"SL kort","sek":1070},
                {"name":"CSN","sek":1100},
                {"name":"Nöjen","sek":3000},
            ],
        },
        "networth_history": [
            {"date":"2021-04-01","assets":5784000,"debts":3541000},
            {"date":"2022-01-01","assets":5633846,"debts":3524767},
            {"date":"2022-07-01","assets":6494301,"debts":3360158},
            {"date":"2023-01-01","assets":6099010,"debts":3318851},
            {"date":"2023-07-01","assets":5813089,"debts":3247949},
            {"date":"2024-01-01","assets":6269932,"debts":3271815},
            {"date":"2024-07-01","assets":7008208,"debts":3200000},
            {"date":"2025-01-01","assets":7623704,"debts":3128705},
            {"date":"2025-07-01","assets":5860913,"debts":3100000},
            {"date":"2026-01-01","assets":7623704,"debts":3050000},
        ],
    }


def fetch_price(symbol):
    for attempt in range(2):
        try:
            t = yf.Ticker(symbol)
            h = t.history(period='5d')
            if h is not None and not h.empty:
                p = h['Close'].iloc[-1]
                prev = h['Close'].iloc[-2] if len(h) >= 2 else p
                return float(p), float((p/prev - 1)) if prev > 0 else 0
        except Exception as e:
            if attempt == 0:
                time.sleep(0.5)
                continue
    return None, None


def _safe_float(v):
    """Convert value to float, return None if not a valid number."""
    if v is None: return None
    try:
        f = float(v)
        if np.isnan(f) or np.isinf(f): return None
        return f
    except (ValueError, TypeError):
        return None

def fetch_fundamentals(ticker_yf):
    for attempt in range(2):
        try:
            t = yf.Ticker(ticker_yf)
            info = t.info or {}
            if not info or info.get('regularMarketPrice') is None:
                if attempt == 0:
                    time.sleep(0.5)
                    continue
                return None
            inc = t.income_stmt
            bs = t.balance_sheet
            mc = _safe_float(info.get('marketCap', 0)) or 0
            pe = _safe_float(info.get('trailingPE'))
            name = info.get('shortName', ticker_yf.replace('.IS','').replace('.ST',''))
            ebit, revenue, gp, ni, td, te, ta, cash = [None]*8
            if inc is not None and not inc.empty:
                c = inc.columns[0]
                ebit = _safe_float(inc.loc['EBIT',c]) if 'EBIT' in inc.index else None
                revenue = _safe_float(inc.loc['Total Revenue',c]) if 'Total Revenue' in inc.index else None
                gp = _safe_float(inc.loc['Gross Profit',c]) if 'Gross Profit' in inc.index else None
                ni = _safe_float(inc.loc['Net Income',c]) if 'Net Income' in inc.index else None
            if bs is not None and not bs.empty:
                c = bs.columns[0]
                td = _safe_float(bs.loc['Total Debt',c]) if 'Total Debt' in bs.index else None
                te = _safe_float(bs.loc['Stockholders Equity',c]) if 'Stockholders Equity' in bs.index else None
                ta = _safe_float(bs.loc['Total Assets',c]) if 'Total Assets' in bs.index else None
                cash = _safe_float(bs.loc['Cash And Cash Equivalents',c]) if 'Cash And Cash Equivalents' in bs.index else None
            ev = mc + (td or 0) - (cash or 0)
            sector = info.get('sector', 'Other')
            return {'name':name,'pe':pe,'mc':mc,'ebit':ebit,'revenue':revenue,'gp':gp,'ni':ni,
                    'td':td,'te':te,'ta':ta,'cash':cash, 'sector': sector,
                    'ev_ebit': _safe_float(ev/ebit) if ebit and ebit > 0 else None,
                    'roic': _safe_float(ebit/(ta-(cash or 0))) if ebit and ta and (ta-(cash or 0))>0 else None,
                    'de': _safe_float(td/te) if td and te and te > 0 else None,
                    'gm': _safe_float(gp/revenue) if gp and revenue and revenue > 0 else None,
                    'ey': _safe_float(ebit/ev) if ebit and ev and ev > 0 else None}
        except Exception:
            if attempt == 0:
                time.sleep(0.5)
                continue
    return None


def compute_score(fund):
    if not fund: return 0, 0
    f = 0
    if fund.get('ni') and fund['ni']>0: f+=1
    if fund.get('roic') and fund['roic']>0: f+=1
    if fund.get('gm') and fund['gm']>0.15: f+=1
    if fund.get('de') is not None and fund['de']<1: f+=1
    if fund.get('ey') and fund['ey']>0.05: f+=1
    if fund.get('revenue') and fund['revenue']>0: f+=1
    if fund.get('ebit') and fund['ebit']>0: f+=1
    if fund.get('gm') and fund['gm']>0.25: f+=1
    if fund.get('roic') and fund['roic']>0.10: f+=1
    f = min(f, 9)
    infl = 0
    if fund.get('roic') and fund['roic']>0.05: infl+=25
    if fund.get('gm') and fund['gm']>0.15: infl+=25
    if fund.get('de') is not None and fund['de']<1: infl+=25
    if fund.get('ey') and fund['ey']>0.05: infl+=25
    mf = 0
    if fund.get('ev_ebit') and fund['ev_ebit']>0 and fund.get('roic') and fund['roic']>0:
        mf = (max(0,100-fund['ev_ebit']*3) + min(100,fund['roic']*500))/2
    comp = mf*0.4 + (f/9*100)*0.3 + infl*0.3
    return comp, f


def refresh_data():
    now = time.time()
    with _lock:
        if now - _cache['last_fetch'] < CACHE_DURATION:
            return
    cfg = load_config()
    bist_screener_tickers = cfg.get('bist_screener_tickers', DEFAULT_BIST_SCREENER)
    se_screener_tickers = cfg.get('se_screener_tickers', DEFAULT_SE_SCREENER)
    all_tickers = set(cfg.get('stocks',{}).keys())
    all_tickers.update(bist_screener_tickers)

    prices = {}
    funds = {}

    # Parallel fetch: prices + fundamentals for all BIST tickers
    def _fetch_one(tk, suffix='.IS'):
        sym = tk + suffix if not tk.endswith(suffix) else tk
        p, ch = fetch_price(sym)
        fu = fetch_fundamentals(sym)
        if fu and fu.get('name'):
            fu['name'] = fu['name'].replace('.IS','').replace('.ST','')
        return tk, p, ch, fu

    print(f"  Fetching {len(all_tickers)} BIST tickers...")
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(_fetch_one, tk, '.IS'): tk for tk in all_tickers}
        for f in as_completed(futures):
            try:
                tk = futures[f]
                _, p, ch, fu = f.result()
                if p: prices[tk] = {'price':p,'change':ch}
                if fu: funds[tk] = fu
            except:
                pass
    print(f"  BIST: {len(funds)}/{len(all_tickers)} fundamentals, {len(prices)} prices")

    time.sleep(1)  # brief pause before SE fetch to avoid rate-limiting

    print(f"  Fetching {len(se_screener_tickers)} SE tickers...")
    se_funds = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_fetch_one, tk, '.ST'): tk for tk in se_screener_tickers}
        for f in as_completed(futures):
            try:
                tk = futures[f]
                _, p, ch, fu = f.result()
                if fu: se_funds[tk] = fu
            except:
                pass
    print(f"  SE: {len(se_funds)}/{len(se_screener_tickers)} fundamentals")

    # FX + Gold + Index — also parallel
    fx = {}
    fx_results = {}
    def _fetch_fx(name, sym):
        p, ch = fetch_price(sym)
        return name, p, ch

    fx_jobs = [('USDSEK','SEK=X'),('EURSEK','EURSEK=X'),('USDTRY','TRY=X'),('GOLD','GC=F'),('INDEX','XU100.IS')]
    crypto_syms = [(c['symbol'], c['symbol']) for c in cfg.get('crypto', [])]
    fx_jobs += crypto_syms

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_fetch_fx, name, sym): name for name, sym in fx_jobs}
        for f in as_completed(futures):
            try:
                name, p, ch = f.result()
                fx_results[name] = (p, ch)
            except:
                pass

    if fx_results.get('USDSEK') and fx_results['USDSEK'][0]:
        fx['USDSEK'] = fx_results['USDSEK'][0]
    if fx_results.get('EURSEK') and fx_results['EURSEK'][0]:
        fx['EURSEK'] = fx_results['EURSEK'][0]
    usd_try = fx_results.get('USDTRY', (None,None))[0]
    usd_sek = fx.get('USDSEK')
    if usd_try and usd_sek:
        fx['TRYSEK'] = usd_sek / usd_try
    elif usd_sek:
        fx['TRYSEK'] = usd_sek / 38.0

    gold_usd = fx_results.get('GOLD', (None,None))[0]
    if gold_usd and fx.get('USDSEK'):
        fx['GOLD_GRAM_SEK'] = gold_usd * fx['USDSEK'] / 31.1035

    crypto = {}
    for c in cfg.get('crypto', []):
        r = fx_results.get(c['symbol'])
        if r and r[0]: crypto[c['symbol']] = {'price': r[0], 'change': r[1]}

    idx_p, idx_ch = fx_results.get('INDEX', (None, None))

    # Helper: build screener list from fundamentals dict
    def _build_screener(ticker_list, fund_data):
        result = []
        for tk in ticker_list:
            fu = fund_data.get(tk)
            if not fu: continue
            comp, f = compute_score(fu)
            result.append({
                'ticker':tk, 'name':fu.get('name',tk),
                'sector':fu.get('sector','Other'),  # live from Yahoo Finance
                'composite':comp, 'f_score':f,
                'ev_ebit':fu.get('ev_ebit'), 'roic':fu.get('roic'),
                'infl_score': sum([25 for x in [
                    fu.get('roic') and fu['roic']>0.05,
                    fu.get('gm') and fu['gm']>0.15,
                    fu.get('de') is not None and fu['de']<1,
                    fu.get('ey') and fu['ey']>0.05,
                ] if x]),
                'pe':fu.get('pe'), 'de':fu.get('de'), 'gm':fu.get('gm'),
            })
        result.sort(key=lambda x: -x['composite'])
        for i, s in enumerate(result): s['rank'] = i+1
        return result

    # Build screeners from fetched data
    screener = _build_screener(list(all_tickers), funds)
    se_screener = _build_screener(se_screener_tickers, se_funds)

    with _lock:
        _cache['prices'] = prices
        _cache['fundamentals'] = funds
        _cache['screener'] = screener
        _cache['se_screener'] = se_screener
        _cache['fx'] = fx
        _cache['crypto'] = crypto
        _cache['index'] = idx_p
        _cache['index_ch'] = idx_ch
        _cache['last_fetch'] = time.time()
    _save_cache_to_disk()
    print("  [cache] Data saved to disk")


def compute_networth():
    cfg = load_config()
    with _lock:
        prices = _cache['prices']
        fx = _cache['fx']
        crypto = _cache['crypto']
    trysek = fx.get('TRYSEK', 0.21)
    usdsek = fx.get('USDSEK', 10.5)
    gold_sek = fx.get('GOLD_GRAM_SEK', 950)

    # Stocks (TRY -> SEK)
    stock_value_try = 0
    stock_cost_try = 0
    stock_rows = []
    for tk, h in cfg.get('stocks', {}).items():
        p = prices.get(tk, {}).get('price', 0)
        ch = prices.get(tk, {}).get('change', 0)
        val = h['shares'] * p
        cost = h['cost']
        pnl = (val/cost - 1) if cost > 0 else 0
        stock_value_try += val
        stock_cost_try += cost
        scr = next((s for s in _cache['screener'] if s['ticker']==tk), None)
        fu = _cache.get('fundamentals', {}).get(tk, {}) or {}
        # Sell signals
        f_score = scr['f_score'] if scr else None
        de = fu.get('de')
        ebit = fu.get('ebit')
        sell_signals = []
        if f_score is not None and f_score < 3:
            sell_signals.append(f'F-Score {f_score}/9 (under 3)')
        if ebit is not None and ebit < 0:
            sell_signals.append(f'Negativt EBIT')
        if de is not None and de > 2.0:
            sell_signals.append(f'D/E {de:.1f} (över 2.0)')
        stock_rows.append({
            'ticker':tk, 'shares':h['shares'], 'cost':cost,
            'price':p, 'change':ch, 'value_try':val, 'value_sek':val*trysek,
            'pnl':pnl, 'sector':fu.get('sector','Other') if fu else 'Other',
            'rank': scr['rank'] if scr else None,
            'score': scr['composite'] if scr else None,
            'f_score': f_score, 'de': de, 'ebit': ebit,
            'sell_signals': sell_signals,
        })
    stock_rows.sort(key=lambda x: -x['value_try'])
    stocks_sek = stock_value_try * trysek

    # Real estate (support value_try for TRY-denominated properties)
    re_total = 0
    for r in cfg.get('real_estate', []):
        if 'value_try' in r:
            r['value_sek'] = r['value_try'] * trysek
        re_total += r.get('value_sek', 0)
    # Compute loan_sek per property dynamically from loans list (single source of truth)
    prop_loans = {}
    for l in cfg.get('loans', []):
        prop = l.get('property')
        if prop:
            prop_loans[prop] = prop_loans.get(prop, 0) + l['amount']
    for r in cfg.get('real_estate', []):
        r['loan_sek'] = prop_loans.get(r['name'], 0)
    re_loans = sum(r.get('loan_sek', 0) for r in cfg.get('real_estate', []))

    # Bank accounts
    bank_total = sum(b['sek'] for b in cfg.get('bank_accounts', []))

    # Crypto
    crypto_sek = 0
    crypto_rows = []
    for c in cfg.get('crypto', []):
        cp = crypto.get(c['symbol'], {})
        p_usd = cp.get('price', 0)
        val = c['amount'] * p_usd * usdsek
        crypto_sek += val
        crypto_rows.append({'name':c['name'],'amount':c['amount'],'price_usd':p_usd,'value_sek':val,'change':cp.get('change',0)})

    # Cash (TRY)
    cash_sek = sum(c.get('try', 0) * trysek for c in cfg.get('cash', []))

    # Gold
    gold_sek_total = sum(g['grams'] * gold_sek for g in cfg.get('gold', []))

    # Instruments
    instr_sek = 0
    for i in cfg.get('instruments', []):
        if 'sek' in i: instr_sek += i['sek']
        elif 'usd' in i: instr_sek += i['usd'] * usdsek

    # Loans & credits
    loans_total = sum(l['amount'] for l in cfg.get('loans', []))
    credits_total = sum(c['amount'] for c in cfg.get('credits', []))

    # Budget
    budget = cfg.get('budget', {})
    income = sum(i['sek'] for i in budget.get('income', []))
    expenses = sum(e['sek'] for e in budget.get('expenses', []))

    total_assets = re_total + bank_total + stocks_sek + crypto_sek + cash_sek + gold_sek_total  # instruments excluded to match Sheets
    total_debts = loans_total + credits_total
    networth = total_assets - total_debts

    # Forecast projection
    fc = cfg.get('forecast', {})
    annual_growth = fc.get('annual_growth_pct', 7)
    monthly_rate = (1 + annual_growth / 100) ** (1/12) - 1
    monthly_save_override = fc.get('monthly_savings_override')
    monthly_save = monthly_save_override if monthly_save_override is not None else (income - expenses)
    forecast_rows = []
    for yr in [1, 2, 3, 5, 7, 10, 15, 20]:
        val = networth
        for _ in range(yr * 12):
            val = val * (1 + monthly_rate) + monthly_save
        saved = monthly_save * yr * 12
        growth = val - networth - saved
        forecast_rows.append({'year': yr, 'cal_year': 2026 + yr, 'value': val, 'growth': growth, 'saved': saved})

    # Build monthly grid for net worth chart (even time axis)
    history = cfg.get('networth_history', [])
    nw_grid = []
    if history:
        by_month = {}
        for h in history:
            m = h['date'][:7]
            by_month[m] = {'assets': h['assets'], 'debts': h['debts']}
        months_sorted = sorted(by_month.keys())
        fy, fm = int(months_sorted[0][:4]), int(months_sorted[0][5:7])
        ly, lm = int(months_sorted[-1][:4]), int(months_sorted[-1][5:7])
        last_a, last_d = None, None
        y, mo = fy, fm
        while y < ly or (y == ly and mo <= lm):
            key = f"{y}-{mo:02d}"
            if key in by_month:
                last_a = by_month[key]['assets']
                last_d = by_month[key]['debts']
                real = True
            else:
                real = False
            if last_a is not None:
                nw_grid.append({'month': key, 'assets': last_a, 'debts': last_d, 'real': real})
            mo += 1
            if mo > 12:
                mo = 1; y += 1

    max_assets = max((g['assets'] for g in nw_grid), default=1) if nw_grid else 1

    # SVG line chart data
    nw_svg = ''
    if nw_grid:
        W, H = 1200, 280
        PAD_L, PAD_R, PAD_T, PAD_B = 80, 20, 20, 40
        cw = W - PAD_L - PAD_R
        ch = H - PAD_T - PAD_B
        n = len(nw_grid)
        max_v = max(g['assets'] for g in nw_grid)
        min_v = min(g['assets'] - g['debts'] for g in nw_grid)
        min_v = min(min_v, 0)
        rng = max_v - min_v if max_v != min_v else 1

        def xp(i): return PAD_L + (i / max(n - 1, 1)) * cw
        def yp(v): return PAD_T + (1 - (v - min_v) / rng) * ch

        svg = f'<svg viewBox="0 0 {W} {H}" style="width:100%;height:auto;display:block">\n'
        # Background
        svg += f'<rect x="0" y="0" width="{W}" height="{H}" fill="#0a0a0f" rx="8"/>\n'
        # Grid lines
        for val in range(0, int(max_v) + 1, 1000000):
            if val < min_v: continue
            y_pos = yp(val)
            svg += f'<line x1="{PAD_L}" y1="{y_pos:.0f}" x2="{W-PAD_R}" y2="{y_pos:.0f}" stroke="#1f2937" stroke-width="1"/>\n'
            svg += f'<text x="{PAD_L-8}" y="{y_pos:.0f}" fill="#6b7280" font-size="10" text-anchor="end" dominant-baseline="middle">{val/1000000:.0f}M</text>\n'
        # Year separators
        for i, g in enumerate(nw_grid):
            if g['month'].endswith('-01') and i > 0:
                x = xp(i)
                yr = g['month'][:4]
                svg += f'<line x1="{x:.0f}" y1="{PAD_T}" x2="{x:.0f}" y2="{H-PAD_B}" stroke="#374151" stroke-width="1" stroke-dasharray="4,4"/>\n'
                svg += f'<text x="{x:.0f}" y="{H-PAD_B+14}" fill="#9ca3af" font-size="11" text-anchor="middle" font-weight="600">{yr}</text>\n'
        # First year label
        svg += f'<text x="{xp(0):.0f}" y="{H-PAD_B+14}" fill="#9ca3af" font-size="11" text-anchor="middle" font-weight="600">{nw_grid[0]["month"][:4]}</text>\n'

        # Assets area fill
        pts_a = ' '.join(f'{xp(i):.1f},{yp(g["assets"]):.1f}' for i, g in enumerate(nw_grid))
        svg += f'<polygon points="{xp(0):.1f},{yp(min_v):.1f} {pts_a} {xp(n-1):.1f},{yp(min_v):.1f}" fill="#1e3a5f" opacity="0.3"/>\n'
        # Netto area fill
        pts_n = ' '.join(f'{xp(i):.1f},{yp(g["assets"]-g["debts"]):.1f}' for i, g in enumerate(nw_grid))
        svg += f'<polygon points="{xp(0):.1f},{yp(min_v):.1f} {pts_n} {xp(n-1):.1f},{yp(min_v):.1f}" fill="#22c55e" opacity="0.15"/>\n'
        # Assets line
        svg += f'<polyline points="{pts_a}" fill="none" stroke="#3b82f6" stroke-width="2" opacity="0.7"/>\n'
        # Debts line
        pts_d = ' '.join(f'{xp(i):.1f},{yp(g["debts"]):.1f}' for i, g in enumerate(nw_grid))
        svg += f'<polyline points="{pts_d}" fill="none" stroke="#f87171" stroke-width="1.5" stroke-dasharray="4,3" opacity="0.6"/>\n'
        # Netto line (bold, main)
        svg += f'<polyline points="{pts_n}" fill="none" stroke="#4ade80" stroke-width="2.5"/>\n'
        # Data point dots (only real data)
        for i, g in enumerate(nw_grid):
            if g['real']:
                netto = g['assets'] - g['debts']
                svg += f'<circle cx="{xp(i):.1f}" cy="{yp(netto):.1f}" r="3" fill="#4ade80" opacity="0.8"><title>{g["month"]}&#10;Tillgångar: {g["assets"]:,.0f} kr&#10;Skulder: {g["debts"]:,.0f} kr&#10;Netto: {netto:,.0f} kr</title></circle>\n'
        svg += '</svg>'
        nw_svg = svg

    # Growth & CAGR statistics
    growth_stats = {}
    real_points = [g for g in nw_grid if g['real']]
    if len(real_points) >= 2:
        first, last = real_points[0], real_points[-1]
        # Parse months for year fraction
        fy2, fm2 = int(first['month'][:4]), int(first['month'][5:7])
        ly2, lm2 = int(last['month'][:4]), int(last['month'][5:7])
        years = (ly2 - fy2) + (lm2 - fm2) / 12
        if years > 0:
            netto_first = first['assets'] - first['debts']
            netto_last = last['assets'] - last['debts']
            assets_first, assets_last = first['assets'], last['assets']
            debts_first, debts_last = first['debts'], last['debts']
            growth_stats['years'] = round(years, 1)
            growth_stats['period'] = f"{first['month']} → {last['month']}"
            # Net worth
            growth_stats['nw_start'] = netto_first
            growth_stats['nw_end'] = netto_last
            growth_stats['nw_change'] = netto_last - netto_first
            growth_stats['nw_change_pct'] = ((netto_last / netto_first) - 1) * 100 if netto_first > 0 else 0
            growth_stats['nw_cagr'] = ((netto_last / netto_first) ** (1 / years) - 1) * 100 if netto_first > 0 else 0
            # Assets
            growth_stats['assets_start'] = assets_first
            growth_stats['assets_end'] = assets_last
            growth_stats['assets_cagr'] = ((assets_last / assets_first) ** (1 / years) - 1) * 100 if assets_first > 0 else 0
            # Debts
            growth_stats['debts_start'] = debts_first
            growth_stats['debts_end'] = debts_last
            growth_stats['debts_change'] = debts_last - debts_first
            growth_stats['debts_cagr'] = ((debts_last / debts_first) ** (1 / years) - 1) * 100 if debts_first > 0 else 0

    return {
        'networth': networth, 'total_assets': total_assets, 'total_debts': total_debts,
        'stocks_sek': stocks_sek, 'stock_value_try': stock_value_try, 'stock_cost_try': stock_cost_try,
        'stock_rows': stock_rows, 're_total': re_total, 're_loans': re_loans,
        'bank_total': bank_total, 'crypto_sek': crypto_sek, 'crypto_rows': crypto_rows,
        'cash_sek': cash_sek, 'gold_sek': gold_sek_total, 'instr_sek': instr_sek,
        'loans_total': loans_total, 'credits_total': credits_total,
        'monthly_loan_cost': sum(l['amount'] * l['rate'] / 12 for l in cfg.get('loans', []) + cfg.get('credits', [])),
        'income': income, 'expenses': expenses, 'savings': income - expenses,
        'fx': fx, 'trysek': trysek, 'usdsek': usdsek,
        'config': cfg,
        'forecast_rows': forecast_rows, 'forecast_growth': annual_growth, 'forecast_monthly_save': monthly_save,
        'nw_grid': nw_grid, 'nw_max': max_assets, 'nw_svg': nw_svg,
        'growth_stats': growth_stats,
    }


# ══════════════════════════════════════════════════════════════
# HTML TEMPLATE
# ══════════════════════════════════════════════════════════════
HTML = """<!DOCTYPE html>
<html lang="sv"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Brusk Ekonomi</title>
<meta http-equiv="refresh" content="900">
<style>
*{margin:0;padding:0;box-sizing:border-box}
html,body{min-height:100%;overflow-y:auto}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0a0a0f;color:#e2e8f0;transform:translateZ(0)}
.container{max-width:1400px;margin:0 auto;padding:16px 16px 60px}
h1{font-size:1.6rem;color:#38bdf8;display:flex;align-items:center;gap:8px}
.dot{width:8px;height:8px;background:#4ade80;border-radius:50%;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
.sub{color:#475569;font-size:.8rem;margin-bottom:16px}
.grid{display:grid;gap:12px;margin-bottom:16px}
.g2{grid-template-columns:repeat(2,1fr)} .g3{grid-template-columns:repeat(3,1fr)}
.g4{grid-template-columns:repeat(4,1fr)} .g5{grid-template-columns:repeat(5,1fr)}
.g6{grid-template-columns:repeat(6,1fr)}
@media(max-width:900px){.g3,.g4,.g5,.g6{grid-template-columns:repeat(2,1fr)}}
.card{background:#111827;border-radius:10px;padding:16px;border:1px solid #1f2937}
.card-sm{padding:12px}
.lbl{font-size:.7rem;color:#6b7280;text-transform:uppercase;letter-spacing:.05em}
.val{font-size:1.4rem;font-weight:700;margin-top:2px}
.val-sm{font-size:1.1rem}
.sub-val{font-size:.8rem;color:#9ca3af;margin-top:2px}
.g{color:#4ade80}.r{color:#f87171}.b{color:#38bdf8}.y{color:#fbbf24}.p{color:#c084fc}.w{color:#f1f5f9}
.section{background:#111827;border-radius:10px;padding:16px;margin-bottom:16px;border:1px solid #1f2937}
.stitle{font-size:1rem;font-weight:600;margin-bottom:12px;display:flex;align-items:center;gap:8px}
table{width:100%;border-collapse:collapse;font-size:.8rem}
th{text-align:left;padding:8px;color:#6b7280;border-bottom:2px solid #1f2937;font-size:.7rem;text-transform:uppercase}
td{padding:8px;border-bottom:1px solid #111827}
tr:hover{background:#1f2937}
.badge{padding:2px 8px;border-radius:12px;font-size:.7rem;font-weight:600}
.bg{background:#065f46;color:#6ee7b7}.br{background:#7f1d1d;color:#fca5a5}.by{background:#78350f;color:#fcd34d}.bb{background:#1e3a5f;color:#93c5fd}
.pct{font-weight:600;font-variant-numeric:tabular-nums}
.bar{height:5px;border-radius:3px;background:#1f2937;overflow:hidden;width:80px;display:inline-block;vertical-align:middle}
.bar-f{height:100%;border-radius:3px}
.tabs{display:flex;gap:4px;margin-bottom:16px;flex-wrap:wrap}
.tab{padding:8px 16px;background:#111827;border:1px solid #1f2937;border-radius:6px 6px 0 0;cursor:pointer;color:#6b7280;font-size:.85rem;font-weight:500}
.tab.active{background:#1f2937;color:#f1f5f9}
.tc{display:none}.tc.active{display:block;overflow:visible;color:#e2e8f0}
.nw-chart{display:flex;align-items:flex-end;gap:1px;height:140px;padding:8px 0}
.nw-bar{flex:1;background:#1f2937;border-radius:2px 2px 0 0;position:relative;min-width:0}
.nw-bar .fill{position:absolute;bottom:0;left:0;right:0;border-radius:2px 2px 0 0}
.nw-bar .lbl2{position:absolute;bottom:-18px;left:50%;transform:translateX(-50%);font-size:.6rem;color:#6b7280;white-space:nowrap}
.clickable{cursor:pointer;transition:background .15s}.clickable:hover{background:#1e3a5f !important}
.modal-bg{display:none;position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:200;justify-content:center;align-items:center}
.modal-bg.open{display:flex}
.modal{background:#111827;border:1px solid #1f2937;border-radius:12px;padding:24px;max-width:700px;width:90%;max-height:80vh;overflow-y:auto;position:relative}
.modal h2{font-size:1.1rem;color:#38bdf8;margin-bottom:4px}
.modal .close{position:absolute;top:12px;right:16px;color:#6b7280;cursor:pointer;font-size:1.4rem;background:none;border:none}
.modal .close:hover{color:#f1f5f9}
.hist-chart{display:flex;align-items:flex-end;gap:3px;height:120px;margin:16px 0}
.hist-bar{flex:1;background:#22c55e;border-radius:3px 3px 0 0;position:relative;min-width:16px;transition:opacity .15s}
.hist-bar:hover{opacity:.8}
.hist-bar .ht{display:none;position:absolute;top:-30px;left:50%;transform:translateX(-50%);background:#1f2937;color:#e2e8f0;padding:2px 8px;border-radius:4px;font-size:.65rem;white-space:nowrap;z-index:10}
.hist-bar:hover .ht{display:block}
.sell-box{background:#1c1917;border:1px solid #dc2626;border-radius:6px;padding:12px;margin-top:12px}
.sell-box h3{color:#dc2626;font-size:.85rem;margin-bottom:6px}
.sell-box li{color:#fca5a5;font-size:.8rem;margin-left:14px;margin-bottom:2px}
.dca-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px}
.dca-c{background:#0a0a0f;border-radius:6px;padding:12px;text-align:center;border:1px solid #1f2937}
.dca-tk{font-size:1rem;font-weight:700;color:#38bdf8}
.dca-amt{font-size:1.2rem;font-weight:700;color:#4ade80;margin:6px 0}
.alloc-bar{display:flex;height:28px;border-radius:6px;overflow:hidden;margin-bottom:8px}
.alloc-seg{display:flex;align-items:center;justify-content:center;font-size:.65rem;font-weight:600;color:#fff;min-width:30px}
</style></head>
<body>
<div class="container">
<div style="display:flex;justify-content:space-between;align-items:flex-start">
<div><h1><span class="dot"></span> Brusk Ekonomi</h1>
<div class="sub">Live data · Yahoo Finance · Auto-refresh 15 min · <a href="/?force=1" style="color:#38bdf8">Uppdatera</a> · <a href="/edit" style="color:#a78bfa">Redigera</a></div></div>
<div style="text-align:right;font-size:.75rem;color:#475569">{{ now }}<br>
TRY/SEK: {{ "%.4f"|format(d.trysek) }} · USD/SEK: {{ "%.2f"|format(d.usdsek) }}<br>
{% if refreshing %}<span style="color:#fbbf24">⟳</span> Uppdaterar i bakgrunden...{% else %}<span style="color:#4ade80">●</span>{% endif %} Data uppdaterad: {{ data_updated }}{% if data_age_min > 15 %} <span style="color:#fbbf24">({{ data_age_min }} min sedan)</span>{% endif %}</div>
</div>

<!-- NET WORTH -->
<div class="grid g5" style="margin-bottom:16px">
<div class="card" style="grid-column:span 2">
<div class="lbl">Net Worth</div>
<div class="val b" style="font-size:2rem">{{ "{:,.0f}".format(d.networth) }} kr</div>
<div class="sub-val">Tillgångar {{ "{:,.0f}".format(d.total_assets) }} kr — Skulder {{ "{:,.0f}".format(d.total_debts) }} kr</div>
</div>
<div class="card card-sm"><div class="lbl">Turkiska Aktier</div>
<div class="val val-sm g">{{ "{:,.0f}".format(d.stocks_sek) }} kr</div>
<div class="sub-val">₺{{ "{:,.0f}".format(d.stock_value_try) }}</div></div>
<div class="card card-sm"><div class="lbl">Fastigheter (netto)</div>
<div class="val val-sm p">{{ "{:,.0f}".format(d.re_total - d.re_loans) }} kr</div></div>
<div class="card card-sm"><div class="lbl">Sparkvot</div>
<div class="val val-sm {{ 'g' if d.savings > 0 else 'r' }}">{{ "{:,.0f}".format(d.savings) }} kr/mån</div>
<div class="sub-val">{{ "%.0f"|format(d.savings/d.income * 100) if d.income else '—' }}{{ "%" if d.income else "" }}</div></div>
</div>

<!-- ALLOCATION BAR -->
<div class="card" style="margin-bottom:16px">
<div class="lbl" style="margin-bottom:6px">Tillgångsfördelning</div>
{% set parts = [
    ('Fastigheter', d.re_total, '#8b5cf6'),
    ('Aktier (TR)', d.stocks_sek, '#22c55e'),
    ('Banker', d.bank_total, '#3b82f6'),
    ('Crypto', d.crypto_sek, '#f59e0b'),
    ('Guld', d.gold_sek, '#eab308'),
    ('Cash', d.cash_sek, '#6b7280'),
] %}
<div class="alloc-bar">
{% for name, val, color in parts %}
{% if val > 0 %}
<div class="alloc-seg" style="width:{{ (val/(d.total_assets or 1)*100)|round(1) }}%;background:{{ color }}">
{{ "%.0f"|format(val/(d.total_assets or 1)*100) }}%</div>
{% endif %}
{% endfor %}
</div>
<div style="display:flex;gap:16px;flex-wrap:wrap;font-size:.75rem;color:#9ca3af">
{% for name, val, color in parts %}
{% if val > 0 %}
<span><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{{ color }};margin-right:4px"></span>{{ name }}: {{ "{:,.0f}".format(val) }} kr</span>
{% endif %}
{% endfor %}
</div>
<div style="margin-top:8px;font-size:.7rem;color:#475569;border-top:1px solid #1f2937;padding-top:6px">
Detaljerad uppdelning: Fastigheter {{ "{:,.0f}".format(d.re_total) }} + Aktier {{ "{:,.0f}".format(d.stocks_sek) }} + Banker {{ "{:,.0f}".format(d.bank_total) }} + Crypto {{ "{:,.0f}".format(d.crypto_sek) }} + Guld {{ "{:,.0f}".format(d.gold_sek) }} + Cash {{ "{:,.0f}".format(d.cash_sek) }} = <strong style="color:#9ca3af">{{ "{:,.0f}".format(d.total_assets) }}</strong> — Skulder {{ "{:,.0f}".format(d.total_debts) }} = <strong style="color:#38bdf8">{{ "{:,.0f}".format(d.networth) }}</strong>
<br>Instrument (ej i förmögenhet): {{ "{:,.0f}".format(d.instr_sek) }} kr
</div>
</div>

<!-- TABS -->
<div class="tabs">
<div class="tab active" onclick="sw('stocks')">Innehav</div>
<div class="tab" onclick="sw('dca')">DCA</div>
<div class="tab" onclick="sw('screener')">BIST Screener</div>
<div class="tab" onclick="sw('se_screener')">Sverige Screener</div>
<div class="tab" onclick="sw('budget')">Budget & Lån</div>
<div class="tab" onclick="sw('assets')">Övriga Tillgångar</div>
<div class="tab" onclick="sw('history')">Historik</div>
</div>

<!-- TAB: STOCKS / INNEHAV -->
<div id="t-stocks" class="tc active">
<div class="grid g2" style="margin-bottom:12px">
<div class="card card-sm"><div class="lbl">BIST 100</div>
<div class="val val-sm">{{ "{:,.0f}".format(idx) if idx else 'N/A' }}</div>
<div class="sub-val {{ 'g' if idx_ch and idx_ch > 0 else 'r' }}">{{ "%+.1f"|format(idx_ch * 100) if idx_ch else '' }}{{ "%" if idx_ch else "" }}</div></div>
<div class="card card-sm"><div class="lbl">Portfölj P/L</div>
<div class="val val-sm {{ 'g' if d.stock_value_try > d.stock_cost_try else 'r' }}">
{{ "%+.1f"|format((d.stock_value_try/d.stock_cost_try - 1) * 100) if d.stock_cost_try else '—' }}{{ "%" if d.stock_cost_try else "" }}</div>
<div class="sub-val">₺{{ "{:+,.0f}".format(d.stock_value_try - d.stock_cost_try) }}</div></div>
</div>
<div class="section">
<div class="stitle">Dina Innehav</div>
<div style="max-height:500px;overflow-y:auto">
<table><tr><th style="position:sticky;top:0;background:#111827;z-index:1">Ticker</th><th style="position:sticky;top:0;background:#111827;z-index:1">Sektor</th><th style="position:sticky;top:0;background:#111827;z-index:1">Antal</th><th style="position:sticky;top:0;background:#111827;z-index:1">Pris</th><th style="position:sticky;top:0;background:#111827;z-index:1">Dag</th><th style="position:sticky;top:0;background:#111827;z-index:1">Värde (TRY)</th><th style="position:sticky;top:0;background:#111827;z-index:1">Värde (SEK)</th><th style="position:sticky;top:0;background:#111827;z-index:1">Vikt</th><th style="position:sticky;top:0;background:#111827;z-index:1">P/L</th><th style="position:sticky;top:0;background:#111827;z-index:1">Rank</th><th style="position:sticky;top:0;background:#111827;z-index:1">Score</th><th style="position:sticky;top:0;background:#111827;z-index:1">Action</th></tr>
{% for h in d.stock_rows %}
<tr class="clickable" onclick="showHist('stock:{{ h.ticker }}','{{ h.ticker }}')">
<td><strong>{{ h.ticker }}</strong></td>
<td style="color:#6b7280">{{ h.sector }}</td>
<td>{{ "{:,}".format(h.shares) }}</td>
<td>₺{{ "%.2f"|format(h.price) }}</td>
<td class="pct {{ 'g' if h.change > 0 else 'r' }}">{{ "%+.1f"|format(h.change * 100) }}%</td>
<td>₺{{ "{:,.0f}".format(h.value_try) }}</td>
<td>{{ "{:,.0f}".format(h.value_sek) }} kr</td>
<td>{% set wt = (h.value_try/d.stock_value_try) if d.stock_value_try else 0 %}<div class="bar"><div class="bar-f" style="width:{{ (wt*100)|int }}%;background:{{ '#f87171' if wt > 0.15 else '#38bdf8' }}"></div></div> {{ "%.1f"|format(wt*100) }}%</td>
<td class="pct {{ 'g' if h.pnl > 0 else 'r' }}">{{ "%+.1f"|format(h.pnl * 100) }}%</td>
<td>{{ "#%d"|format(h.rank) if h.rank else '—' }}</td>
<td>{{ "%.0f"|format(h.score) if h.score else '—' }}</td>
<td>{% if h.sell_signals %}<span class="badge br" title="{{ h.sell_signals|join(', ') }}">SÄLJ ⚠</span>
{% elif d.stock_value_try and h.value_try/d.stock_value_try > 0.15 %}<span class="badge br">ÖVERVIKT</span>
{% elif h.rank and h.rank <= 7 %}<span class="badge bg">{{ 'KÖP MER' if d.stock_value_try and h.value_try/d.stock_value_try < 0.10 else 'HÅLL' }}</span>
{% else %}<span class="badge bb">HÅLL</span>{% endif %}</td>
</tr>{% endfor %}
</table></div>

<div class="sell-box"><h3>SÄLJ BARA om:</h3><ul>
<li>F-Score under 3</li><li>Negativt EBIT 2 kvartal i rad</li><li>D/E över 2.0</li><li>Avlistning/fusion</li></ul></div>
</div>
</div>

<!-- TAB: DCA -->
<div id="t-dca" class="tc">
<div class="section">
<div class="stitle">Månatlig DCA — ₺{{ "{:,.0f}".format(d.config.monthly_dca_try) }}/månad <span style="font-size:.7rem;color:#6b7280">(hoppar över >10% vikt, max 2/sektor)</span></div>
<div class="dca-grid">
{% for s in dca_picks %}
<div class="dca-c">
<div class="dca-tk">{{ s.ticker }}</div>
<div style="color:#6b7280;font-size:.7rem">{{ s.sector }} · #{{ s.rank }}</div>
<div class="dca-amt">₺{{ "{:,.0f}".format(d.config.monthly_dca_try / (dca_picks|length or 1)) }}</div>
<div style="font-size:.7rem;color:#6b7280">Score: {{ "%.0f"|format(s.composite) }} · F: {{ s.f_score }}</div>
</div>{% endfor %}
</div>
{% if dca_skipped %}<div style="margin-top:10px;padding:8px 12px;background:#1e293b;border-radius:6px;font-size:.8rem;color:#94a3b8">
<strong style="color:#f87171">Hoppade över:</strong>
{% for sk in dca_skipped %}<span style="margin-right:12px">{{ sk.ticker }} <span style="color:#6b7280">(#{{ sk.rank }}, {{ sk.reason }})</span></span>{% endfor %}
</div>{% endif %}
</div>
</div>

<!-- TAB: SCREENER -->
<div id="t-screener" class="tc">
<div class="section">
<div class="stitle">BIST Screener — {{ screener|length }} bolag (live)</div>
<div style="max-height:600px;overflow-y:auto">
<table><tr><th style="position:sticky;top:0;background:#111827;z-index:1">#</th><th style="position:sticky;top:0;background:#111827;z-index:1">Ticker</th><th style="position:sticky;top:0;background:#111827;z-index:1">Sektor</th><th style="position:sticky;top:0;background:#111827;z-index:1">Score</th><th style="position:sticky;top:0;background:#111827;z-index:1">EV/EBIT</th><th style="position:sticky;top:0;background:#111827;z-index:1">ROIC</th><th style="position:sticky;top:0;background:#111827;z-index:1">F</th><th style="position:sticky;top:0;background:#111827;z-index:1">Infl</th><th style="position:sticky;top:0;background:#111827;z-index:1">P/E</th><th style="position:sticky;top:0;background:#111827;z-index:1">D/E</th></tr>
{% for s in screener %}
<tr style="{{ 'background:#052e16' if s.rank <= 7 else '' }}">
<td><strong>{{ s.rank }}</strong></td><td><strong>{{ s.ticker }}</strong></td><td>{{ s.sector }}</td>
<td class="pct {{ 'g' if s.composite >= 70 else 'y' if s.composite >= 50 else 'r' }}">{{ "%.1f"|format(s.composite) }}</td>
<td>{{ "%.1f"|format(s.ev_ebit) if s.ev_ebit else '—' }}</td>
<td>{{ "%.1f"|format(s.roic * 100) if s.roic else '—' }}{{ "%" if s.roic else "" }}</td>
<td>{{ s.f_score }}/9</td><td>{{ s.infl_score }}</td>
<td>{{ "%.1f"|format(s.pe) if s.pe else '—' }}</td>
<td>{{ "%.2f"|format(s.de) if s.de else '—' }}</td>
</tr>{% endfor %}
</table></div></div>
</div>

<!-- TAB: SVERIGE SCREENER -->
<div id="t-se_screener" class="tc">
<div class="section">
<div class="stitle">Sverige Screener — {{ se_screener|length }} bolag (live)</div>
<div style="max-height:600px;overflow-y:auto">
<table><tr><th style="position:sticky;top:0;background:#111827;z-index:1">#</th><th style="position:sticky;top:0;background:#111827;z-index:1">Ticker</th><th style="position:sticky;top:0;background:#111827;z-index:1">Namn</th><th style="position:sticky;top:0;background:#111827;z-index:1">Sektor</th><th style="position:sticky;top:0;background:#111827;z-index:1">Score</th><th style="position:sticky;top:0;background:#111827;z-index:1">EV/EBIT</th><th style="position:sticky;top:0;background:#111827;z-index:1">ROIC</th><th style="position:sticky;top:0;background:#111827;z-index:1">F</th><th style="position:sticky;top:0;background:#111827;z-index:1">Infl</th><th style="position:sticky;top:0;background:#111827;z-index:1">P/E</th><th style="position:sticky;top:0;background:#111827;z-index:1">D/E</th><th style="position:sticky;top:0;background:#111827;z-index:1">GM</th></tr>
{% for s in se_screener %}
<tr style="{{ 'background:#052e16' if s.rank <= 7 else '' }}">
<td><strong>{{ s.rank }}</strong></td><td><strong>{{ s.ticker }}</strong></td><td style="color:#9ca3af;font-size:.75rem;max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ s.name }}</td><td>{{ s.sector }}</td>
<td class="pct {{ 'g' if s.composite >= 70 else 'y' if s.composite >= 50 else 'r' }}">{{ "%.1f"|format(s.composite) }}</td>
<td>{{ "%.1f"|format(s.ev_ebit) if s.ev_ebit else '—' }}</td>
<td>{{ "%.1f"|format(s.roic * 100) if s.roic else '—' }}{{ "%" if s.roic else "" }}</td>
<td>{{ s.f_score }}/9</td><td>{{ s.infl_score }}</td>
<td>{{ "%.1f"|format(s.pe) if s.pe else '—' }}</td>
<td>{{ "%.2f"|format(s.de) if s.de is not none else '—' }}</td>
<td>{{ "%.0f"|format(s.gm * 100) if s.gm else '—' }}{{ "%" if s.gm else "" }}</td>
</tr>{% endfor %}
</table></div></div>
</div>

<!-- TAB: BUDGET -->
<div id="t-budget" class="tc">
<div class="grid g2">
<div class="section"><div class="stitle g">Inkomster</div>
<table>{% for i in d.config.budget.income %}<tr><td>{{ i.name }}</td><td class="g pct" style="text-align:right">{{ "{:,.0f}".format(i.sek) }} kr</td></tr>{% endfor %}
<tr style="border-top:2px solid #1f2937"><td><strong>Total</strong></td><td class="g pct" style="text-align:right"><strong>{{ "{:,.0f}".format(d.income) }} kr</strong></td></tr></table></div>
<div class="section"><div class="stitle r">Utgifter</div>
<table>{% for e in d.config.budget.expenses %}<tr><td>{{ e.name }}</td><td class="r pct" style="text-align:right">{{ "{:,.0f}".format(e.sek) }} kr</td></tr>{% endfor %}
<tr style="border-top:2px solid #1f2937"><td><strong>Total</strong></td><td class="r pct" style="text-align:right"><strong>{{ "{:,.0f}".format(d.expenses) }} kr</strong></td></tr></table></div>
</div>
<div class="section"><div class="stitle">Lån</div>
<table><tr><th>Lån</th><th>Belopp</th><th>Ränta</th><th>Kostnad/mån</th></tr>
{% for l in d.config.loans + d.config.credits %}
<tr><td>{{ l.name }}</td><td>{{ "{:,.0f}".format(l.amount) }} kr</td>
<td>{{ "%.2f"|format(l.rate * 100) }}%</td>
<td class="r">{{ "{:,.0f}".format(l.amount * l.rate / 12) }} kr</td></tr>{% endfor %}
<tr style="border-top:2px solid #1f2937"><td><strong>Total skuld</strong></td><td><strong>{{ "{:,.0f}".format(d.loans_total + d.credits_total) }} kr</strong></td>
<td></td><td class="r"><strong>{{ "{:,.0f}".format(d.monthly_loan_cost) }} kr</strong></td></tr>
</table></div>
</div>

<!-- TAB: ASSETS -->
<div id="t-assets" class="tc">
<div style="margin-bottom:12px;font-size:.75rem;color:#475569">Klicka på en rad för att se historisk utveckling</div>
<div class="grid g2">
<div class="section"><div class="stitle p">Fastigheter</div>
<table><tr><th>Namn</th><th>Värde</th><th>Lån</th><th>Netto</th></tr>
{% for r in d.config.real_estate %}<tr class="clickable" onclick="showHist('re:{{ r.name }}','{{ r.name }}')"><td>{{ r.name }}</td><td>{{ "{:,.0f}".format(r.value_sek) }} kr</td>
<td class="r">{{ "{:,.0f}".format(r.get('loan_sek',0)) }} kr</td>
<td class="{{ 'g' if r.value_sek - r.get('loan_sek',0) > 0 else 'r' }}">{{ "{:,.0f}".format(r.value_sek - r.get('loan_sek',0)) }} kr</td></tr>{% endfor %}
</table></div>
<div class="section"><div class="stitle y">Crypto</div>
<table><tr><th>Namn</th><th>Antal</th><th>Pris (USD)</th><th>Värde (SEK)</th><th>Dag</th></tr>
{% for c in d.crypto_rows %}<tr class="clickable" onclick="showHist('crypto:{{ c.name }}','{{ c.name }}')"><td>{{ c.name }}</td><td>{{ c.amount }}</td><td>${{ "{:,.0f}".format(c.price_usd) }}</td>
<td>{{ "{:,.0f}".format(c.value_sek) }} kr</td>
<td class="pct {{ 'g' if c.change > 0 else 'r' }}">{{ "%+.1f"|format(c.change * 100) }}%</td></tr>{% endfor %}
</table></div>
</div>
<div class="grid g2">
<div class="section"><div class="stitle">Instrument & Inventarier</div>
<table>{% for i in d.config.instruments %}<tr><td>{{ i.name }}</td>
<td style="text-align:right">{{ "{:,.0f}".format(i.get('sek', i.get('usd',0) * d.usdsek)) }} kr</td></tr>{% endfor %}
<tr style="border-top:2px solid #1f2937"><td><strong>Total</strong></td><td style="text-align:right"><strong>{{ "{:,.0f}".format(d.instr_sek) }} kr</strong></td></tr></table></div>
<div class="section"><div class="stitle">Banker & Cash</div>
<table>{% for b in d.config.bank_accounts %}<tr class="clickable" onclick="showHist('bank:{{ b.name }}','{{ b.name }}')"><td>{{ b.name }}</td><td class="b" style="text-align:right">{{ "{:,.0f}".format(b.sek) }} kr</td></tr>{% endfor %}
{% for c in d.config.cash %}<tr><td>{{ c.name }}</td><td style="text-align:right">{{ "{:,.0f}".format(c.get('try',0) * d.trysek) }} kr (₺{{ "{:,.0f}".format(c.get('try',0)) }})</td></tr>{% endfor %}
{% for g in d.config.gold %}<tr><td>{{ g.name }}</td><td style="text-align:right">{{ "{:,.0f}".format(g.grams * d.fx.get('GOLD_GRAM_SEK', 950)) }} kr</td></tr>{% endfor %}
</table></div>
</div>
</div>

<!-- TAB: HISTORY -->
<div id="t-history" class="tc">

<!-- Net Worth Chart — pure Jinja2, even monthly grid -->
<div class="section">
<div class="stitle">Net Worth Historik (sedan 2021)</div>
{% if nw_svg %}
{{ nw_svg|safe }}
{% endif %}
<div style="margin-top:12px;font-size:.75rem;color:#6b7280">
<span style="display:inline-block;width:10px;height:10px;background:#3b82f6;margin-right:4px"></span>Tillgångar
<span style="display:inline-block;width:10px;height:10px;background:#f87171;margin-left:12px;margin-right:4px"></span>Skulder
<span style="display:inline-block;width:10px;height:10px;background:#4ade80;margin-left:12px;margin-right:4px"></span>Netto (tillgångar - skulder)
<span style="color:#6b7280;margin-left:12px">&#9679;</span> Datapunkter (ej interpolerad)</div>

<!-- Growth stats cards -->
{% if gs %}
<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-top:16px">
<div style="background:#111827;border:1px solid #1f2937;border-radius:8px;padding:14px">
<div style="font-size:.7rem;color:#6b7280;text-transform:uppercase;letter-spacing:.05em">Förmögenhet (Netto)</div>
<div style="font-size:1.3rem;font-weight:700;color:#4ade80;margin:4px 0">{{ "{:+,.0f}".format(gs.nw_change) }} kr</div>
<div style="font-size:.8rem;color:#9ca3af">{{ "{:,.0f}".format(gs.nw_start) }} → {{ "{:,.0f}".format(gs.nw_end) }} kr</div>
<div style="font-size:.8rem;margin-top:4px"><span style="color:#4ade80">{{ "{:+.1f}".format(gs.nw_change_pct) }}%</span> totalt · <span style="color:#38bdf8">{{ "{:.1f}".format(gs.nw_cagr) }}% CAGR</span></div>
<div style="font-size:.7rem;color:#6b7280">{{ gs.period }} ({{ gs.years }} år)</div>
</div>
<div style="background:#111827;border:1px solid #1f2937;border-radius:8px;padding:14px">
<div style="font-size:.7rem;color:#6b7280;text-transform:uppercase;letter-spacing:.05em">Tillgångar</div>
<div style="font-size:1.3rem;font-weight:700;color:#3b82f6;margin:4px 0">{{ "{:+,.0f}".format(gs.assets_end - gs.assets_start) }} kr</div>
<div style="font-size:.8rem;color:#9ca3af">{{ "{:,.0f}".format(gs.assets_start) }} → {{ "{:,.0f}".format(gs.assets_end) }} kr</div>
<div style="font-size:.8rem;margin-top:4px"><span style="color:#38bdf8">{{ "{:.1f}".format(gs.assets_cagr) }}% CAGR</span></div>
</div>
<div style="background:#111827;border:1px solid #1f2937;border-radius:8px;padding:14px">
<div style="font-size:.7rem;color:#6b7280;text-transform:uppercase;letter-spacing:.05em">Skulder</div>
<div style="font-size:1.3rem;font-weight:700;color:{{ '#4ade80' if gs.debts_change < 0 else '#f87171' }};margin:4px 0">{{ "{:+,.0f}".format(gs.debts_change) }} kr</div>
<div style="font-size:.8rem;color:#9ca3af">{{ "{:,.0f}".format(gs.debts_start) }} → {{ "{:,.0f}".format(gs.debts_end) }} kr</div>
<div style="font-size:.8rem;margin-top:4px"><span style="color:{{ '#4ade80' if gs.debts_cagr < 0 else '#f87171' }}">{{ "{:+.1f}".format(gs.debts_cagr) }}% CAGR</span> (negativt = bra)</div>
</div>
</div>
{% endif %}

<!-- Summary table — reversed (newest first), collapsible -->
{% set hist_rev = d.config.networth_history|reverse|list %}
<table style="margin-top:12px" id="nw-hist-table"><tr><th>Datum</th><th>Tillgångar</th><th>Skulder</th><th>Netto</th><th>Förändring</th></tr>
{% for h in hist_rev %}
{% set prev_netto = hist_rev[loop.index].assets - hist_rev[loop.index].debts if loop.index < hist_rev|length else None %}
<tr class="nw-hist-row" {% if loop.index0 >= 5 %}style="display:none"{% endif %}>
<td>{{ h.date }}</td><td class="b">{{ "{:,.0f}".format(h.assets) }} kr</td>
<td class="r">{{ "{:,.0f}".format(h.debts) }} kr</td>
<td class="{{ 'g' if h.assets-h.debts > 0 else 'r' }}">{{ "{:,.0f}".format(h.assets - h.debts) }} kr</td>
<td class="pct {{ 'g' if prev_netto is not none and (h.assets-h.debts) > prev_netto else 'r' if prev_netto is not none else '' }}">
{% if prev_netto is not none %}{{ "{:+,.0f}".format((h.assets-h.debts) - prev_netto) }} kr{% endif %}</td>
</tr>{% endfor %}
</table>
{% if hist_rev|length > 5 %}
<div style="text-align:center;margin-top:8px">
<button onclick="var rows=document.querySelectorAll('.nw-hist-row');var hidden=rows[5].style.display==='none';rows.forEach(function(r,i){if(i>=5)r.style.display=hidden?'':'none'});this.textContent=hidden?'Visa färre ↑':'Visa alla ('+rows.length+') ↓'" style="background:#1f2937;color:#9ca3af;border:1px solid #374151;border-radius:6px;padding:6px 16px;cursor:pointer;font-size:.8rem">Visa alla ({{ hist_rev|length }}) ↓</button>
</div>
{% endif %}
</div>

<!-- Per-asset breakdown (only for snapshots that have detail) -->
{% set detailed = d.config.networth_history|selectattr('stocks_sek', 'defined')|list %}
{% if detailed %}
<div class="section">
<div class="stitle">Tillgångsklass per period</div>
<div style="max-height:400px;overflow-y:auto">
<table>
<tr>
<th style="position:sticky;top:0;background:#111827;z-index:1">Datum</th>
<th style="position:sticky;top:0;background:#111827;z-index:1">Aktier</th>
<th style="position:sticky;top:0;background:#111827;z-index:1">Fastigheter</th>
<th style="position:sticky;top:0;background:#111827;z-index:1">Banker</th>
<th style="position:sticky;top:0;background:#111827;z-index:1">Crypto</th>
<th style="position:sticky;top:0;background:#111827;z-index:1">Guld</th>
<th style="position:sticky;top:0;background:#111827;z-index:1">Cash</th>
<th style="position:sticky;top:0;background:#111827;z-index:1">Netto</th>
</tr>
{% for h in detailed %}
<tr>
<td>{{ h.date }}</td>
<td class="g">{{ "{:,.0f}".format(h.get('stocks_sek', 0)) }}</td>
<td class="p">{{ "{:,.0f}".format(h.get('re_total', 0)) }}</td>
<td class="b">{{ "{:,.0f}".format(h.get('bank_total', 0)) }}</td>
<td class="y">{{ "{:,.0f}".format(h.get('crypto_sek', 0)) }}</td>
<td style="color:#eab308">{{ "{:,.0f}".format(h.get('gold_sek', 0)) }}</td>
<td>{{ "{:,.0f}".format(h.get('cash_sek', 0)) }}</td>
<td class="{{ 'g' if h.assets-h.debts > 0 else 'r' }}"><strong>{{ "{:,.0f}".format(h.assets - h.debts) }}</strong></td>
</tr>
{% endfor %}
</table>
</div>
<div style="margin-top:8px;font-size:.7rem;color:#475569">Detaljerad uppdelning sparas automatiskt vid varje ny ögonblicksbild. Äldre poster visar bara total.</div>
</div>
{% endif %}

<!-- 4% RULE -->
<div class="section">
<div class="stitle" style="color:#fbbf24">4%-regeln (FIRE)</div>
{% set withdraw_yr = d.networth * 0.04 %}
{% set withdraw_mo = withdraw_yr / 12 %}
<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px">
<div style="background:#111827;border:1px solid #1f2937;border-radius:8px;padding:14px">
<div style="font-size:.7rem;color:#6b7280;text-transform:uppercase;letter-spacing:.05em">Årligt uttag (4%)</div>
<div style="font-size:1.3rem;font-weight:700;color:#fbbf24;margin:4px 0">{{ "{:,.0f}".format(withdraw_yr) }} kr</div>
</div>
<div style="background:#111827;border:1px solid #1f2937;border-radius:8px;padding:14px">
<div style="font-size:.7rem;color:#6b7280;text-transform:uppercase;letter-spacing:.05em">Månadsbudget</div>
<div style="font-size:1.3rem;font-weight:700;color:#fbbf24;margin:4px 0">{{ "{:,.0f}".format(withdraw_mo) }} kr/mån</div>
</div>
<div style="background:#111827;border:1px solid #1f2937;border-radius:8px;padding:14px">
<div style="font-size:.7rem;color:#6b7280;text-transform:uppercase;letter-spacing:.05em">Nuvarande utgifter</div>
<div style="font-size:1.3rem;font-weight:700;color:{{ '#4ade80' if withdraw_mo >= d.expenses else '#f87171' }};margin:4px 0">{{ "{:,.0f}".format(d.expenses) }} kr/mån</div>
<div style="font-size:.75rem;color:#9ca3af">{{ "{:+,.0f}".format(withdraw_mo - d.expenses) }} kr {{ "överskott" if withdraw_mo >= d.expenses else "underskott" }}</div>
</div>
</div>
<div style="font-size:.75rem;color:#6b7280;margin-top:8px">Baserat på nuvarande netto {{ "{:,.0f}".format(d.networth) }} kr. 4%-regeln innebär att du kan ta ut 4% per år utan att tömma kapitalet (historiskt 30+ år).</div>
</div>

<!-- FORECAST / PROGNOS -->
<div class="section">
<div class="stitle" style="color:#38bdf8">Förmögenhetsprognos</div>
<div style="margin-bottom:12px;font-size:.8rem;color:#9ca3af">
Baserat på: nuvarande förmögenhet {{ "{:,.0f}".format(d.networth) }} kr,
sparkvot {{ "{:,.0f}".format(d.forecast_monthly_save) }} kr/mån{{ " (manuellt)" if d.config.get('forecast', {}).get('monthly_savings_override') is not none else " (budget)" }},
{{ d.forecast_growth }}% årlig tillväxt på investerat kapital.
<br><span style="color:#475569">Ändra tillväxtantagande i <a href="/edit" style="color:#a78bfa">Redigera → Prognos</a>.</span>
</div>

<!-- Visual bar chart for forecast -->
{% if d.forecast_rows %}
{% set fc_max = d.forecast_rows[-1].value %}
<div style="display:flex;align-items:flex-end;gap:6px;height:140px;padding:8px 0;margin-bottom:16px">
<div style="flex:1;position:relative;height:100%">
<div style="position:absolute;bottom:0;left:0;right:0;height:{{ (d.networth / fc_max * 100)|int }}%;background:#1f2937;border-radius:3px 3px 0 0"></div>
<div style="position:absolute;bottom:-18px;left:50%;transform:translateX(-50%);font-size:.6rem;color:#6b7280;white-space:nowrap">Nu</div>
</div>
{% for r in d.forecast_rows %}
<div style="flex:1;position:relative;height:100%">
<div style="position:absolute;bottom:0;left:0;right:0;height:{{ (r.value / fc_max * 100)|int }}%;background:{{ '#22c55e' if r.value < 10000000 else '#38bdf8' if r.value < 20000000 else '#fbbf24' }};border-radius:3px 3px 0 0"></div>
<div style="position:absolute;bottom:-18px;left:50%;transform:translateX(-50%);font-size:.6rem;color:#6b7280;white-space:nowrap">{{ r.year }}å</div>
</div>
{% endfor %}
</div>
{% endif %}

<table style="margin-top:24px">
<tr><th>År</th><th>Förmögenhet</th><th>Tillväxt (ränta-på-ränta)</th><th>Sparat (kum.)</th><th>4%-uttag/mån</th><th></th></tr>
{% for r in d.forecast_rows %}
<tr{% if r.year in [1,5,10] %} style="background:#1f2937"{% endif %}>
<td>{{ r.year }} år <span style="color:#475569;font-size:.7rem">({{ r.cal_year }})</span></td>
<td class="g"><strong>{{ "{:,.0f}".format(r.value) }} kr</strong></td>
<td class="b">{{ "{:+,.0f}".format(r.growth) }} kr</td>
<td>{{ "{:,.0f}".format(r.saved) }} kr</td>
<td style="color:#fbbf24">{{ "{:,.0f}".format(r.value * 0.04 / 12) }} kr</td>
<td>{% if r.value >= 10000000 %}{% set prev_found = [] %}{% for pr in d.forecast_rows %}{% if pr.year < r.year and pr.value >= 10000000 %}{% if prev_found.append(1) %}{% endif %}{% endif %}{% endfor %}{% if not prev_found %}<span class="badge bg">🎯 10M!</span>{% endif %}{% endif %}
{% if r.value >= 20000000 %}{% set prev_found2 = [] %}{% for pr in d.forecast_rows %}{% if pr.year < r.year and pr.value >= 20000000 %}{% if prev_found2.append(1) %}{% endif %}{% endif %}{% endfor %}{% if not prev_found2 %}<span class="badge bb">🎯 20M!</span>{% endif %}{% endif %}</td>
</tr>
{% endfor %}
</table>
<div style="margin-top:8px;font-size:.7rem;color:#475569">
Antar konstant sparkvot och {{ d.forecast_growth }}% årlig avkastning (ränta-på-ränta). Verkligt utfall varierar beroende på marknad, FX, och livshändelser.
</div>
</div>

</div>

</div>

<!-- HISTORY MODAL -->
<div class="modal-bg" id="histModal" onclick="if(event.target===this)closeHist()">
<div class="modal">
<button class="close" onclick="closeHist()">&times;</button>
<h2 id="histTitle">—</h2>
<div id="histSub" style="font-size:.8rem;color:#9ca3af;margin-bottom:12px"></div>
<div id="histChart" class="hist-chart"></div>
<table id="histTable" style="margin-top:8px">
<thead><tr><th>Datum</th><th>Värde</th><th>Förändring</th></tr></thead>
<tbody id="histBody"></tbody>
</table>
<div id="histEmpty" style="display:none;text-align:center;padding:30px;color:#6b7280">
Ingen historik ännu. Historik sparas automatiskt vid varje ögonblicksbild.<br>
Gå till <a href="/edit" style="color:#a78bfa">Redigera</a> och spara för att skapa en ögonblicksbild.
</div>
</div>
</div>

<script>
function sw(n){document.querySelectorAll('.tc').forEach(t=>t.classList.remove('active'));
document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
var el=document.getElementById('t-'+n);el.classList.add('active');event.target.classList.add('active');
window.scrollTo(0,0)}

function showHist(key, name){
  document.getElementById('histTitle').textContent=name+' — Historik';
  document.getElementById('histSub').textContent='Laddar...';
  document.getElementById('histChart').innerHTML='';
  var oldLbl=document.getElementById('histMonthLabels');if(oldLbl)oldLbl.remove();
  document.getElementById('histBody').innerHTML='';
  document.getElementById('histEmpty').style.display='none';
  document.getElementById('histTable').style.display='';
  document.getElementById('histModal').classList.add('open');

  fetch('/api/asset_history/'+encodeURIComponent(key))
    .then(r=>r.json())
    .then(function(data){
      var pts=data.points;
      if(!pts||pts.length===0){
        document.getElementById('histSub').textContent='';
        document.getElementById('histEmpty').style.display='block';
        document.getElementById('histTable').style.display='none';
        return;
      }
      // Summary with CAGR
      var firstVal=pts[0].value, lastVal=pts[pts.length-1].value;
      var diff=lastVal-firstVal;
      var pct=firstVal!==0?((lastVal/firstVal-1)*100).toFixed(1):'—';
      // Calculate years between first and last data point
      var d1=new Date(pts[0].date), d2=new Date(pts[pts.length-1].date);
      var yrs=((d2-d1)/(365.25*24*60*60*1000));
      var cagr='—';
      if(yrs>0.1 && firstVal>0 && lastVal>0){
        cagr=((Math.pow(lastVal/firstVal,1/yrs)-1)*100).toFixed(1);
      }
      var subHtml='Nuvarande: <strong style="color:#4ade80">'+fmt(lastVal)+' kr</strong> · '+
        'Förändring: <span style="color:'+(diff>=0?'#4ade80':'#f87171')+'">'+
        (diff>=0?'+':'')+fmt(diff)+' kr ('+pct+'%)</span>';
      if(cagr!=='—') subHtml+=' · <span style="color:#38bdf8">CAGR '+cagr+'%</span>';
      subHtml+=' · '+pts.length+' datapunkter ('+yrs.toFixed(1)+' år)';
      document.getElementById('histSub').innerHTML=subHtml;

      // Normalize to even monthly grid
      // 1. Index raw points by date (last value wins)
      var byDate={};
      pts.forEach(function(p){byDate[p.date]=p.value});
      var sortedDates=Object.keys(byDate).sort();

      // 2. Build monthly grid from first to last date
      var first=new Date(sortedDates[0]);
      var last=new Date(sortedDates[sortedDates.length-1]);
      var months=[];
      var d=new Date(first.getFullYear(), first.getMonth(), 1);
      while(d<=last||months.length===0){
        months.push(d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0'));
        d=new Date(d.getFullYear(), d.getMonth()+1, 1);
      }
      // Make sure we include the last month
      var lastMonth=last.getFullYear()+'-'+String(last.getMonth()+1).padStart(2,'0');
      if(months[months.length-1]!==lastMonth) months.push(lastMonth);

      // 3. For each month, pick the latest data point in that month (or carry forward)
      var grid=[];
      var lastVal=null;
      months.forEach(function(m){
        // Find all dates in this month
        var best=null;
        sortedDates.forEach(function(sd){
          if(sd.substring(0,7)===m) best=byDate[sd];
        });
        if(best!==null) lastVal=best;
        if(lastVal!==null) grid.push({month:m, value:lastVal, hasData:best!==null});
      });

      // Chart: even-width bars, one per month
      var max=Math.max.apply(null,grid.map(function(g){return Math.abs(g.value)}));
      if(max===0) max=1;
      var chart=document.getElementById('histChart');
      chart.innerHTML='';
      grid.forEach(function(g){
        var h=Math.max(4, Math.abs(g.value)/max*100);
        var bar=document.createElement('div');
        bar.className='hist-bar';
        bar.style.height=h+'%';
        bar.style.flex='1';
        bar.style.background=g.hasData?(g.value>=0?'#22c55e':'#f87171'):'#1f2937';
        bar.style.opacity=g.hasData?'1':'0.4';
        bar.innerHTML='<div class="ht">'+g.month+(g.hasData?'':' (uppskattad)')+'<br>'+fmt(g.value)+' kr</div>';
        chart.appendChild(bar);
      });
      // Month labels under chart (show every few months to avoid clutter)
      var lblRow=document.createElement('div');
      lblRow.id='histMonthLabels';
      lblRow.style.cssText='display:flex;gap:3px;margin-top:4px';
      var step=Math.max(1,Math.floor(grid.length/12));
      grid.forEach(function(g,i){
        var lbl=document.createElement('div');
        lbl.style.cssText='flex:1;text-align:center;font-size:.55rem;color:#6b7280';
        lbl.textContent=(i%step===0||i===grid.length-1)?g.month:'';
        lblRow.appendChild(lbl);
      });
      chart.parentNode.insertBefore(lblRow,chart.nextSibling);

      // Table: show only months with actual data
      var tbody=document.getElementById('histBody');
      tbody.innerHTML='';
      var dataGrid=grid.filter(function(g){return g.hasData});
      dataGrid.forEach(function(g,i){
        var tr=document.createElement('tr');
        var ch='—';
        if(i>0){
          var d2=g.value-dataGrid[i-1].value;
          ch='<span style="color:'+(d2>=0?'#4ade80':'#f87171')+'">'+(d2>=0?'+':'')+fmt(d2)+' kr</span>';
        }
        tr.innerHTML='<td>'+g.month+'</td><td style="color:#e2e8f0">'+fmt(g.value)+' kr</td><td>'+ch+'</td>';
        tbody.appendChild(tr);
      });
    });
}

function closeHist(){document.getElementById('histModal').classList.remove('open')}
function fmt(n){return n.toLocaleString('sv-SE',{maximumFractionDigits:0})}
document.addEventListener('keydown',function(e){if(e.key==='Escape')closeHist()});
</script>
</body></html>"""


def _background_refresh():
    """Run refresh_data in background thread."""
    global _refreshing
    if _refreshing:
        return
    _refreshing = True
    def _do():
        global _refreshing
        try:
            _cache['last_fetch'] = 0  # force refresh
            refresh_data()
        finally:
            _refreshing = False
    threading.Thread(target=_do, daemon=True).start()


@app.route('/')
@auth_required
def index():
    if request.args.get('force'):
        _cache['last_fetch'] = 0
        refresh_data()  # force = synchronous wait
    elif _cache['last_fetch'] == 0:
        # No data yet — start background fetch and show loading page
        _background_refresh()
        return '''<!DOCTYPE html><html><head><meta charset="utf-8">
        <title>Babalisk Economy — Loading</title>
        <meta http-equiv="refresh" content="5">
        <style>body{background:#0a0a0a;color:#e0e0e0;font-family:system-ui;
        display:flex;justify-content:center;align-items:center;height:100vh;margin:0}
        .box{text-align:center}.spinner{width:50px;height:50px;border:4px solid #333;
        border-top:4px solid #00d4aa;border-radius:50%;animation:spin 1s linear infinite;
        margin:0 auto 20px}@keyframes spin{to{transform:rotate(360deg)}}</style></head>
        <body><div class="box"><div class="spinner"></div>
        <h2>Babalisk Economy</h2><p>Hämtar marknadsdata... sidan laddas om automatiskt.</p>
        </div></body></html>'''
    elif time.time() - _cache['last_fetch'] > CACHE_DURATION:
        # Stale data — serve old data immediately, refresh in background
        _background_refresh()
    d = compute_networth()
    with _lock:
        screener = list(_cache['screener'])

    class D(dict):
        __getattr__ = dict.__getitem__
    class C(dict):
        __getattr__ = dict.__getitem__

    cfg = D(d['config'])
    cfg['budget'] = D(cfg.get('budget', {}))
    dd = D(d)
    dd['config'] = cfg

    # Smart DCA: skip overweight stocks, max 2 per sector
    MAX_WEIGHT = 0.10  # skip if >10% of portfolio
    MAX_SECTOR = 2
    DCA_SLOTS = 7
    holdings_weight = {}
    if d.get('stock_value_try') and d['stock_value_try'] > 0:
        for row in d.get('stock_rows', []):
            holdings_weight[row['ticker']] = row['value_try'] / d['stock_value_try']
    dca_picks = []
    dca_skipped = []
    dca_sectors = {}
    for s in screener:
        if len(dca_picks) >= DCA_SLOTS:
            break
        tk = s['ticker']
        weight = holdings_weight.get(tk, 0)
        sector = s.get('sector', 'Other')
        if weight > MAX_WEIGHT:
            dca_skipped.append({'ticker': tk, 'reason': 'övervikt %.0f%%' % (weight*100), 'rank': s['rank'], 'sector': sector})
            continue
        if dca_sectors.get(sector, 0) >= MAX_SECTOR:
            dca_skipped.append({'ticker': tk, 'reason': 'max 2 %s' % sector, 'rank': s['rank'], 'sector': sector})
            continue
        dca_picks.append(s)
        dca_sectors[sector] = dca_sectors.get(sector, 0) + 1

    # Last data fetch timestamp
    lf = _cache['last_fetch']
    data_updated = datetime.fromtimestamp(lf).strftime('%Y-%m-%d %H:%M') if lf else 'Aldrig'
    data_age_min = int((time.time() - lf) / 60) if lf else 999

    return render_template_string(HTML,
        d=dd, screener=screener, se_screener=list(_cache.get('se_screener', [])),
        dca_picks=dca_picks, dca_skipped=dca_skipped,
        idx=_cache['index'], idx_ch=_cache['index_ch'],
        now=datetime.now().strftime('%Y-%m-%d %H:%M'),
        data_updated=data_updated, data_age_min=data_age_min,
        refreshing=_refreshing,
        nw_grid=d.get('nw_grid', []), nw_max=d.get('nw_max', 1),
        nw_svg=d.get('nw_svg', ''),
        gs=d.get('growth_stats', {}))


@app.route('/api/networth')
@auth_required
def api_networth():
    refresh_data()
    d = compute_networth()
    return jsonify({k: v for k, v in d.items() if k not in ['config', 'stock_rows', 'crypto_rows']})

@app.route('/api/asset_history/<path:key>')
@auth_required
def api_asset_history(key):
    """Return historical values for a specific asset item."""
    cfg = load_config()
    history = cfg.get('networth_history', [])
    points = []
    for h in history:
        items = h.get('items', {})
        if key in items:
            points.append({'date': h['date'], 'value': items[key]})
    # Also add current live value
    refresh_data()
    d = compute_networth()
    today = datetime.now().strftime('%Y-%m-%d')
    snap = _make_snapshot(d, today)
    curr = snap.get('items', {}).get(key)
    if curr is not None:
        if not points or points[-1]['date'] != today:
            points.append({'date': today, 'value': curr})
        else:
            points[-1]['value'] = curr
    return jsonify({'key': key, 'points': points})


# ══════════════════════════════════════════════════════════════
# ADMIN — Edit config via web forms
# ══════════════════════════════════════════════════════════════
EDIT_HTML = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>Redigera — Brusk Ekonomi</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0f172a;color:#e2e8f0;font-family:system-ui;padding:20px;max-width:900px;margin:0 auto}
h1{color:#38bdf8;margin-bottom:10px}
a{color:#38bdf8}
.back{margin-bottom:20px;display:inline-block}
table{width:100%;border-collapse:collapse;margin-bottom:15px}
th,td{padding:6px 8px;text-align:left;border-bottom:1px solid #1e293b}
th{color:#94a3b8;font-size:0.85em}
select{background:#1e293b;border:1px solid #334155;color:#e2e8f0;padding:6px 10px;border-radius:4px}
input[type=text],input[type=number]{background:#1e293b;border:1px solid #334155;color:#e2e8f0;padding:6px 10px;border-radius:4px;width:100%}
input[type=number]{width:120px}
button,input[type=submit]{background:#38bdf8;color:#0f172a;border:none;padding:8px 20px;border-radius:6px;cursor:pointer;font-weight:bold;margin:5px 2px}
button:hover,input[type=submit]:hover{background:#7dd3fc}
.del{background:#ef4444;color:white;padding:4px 10px;font-size:0.85em}
.del:hover{background:#f87171}
.add{background:#22c55e;margin-top:5px}
.toast{position:fixed;top:20px;right:20px;background:#166534;color:#4ade80;padding:14px 24px;border-radius:10px;font-weight:600;font-size:.95rem;box-shadow:0 8px 30px rgba(0,0,0,.5);z-index:100;animation:slideIn .4s ease,fadeOut .5s ease 3s forwards;border:1px solid #22c55e}
@keyframes slideIn{from{transform:translateX(120%);opacity:0}to{transform:translateX(0);opacity:1}}
@keyframes fadeOut{from{opacity:1}to{opacity:0}}
.sec{background:#1e293b;border-radius:8px;margin-bottom:12px;overflow:hidden}
.sec-head{padding:14px 18px;cursor:pointer;display:flex;justify-content:space-between;align-items:center;user-select:none}
.sec-head:hover{background:#334155}
.sec-head h2{color:#a78bfa;margin:0;font-size:1rem}
.sec-head .arrow{color:#a78bfa;font-size:1.2rem;transition:transform .2s}
.sec-head.open .arrow{transform:rotate(90deg)}
.sec-body{display:none;padding:0 18px 15px}
.sec-body.open{display:block}
.nav{display:flex;flex-wrap:wrap;gap:8px;margin:15px 0}
.nav a{background:#1e293b;padding:8px 16px;border-radius:6px;text-decoration:none;color:#94a3b8;font-size:.85rem;border:1px solid #334155}
.nav a:hover{color:#e2e8f0;border-color:#a78bfa}
.save-bar{position:sticky;bottom:0;background:#0f172a;padding:12px 0;border-top:1px solid #334155;z-index:10}
</style></head><body>
<a href="/" class="back">&larr; Tillbaka till Dashboard</a>
<h1>Redigera Ekonomi</h1>
<p style="color:#6b7280;font-size:.85rem;margin-bottom:10px">Klicka på en sektion för att expandera. Tryck "Spara" längst ner — en datummärkt ögonblicksbild sparas automatiskt.</p>
{% if msg %}<div class="toast" id="toast">{{ msg }}</div>{% endif %}

<form method="POST" action="/edit">

<div class="sec"><div class="sec-head" onclick="tog(this)"><h2>Aktier (Turkiska)</h2><span class="arrow">&#9654;</span></div>
<div class="sec-body">
<table><tr><th>Ticker</th><th>Antal</th><th>Inköpskostnad (TRY)</th><th></th></tr>
{% for tk, s in config.stocks.items() %}
<tr><td><input type="text" name="stock_ticker_{{ loop.index0 }}" value="{{ tk }}"></td>
<td><input type="number" name="stock_shares_{{ loop.index0 }}" value="{{ s.shares }}"></td>
<td><input type="number" name="stock_cost_{{ loop.index0 }}" value="{{ s.cost }}"></td>
<td><button type="button" class="del" onclick="this.closest('tr').remove();reIdx(this)">Ta bort</button></td></tr>
{% endfor %}
</table>
<button type="button" class="add" onclick="addRow(this,'stock',[{name:'ticker',type:'text',val:''},{name:'shares',type:'number',val:'0'},{name:'cost',type:'number',val:'0'}])">+ Lägg till aktie</button>
</div></div>

<div class="sec"><div class="sec-head" onclick="tog(this)"><h2>Bankkonton</h2><span class="arrow">&#9654;</span></div>
<div class="sec-body">
<table><tr><th>Namn</th><th>Saldo (SEK)</th><th></th></tr>
{% for b in config.bank_accounts %}
<tr><td><input type="text" name="bank_name_{{ loop.index0 }}" value="{{ b.name }}"></td>
<td><input type="number" name="bank_sek_{{ loop.index0 }}" value="{{ b.sek }}"></td>
<td><button type="button" class="del" onclick="this.closest('tr').remove();reIdx(this)">Ta bort</button></td></tr>
{% endfor %}
</table>
<button type="button" class="add" onclick="addRow(this,'bank',[{name:'name',type:'text',val:'Nytt konto'},{name:'sek',type:'number',val:'0'}])">+ Lägg till konto</button>
</div></div>

<div class="sec"><div class="sec-head" onclick="tog(this)"><h2>Fastigheter</h2><span class="arrow">&#9654;</span></div>
<div class="sec-body">
<table><tr><th>Namn</th><th>Värde</th><th>Valuta</th></tr>
{% for r in config.real_estate %}
<tr><td><input type="text" name="re_name_{{ loop.index0 }}" value="{{ r.name }}"></td>
<td><input type="number" name="re_value_{{ loop.index0 }}" value="{{ r.get('value_try', r.get('value_sek', 0)) }}"></td>
<td><select name="re_currency_{{ loop.index0 }}"><option value="SEK" {{ 'selected' if 'value_sek' in r and 'value_try' not in r else '' }}>SEK</option><option value="TRY" {{ 'selected' if 'value_try' in r else '' }}>TRY</option></select></td></tr>
{% endfor %}
</table>
<div style="font-size:.75rem;color:#6b7280;margin-top:4px">Lån kopplas via Lån & Skulder nedan (fält "Fastighet")</div>
</div></div>

<div class="sec"><div class="sec-head" onclick="tog(this)"><h2>Lån & Skulder</h2><span class="arrow">&#9654;</span></div>
<div class="sec-body">
<table><tr><th>Namn</th><th>Belopp (SEK)</th><th>Ränta (decimal)</th><th>Fastighet</th><th></th></tr>
{% set prop_names = config.real_estate|map(attribute='name')|list %}
{% for l in config.loans + config.get('credits', []) %}
<tr><td><input type="text" name="loan_name_{{ loop.index0 }}" value="{{ l.name }}"></td>
<td><input type="number" name="loan_amount_{{ loop.index0 }}" value="{{ l.amount }}"></td>
<td><input type="number" name="loan_rate_{{ loop.index0 }}" value="{{ l.rate }}" step="0.001"></td>
<td><select name="loan_prop_{{ loop.index0 }}"><option value="">—</option>{% for p in prop_names %}<option value="{{ p }}" {{ 'selected' if l.get('property') == p else '' }}>{{ p }}</option>{% endfor %}</select></td>
<td><button type="button" class="del" onclick="this.closest('tr').remove();reIdx(this)">Ta bort</button></td></tr>
{% endfor %}
</table>
<button type="button" class="add" onclick="addRow(this,'loan',[{name:'name',type:'text',val:'Nytt lån'},{name:'amount',type:'number',val:'0'},{name:'rate',type:'number',val:'0.03',step:'0.001'},{name:'prop',type:'select',options:['—',{% for r in config.real_estate %}'{{ r.name }}',{% endfor %}]}])">+ Lägg till lån</button>
</div></div>

<div class="sec"><div class="sec-head" onclick="tog(this)"><h2>Crypto</h2><span class="arrow">&#9654;</span></div>
<div class="sec-body">
<table><tr><th>Namn</th><th>Symbol</th><th>Antal</th></tr>
{% for c in config.crypto %}
<tr><td><input type="text" name="crypto_name_{{ loop.index0 }}" value="{{ c.name }}"></td>
<td><input type="text" name="crypto_sym_{{ loop.index0 }}" value="{{ c.symbol }}"></td>
<td><input type="number" name="crypto_amount_{{ loop.index0 }}" value="{{ c.amount }}" step="0.0001"></td></tr>
{% endfor %}
</table>
</div></div>

<div class="sec"><div class="sec-head" onclick="tog(this)"><h2>Kontanter & Guld</h2><span class="arrow">&#9654;</span></div>
<div class="sec-body">
<table><tr><th>Kontant</th><th>Belopp (TRY)</th><th>Guld</th><th>Gram</th></tr>
{% for c in config.cash %}
<tr><td><input type="text" name="cash_name_{{ loop.index0 }}" value="{{ c.name }}"></td>
<td><input type="number" name="cash_try_{{ loop.index0 }}" value="{{ c.get('try',0) }}"></td>
<td>{% if loop.index0 < config.gold|length %}{{ config.gold[loop.index0].name }}{% endif %}</td>
<td>{% if loop.index0 < config.gold|length %}<input type="number" name="gold_grams_{{ loop.index0 }}" value="{{ config.gold[loop.index0].grams }}" step="0.1">{% endif %}</td></tr>
{% endfor %}
</table>
</div></div>

<div class="sec"><div class="sec-head" onclick="tog(this)"><h2>Budget</h2><span class="arrow">&#9654;</span></div>
<div class="sec-body">
<h3 style="color:#4ade80;margin-bottom:8px">Inkomster</h3>
<table><tr><th>Namn</th><th>SEK/mån</th><th></th></tr>
{% for i in config.budget.income %}
<tr><td><input type="text" name="inc_name_{{ loop.index0 }}" value="{{ i.name }}"></td>
<td><input type="number" name="inc_sek_{{ loop.index0 }}" value="{{ i.sek }}"></td>
<td><button type="button" class="del" onclick="this.closest('tr').remove();reIdx(this)">Ta bort</button></td></tr>
{% endfor %}
</table>
<button type="button" class="add" onclick="addRow(this,'inc',[{name:'name',type:'text',val:'Ny inkomst'},{name:'sek',type:'number',val:'0'}])">+ Lägg till inkomst</button>
<h3 style="color:#f87171;margin-top:16px;margin-bottom:8px">Utgifter</h3>
<table><tr><th>Namn</th><th>SEK/mån</th><th></th></tr>
{% for e in config.budget.expenses %}
<tr><td><input type="text" name="exp_name_{{ loop.index0 }}" value="{{ e.name }}"></td>
<td><input type="number" name="exp_sek_{{ loop.index0 }}" value="{{ e.sek }}"></td>
<td><button type="button" class="del" onclick="this.closest('tr').remove();reIdx(this)">Ta bort</button></td></tr>
{% endfor %}
</table>
<button type="button" class="add" onclick="addRow(this,'exp',[{name:'name',type:'text',val:'Ny utgift'},{name:'sek',type:'number',val:'0'}])">+ Lägg till utgift</button>
</div></div>

<div class="sec"><div class="sec-head" onclick="tog(this)"><h2>Prognos</h2><span class="arrow">&#9654;</span></div>
<div class="sec-body">
{% set fc = config.get('forecast', {}) %}
<table>
<tr><td>Årlig tillväxt (%)</td><td><input type="number" step="0.5" name="forecast_growth" value="{{ fc.get('annual_growth_pct', 7) }}"></td></tr>
<tr><td>Sparkvot (kr/mån)</td><td><input type="number" name="forecast_savings" value="{{ fc.get('monthly_savings_override', '') }}" placeholder="Auto från budget"></td></tr>
</table>
<div style="color:#6b7280;font-size:.8rem;margin-top:6px">Sparkvot: lämna tomt för att räkna från budget (inkomst − utgifter), eller ange manuellt belopp. T.ex. 15000 om du sparar 15k/mån.</div>
</div></div>

<div class="sec"><div class="sec-head" onclick="tog(this)"><h2>Screener-listor</h2><span class="arrow">&#9654;</span></div>
<div class="sec-body">
<div style="color:#6b7280;font-size:.8rem;margin-bottom:8px">Ange tickers separerade med komma. BIST-tickers utan suffix. Svenska tickers som på Yahoo Finance (t.ex. VOLV-B, SEB-A). Sektorer hämtas automatiskt.</div>
<label style="color:#94a3b8;font-size:.85rem">BIST Screener-tickers:</label>
<textarea name="bist_screener_tickers" rows="4" style="width:100%;background:#0f172a;border:1px solid #334155;color:#e2e8f0;padding:8px;border-radius:4px;font-family:monospace;font-size:.8rem;margin:4px 0 12px">{{ config.get('bist_screener_tickers', [])|join(', ') if config.get('bist_screener_tickers') else '' }}</textarea>
<label style="color:#94a3b8;font-size:.85rem">Sverige Screener-tickers:</label>
<textarea name="se_screener_tickers" rows="6" style="width:100%;background:#0f172a;border:1px solid #334155;color:#e2e8f0;padding:8px;border-radius:4px;font-family:monospace;font-size:.8rem;margin:4px 0">{{ config.get('se_screener_tickers', [])|join(', ') if config.get('se_screener_tickers') else '' }}</textarea>
<div style="color:#475569;font-size:.75rem;margin-top:4px">Lämna tomt för att använda standardlistan ({{ bist_default_count }} BIST + {{ se_default_count }} svenska).</div>
</div></div>

<div class="save-bar">
<input type="submit" name="action" value="Spara allt" style="font-size:1.1em;padding:10px 30px">
<span style="color:#6b7280;font-size:.8rem;margin-left:10px">Sparar + skapar automatisk ögonblicksbild med dagens datum</span>
</div>
</form>
<script>
function tog(el){el.classList.toggle('open');el.nextElementSibling.classList.toggle('open')}
var t=document.getElementById('toast');if(t)setTimeout(function(){t.remove()},3500)

/* Re-index all input/select names in the table after add/remove so indices are sequential */
function reIdx(el){
  var tbl=el.closest?el.closest('table'):el.parentNode.previousElementSibling;
  if(!tbl||tbl.tagName!=='TABLE') tbl=el.previousElementSibling;
  if(!tbl||tbl.tagName!=='TABLE') return;
  var rows=tbl.querySelectorAll('tr');
  var idx=0;
  for(var r=1;r<rows.length;r++){
    var fields=rows[r].querySelectorAll('input,select');
    fields.forEach(function(f){
      var n=f.getAttribute('name');
      if(n){f.setAttribute('name',n.replace(/_\d+$/,'_'+idx));}
    });
    idx++;
  }
}

function addRow(btn,prefix,fields){
  var tbl=btn.previousElementSibling;
  while(tbl&&tbl.tagName!=='TABLE') tbl=tbl.previousElementSibling;
  if(!tbl) return;
  var idx=tbl.rows.length-1;
  var tr=tbl.insertRow(-1);
  fields.forEach(function(f){
    var td=tr.insertCell(-1);
    if(f.type==='select'){
      var sel=document.createElement('select');
      sel.name=prefix+'_'+f.name+'_'+idx;
      f.options.forEach(function(o){var opt=document.createElement('option');opt.value=o;opt.textContent=o;sel.appendChild(opt)});
      td.appendChild(sel);
    } else {
      var inp=document.createElement('input');
      inp.type=f.type||'text';
      inp.name=prefix+'_'+f.name+'_'+idx;
      inp.value=f.val||'';
      if(f.step) inp.step=f.step;
      td.appendChild(inp);
    }
  });
  var td=tr.insertCell(-1);
  var b=document.createElement('button');b.type='button';b.className='del';b.textContent='Ta bort';
  b.onclick=function(){tr.remove();reIdx(btn)};
  td.appendChild(b);
}
</script>
</body></html>"""


@app.route('/edit', methods=['GET','POST'])
@auth_required
def edit_page():
    cfg = load_config()
    msg = None

    if request.method == 'POST':
        action = request.form.get('action', '')

        if action == 'Spara allt':
            # -- Stocks --
            new_stocks = {}
            i = 0
            while f'stock_ticker_{i}' in request.form:
                tk = request.form[f'stock_ticker_{i}'].strip().upper()
                if tk:
                    new_stocks[tk] = {
                        'shares': int(float(request.form.get(f'stock_shares_{i}', 0))),
                        'cost': int(float(request.form.get(f'stock_cost_{i}', 0)))
                    }
                i += 1
            cfg['stocks'] = new_stocks

            # -- Banks --
            new_banks = []
            i = 0
            while f'bank_name_{i}' in request.form:
                new_banks.append({
                    'name': request.form[f'bank_name_{i}'],
                    'sek': int(float(request.form.get(f'bank_sek_{i}', 0)))
                })
                i += 1
            cfg['bank_accounts'] = new_banks

            # -- Real estate --
            new_re = []
            i = 0
            while f're_name_{i}' in request.form:
                entry = {'name': request.form[f're_name_{i}']}
                val = int(float(request.form.get(f're_value_{i}', 0)))
                cur = request.form.get(f're_currency_{i}', 'SEK')
                if cur == 'TRY':
                    entry['value_try'] = val
                else:
                    entry['value_sek'] = val
                new_re.append(entry)
                i += 1
            cfg['real_estate'] = new_re

            # -- Loans & Credits --
            all_loans_raw = cfg.get('loans', []) + cfg.get('credits', [])
            n_orig_loans = len(cfg.get('loans', []))
            new_all = []
            i = 0
            while f'loan_name_{i}' in request.form:
                loan_entry = {
                    'name': request.form[f'loan_name_{i}'],
                    'amount': int(float(request.form.get(f'loan_amount_{i}', 0))),
                    'rate': float(request.form.get(f'loan_rate_{i}', 0))
                }
                prop = request.form.get(f'loan_prop_{i}', '').strip()
                if prop and prop != '—':
                    loan_entry['property'] = prop
                new_all.append(loan_entry)
                i += 1
            # Split back: loans = bostadslån, credits = rest
            cfg['loans'] = [l for l in new_all if 'bostads' in l['name'].lower() or 'bostad' in l['name'].lower()]
            cfg['credits'] = [l for l in new_all if l not in cfg['loans']]

            # -- Crypto --
            new_crypto = []
            i = 0
            while f'crypto_name_{i}' in request.form:
                new_crypto.append({
                    'name': request.form[f'crypto_name_{i}'],
                    'symbol': request.form[f'crypto_sym_{i}'],
                    'amount': float(request.form.get(f'crypto_amount_{i}', 0))
                })
                i += 1
            cfg['crypto'] = new_crypto

            # -- Cash --
            new_cash = []
            i = 0
            while f'cash_name_{i}' in request.form:
                new_cash.append({
                    'name': request.form[f'cash_name_{i}'],
                    'try': int(float(request.form.get(f'cash_try_{i}', 0)))
                })
                i += 1
            cfg['cash'] = new_cash

            # -- Gold --
            new_gold = []
            i = 0
            while f'gold_grams_{i}' in request.form:
                orig = cfg.get('gold', [])
                name = orig[i]['name'] if i < len(orig) else f'Gold {i+1}'
                new_gold.append({'name': name, 'grams': float(request.form[f'gold_grams_{i}'])})
                i += 1
            if new_gold:
                cfg['gold'] = new_gold

            # -- Budget --
            inc = []
            i = 0
            while f'inc_name_{i}' in request.form:
                inc_val = request.form.get(f'inc_sek_{i}', '').strip()
                inc.append({'name': request.form[f'inc_name_{i}'], 'sek': int(float(inc_val)) if inc_val else 0})
                i += 1
            exp = []
            i = 0
            while f'exp_name_{i}' in request.form:
                exp_val = request.form.get(f'exp_sek_{i}', '').strip()
                exp.append({'name': request.form[f'exp_name_{i}'], 'sek': int(float(exp_val)) if exp_val else 0})
                i += 1
            cfg['budget'] = {'income': inc, 'expenses': exp}

            # Forecast settings
            fg = request.form.get('forecast_growth')
            fs = request.form.get('forecast_savings', '').strip()
            fc_cfg = {'annual_growth_pct': float(fg) if fg else 7}
            if fs:
                fc_cfg['monthly_savings_override'] = int(float(fs))
            cfg['forecast'] = fc_cfg

            # Screener ticker lists
            bist_raw = request.form.get('bist_screener_tickers', '').strip()
            se_raw = request.form.get('se_screener_tickers', '').strip()
            if bist_raw:
                cfg['bist_screener_tickers'] = [t.strip().upper() for t in bist_raw.split(',') if t.strip()]
            else:
                cfg.pop('bist_screener_tickers', None)  # use defaults
            if se_raw:
                cfg['se_screener_tickers'] = [t.strip().upper() for t in se_raw.split(',') if t.strip()]
            else:
                cfg.pop('se_screener_tickers', None)  # use defaults

            save_config(cfg)
            _cache['last_fetch'] = 0  # invalidate cache so dashboard reloads fresh
            # Auto-save snapshot using CACHED data (no slow API calls)
            today = datetime.now().strftime('%Y-%m-%d')
            cfg['last_edit'] = today
            if _cache.get('prices'):
                try:
                    d = compute_networth()
                    snap = _make_snapshot(d, today)
                    history = cfg.get('networth_history', [])
                    if history and history[-1].get('date') == today:
                        history[-1] = snap
                    else:
                        history.append(snap)
                    cfg['networth_history'] = history
                    save_config(cfg)
                    msg = "Sparat + ögonblicksbild %s!" % today
                except:
                    save_config(cfg)
                    msg = "Sparat!"
            else:
                save_config(cfg)
                msg = "Sparat! (Ladda dashboarden för ögonblicksbild)"

    # Convert config to use D class for template access
    class D(dict):
        __getattr__ = dict.__getitem__
    cfg_d = D(cfg)
    cfg_d['budget'] = D(cfg.get('budget', {}))
    return render_template_string(EDIT_HTML, config=cfg_d, msg=msg,
        bist_default_count=len(DEFAULT_BIST_SCREENER),
        se_default_count=len(DEFAULT_SE_SCREENER))


# Load cache on import (works with both Gunicorn and direct run)
_load_cache_from_disk()
if _cache['last_fetch'] > 0:
    _background_refresh()  # refresh stale data in background

if __name__ == '__main__':
    # Save default config if not exists
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'w') as f:
            json.dump(get_default_config(), f, indent=2, ensure_ascii=False)
        print(f"Created config: {CONFIG_FILE}")

    print("=" * 60)
    print("BRUSK EKONOMI — Personal Finance Dashboard")
    print("=" * 60)
    print(f"Config: {CONFIG_FILE}")
    print(f"Server: http://localhost:5001")
    print(f"Refresh: every {CACHE_DURATION}s")
    print("=" * 60)

    # Load cached data from disk for instant startup
    has_cache = _load_cache_from_disk()
    if has_cache:
        print("  Sidan laddas direkt med cachad data!")
        print("  Ny data hämtas i bakgrunden...\n")
        # Start background refresh so data updates while user browses
        _background_refresh()
    else:
        print("\n  Första start — ingen cache finns.")
        print("  Första laddningen tar ~90s...\n")

    print("Press Ctrl+C to stop.\n")
    port = int(os.environ.get('PORT', 5001))
    debug = os.environ.get('RAILWAY_ENVIRONMENT') is None  # debug only locally
    app.run(host='0.0.0.0', port=port, debug=debug)

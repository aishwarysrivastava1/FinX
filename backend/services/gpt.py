# backend/services/gpt.py
import os, json, re, time, datetime
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(override=True)
from database import db_fetchall, db_fetchone, db_execute

# ── API keys ─────────────────────────────────────────────────
# Primary: Groq (key starts with "gsk_") or OpenRouter (key starts with "sk-or-")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
LLAMA_API_KEY = os.getenv("LLAMA_API_KEY", "").strip() or GROQ_API_KEY

# Provider defaults:
# - Groq (OpenAI-compatible): https://api.groq.com/openai/v1, key starts with "gsk_"
# - OpenRouter: https://openrouter.ai/api/v1, key starts with "sk-or-"
_env_base = os.getenv("LLAMA_BASE_URL", "").strip()
_env_model = os.getenv("LLAMA_MODEL", "").strip()

if not _env_base:
    if LLAMA_API_KEY.startswith("gsk_"):
        LLAMA_BASE_URL = "https://api.groq.com/openai/v1"
    else:
        LLAMA_BASE_URL = "https://openrouter.ai/api/v1"
else:
    LLAMA_BASE_URL = _env_base

if not _env_model:
    # Sensible defaults per provider
    if "groq.com" in LLAMA_BASE_URL:
        LLAMA_MODEL = "llama-3.3-70b-versatile"
    else:
        LLAMA_MODEL = "meta-llama/llama-3.3-70b-instruct"
else:
    LLAMA_MODEL = _env_model

# Kept as fallback only (if GROQ/LLAMA key isn't set)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()

# ── Prompt loader ────────────────────────────────────────────
PROMPTS_DIR = Path(__file__).parent.parent / 'prompts'

def load_prompt(filename: str) -> str:
    try:
        with open(PROMPTS_DIR / filename, 'r') as f:
            return f.read().strip()
    except Exception as e:
        print(f'[WARN] Could not load prompt {filename}: {e}')
        return ''

# Load at import time — fast path for every request
SYSTEM_PROMPT = load_prompt('system.txt')
SIGNAL_PROMPT = load_prompt('signal.txt')
CARD_PROMPT   = load_prompt('card.txt')

# ── OpenAI fallback ──────────────────────────────────────────
def _openai_generate(prompt: str, max_tokens: int = 1024, temperature: float = 0.3) -> str:
    """Call OpenAI gpt-4o-mini as fallback when Groq is unavailable."""
    if not OPENAI_API_KEY:
        print('[WARN] OPENAI_API_KEY missing — cannot use OpenAI fallback')
        raise RuntimeError('No AI API key configured')
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY, timeout=10)
        resp = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=[
                {'role': 'system', 'content': SYSTEM_PROMPT},
                {'role': 'user',   'content': prompt},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return resp.choices[0].message.content or ''
    except Exception as e:
        print(f'[OpenAI] Error: {e}')
        raise

def _openai_chat(messages: list, last_content: str) -> str:
    """Call OpenAI gpt-4o-mini for multi-turn chat fallback."""
    if not OPENAI_API_KEY:
        print('[WARN] OPENAI_API_KEY missing — cannot use OpenAI chat fallback')
        return 'AI service temporarily unavailable. Please check NSE India and ET Markets directly.'
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY, timeout=10)
        oai_messages = [{'role': 'system', 'content': SYSTEM_PROMPT}]
        for m in messages[:-1]:
            oai_messages.append({'role': m['role'], 'content': m['content']})
        oai_messages.append({'role': 'user', 'content': last_content})
        resp = client.chat.completions.create(
            model='gpt-4o-mini',
            messages=oai_messages,
            max_tokens=800,
            temperature=0.4,
        )
        return resp.choices[0].message.content or ''
    except Exception as e:
        print(f'[OpenAI Chat] Error: {e}')
        return 'I am having trouble connecting right now. Please check NSE India and ET Markets directly.'

# ── Llama 3.3 70B (OpenAI-compatible) ────────────────────────
def _llama_generate(prompt: str, max_tokens: int = 1024, temperature: float = 0.3) -> str:
    """
    Calls Llama-3.3-70B via an OpenAI-compatible endpoint.
    Defaults to OpenRouter; override with LLAMA_BASE_URL/LLAMA_MODEL.
    """
    if not LLAMA_API_KEY:
        # Keep existing behavior: if Llama key isn't configured, use existing OpenAI fallback.
        return _openai_generate(prompt, max_tokens=max_tokens, temperature=temperature)
    try:
        from openai import OpenAI
        client = OpenAI(api_key=LLAMA_API_KEY, base_url=LLAMA_BASE_URL, timeout=15)
        resp = client.chat.completions.create(
            model=LLAMA_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return resp.choices[0].message.content or ""
    except Exception as e:
        print(f"[Llama] Error: {e}")
        # Preserve resilience: fall back to existing OpenAI key if present.
        return _openai_generate(prompt, max_tokens=max_tokens, temperature=temperature)


def _llama_chat(messages: list, last_content: str) -> str:
    if not LLAMA_API_KEY:
        return _openai_chat(messages, last_content)
    try:
        from openai import OpenAI
        client = OpenAI(api_key=LLAMA_API_KEY, base_url=LLAMA_BASE_URL, timeout=15)
        oai_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for m in messages[:-1]:
            oai_messages.append({"role": m["role"], "content": m["content"]})
        oai_messages.append({"role": "user", "content": last_content})
        resp = client.chat.completions.create(
            model=LLAMA_MODEL,
            messages=oai_messages,
            max_tokens=800,
            temperature=0.4,
        )
        return resp.choices[0].message.content or ""
    except Exception as e:
        print(f"[Llama Chat] Error: {e}")
        return _openai_chat(messages, last_content)


# ── Primary AI call (Groq / OpenRouter / OpenAI-compatible) ──
def groq_call(
    prompt:       str,
    json_mode:    bool = False,
    max_tokens:   int  = 1024,
    temperature:  float = 0.3,
) -> str:
    """
    Primary AI call using Groq (Llama-3.3-70B). Falls back to OpenAI if needed.
    json_mode is best-effort (depends on provider support).
    """
    return _llama_generate(prompt, max_tokens=max_tokens, temperature=temperature)

# Alias for backward compatibility
gemini_call = groq_call

# ── Safe JSON parser ─────────────────────────────────────────
def parse_json_response(text: str, fallback: dict = None) -> dict:
    """Parses AI JSON response safely. Returns fallback on failure."""
    if not text:
        return fallback or {}
    try:
        cleaned = re.sub(r'```(?:json)?', '', text).strip().rstrip('`').strip()
        # Direct parse first
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass
        # Find the first {...} JSON object (handles leading/trailing prose)
        match = re.search(r'\{[\s\S]*\}', cleaned)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        print(f'[AI] JSON parse failed: {repr(text[:200])}')
        return fallback or {'error': 'Parse failed'}
    except Exception as e:
        print(f'[AI] JSON parse error: {e}')
        return fallback or {'error': 'Parse failed'}

# ── Live context builder ─────────────────────────────────────
def _get_card_tech(symbol: str) -> dict:
    """Fast card_cache lookup for technical fields. Never raises."""
    try:
        row = db_fetchone('SELECT card_json FROM card_cache WHERE symbol=?', (symbol,))
        if row and row.get('card_json'):
            card = json.loads(row['card_json'])
            return {
                'rsi':              card.get('rsi'),
                'rsi_zone':         card.get('rsi_zone'),
                'ema_signal':       card.get('ema_signal'),
                'ema20':            card.get('ema20'),
                'ema50':            card.get('ema50'),
                'sma200':           card.get('sma200'),
                'high_52w':         card.get('high_52w'),
                'low_52w':          card.get('low_52w'),
                'technical_snapshot': card.get('technical_snapshot'),
                'sentiment':        card.get('sentiment'),
                'sentiment_score':  card.get('sentiment_score'),
            }
    except Exception:
        pass
    return {}


def build_chat_context() -> str:
    """
    Builds live NSE context injected into every chat message.
    Includes: Nifty snapshot, recent Opportunity Radar signals with full technical
    data, recently viewed stock cards (from card_cache), and ET Markets headlines.
    """
    try:
        from services.indicators import get_nifty_snapshot
        from services.news_fetcher import get_market_headlines

        nifty     = get_nifty_snapshot()
        headlines = get_market_headlines(4)
        signals   = db_fetchall(
            'SELECT symbol, signal_type, explanation, risk_level, confidence '
            'FROM signals ORDER BY created_at DESC LIMIT 5'
        )

        today = datetime.date.today().isoformat()
        ctx   = f"\n\n--- LIVE NSE CONTEXT ({today}) ---\n"
        ctx  += f"Nifty 50: {nifty.get('nifty50', 'N/A')} "
        ctx  += f"({nifty.get('nifty50_change_pct', 'N/A')}% today, "
        ctx  += f"direction: {nifty.get('nifty50_direction', 'N/A')})\n"

        # ── Opportunity Radar signals ─────────────────────────
        ctx += "\nOpportunity Radar — recent bulk/block deal signals:\n"
        for i, s in enumerate(signals, 1):
            sym      = s['symbol']
            sig_type = (s.get('signal_type') or 'neutral').upper()
            risk     = s.get('risk_level', 'medium')
            snippet  = (s.get('explanation') or '')[:120]

            tech = _get_card_tech(sym)
            tech_parts = []
            if tech.get('rsi') is not None:
                zone = (tech.get('rsi_zone') or '').replace('_', ' ')
                tech_parts.append(f"RSI {tech['rsi']} ({zone})")
            if tech.get('ema_signal'):
                tech_parts.append(f"EMA {tech['ema_signal'].replace('_', ' ')}")
            if tech.get('sma200') is not None:
                current_price_proxy = tech.get('ema20') or 0
                trend = ('above SMA-200 — bullish structure'
                         if current_price_proxy > tech['sma200']
                         else 'below SMA-200 — bearish structure')
                tech_parts.append(trend)
            if tech.get('technical_snapshot'):
                # Include the full AI/rule-based snapshot for richer context
                ctx += f"{i}. {sym} [{sig_type}] risk:{risk}\n"
                ctx += f"   Technicals: {tech['technical_snapshot'][:160]}\n"
                ctx += f"   Signal: {snippet[:100]}...\n"
            else:
                tech_str = ' | '.join(tech_parts)
                ctx += f"{i}. {sym} [{sig_type}] risk:{risk}"
                if tech_str:
                    ctx += f" — {tech_str}"
                ctx += f"\n   {snippet[:100]}...\n"

        # ── Recently viewed stock cards (past 30 min from card_cache) ──
        try:
            recent_cards = db_fetchall(
                "SELECT symbol, card_json FROM card_cache "
                "WHERE expires_at > datetime('now') "
                "ORDER BY expires_at DESC LIMIT 6"
            )
            if recent_cards:
                ctx += "\nRecently viewed stocks (live card data):\n"
                for row in recent_cards:
                    sym = row['symbol']
                    if not row.get('card_json'):
                        continue
                    try:
                        card = json.loads(row['card_json'])
                        price   = card.get('current_price')
                        chg     = card.get('change_pct')
                        rsi     = card.get('rsi')
                        ema_sig = card.get('ema_signal', '')
                        sma200  = card.get('sma200')
                        snap    = card.get('technical_snapshot', '')

                        price_str = f"₹{price}" if price else "N/A"
                        chg_str   = f"{'+' if (chg or 0) >= 0 else ''}{chg}%" if chg is not None else ""
                        rsi_str   = f"RSI {rsi}" if rsi else ""
                        ema_str   = ema_sig.replace('_', ' ') if ema_sig else ""
                        sma_str   = (f"{'above' if price and price >= sma200 else 'below'} SMA-200 ₹{round(sma200):,}"
                                     if sma200 and price else "")
                        indicators = " | ".join(filter(None, [rsi_str, ema_str, sma_str]))

                        ctx += f"• {sym}: {price_str} {chg_str}"
                        if indicators:
                            ctx += f" | {indicators}"
                        ctx += "\n"
                        if snap and len(snap) > 30:
                            ctx += f"  Analysis: {snap[:180]}\n"
                    except Exception:
                        continue
        except Exception:
            pass

        ctx += "\nLatest ET Markets headlines:\n"
        for h in headlines:
            ctx += f"• {h[:120]}\n"
        ctx += "--- END CONTEXT ---"
        return ctx
    except Exception as e:
        print(f'[Context] Error building context: {e}')
        return ''

# ── Stock context injector ───────────────────────────────────
def _build_stock_context(user_message: str) -> str:
    """
    Detect NSE symbols in user message, fetch live quotes + technical indicators,
    and return an injected context block. Returns empty string if nothing found
    or API fails — never raises.
    """
    try:
        from services.nse_service import extract_symbols_from_text, get_quote
        from services.indicators import get_stock_data, interpret_rsi
        # uppercase so "reliance" → "RELIANCE" is detected
        candidates = extract_symbols_from_text(user_message.upper())
        if not candidates:
            return ''

        stock_blocks = []
        for sym in candidates[:3]:  # cap at 3 symbols per message
            q = get_quote(sym)
            if q and q.get('price') is not None:
                sign  = '+' if (q.get('change') or 0) >= 0 else ''
                pct   = q.get('percent_change')
                chg   = q.get('change')
                lines = [
                    f"Stock: {q['symbol']}",
                    f"Price: ₹{q['price']}",
                    f"Change: {sign}{chg} ({sign}{pct}%)",
                ]
                if q.get('high')       is not None: lines.append(f"Day High: ₹{q['high']}")
                if q.get('low')        is not None: lines.append(f"Day Low: ₹{q['low']}")
                if q.get('prev_close') is not None: lines.append(f"Prev Close: ₹{q['prev_close']}")
                if q.get('volume')     is not None: lines.append(f"Volume: {q['volume']:,}")

                # Enrich with technical indicators — card_cache first (fast), then live fetch
                try:
                    tech = {}
                    # Priority 1: card_cache (sub-ms SQLite read, has all indicators + snapshot)
                    cached_tech = _get_card_tech(sym)
                    if cached_tech.get('rsi') is not None or cached_tech.get('ema20') is not None:
                        tech = cached_tech
                    else:
                        # Priority 2: live get_stock_data (slower, uses close_series_cache)
                        fresh = get_stock_data(sym)
                        if 'error' not in fresh:
                            tech = fresh

                    rsi      = tech.get('rsi')
                    ema_signal = tech.get('ema_signal', '')
                    ema20    = tech.get('ema20')
                    ema50    = tech.get('ema50')
                    sma200   = tech.get('sma200')
                    high_52w = tech.get('high_52w')
                    low_52w  = tech.get('low_52w')
                    rsi_zone = tech.get('rsi_zone') or interpret_rsi(rsi)
                    snapshot = tech.get('technical_snapshot', '')

                    if rsi is not None or ema20 is not None or sma200 is not None:
                        lines.append("--- Technical Indicators ---")
                        if rsi is not None:
                            lines.append(f"RSI(14): {rsi} ({rsi_zone.replace('_', ' ')})")
                        if ema20 is not None:
                            lines.append(f"EMA-20: ₹{ema20}")
                        if ema50 is not None:
                            lines.append(f"EMA-50: ₹{ema50}")
                        if ema_signal:
                            lines.append(f"EMA Signal: {ema_signal.replace('_', ' ')}")
                        if sma200 is not None:
                            price_val = q.get('price')
                            sma_dir = ('above' if price_val and float(price_val) >= float(sma200) else 'below')
                            lines.append(f"SMA-200: ₹{sma200} (price is {sma_dir} — {'bullish' if sma_dir == 'above' else 'bearish'} long-term structure)")
                        if high_52w is not None:
                            lines.append(f"52W High: ₹{high_52w}")
                        if low_52w is not None:
                            lines.append(f"52W Low: ₹{low_52w}")
                        if snapshot and len(snapshot) > 30:
                            lines.append(f"Technical Summary: {snapshot[:200]}")
                except Exception:
                    pass  # technical data is optional — never block the chat

                stock_blocks.append('\n'.join(lines))

        if not stock_blocks:
            return ''

        return '\n\n[LIVE NSE DATA + TECHNICAL ANALYSIS]\n' + '\n\n'.join(stock_blocks) + '\n[END LIVE DATA]'
    except Exception as e:
        print(f'[StockContext] Error: {e}')
        return ''

# ── Rule-based signal engine ──────────────────────────────────
def _rule_based_signal_explanation(deal: dict, stock_data: dict) -> dict:
    """
    Rule-based signal generation used when both Groq + OpenAI are unavailable.
    The spec intentionally uses *only* RSI + EMA to derive `signal_type`.
    """
    symbol     = (deal.get('symbol') or stock_data.get('symbol') or 'UNKNOWN').upper()
    rsi = stock_data.get('rsi')
    ema_signal = (stock_data.get('ema_signal') or 'neutral').lower()
    ema_is_bullish = 'bullish' in ema_signal
    ema_is_bearish = 'bearish' in ema_signal

    # Spec-required signal type logic.
    signal_type = 'neutral'
    if rsi is not None:
        try:
            rsi_val = float(rsi)
            if rsi_val < 30 and ema_is_bullish:
                signal_type = 'bullish'
            elif rsi_val > 70:
                signal_type = 'bearish'
        except (TypeError, ValueError):
            signal_type = 'neutral'

    confidence = 45
    if signal_type == 'bullish':
        confidence = 65
    elif signal_type == 'bearish':
        confidence = 60

    # Lightweight risk mapping using RSI extremes.
    if signal_type == 'bearish':
        risk_level = 'high'
    elif signal_type == 'bullish':
        risk_level = 'medium'
    else:
        risk_level = 'low'

    rsi_part = f'RSI is {round(float(rsi), 1)}' if rsi is not None else 'RSI is unavailable'
    ema_part = f'EMA indicates {("upward" if ema_is_bullish else "downward" if ema_is_bearish else "neutral")} momentum'

    # Spec-required explanation shape: RSI zone + EMA momentum support.
    if signal_type == 'bullish':
        explanation = (
            f'{rsi_part} (oversold) and {ema_part} with bullish setup. '
            f'Rule-based fallback used because Groq/OpenAI is temporarily unavailable. '
            f'No AI provider available for deeper analysis.'
        )
    elif signal_type == 'bearish':
        explanation = (
            f'{rsi_part} (overbought). {ema_part}. '
            f'Rule-based fallback used because Groq/OpenAI is temporarily unavailable. '
            f'No AI provider available for deeper analysis.'
        )
    else:
        explanation = (
            f'{rsi_part}. {ema_part}. '
            f'Rule-based fallback used because Groq/OpenAI is temporarily unavailable. '
            f'No AI provider available for deeper analysis.'
        )

    key_obs = (
        'Oversold + bullish EMA setup suggests potential mean-reversion.' if signal_type == 'bullish' else
        'Overbought RSI suggests potential pullback risk.' if signal_type == 'bearish' else
        'Mixed RSI/EMA conditions — treat as neutral until AI is available.'
    )

    return {
        'explanation': explanation,
        'signal_type': signal_type,
        'risk_level': risk_level,
        'confidence': confidence,
        'key_observation': key_obs,
        'ai_provider': 'rule_based',
        'disclaimer': 'For educational purposes only. Not financial advice.',
    }


# ── Public API ────────────────────────────────────────────────

def explain_signal(deal: dict, stock_data: dict) -> dict:
    """
    Explains a raw NSE bulk/block deal. Returns structured dict.
    Tries AI first; falls back to rule-based engine — never returns generic
    'Signal analysis temporarily unavailable.' text.
    """
    try:
        prompt = SIGNAL_PROMPT.format(
            deal_json  = json.dumps(deal,       indent=2),
            price_json = json.dumps(stock_data, indent=2),
        )
        raw    = groq_call(prompt, json_mode=True, max_tokens=512)
        result = parse_json_response(raw, fallback=None)
        if result and result.get('explanation') and \
                result['explanation'] not in ('Signal analysis temporarily unavailable.', ''):
            # Ensure risk_level is one of the valid values
            if result.get('risk_level') not in ('low', 'medium', 'high'):
                result['risk_level'] = 'medium'
            return result
    except Exception as e:
        print(f'[AI] explain_signal error: {e}')

    # AI unavailable or returned bad data — use rule-based fallback
    print(f'[AI] Using rule-based fallback for {deal.get("symbol", "?")}')
    return _rule_based_signal_explanation(deal, stock_data)

def generate_signal_card(symbol: str, stock_data: dict, news: list) -> dict:
    """Generates a full NSE Signal Card for a stock ticker."""
    _fallback = {
        'symbol':              symbol.upper(),
        'sentiment':           'neutral',
        'sentiment_score':     50,
        'sentiment_reason':    'Analysis temporarily unavailable.',
        'technical_snapshot':  'Technical analysis unavailable.',
        'news_impact_score':   50,
        'news_impact_summary': 'News data unavailable.',
        'risk_flags':          [],
        'actionable_context':  'Please check NSE and ET Markets directly.',
        'disclaimer':          'For educational purposes only. Not financial advice.',
    }
    try:
        news_text = '\n'.join(f"- {n['headline']}" for n in news[:5]) \
                    or 'No recent news available.'
        prompt = CARD_PROMPT.format(
            symbol         = symbol.upper(),
            price_json     = json.dumps(stock_data, indent=2),
            news_headlines = news_text,
        )
        raw = groq_call(prompt, json_mode=True, max_tokens=768)
        return parse_json_response(raw, fallback=_fallback)
    except Exception as e:
        print(f'[AI] generate_signal_card error: {e}')
        return _fallback

def chat_response(messages: list) -> str:
    """
    Multi-turn chat using Llama (preferred) or OpenAI fallback.
    Never crashes — returns a safe fallback string on all failures.
    """
    context  = build_chat_context()
    last_msg = messages[-1] if messages else None

    if not last_msg or last_msg.get('role') != 'user':
        return 'I did not receive a valid message. Please try again.'

    # Inject live NSE stock data if a ticker is detected in the message
    stock_context = _build_stock_context(last_msg['content'])
    augmented_content = last_msg['content'] + stock_context + context

    raw = _llama_chat(messages, augmented_content)
    return _format_chat_reply(raw)


def _format_chat_reply(text: str) -> str:
    """
    Normalizes model output for the current chat UI:
    - removes markdown markers like ** and leading *
    - keeps clear section headings
    - uses plain bullet points
    """
    if not text:
        return "TL;DR: I am unable to generate a response right now."

    cleaned = text.replace("**", "").strip()
    lines = [ln.rstrip() for ln in cleaned.splitlines()]
    out = []

    heading_aliases = {
        "tl;dr": "TL;DR",
        "what i'm seeing": "What I'm seeing",
        "why it matters": "Why it matters",
        "levels / signals to watch": "Levels / signals to watch",
        "next best step": "Next best step",
    }

    def _to_unicode_bold(s: str) -> str:
        # Unicode Mathematical Alphanumeric Symbols (bold)
        out_s = []
        for ch in s:
            o = ord(ch)
            if 0x41 <= o <= 0x5A:  # A-Z
                out_s.append(chr(0x1D400 + (o - 0x41)))
            elif 0x61 <= o <= 0x7A:  # a-z
                out_s.append(chr(0x1D41A + (o - 0x61)))
            else:
                out_s.append(ch)
        return "".join(out_s)

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            if out and out[-1] != "":
                out.append("")
            continue

        # Remove TL;DR lines completely (user requested no TL;DR)
        tl = line.lower().replace("**", "").strip()
        if tl.startswith("tl;dr:") or tl == "tl;dr" or tl == "tl;dr:":
            continue

        # Normalize markdown list markers
        if line.startswith("* "):
            line = f"- {line[2:].strip()}"
        elif line.startswith("- * "):
            line = f"- {line[4:].strip()}"
        elif re.match(r"^\d+\.\s+", line):
            line = "- " + re.sub(r"^\d+\.\s+", "", line)

        # Normalize heading forms like "- Heading:", "Heading:", "**Heading**:"
        heading_candidate = re.sub(r"^[-*]\s*", "", line).strip()
        if ":" in heading_candidate:
            key = heading_candidate.split(":", 1)[0].strip().lower().replace("’", "'")
            if key in heading_aliases:
                rest = heading_candidate.split(":", 1)[1].strip()
                # Output bold section headings, no markdown list markers needed.
                out.append(_to_unicode_bold(heading_aliases[key]))
                if rest:
                    if rest.startswith("* "):
                        rest = rest[2:].strip()
                    out.append(f"- {rest}")
                continue

        out.append(line)

    # Remove duplicate blank lines
    final_lines = []
    for ln in out:
        if ln == "" and final_lines and final_lines[-1] == "":
            continue
        final_lines.append(ln)

    return "\n".join(final_lines).strip()

# backend/services/audio_briefing.py
import json
from datetime import datetime, timedelta
from database import db_fetchall
from services.gpt import groq_call, load_prompt

def generate_market_minutes() -> dict:
    """
    Synthesizes the top 5 'Radar' signals from the last 24 hours into a 100-word script.
    Optimized for Text-To-Speech.
    """
    try:
        cutoff = (datetime.utcnow() - timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')
        signals = db_fetchall(
            "SELECT symbol, signal_type, explanation FROM signals WHERE created_at >= ? ORDER BY created_at DESC LIMIT 5",
            (cutoff,)
        )
        
        if not signals:
            return {"script": "Welcome to Fin-X Market Minutes. There have been no new major radar signals detected in the last twenty four hours. Stay tuned for further updates."}
            
        formatted_signals = "\n".join([f"- {s['symbol']} ({s['signal_type']}): {s['explanation']}" for s in signals])
        
        prompt_template = load_prompt("audio_script.txt")
        if not prompt_template:
            prompt_template = "Synthesize these signals into a 100-word spoken script for a market briefing: {radar_signals}"
            
        prompt = prompt_template.format(radar_signals=formatted_signals)
        # Using a slightly higher temperature for creative, punchy synthesis
        script = groq_call(prompt, max_tokens=256, temperature=0.5)
        
        if not script:
            script = "Welcome to Fin-X Market Minutes. We are currently processing the latest signals and will be back with your brief shortly."
            
        # Strip any markdown framing that might have slipped through
        script = script.replace("*", "").replace("`", "").strip()
        
        return {"script": script}
        
    except Exception as e:
        print(f"[AudioBriefing] Error: {e}")
        return {"script": "Welcome to Fin-X Market Minutes. Our AI is currently offline. Please check the dashboard for the latest opportunities."}

import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import time
import re
import os
from email.utils import parsedate_to_datetime

# --- CONFIGURAZIONE NOTIFICHE ---
TG_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TG_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def send_telegram_alert(title, link, source):
    """Invia un messaggio su Telegram se le chiavi sono presenti."""
    if not TG_TOKEN or not TG_CHAT_ID:
        return 
    
    message = f"🚨 *Nuovo Evento CAI*\n\n📍 *{source}*\n📝 {title}\n\n🔗 [Leggi di più]({link})"
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    data = {
        "chat_id": TG_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, data=data)
        time.sleep(1)
    except Exception as e:
        print(f"Errore invio Telegram: {e}")

# --- FUNZIONI DI SUPPORTO ---

def clean_html(raw_html):
    """Rimuove i tag HTML per pulire il riassunto."""
    cleanr = re.compile('<.*?>')
    cleantext = re.sub(cleanr, '', raw_html)
    return cleantext

def is_recent(dt_obj):
    """Controlla se l'evento è stato pubblicato nelle ultime 9 ore."""
    now = datetime.now()
    diff = now - dt_obj
    return diff < timedelta(hours=9)

def get_sansepolcro_pdfs():
    """Scarica i PDF dalle pagine specifiche di CAI Sansepolcro, evitando duplicati."""
    
    # LISTA DELLE PAGINE DA CONTROLLARE (Scraping extra oltre ai feed)
    urls_to_scrape = [
        "https://www.caisansepolcro.it/prossima-escursione/",
        "https://www.caisansepolcro.it/prossime-escursioni-con-prenotazione/"
    ]
    
    pdf_events = []
    seen_urls = set()
    
    for url in urls_to_scrape:
        print(f"Scraping extra: {url}...")
        
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (compatible; CAI-Aggregator/1.0)'}
            response = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            for link in soup.find_all('a'):
                href = link.get('href')
                
                # Cerca solo i PDF
                if href and href.lower().endswith('.pdf'):
                    if not href.startswith('http'):
                        href = "https://www.caisansepolcro.it" + href.lstrip('/')
                    
                    if href in seen_urls: continue
                    
                    title_text = link.get_text(strip=True)
                    ignore_words = ['download', 'scarica', 'pdf', 'clicca qui', 'leggi', 'programma']
                    
                    if not title_text or title_text.lower() in ignore_words:
                        if link.get('title'): title_text = link.get('title')
                        else: pass 

                    if not title_text or title_text.lower() in ignore_words:
                        title_text = "Programma Escursione (PDF)"

                    seen_urls.add(href)

                    try:
                        head_req = requests.head(href, headers=headers, timeout=5)
                        last_mod = head_req.headers.get('Last-Modified')
                        if last_mod:
                            dt_obj = parsedate_to_datetime(last_mod).replace(tzinfo=None)
                        else:
                            dt_obj = datetime.now()
                    except:
                        dt_obj = datetime.now()
                    
                    # NOTIFICA TELEGRAM
                    if is_recent(dt_obj):
                        print(f"--> Notifica inviata per: {title_text}")
                        send_telegram_alert(f"📄 [PDF] {title_text}", href, "CAI Sansepolcro")

                    pdf_events.append({
                        "title": f"📄 [PDF] {title_text}",
                        "link": href,
                        "date": dt_obj,
                        "summary": "Documento scaricabile dalla sezione Escursioni Sansepolcro.",
                        "source": "CAI Sansepolcro",
                        "color": "#3498db"
                    })
        except Exception as e:
            print(f"Errore scraping su {url}: {e}")
            
    return pdf_events

# --- CONFIGURAZIONE GRUPPI (AGGIORNATA) ---
GROUPS = {
    "index.html": {
        "title": "Toscana Est (Arezzo, Sansepolcro, Stia-Casentino, Valdarno Superiore)",
        "sites": [
            {"url": "https://www.caiarezzo.it/feed/", "name": "CAI Arezzo", "color": "#e74c3c"},
            {"url": "https://caivaldarnosuperiore.it/feed/", "name": "CAI Valdarno Sup.", "color": "#2ecc71"},
            {"url": "https://caistia.it/feed/", "name": "CAI Stia", "color": "#f1c40f"},
            {"url": "https://www.caisansepolcro.it/prossima-serata/feed/", "name": "CAI Sansepolcro", "color": "#3498db"}
        ]
    },
    "costa.html": {
        "title": "Toscana Ovest (Pisa, Livorno, Lucca, Valdarno Inferiore, Viareggio)",
        "sites": [
            {"url": "https://www.caipisa.it/feed/", "name": "CAI Pisa", "color": "#e67e22"},
            {"url": "https://www.caivaldarnoinferiore.it/feed/", "name": "CAI Valdarno Inf.", "color": "#1abc9c"},
            {"url": "https://organizzazione.cai.it/sez-livorno/feed/", "name": "CAI Livorno", "color": "#9b59b6"},
            {"url": "https://www.cailucca.it/feed/", "name": "CAI Lucca", "color": "#34495e"},
            {"url": "https://www.caiviareggio.it/feed/", "name": "CAI Viareggio", "color": "#

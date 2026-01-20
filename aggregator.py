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
            {"url": "https://www.caiviareggio.it/feed/", "name": "CAI Viareggio", "color": "#2980b9"}
        ]
    }
}

def get_nav_html(current_page):
    nav = '<nav style="margin-bottom: 30px; text-align: center;">'
    for filename, data in GROUPS.items():
        style = 'display: inline-block; text-decoration: none; margin: 5px 10px; padding: 8px 15px; border-radius: 20px; font-weight: bold;'
        if filename == current_page:
            style += 'background-color: #2563eb; color: white;'
        else:
            style += 'background-color: #e5e7eb; color: #333;'
        nav += f'<a href="{filename}" style="{style}">{data["title"]}</a>'
    nav += '</nav>'
    return nav

def generate_page(filename, group_data):
    print(f"--- Elaborazione gruppo: {group_data['title']} ---")
    events = []
    
    # 1. SCARICA DAI FEED RSS
    for site in group_data["sites"]:
        print(f"Scaricando {site['name']}...")
        try:
            feed = feedparser.parse(site['url'])
            if not feed.entries:
                continue

            for entry in feed.entries:
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    dt_obj = datetime.fromtimestamp(time.mktime(entry.published_parsed))
                elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                    dt_obj = datetime.fromtimestamp(time.mktime(entry.updated_parsed))
                else:
                    dt_obj = datetime.now()
                
                # NOTIFICA TELEGRAM
                if is_recent(dt_obj):
                    print(f"--> Notifica inviata per: {entry.title}")
                    send_telegram_alert(entry.title, entry.link, site['name'])

                summary = entry.get("summary", "")
                summary_clean = clean_html(summary)
                if len(summary_clean) > 250:
                    summary_clean = summary_clean[:250] + "..."

                events.append({
                    "title": entry.title,
                    "link": entry.link,
                    "date": dt_obj,
                    "summary": summary_clean,
                    "source": site["name"],
                    "color": site["color"]
                })
        except Exception as e:
            print(f"Errore su {site['name']}: {e}")

    # 2. CONTROLLO SPECIALE SANSEPOLCRO (SOLO INDEX)
    # Esegue lo scraping dei PDF oltre al nuovo feed RSS specificato
    if filename == "index.html":
        sansepolcro_pdfs = get_sansepolcro_pdfs()
        if sansepolcro_pdfs:
            events.extend(sansepolcro_pdfs)

    # 3. ORDINA TUTTO PER DATA
    events.sort(key=lambda x: x["date"], reverse=True)

    # 4. GENERA HTML
    nav_html = get_nav_html(filename)
    
    html = f"""
    <!DOCTYPE html>
    <html lang="it">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{group_data['title']} - Aggregatore CAI</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap" rel="stylesheet">
        <style>
            body {{ font-family: 'Inter', sans-serif; background-color: #f3f4f6; color: #1f2937; margin: 0; padding: 20px; }}
            .container {{ max-width: 800px; margin: 0 auto; }}
            header {{ text-align: center; margin-bottom: 20px; }}
            h1 {{ color: #111827; margin-bottom: 5px; font-size: 1.8rem; }}
            .meta {{ color: #6b7280; font-size: 0.9em; margin-bottom: 20px; }}
            .card {{ background: white; border-radius: 12px; padding: 24px; margin-bottom: 24px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); border-left: 6px solid #ccc; transition: transform 0.2s; }}
            .card:hover {{ transform: translateY(-2px); box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1); }}
            .badge {{ display: inline-block; padding: 4px 12px; border-radius: 9999px; color: white; font-size: 0.75rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; }}
            .date {{ float: right; color: #6b7280; font-size: 0.875rem; }}
            h2 {{ margin-top: 12px; margin-bottom: 8px; font-size: 1.25rem; }}
            h2 a {{ text-decoration: none; color: #111827; }}
            h2 a:hover {{ color: #2563eb; }}
            .desc {{ color: #4b5563; line-height: 1.5; font-size: 0.95rem; margin-bottom: 16px; }}
            .read-more {{ display: inline-block; color: #2563eb; font-weight: 600; text-decoration: none; }}
            .read-more:hover {{ text-decoration: underline; }}
        </style>
    </head>
    <body>
        <div class="container">
            {nav_html}
            <header>
                <h1>{group_data['title']}</h1>
                <div class="meta">Aggiornato: {datetime.now().strftime('%d/%m/%Y alle %H:%M')}</div>
            </header>
    """

    for event in events:
        date_str = event["date"].strftime("%d/%m/%Y")
        html += f"""
            <div class="card" style="border-left-color: {event['color']}">
                <div>
                    <span class="badge" style="background-color: {event['color']}">{event['source']}</span>
                    <span class="date">{date_str}</span>
                </div>
                <h2><a href="{event['link']}" target="_blank">{event['title']}</a></h2>
                <div class="desc">{event['summary']}</div>
                <a href="{event['link']}" class="read-more" target="_blank">Leggi di più &rarr;</a>
            </div>
        """

    html += """
        </div>
    </body>
    </html>
    """

    with open(filename, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Generato {filename}")

# --- ESECUZIONE PRINCIPALE ---
for filename, group_data in GROUPS.items():
    generate_page(filename, group_data)

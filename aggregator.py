import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import time
import re
import os
from email.utils import parsedate_to_datetime
from facebook_scraper import get_posts

# --- CONFIGURAZIONE NOTIFICHE ---
TG_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TG_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def send_telegram_alert(title, link, source):
    if not TG_TOKEN or not TG_CHAT_ID: return 
    message = f"🚨 *Nuovo Evento CAI Toscana*\n\n📍 *{source}*\n📝 {title}\n\n🔗 [Leggi di più]({link})"
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
    cleanr = re.compile('<.*?>')
    return re.sub(cleanr, '', raw_html)

def is_recent(dt_obj):
    # Controllo sulle ultime 6 ore
    return (datetime.now() - dt_obj) < timedelta(hours=6)

def clean_filename(url):
    """Estrae un titolo leggibile dal nome del file nell'URL."""
    try:
        filename = url.split('/')[-1]
        name = filename.rsplit('.', 1)[0]
        name = name.replace('cropped-', '').replace('scaled-', '')
        name = name.replace('-', ' ').replace('_', ' ')
        name = re.sub(r'\s\d+x\d+$', '', name) 
        return name.title()
    except:
        return ""

def extract_date_from_url(url):
    """Cerca pattern tipo /2026/02/ nell'URL per datare l'immagine."""
    try:
        match = re.search(r'/(\d{4})/(\d{2})/', url)
        if match:
            year = int(match.group(1))
            month = int(match.group(2))
            return datetime(year, month, 1)
    except:
        pass
    return None

def format_date_friendly(dt):
    """Formatta la data in italiano (es. Domenica 12 Maggio)."""
    days = ['Lunedì', 'Martedì', 'Mercoledì', 'Giovedì', 'Venerdì', 'Sabato', 'Domenica']
    months = ['Gennaio', 'Febbraio', 'Marzo', 'Aprile', 'Maggio', 'Giugno', 'Luglio', 'Agosto', 'Settembre', 'Ottobre', 'Novembre', 'Dicembre']
    return f"{days[dt.weekday()]} {dt.day} {months[dt.month-1]} {dt.year}"

# --- ESTRAZIONE INTELLIGENTE DATE EVENTI ---
def extract_event_date_from_text(text):
    """
    Cerca di indovinare la data dell'evento dal testo (Titolo o descrizione).
    """
    if not text: return None
    text = text.lower()
    months = {
        'gennaio': 1, 'gen': 1, 'febbraio': 2, 'feb': 2, 'marzo': 3, 'mar': 3,
        'aprile': 4, 'apr': 4, 'maggio': 5, 'mag': 5, 'giugno': 6, 'giu': 6,
        'luglio': 7, 'lug': 7, 'agosto': 8, 'ago': 8, 'settembre': 9, 'set': 9, 'sett': 9,
        'ottobre': 10, 'ott': 10, 'novembre': 11, 'nov': 11, 'dicembre': 12, 'dic': 12
    }
    
    today = datetime.now()
    found_date = None

    # 1. Cerca formato dd/mm/yyyy
    match_full = re.search(r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})', text)
    if match_full:
        try:
            d, m, y = int(match_full.group(1)), int(match_full.group(2)), int(match_full.group(3))
            found_date = datetime(y, m, d)
        except: pass

    # 2. Cerca formato dd/mm (presume anno corrente o prossimo)
    if not found_date:
        match_short = re.search(r'(\d{1,2})[/-](\d{1,2})', text)
        if match_short:
            try:
                d, m = int(match_short.group(1)), int(match_short.group(2))
                y = today.year
                temp_date = datetime(y, m, d)
                # Se la data è passata da più di 30 giorni, probabilmente è dell'anno prossimo
                if temp_date < today - timedelta(days=30):
                    y += 1
                found_date = datetime(y, m, d)
            except: pass

    # 3. Cerca formato testuale
    if not found_date:
        for m_name, m_num in months.items():
            pattern = r'(\d{1,2})\s+(?:di\s+)?' + m_name
            match_txt = re.search(pattern, text)
            if match_txt:
                try:
                    d = int(match_txt.group(1))
                    y = today.year
                    temp_date = datetime(y, m_num, d)
                    if temp_date < today - timedelta(days=60):
                        y += 1
                    found_date = datetime(y, m, d)
                    break 
                except: pass
    
    if found_date:
        return found_date
            
    return None

# --- SCRAPER SPECIFICI ---

def get_sansepolcro_media():
    urls = [
        "https://www.caisansepolcro.it/prossima-escursione/",
        "https://www.caisansepolcro.it/prossime-escursioni-con-prenotazione/",
        "https://www.caisansepolcro.it/prossima-serata/"
    ]
    return scrape_generic_media(urls, "CAI Sansepolcro", "https://www.caisansepolcro.it")

def get_grosseto_media():
    urls = ["https://caigrosseto.it/prossimi-eventi/"]
    return scrape_generic_media(urls, "CAI Grosseto", "https://caigrosseto.it", color="#16a085")

def get_carrara_calendar():
    """Scraper specifico per il calendario tabellare di CAI Carrara"""
    url = "https://www.caicarrara.it/calendario-cai-carrara/calendario-generale-cai/calendario-generale-cai-carrara/"
    source_name = "CAI Carrara Cal."
    color = "#7f8c8d" # Grigio
    events = []
    
    print(f"Scraping Calendario {source_name}...")
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (compatible; CAI-Aggregator/1.0)'}
        resp = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Cerca nel contenuto principale (spesso entry-content in WP)
        content = soup.find('div', class_='entry-content') or soup.body
        
        # Analizza righe di tabelle (tr), elementi lista (li) o paragrafi (p)
        # Questo approccio cerca qualsiasi testo che contenga una data
        for tag in content.find_all(['tr', 'li', 'p']):
            text = tag.get_text(" ", strip=True)
            
            # Cerca data
            event_date = extract_event_date_from_text(text)
            
            # Se trova una data futura (o 2026+)
            if event_date and event_date.year >= 2026:
                
                # Cerca link eventuale
                link_tag = tag.find('a')
                if link_tag and link_tag.get('href'):
                    link = link_tag.get('href')
                    if not link.startswith('http'): link = "https://www.caicarrara.it" + link
                else:
                    link = url # Se non c'è link specifico, usa quello del calendario
                
                # Pulisce titolo (taglia se troppo lungo)
                title = text[:150] + "..." if len(text) > 150 else text
                full_title = f"📅 {title}"

                # Evita duplicati identici
                if any(e['title'] == full_title for e in events): continue

                # Notifica (facoltativa per scraping massivo, qui la lasciamo se recente)
                # Ma per il calendario statico, difficile dire quando è stato "pubblicato".
                # Usiamo datetime.now() come data scoperta.
                
                events.append({
                    "title": full_title,
                    "link": link,
                    "date": datetime.now(), # Data scoperta
                    "summary": "Evento estratto dal calendario generale CAI Carrara",
                    "source": source_name,
                    "color": color,
                    "event_date": event_date
                })
                
    except Exception as e:
        print(f"Errore scraping Carrara: {e}")
        
    return events

def get_facebook_events(page_url, source_name, color):
    """Scarica gli ultimi post da una pagina Facebook pubblica usando facebook-scraper."""
    print(f"Scraping Facebook per {source_name}...")
    fb_events = []
    
    # Estrae l'ID o nome pagina dall'URL
    try:
        if "profile.php" in page_url:
            page_id = page_url.split('id=')[-1]
        elif "groups" in page_url:
            page_id = page_url.rstrip('/').split('/')[-1]
        else:
            page_id = page_url.rstrip('/').split('/')[-1]
    except:
        page_id = page_url 

    try:
        # Scarica 2 pagine di post
        for post in get_posts(page_id, pages=2):
            try:
                post_text = post.get('text', '')
                post_time = post.get('time')
                post_url = post.get('post_url')
                
                if not post_time: post_time = datetime.now()
                
                title = " ".join(post_text.split()[:10]) + "..." if post_text else "Post Facebook"
                full_title = f"📘 [FB] {title}"
                
                event_date = extract_event_date_from_text(post_text)

                if is_recent(post_time):
                    send_telegram_alert(full_title, post_url, source_name)
                
                fb_events.append({
                    "title": full_title,
                    "link": post_url,
                    "date": post_time,
                    "summary": post_text[:300] + "...",
                    "source": source_name,
                    "color": color,
                    "event_date": event_date
                })
            except Exception as e:
                continue
                
    except Exception as e:
        print(f"Errore scraping Facebook {source_name} ({page_id}): {e}")
        pass
        
    return fb_events

def scrape_generic_media(urls, source_name, base_domain, color="#3498db"):
    EXTS = ('.pdf', '.jpg', '.jpeg', '.png', '.webp')
    media_events = []
    seen = set()
    
    for url in urls:
        print(f"Scraping media da {source_name}: {url}...")
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (compatible; CAI-Aggregator/1.0)'}
            resp = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # Link
            for link in soup.find_all('a'):
                href = link.get('href')
                if href and href.lower().endswith(EXTS):
                    if not href.startswith('http'): href = base_domain + href.lstrip('/')
                    if href in seen: continue
                    if "aquila" in href.lower() or "cropped" in href.lower(): continue

                    is_pdf = href.lower().endswith('.pdf')
                    icon = "📄" if is_pdf else "🖼️"
                    type_lbl = "[PDF]" if is_pdf else "[IMG]"
                    
                    title = link.get_text(strip=True)
                    if not title:
                        img = link.find('img')
                        if img and img.get('alt'): title = img.get('alt')
                    
                    bad_words = ['download', 'scarica', 'pdf', 'clicca', 'leggi', 'programma', 'locandina', 'volantino']
                    if not title or title.lower() in bad_words: title = clean_filename(href)
                    if not title: title = f"Documento {type_lbl}"
                    
                    seen.add(href)
                    
                    dt = None
                    try:
                        head = requests.head(href, headers=headers, timeout=5)
                        lmod = head.headers.get('Last-Modified')
                        if lmod: dt = parsedate_to_datetime(lmod).replace(tzinfo=None)
                    except: pass
                    
                    if not dt: dt = extract_date_from_url(href)
                    # Se non trovo data, metto 2023. Verra' filtrato via se cerchiamo >= 2026
                    if not dt: dt = datetime(2023, 1, 1) 
                    
                    full_title = f"{icon} {type_lbl} {title}"
                    if is_recent(dt): send_telegram_alert(full_title, href, source_name)
                    
                    media_events.append({
                        "title": full_title, "link": href, "date": dt,
                        "summary": f"Media ({type_lbl}) rilevato su {source_name}.",
                        "source": source_name, "color": color,
                        "event_date": None
                    })

            # Immagini Visualizzate
            for img in soup.find_all('img'):
                src = img.get('src')
                if src and src.lower().endswith(EXTS):
                    if not src.startswith('http'): src = base_domain + src.lstrip('/')
                    if src in seen: continue
                    
                    bad_keywords = ['logo', 'icon', 'caiweb', 'stemma', 'facebook', 'whatsapp', 'instagram', 'aquila', 'cropped', 'retina']
                    if any(keyword in src.lower() for keyword in bad_keywords): continue

                    title = img.get('alt')
                    if not title: title = clean_filename(src)
                    if not title: title = "Locandina"
                    
                    seen.add(src)
                    
                    dt = extract_date_from_url(src)
                    if not dt: dt = datetime(2023, 1, 1)

                    full_title = f"🖼️ [IMG] {title}"
                    if is_recent(dt): send_telegram_alert(full_title, src, source_name)

                    media_events.append({
                        "title": full_title, "link": src, "date": dt,
                        "summary": "Immagine rilevata nella pagina.",
                        "source": source_name, "color": color,
                        "event_date": None
                    })

        except Exception as e: print(f"Err scraping {url}: {e}")
    return media_events

# --- CONFIGURAZIONE GRUPPI ---
GROUPS = {
    "index.html": {
        "title": "Toscana Est (Arezzo, Siena, Sansepolcro, Stia, Valdarno Sup.)",
        "sites": [
            {"url": "https://www.caiarezzo.it/feed/", "name": "CAI Arezzo", "color": "#e74c3c"},
            {"url": "https://caivaldarnosuperiore.it/feed/", "name": "CAI Valdarno Sup.", "color": "#2ecc71"},
            {"url": "https://caistia.it/feed/", "name": "CAI Stia", "color": "#f1c40f"},
            {"url": "https://www.caisansepolcro.it/feed/", "name": "CAI Sansepolcro", "color": "#3498db"},
            {"url": "https://organizzazione.cai.it/sez-siena/feed/", "name": "CAI Siena", "color": "#9b59b6"}
        ]
    },
    "costa.html": {
        "title": "Toscana Ovest (Pisa, Livorno, Viareggio, Massa, Carrara, Grosseto, Pietrasanta, Forte, Pontedera)",
        "sites": [
            {"url": "https://www.caipisa.it/feed/", "name": "CAI Pisa", "color": "#e67e22"},
            {"url": "https://organizzazione.cai.it/sez-livorno/feed/", "name": "CAI Livorno", "color": "#9b59b6"},
            {"url": "https://caiviareggio.it/feed/", "name": "CAI Viareggio", "color": "#3b5998"},
            {"url": "https://www.caifortedeimarmi.it/feed/", "name": "CAI Forte d. Marmi", "color": "#3498db"}, 
            {"url": "https://www.caipontedera.it/feed/", "name": "CAI Pontedera", "color": "#1abc9c"},
            {"url": "https://www.caicarrara.it/feed/", "name": "CAI Carrara", "color": "#7f8c8d"},
            {"url": "https://www.caigrosseto.it/feed/", "name": "CAI Grosseto", "color": "#16a085"},
            {"url": "https://www.caipietrasanta.it/feed/", "name": "CAI Pietrasanta", "color": "#d35400"},
            {"url": "https://www.caimassa.it/feed/", "name": "CAI Massa", "color": "#2c3e50"},
            {"url": "https://www.facebook.com/cailivorno", "name": "FB CAI Livorno", "color": "#3b5998"},
            {"url": "https://www.facebook.com/CAIViareggio", "name": "FB CAI Viareggio", "color": "#3b5558"},
            {"url": "https://www.facebook.com/CaiPietrasanta/", "name": "FB CAI Pietrasanta", "color": "#d35400"},
            {"url": "https://www.facebook.com/groups/1487615384876547", "name": "FB CAI Grosseto", "color": "#16a085"},
            {"url": "https://www.facebook.com/cai.fortedeimarmi", "name": "FB CAI Forte", "color": "#3498db"}
        ]
    },
    "nord.html": {
        "title": "Toscana Nord (Pistoia, Lucca, Pontremoli, Fivizzano, Barga, Maresca, Castelnuovo, Pescia)",
        "sites": [
            {"url": "https://www.caipistoia.org/feed/", "name": "CAI Pistoia", "color": "#8e44ad"},
            {"url": "https://www.cailucca.it/feed/", "name": "CAI Lucca", "color": "#34495e"},
            {"url": "https://caipontremoli.it/feed/", "name": "CAI Pontremoli", "color": "#9b59b6"},
            {"url": "https://www.caifivizzano.it/feed/", "name": "CAI Fivizzano", "color": "#27ae60"},
            {"url": "https://www.caibarga.it/feed/", "name": "CAI Barga", "color": "#d35400"},
            {"url": "https://www.caimaresca.it/feed/", "name": "CAI Maresca", "color": "#16a085"},
            {"url": "https://www.caicastelnuovogarfagnana.org/feed/", "name": "CAI Castelnuovo G.", "color": "#2980b9"},
            {"url": "https://www.caipescia.it/feed/", "name": "CAI Pescia", "color": "#e67e22"},
            {"url": "https://www.facebook.com/groups/www.caipescia.it", "name": "FB CAI Pescia", "color": "#e67e22"},
            {"url": "https://www.facebook.com/cai.barga", "name": "FB CAI Barga", "color": "#d35400"},
            {"url": "https://www.facebook.com/profile.php?id=100093533902575", "name": "FB CAI Garfagnana", "color": "#2980b9"},
            {"url": "https://www.facebook.com/CaisezionediMassa", "name": "FB CAI Massa", "color": "#2c3e50"}
         ]
    },
    "firenze.html": {
        "title": "Area Fiorentina (Firenze, Sesto, Scandicci, Prato, Pontassieve, Valdarno Inf.)",
        "sites": [
            {"url": "https://www.caifirenze.it/feed/", "name": "CAI Firenze", "color": "#c0392b"},
            {"url": "https://www.caisesto.it/feed/", "name": "CAI Sesto F.", "color": "#2980b9"},
            {"url": "https://www.caipontassieve.it/feed/", "name": "CAI Pontassieve", "color": "#3b5998"},
            {"url": "https://www.caiprato.it/feed/", "name": "CAI Prato", "color": "#d35400"},
            {"url": "https://www.caivaldarnoinferiore.it/feed/", "name": "CAI Valdarno Inf.", "color": "#1abc9c"},
            {"url": "https://www.caiscandicci.it/feed/", "name": "CAI Scandicci", "color": "#16a085"}
        ]
    }
}

# --- GENERAZIONE HTML E NAVIGAZIONE ---
def get_nav_html(current_page):
    nav = '<nav style="margin-bottom: 30px; text-align: center; line-height: 2.5;">'
    
    style_cal = 'display: inline-block; text-decoration: none; margin: 5px; padding: 8px 15px; border-radius: 20px; font-weight: bold; border: 2px solid #e67e22;'
    if current_page == "calendario.html": style_cal += 'background-color: #e67e22; color: white;'
    else: style_cal += 'background-color: white; color: #e67e22;'
    nav += f'<a href="calendario.html" style="{style_cal}">📅 CALENDARIO FUTURO</a> '

    style_all = 'display: inline-block; text-decoration: none; margin: 5px; padding: 8px 15px; border-radius: 20px; font-weight: bold; border: 2px solid #333;'
    if current_page == "tutto.html": style_all += 'background-color: #333; color: white;'
    else: style_all += 'background-color: white; color: #333;'
    nav += f'<a href="tutto.html" style="{style_all}">🌍 TUTTE LE SEZIONI TOSCANA</a> '

    for filename, data in GROUPS.items():
        style = 'display: inline-block; text-decoration: none; margin: 5px; padding: 8px 15px; border-radius: 20px; font-weight: bold;'
        if filename == current_page: style += 'background-color: #2563eb; color: white;'
        else: style += 'background-color: #e5e7eb; color: #333;'
        short_title = data['title'].split('(')[0].strip()
        nav += f'<a href="{filename}" style="{style}">{short_title}</a>'
    nav += '</nav>'
    return nav

def write_html_file(filename, title, events, is_calendar=False):
    nav_html = get_nav_html(filename)
    html = f"""
    <!DOCTYPE html>
    <html lang="it">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title}</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap" rel="stylesheet">
        <style>
            body {{ font-family: 'Inter', sans-serif; background-color: #f3f4f6; color: #1f2937; margin: 0; padding: 20px; }}
            .container {{ max-width: 900px; margin: 0 auto; }}
            header {{ text-align: center; margin-bottom: 20px; }}
            h1 {{ color: #111827; margin-bottom: 5px; font-size: 1.8rem; }}
            .meta {{ color: #6b7280; font-size: 0.9em; margin-bottom: 20px; }}
            .card {{ background: white; border-radius: 12px; padding: 24px; margin-bottom: 24px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); border-left: 6px solid #ccc; transition: transform 0.2s; }}
            .card:hover {{ transform: translateY(-2px); box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1); }}
            .badge {{ display: inline-block; padding: 4px 12px; border-radius: 9999px; color: white; font-size: 0.75rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; }}
            .date {{ float: right; color: #6b7280; font-size: 0.875rem; }}
            /* HEADER DATA A TUTTA LARGHEZZA */
            .date-header {{ 
                background: #2c3e50; 
                color: white; 
                padding: 10px 20px; 
                border-radius: 8px; 
                margin: 30px 0 15px 0; 
                font-size: 1.2rem; 
                display: block; 
                width: 100%;
                box-sizing: border-box;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1); 
            }}
            .date-header::before {{ content: '🗓'; margin-right: 10px; }}
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
                <h1>{title}</h1>
                <div class="meta">Ultimo aggiornamento: {datetime.now().strftime('%d/%m/%Y alle %H:%M')}</div>
            </header>
    """
    
    if not events:
        html += "<p style='text-align:center;'>Nessun evento futuro trovato (o data non riconosciuta).</p>"
    
    last_header_date = None

    for event in events:
        if is_calendar:
            current_date_obj = event.get('event_date', event['date'])
            current_date_key = current_date_obj.date()
            
            if current_date_key != last_header_date:
                friendly_date = format_date_friendly(current_date_obj)
                html += f"<div class='date-header'>{friendly_date}</div>"
                last_header_date = current_date_key
            
            sort_date_str = "" 
        else:
            sort_date_str = event['date'].strftime("%d/%m/%Y")

        html += f"""
            <div class="card" style="border-left-color: {event['color']}">
                <div>
                    <span class="badge" style="background-color: {event['color']}">{event['source']}</span>
                    <span class="date">{sort_date_str}</span>
                </div>
                <h2><a href="{event['link']}" target="_blank">{event['title']}</a></h2>
                <div class="desc">{event['summary']}</div>
                <a href="{event['link']}" class="read-more" target="_blank">Apri risorsa &rarr;</a>
            </div>
        """
    html += "</div></body></html>"
    with open(filename, "w", encoding="utf-8") as f: f.write(html)
    print(f"✅ Generato: {filename}")

# --- ESECUZIONE PRINCIPALE ---
GLOBAL_EVENTS = [] 
CALENDAR_EVENTS = [] 

for filename, group_data in GROUPS.items():
    print(f"\n--- Elaborazione Gruppo: {group_data['title']} ---")
    current_group_events = []
    
    # GESTIONE RSS E FACEBOOK
    for site in group_data["sites"]:
        
        # GESTIONE FACEBOOK
        if "facebook.com" in site['url']:
            fb_events = get_facebook_events(site['url'], site['name'], site['color'])
            for ev in fb_events:
                # --- FILTRO ANNO 2026 ---
                if ev['date'].year < 2026: continue
                # ------------------------
                
                current_group_events.append(ev)
                if ev.get('event_date') and ev['event_date'].date() >= datetime.now().date():
                    CALENDAR_EVENTS.append(ev)
            continue # Passa al prossimo sito
        
        # GESTIONE RSS STANDARD
        print(f"Scaricando {site['name']}...")
        try:
            feed = feedparser.parse(site['url'])
            if not feed.entries: continue
            for entry in feed.entries:
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    dt = datetime.fromtimestamp(time.mktime(entry.published_parsed))
                elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                    dt = datetime.fromtimestamp(time.mktime(entry.updated_parsed))
                else: dt = datetime.now()
                
                # --- FILTRO ANNO 2026 ---
                if dt.year < 2026: continue
                # ------------------------

                if is_recent(dt):
                    print(f"--> Notifica: {entry.title}")
                    send_telegram_alert(entry.title, entry.link, site['name'])
                
                summ = clean_html(entry.get("summary", ""))
                
                text_to_scan = entry.title + " " + summ
                event_date = extract_event_date_from_text(text_to_scan)
                
                if len(summ) > 250: summ = summ[:250] + "..."
                
                ev = {
                    "title": entry.title, "link": entry.link, "date": dt, 
                    "summary": summ, "source": site["name"], "color": site["color"],
                    "event_date": event_date
                }
                current_group_events.append(ev)
                
                # FIX EVENTI FEBBRAIO: Uso .date() per ignorare l'ora e includere oggi
                if event_date and event_date.date() >= datetime.now().date():
                    CALENDAR_EVENTS.append(ev)

        except Exception as e: print(f"Errore {site['name']}: {e}")

    # B. SCRAPING SPECIFICI
    site_names_in_group = [s['name'] for s in group_data['sites']]
    extra_events_list = []
    
    if "CAI Sansepolcro" in site_names_in_group:
        extra_events_list.extend(get_sansepolcro_media())
    if "CAI Grosseto" in site_names_in_group:
        extra_events_list.extend(get_grosseto_media())
    # Aggiunta chiamata al nuovo scraper Carrara
    if "CAI Carrara" in site_names_in_group:
        extra_events_list.extend(get_carrara_calendar())

    for ev in extra_events_list:
        # --- FILTRO ANNO 2026 ---
        if ev['date'].year < 2026: continue
        # ------------------------

        # Se non è già stata estratta la data (es. dal scraper Carrara), prova ora
        if not ev.get('event_date'):
            extracted_date = extract_event_date_from_text(ev['title'])
            
            if extracted_date:
                ev['event_date'] = extracted_date
            elif ev['date'] > datetime.now():
                ev['event_date'] = ev['date']
            else:
                ev['event_date'] = None
            
        current_group_events.append(ev)
        
        # FIX EVENTI FEBBRAIO: Uso .date() per ignorare l'ora e includere oggi
        if ev.get('event_date') and ev['event_date'].date() >= datetime.now().date():
             CALENDAR_EVENTS.append(ev)

    # C. Salva Gruppo
    current_group_events.sort(key=lambda x: x["date"], reverse=True)
    write_html_file(filename, group_data['title'], current_group_events)
    GLOBAL_EVENTS.extend(current_group_events)

# Pagina Generale
print(f"\n--- Generazione Pagina Generale ---")
GLOBAL_EVENTS.sort(key=lambda x: x["date"], reverse=True)
write_html_file("tutto.html", "Tutti gli Eventi CAI (Aggregati)", GLOBAL_EVENTS)

# Pagina Calendario
print(f"\n--- Generazione Calendario Futuro ---")
CALENDAR_EVENTS.sort(key=lambda x: x["event_date"])
write_html_file("calendario.html", "📅 Calendario Prossimi Eventi CAI TOSCANA", CALENDAR_EVENTS, is_calendar=True)

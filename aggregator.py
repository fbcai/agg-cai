import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import time
import re
import os
import json
from email.utils import parsedate_to_datetime
from facebook_scraper import get_posts
import urllib.parse

# --- CONFIGURAZIONE NOTIFICHE ---
TG_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TG_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# --- CONFIGURAZIONE WHATSAPP MULTIPLO ---
wa_phones_env = os.environ.get("WHATSAPP_PHONE", "")
wa_keys_env = os.environ.get("WHATSAPP_KEY", "")

WA_PHONES = [p.strip() for p in wa_phones_env.split(',') if p.strip()]
WA_KEYS = [k.strip() for k in wa_keys_env.split(',') if k.strip()]

# --- CONFIGURAZIONE COOKIES FACEBOOK ---
# Se inseriti nei secrets di GitHub come 'FACEBOOK_COOKIES' (formato JSON o percorso file)
FB_COOKIES_ENV = os.environ.get("FACEBOOK_COOKIES")

def send_telegram_alert(title, link, source):
    if not TG_TOKEN or not TG_CHAT_ID: return 
    message = f"🚨 *Nuovo Evento CAI Toscana*\n\n📍 *{source}*\n📝 {title}\n\n🔗 [Leggi di più]({link})"
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    data = {"chat_id": TG_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, data=data)
        time.sleep(1)
    except Exception as e:
        print(f"Errore invio Telegram: {e}")

def send_whatsapp_alert(title, link, source):
    if not WA_PHONES or not WA_KEYS: return
    message = f"🚨 *Nuovo Evento CAI Toscana*\n\n📍 *{source}*\n📝 {title}\n\n🔗 {link}"
    encoded_msg = urllib.parse.quote(message)
    for phone, apikey in zip(WA_PHONES, WA_KEYS):
        url = f"https://api.callmebot.com/whatsapp.php?phone={phone}&text={encoded_msg}&apikey={apikey}"
        try:
            requests.get(url, timeout=10)
            time.sleep(1)
        except Exception as e:
            print(f"Errore invio WhatsApp a {phone}: {e}")

def send_alerts(title, link, source):
    send_telegram_alert(title, link, source)
    send_whatsapp_alert(title, link, source)

# --- FUNZIONI DI SUPPORTO ---
def clean_html(raw_html):
    cleanr = re.compile('<.*?>')
    return re.sub(cleanr, '', raw_html)

def is_recent(dt_obj):
    return (datetime.now() - dt_obj) < timedelta(hours=6)

def clean_filename(url):
    try:
        filename = url.split('/')[-1]
        name = filename.rsplit('.', 1)[0]
        name = name.replace('cropped-', '').replace('scaled-', '')
        name = name.replace('-', ' ').replace('_', ' ')
        name = re.sub(r'\s\d+x\d+$', '', name) 
        return name.title()
    except: return ""

def extract_date_from_url(url):
    try:
        match = re.search(r'/(\d{4})/(\d{2})/', url)
        if match: return datetime(int(match.group(1)), int(match.group(2)), 1)
    except: pass
    return None

def format_date_friendly(dt):
    days = ['Lunedì', 'Martedì', 'Mercoledì', 'Giovedì', 'Venerdì', 'Sabato', 'Domenica']
    months = ['Gennaio', 'Febbraio', 'Marzo', 'Aprile', 'Maggio', 'Giugno', 'Luglio', 'Agosto', 'Settembre', 'Ottobre', 'Novembre', 'Dicembre']
    return f"{days[dt.weekday()]} {dt.day} {months[dt.month-1]} {dt.year}"

# --- ESTRAZIONE INTELLIGENTE DATE ---
def extract_event_date_from_text(text):
    if not text: return None
    text = text.lower()
    months = {'gennaio': 1, 'gen': 1, 'febbraio': 2, 'feb': 2, 'marzo': 3, 'mar': 3, 'aprile': 4, 'apr': 4, 'maggio': 5, 'mag': 5, 'giugno': 6, 'giu': 6, 'luglio': 7, 'lug': 7, 'agosto': 8, 'ago': 8, 'settembre': 9, 'set': 9, 'sett': 9, 'ottobre': 10, 'ott': 10, 'novembre': 11, 'nov': 11, 'dicembre': 12, 'dic': 12}
    today = datetime.now()
    
    # 1. dd/mm/yyyy
    match_full = re.search(r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})', text)
    if match_full:
        try: return datetime(int(match_full.group(3)), int(match_full.group(2)), int(match_full.group(1)))
        except: pass

    # 2. Testuale con range (4 al 5 febbraio)
    for m_name, m_num in months.items():
        range_pattern = r'(\d{1,2})\s*(?:[-/e]|al|&)\s*(?:\d{1,2})\s+(?:di\s+)?' + m_name
        match_range = re.search(range_pattern, text)
        if match_range:
            try:
                d, y = int(match_range.group(1)), today.year
                temp_date = datetime(y, m_num, d)
                if temp_date < today - timedelta(days=60): y += 1
                return datetime(y, m_num, d)
            except: pass
        
        single_pattern = r'(\d{1,2})\s+(?:di\s+)?' + m_name
        match_single = re.search(single_pattern, text)
        if match_single:
            try:
                d, y = int(match_single.group(1)), today.year
                temp_date = datetime(y, m_num, d)
                if temp_date < today - timedelta(days=60): y += 1
                return datetime(y, m_num, d)
            except: pass

    # 3. dd/mm
    match_short = re.search(r'(\d{1,2})[/-](\d{1,2})', text)
    if match_short:
        try:
            d, m = int(match_short.group(1)), int(match_short.group(2))
            if m <= 12:
                y = today.year
                temp_date = datetime(y, m, d)
                if temp_date < today - timedelta(days=30): y += 1
                return datetime(y, m, d)
        except: pass
    return None

# --- SCRAPER SPECIFICI ---
def get_sansepolcro_media():
    urls = ["https://www.caisansepolcro.it/prossima-escursione/", "https://www.caisansepolcro.it/prossime-escursioni-con-prenotazione/", "https://www.caisansepolcro.it/prossima-serata/"]
    return scrape_generic_media(urls, "CAI Sansepolcro", "https://www.caisansepolcro.it")

def get_grosseto_media():
    urls = ["https://caigrosseto.it/prossimi-eventi/"]
    return scrape_generic_media(urls, "CAI Grosseto", "https://caigrosseto.it", color="#16a085")

def get_carrara_calendar():
    base_url = "https://www.caicarrara.it/login-utenti-cai/lista-eventi.html"
    base_domain = "https://www.caicarrara.it"
    source_name = "CAI Carrara"
    color = "#7f8c8d"
    events = []
    print(f"Scraping DEEP {source_name}...")
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (compatible; CAI-Aggregator/1.0)'}
        resp = requests.get(base_url, headers=headers, timeout=15)
        soup = BeautifulSoup(resp.text, 'html.parser')
        main_content = soup.find('div', class_='component-content') or soup.find('main') or soup.body
        links_to_check = set()
        for a in main_content.find_all('a', href=True):
            href = a['href']
            if "lista-eventi/" in href and ".html" in href:
                full_link = urllib.parse.urljoin(base_domain, href.strip())
                if full_link != base_url: links_to_check.add(full_link)
        
        print(f" -> {len(links_to_check)} link potenziali Carrara.")
        for link in links_to_check:
            try:
                time.sleep(1.5)
                sub_resp = requests.get(link, headers=headers, timeout=10)
                sub_soup = BeautifulSoup(sub_resp.text, 'html.parser')
                date_span = sub_soup.find('span', class_='ic-period-startdate')
                event_date = None
                if date_span:
                    try: event_date = datetime.strptime(date_span.get_text(strip=True), "%d/%m/%Y")
                    except: pass
                if not event_date:
                    title_tag = sub_soup.find('title')
                    if title_tag: event_date = extract_event_date_from_text(title_tag.get_text())
                
                if event_date and event_date.year >= 2026:
                    page_title_tag = sub_soup.find('title')
                    if page_title_tag and page_title_tag.string:
                        title = page_title_tag.string.replace("- CAI Carrara", "").strip()
                    else: title = "Evento CAI Carrara"
                    full_title = f"⛰️ {title}"
                    if any(e['link'] == link for e in events): continue
                    events.append({"title": full_title, "link": link, "date": datetime.now(), "summary": f"Data: {event_date.strftime('%d/%m/%Y')}", "source": source_name, "color": color, "event_date": event_date})
            except Exception as e: continue
    except Exception as e: print(f"Errore Carrara: {e}")
    return events

# --- FACEBOOK SCRAPER FIX ---
def get_facebook_events(page_url, source_name, color):
    print(f"Scraping FB: {source_name}...")
    fb_events = []
    
    # 1. Estrazione ID/Nome precisa
    page_id = None
    # Caso Profilo ID (es. profile.php?id=1000...)
    match_id = re.search(r'id=(\d+)', page_url)
    if match_id:
        page_id = match_id.group(1)
    else:
        # Caso Pagina/Gruppo (es. /groups/12345 o /cai.barga)
        # Rimuove slash finale e prende l'ultimo pezzo
        clean_url = page_url.rstrip('/')
        page_id = clean_url.split('/')[-1]

    # 2. Gestione Cookies (Se disponibili nei secrets)
    cookies = None
    if FB_COOKIES_ENV:
        try:
            cookies = json.loads(FB_COOKIES_ENV)
            print(" -> Cookies caricati.")
        except:
            print(" -> Errore parsing cookies.")

    # 3. Tentativo Scraping
    try:
        # Per i Gruppi è obbligatorio specificare group=True se usiamo l'ID
        is_group = "groups" in page_url
        
        # Opzioni per ridurre blocchi
        opts = {"allow_extra_requests": False, "posts_per_page": 2}
        if is_group:
            # Nota: get_posts per gruppi funziona meglio se passiamo cookies
            print(f" -> Modalità Gruppo ({page_id})")
        
        for post in get_posts(page_id, pages=2, cookies=cookies, options=opts):
            try:
                post_text = post.get('text', '')
                post_time = post.get('time')
                post_url = post.get('post_url')
                
                # Se post_url manca, ricostruiscilo
                if not post_url and post.get('post_id'):
                    if is_group:
                        post_url = f"https://www.facebook.com/groups/{page_id}/posts/{post.get('post_id')}"
                    else:
                        post_url = f"https://www.facebook.com/{page_id}/posts/{post.get('post_id')}"

                if not post_time: post_time = datetime.now()
                if not post_text: post_text = "Foto/Media senza testo"

                title = " ".join(post_text.split()[:10]) + "..."
                full_title = f"📘 [FB] {title}"
                event_date = extract_event_date_from_text(post_text)

                if is_recent(post_time):
                    send_alerts(full_title, post_url, source_name)
                
                fb_events.append({
                    "title": full_title, "link": post_url, "date": post_time,
                    "summary": post_text[:300] + "...", "source": source_name, "color": color,
                    "event_date": event_date
                })
            except Exception as e: continue
            
    except Exception as e:
        print(f"Errore FB {source_name}: {e}")
        if "Login required" in str(e):
            print(" -> ⚠️ I Gruppi/Profili richiedono Cookies per funzionare.")
    
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
            for link in soup.find_all('a'):
                href = link.get('href')
                if href and href.lower().endswith(EXTS):
                    full_link = urllib.parse.urljoin(base_domain, href.strip())
                    if full_link in seen: continue
                    if "aquila" in full_link.lower() or "cropped" in full_link.lower(): continue
                    is_pdf = full_link.lower().endswith('.pdf')
                    icon = "📄" if is_pdf else "🖼️"
                    type_lbl = "[PDF]" if is_pdf else "[IMG]"
                    title = link.get_text(strip=True)
                    if not title:
                        img = link.find('img')
                        if img and img.get('alt'): title = img.get('alt')
                    bad_words = ['download', 'scarica', 'pdf', 'clicca', 'leggi', 'programma', 'locandina', 'volantino']
                    if not title or title.lower() in bad_words: title = clean_filename(full_link)
                    if not title: title = f"Documento {type_lbl}"
                    seen.add(full_link)
                    dt = None
                    try:
                        head = requests.head(full_link, headers=headers, timeout=5)
                        lmod = head.headers.get('Last-Modified')
                        if lmod: dt = parsedate_to_datetime(lmod).replace(tzinfo=None)
                    except: pass
                    if not dt: dt = extract_date_from_url(full_link)
                    if not dt: dt = datetime(2023, 1, 1) 
                    full_title = f"{icon} {type_lbl} {title}"
                    if is_recent(dt): send_alerts(full_title, full_link, source_name)
                    media_events.append({"title": full_title, "link": full_link, "date": dt, "summary": f"Media ({type_lbl}) rilevato su {source_name}.", "source": source_name, "color": color, "event_date": None})
            for img in soup.find_all('img'):
                src = img.get('src')
                if src and src.lower().endswith(EXTS):
                    full_src = urllib.parse.urljoin(base_domain, src.strip())
                    if full_src in seen: continue
                    bad_keywords = ['logo', 'icon', 'caiweb', 'stemma', 'facebook', 'whatsapp', 'instagram', 'aquila', 'cropped', 'retina']
                    if any(keyword in full_src.lower() for keyword in bad_keywords): continue
                    title = img.get('alt')
                    if not title: title = clean_filename(full_src)
                    if not title: title = "Locandina"
                    seen.add(full_src)
                    dt = extract_date_from_url(full_src)
                    if not dt: dt = datetime(2023, 1, 1)
                    full_title = f"🖼️ [IMG] {title}"
                    if is_recent(dt): send_alerts(full_title, full_src, source_name)
                    media_events.append({"title": full_title, "link": full_src, "date": dt, "summary": "Immagine rilevata nella pagina.", "source": source_name, "color": color, "event_date": None})
        except Exception as e: print(f"Err scraping {url}: {e}")
    return media_events

# --- CONFIGURAZIONE GRUPPI ---
GROUPS = {
    "index.html": {
        "title": "Toscana SudEst (Arezzo, Siena, Grosseto, Sansepolcro, Stia, Valdarno Sup.)",
        "sites": [
            {"url": "https://www.caiarezzo.it/feed/", "name": "CAI Arezzo", "color": "#e74c3c"},
            {"url": "https://caivaldarnosuperiore.it/feed/", "name": "CAI Valdarno Sup.", "color": "#2ecc71"},
            {"url": "https://caistia.it/feed/", "name": "CAI Stia", "color": "#f1c40f"},
            {"url": "https://www.caisansepolcro.it/feed/", "name": "CAI Sansepolcro", "color": "#3498db"},
            {"url": "https://organizzazione.cai.it/sez-siena/feed/", "name": "CAI Siena", "color": "#9b59b6"},
            {"url": "https://www.caigrosseto.it/feed/", "name": "CAI Grosseto", "color": "#16a085"},
            {"url": "https://www.facebook.com/groups/1487615384876547", "name": "FB CAI Grosseto", "color": "#16a085"}
        ]
    },
    "costa.html": {
        "title": "Toscana Ovest (Pisa, Livorno, Viareggio, Massa, Carrara, Pietrasanta, Forte, Pontedera)",
        "sites": [
            {"url": "https://www.caipisa.it/feed/", "name": "CAI Pisa", "color": "#e67e22"},
            {"url": "https://organizzazione.cai.it/sez-livorno/feed/", "name": "CAI Livorno", "color": "#9b59b6"},
            {"url": "https://caiviareggio.it/feed/", "name": "CAI Viareggio", "color": "#3b5998"},
            {"url": "https://www.caifortedeimarmi.it/feed/", "name": "CAI Forte d. Marmi", "color": "#3498db"}, 
            {"url": "https://www.caipontedera.it/feed/", "name": "CAI Pontedera", "color": "#1abc9c"},
            {"url": "https://www.caicarrara.it/feed/", "name": "CAI Carrara", "color": "#7f8c8d"},
            {"url": "https://www.caipietrasanta.it/feed/", "name": "CAI Pietrasanta", "color": "#d35400"},
            {"url": "https://www.caimassa.it/feed/", "name": "CAI Massa", "color": "#2c3e50"},
            {"url": "https://www.facebook.com/cailivorno", "name": "FB CAI Livorno", "color": "#3b5998"},
            {"url": "https://www.facebook.com/CAIViareggio", "name": "FB CAI Viareggio", "color": "#3b5558"},
            {"url": "https://www.facebook.com/CaiPietrasanta/", "name": "FB CAI Pietrasanta", "color": "#d35400"},
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

# --- GENERAZIONE HTML ---
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
    html = f"""<!DOCTYPE html><html lang="it"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>{title}</title><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap" rel="stylesheet"><style>body {{ font-family: 'Inter', sans-serif; background-color: #f3f4f6; color: #1f2937; margin: 0; padding: 20px; }} .container {{ max-width: 900px; margin: 0 auto; }} header {{ text-align: center; margin-bottom: 20px; }} h1 {{ color: #111827; margin-bottom: 5px; font-size: 1.8rem; }} .meta {{ color: #6b7280; font-size: 0.9em; margin-bottom: 20px; }} .card {{ background: white; border-radius: 12px; padding: 24px; margin-bottom: 24px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); border-left: 6px solid #ccc; transition: transform 0.2s; }} .card:hover {{ transform: translateY(-2px); box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1); }} .badge {{ display: inline-block; padding: 4px 12px; border-radius: 9999px; color: white; font-size: 0.75rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; }} .date {{ float: right; color: #6b7280; font-size: 0.875rem; }} .date-header {{ background: #2c3e50; color: white; padding: 10px 20px; border-radius: 8px; margin: 30px 0 15px 0; font-size: 1.2rem; display: block; width: 100%; box-sizing: border-box; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }} .date-header::before {{ content: '🗓'; margin-right: 10px; }} h2 {{ margin-top: 12px; margin-bottom: 8px; font-size: 1.25rem; }} h2 a {{ text-decoration: none; color: #111827; }} h2 a:hover {{ color: #2563eb; }} .desc {{ color: #4b5563; line-height: 1.5; font-size: 0.95rem; margin-bottom: 16px; }} .read-more {{ display: inline-block; color: #2563eb; font-weight: 600; text-decoration: none; }} .read-more:hover {{ text-decoration: underline; }}</style></head><body><div class="container">{nav_html}<header><h1>{title}</h1><div class="meta">Ultimo aggiornamento: {datetime.now().strftime('%d/%m/%Y alle %H:%M')}</div></header>"""
    if not events: html += "<p style='text-align:center;'>Nessun evento futuro trovato.</p>"
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
        else: sort_date_str = event['date'].strftime("%d/%m/%Y")
        html += f"""<div class="card" style="border-left-color: {event['color']}"><div><span class="badge" style="background-color: {event['color']}">{event['source']}</span><span class="date">{sort_date_str}</span></div><h2><a href="{event['link']}" target="_blank">{event['title']}</a></h2><div class="desc">{event['summary']}</div><a href="{event['link']}" class="read-more" target="_blank">Apri risorsa &rarr;</a></div>"""
    html += "</div></body></html>"
    with open(filename, "w", encoding="utf-8") as f: f.write(html)
    print(f"✅ Generato: {filename}")

# --- ESECUZIONE ---
GLOBAL_EVENTS = [] 
CALENDAR_EVENTS = [] 
for filename, group_data in GROUPS.items():
    print(f"\n--- Gruppo: {group_data['title']} ---")
    current_group_events = []
    for site in group_data["sites"]:
        if "facebook.com" in site['url']:
            fb_events = get_facebook_events(site['url'], site['name'], site['color'])
            for ev in fb_events:
                if ev['date'].year < 2026: continue
                current_group_events.append(ev)
                if ev.get('event_date') and ev['event_date'].date() >= datetime.now().date(): CALENDAR_EVENTS.append(ev)
            continue
        
        print(f"Scaricando {site['name']}...")
        try:
            feed = feedparser.parse(site['url'])
            if not feed.entries: continue
            for entry in feed.entries:
                if hasattr(entry, 'published_parsed') and entry.published_parsed: dt = datetime.fromtimestamp(time.mktime(entry.published_parsed))
                elif hasattr(entry, 'updated_parsed') and entry.updated_parsed: dt = datetime.fromtimestamp(time.mktime(entry.updated_parsed))
                else: dt = datetime.now()
                if dt.year < 2026: continue
                if is_recent(dt):
                    print(f"--> Notifica: {entry.title}")
                    send_alerts(entry.title, entry.link, site['name'])
                summ = clean_html(entry.get("summary", ""))
                event_date = extract_event_date_from_text(entry.title + " " + summ)
                if len(summ) > 250: summ = summ[:250] + "..."
                ev = {"title": entry.title, "link": entry.link, "date": dt, "summary": summ, "source": site["name"], "color": site["color"], "event_date": event_date}
                current_group_events.append(ev)
                if event_date and event_date.date() >= datetime.now().date(): CALENDAR_EVENTS.append(ev)
        except Exception as e: print(f"Errore {site['name']}: {e}")

    site_names = [s['name'] for s in group_data['sites']]
    extra_events = []
    if "CAI Sansepolcro" in site_names: extra_events.extend(get_sansepolcro_media())
    if "CAI Grosseto" in site_names: extra_events.extend(get_grosseto_media())
    if "CAI Carrara" in site_names: extra_events.extend(get_carrara_calendar())

    for ev in extra_events:
        if ev['date'].year < 2026: continue
        if not ev.get('event_date'):
            extracted_date = extract_event_date_from_text(ev['title'])
            if extracted_date: ev['event_date'] = extracted_date
            elif ev['date'] > datetime.now(): ev['event_date'] = ev['date']
            else: ev['event_date'] = None
        current_group_events.append(ev)
        if ev.get('event_date') and ev['event_date'].date() >= datetime.now().date(): CALENDAR_EVENTS.append(ev)

    current_group_events.sort(key=lambda x: x["date"], reverse=True)
    write_html_file(filename, group_data['title'], current_group_events)
    GLOBAL_EVENTS.extend(current_group_events)

GLOBAL_EVENTS.sort(key=lambda x: x["date"], reverse=True)
write_html_file("tutto.html", "Tutti gli Eventi CAI (Aggregati)", GLOBAL_EVENTS)
CALENDAR_EVENTS.sort(key=lambda x: x["event_date"])
write_html_file("calendario.html", "📅 Calendario Prossimi Eventi CAI TOSCANA", CALENDAR_EVENTS, is_calendar=True)

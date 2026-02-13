import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import time
import re
import os
import io
import json
from email.utils import parsedate_to_datetime
from facebook_scraper import get_posts
import urllib.parse
from pypdf import PdfReader
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- CONFIGURAZIONE NOTIFICHE ---
TG_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TG_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# --- CONFIGURAZIONE WHATSAPP MULTIPLO ---
wa_phones_env = os.environ.get("WHATSAPP_PHONE", "")
wa_keys_env = os.environ.get("WHATSAPP_KEY", "")

WA_PHONES = [p.strip() for p in wa_phones_env.split(',') if p.strip()]
WA_KEYS = [k.strip() for k in wa_keys_env.split(',') if k.strip()]

# --- GESTIONE REGISTRO LINK (MEMORIA STORICA) ---
REGISTRY_FILE = "link_registry.json"
LINK_REGISTRY = {}
IS_FIRST_RUN = False

def load_registry():
    global LINK_REGISTRY, IS_FIRST_RUN
    if os.path.exists(REGISTRY_FILE):
        try:
            with open(REGISTRY_FILE, 'r', encoding='utf-8') as f:
                LINK_REGISTRY = json.load(f)
        except:
            LINK_REGISTRY = {}
    else:
        IS_FIRST_RUN = True
        LINK_REGISTRY = {}

def save_registry():
    try:
        with open(REGISTRY_FILE, 'w', encoding='utf-8') as f:
            json.dump(LINK_REGISTRY, f, indent=4)
    except Exception as e:
        print(f"Errore salvataggio registro: {e}")

def get_pub_date(link, title_discriminator=""):
    key = link
    if title_discriminator:
        key = f"{link}::{title_discriminator}"

    if key in LINK_REGISTRY:
        return datetime.fromisoformat(LINK_REGISTRY[key])
    else:
        if IS_FIRST_RUN:
            # Data fissa per il pregresso (09 Feb 2026)
            discovery_date = datetime(2026, 2, 9, 10, 0, 0)
        else:
            # Data attuale per i nuovi inserimenti
            discovery_date = datetime.now()
        
        LINK_REGISTRY[key] = discovery_date.isoformat()
        return discovery_date

load_registry()

def send_telegram_alert(title, link, source):
    if not TG_TOKEN or not TG_CHAT_ID: return 
    message = f"🚨 *Nuovo Evento CAI Toscana*\n\n📍 *{source}*\n📝 {title}\n\n🔗 [Leggi di più]({link})"
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    data = {"chat_id": TG_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, data=data)
        time.sleep(1)
    except: pass

def send_whatsapp_alert(title, link, source):
    if not WA_PHONES or not WA_KEYS: return
    message = f"🚨 *Nuovo Evento CAI Toscana*\n\n📍 *{source}*\n📝 {title}\n\n🔗 {link}"
    encoded_msg = urllib.parse.quote(message)
    for phone, apikey in zip(WA_PHONES, WA_KEYS):
        try:
            requests.get(f"https://api.callmebot.com/whatsapp.php?phone={phone}&text={encoded_msg}&apikey={apikey}", timeout=10)
            time.sleep(1)
        except: pass

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

# --- ESTRAZIONE DATE ---
def extract_event_date_from_text(text):
    if not text: return None
    text = text.lower()
    months = {'gennaio': 1, 'gen': 1, 'febbraio': 2, 'feb': 2, 'marzo': 3, 'mar': 3, 'aprile': 4, 'apr': 4, 'maggio': 5, 'mag': 5, 'giugno': 6, 'giu': 6, 'luglio': 7, 'lug': 7, 'agosto': 8, 'ago': 8, 'settembre': 9, 'set': 9, 'sett': 9, 'ottobre': 10, 'ott': 10, 'novembre': 11, 'nov': 11, 'dicembre': 12, 'dic': 12}
    today = datetime.now()
    
    match_full = re.search(r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})', text)
    if match_full:
        try: return datetime(int(match_full.group(3)), int(match_full.group(2)), int(match_full.group(1)))
        except: pass

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

def get_garfagnana_media():
    urls = ["https://organizzazione.cai.it/sez-castelnuovo-garfagnana/news/"]
    return scrape_generic_media(urls, "CAI Castelnuovo G.", "https://organizzazione.cai.it", color="#2980b9")

# --- SCRAPER CAI SCANDICCI ---
def get_scandicci_events():
    url = "https://www.caiscandicci.it/programma-attivita/eventi-in-corso.html"
    base_domain = "https://www.caiscandicci.it"
    source_name = "CAI Scandicci"
    color = "#16a085"
    events = []
    
    print(f"Scraping {source_name}...")
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers, timeout=20)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        for link in soup.find_all('a', href=True):
            href = link['href']
            if "javascript" in href or "mailto" in href: continue
            
            full_link = urllib.parse.urljoin(base_domain, href)
            title = link.get_text(strip=True)
            container = link.find_parent(['tr', 'li', 'p', 'div'])
            text_context = container.get_text(" ", strip=True) if container else title
            event_date = extract_event_date_from_text(text_context)
            
            if event_date and event_date.year >= 2026:
                full_title_text = title if len(title) > 5 else text_context[:100]
                full_title = f"⛰️ {full_title_text}"
                
                if any(e['link'] == full_link for e in events): continue
                pub_date = get_pub_date(full_link)
                
                events.append({
                    "title": full_title, "link": full_link, "date": pub_date,
                    "summary": f"Evento CAI Scandicci del {event_date.strftime('%d/%m/%Y')}",
                    "source": source_name, "color": color, "event_date": event_date
                })
                print(f"   + Scandicci Trovato: {full_title}")
    except Exception as e: print(f"Errore Scandicci: {e}")
    return events

# --- SCRAPER CAI BARGA ROBUSTO ---
def get_barga_activities():
    url = "https://www.caibarga.it/Gite.htm"
    base_domain = "https://www.caibarga.it"
    source_name = "CAI Barga"
    color = "#d35400"
    events = []
    
    print(f"Scraping {source_name}...")
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers, timeout=20)
        resp.encoding = resp.apparent_encoding 
        soup = BeautifulSoup(resp.content, 'html.parser')
        
        for row in soup.find_all(['tr', 'p', 'li', 'td']):
            text = row.get_text(" ", strip=True)
            if len(text) < 5: continue

            if not re.search(r'\d{1,2}[./-]\d{1,2}', text): continue
            
            event_date = extract_event_date_from_text(text)
            
            if event_date and event_date.year >= 2026:
                link_tag = row.find('a')
                if not link_tag: continue
                href = link_tag.get('href')
                if not href or "mailto" in href: continue
                
                full_link = urllib.parse.urljoin(base_domain, href)
                
                clean_title = text
                clean_title = re.sub(r'\d{1,2}[./-]\d{1,2}[./-]?\d{0,4}', '', clean_title)
                clean_title = clean_title.replace("Programma", "").replace("Scarica", "").strip()
                clean_title = clean_title.strip("- .|").strip()
                if len(clean_title) < 4: clean_title = "Attività CAI Barga"
                
                full_title = f"⛰️ {clean_title}"
                if any(e['link'] == full_link for e in events): continue
                pub_date = get_pub_date(full_link)

                events.append({
                    "title": full_title, "link": full_link, "date": pub_date,
                    "summary": f"Gita CAI Barga del {event_date.strftime('%d/%m/%Y')}",
                    "source": source_name, "color": color, "event_date": event_date
                })
    except Exception as e: print(f"Err Barga: {e}")
    return events

# --- SCRAPER CAI MASSA ROBUSTO ---
def get_massa_events():
    url = "https://www.caimassa.com/"
    base_domain = "https://www.caimassa.com/"
    source_name = "CAI Massa"
    color = "#2c3e50"
    events = []
    
    print(f"Scraping {source_name}...")
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers, timeout=20, verify=False)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        for item in soup.find_all(['h2', 'h3', 'h4', 'h5']):
            link_tag = item.find('a')
            if not link_tag: continue
            href = link_tag.get('href')
            if not href: continue
            
            full_link = urllib.parse.urljoin(base_domain, href)
            title_text = link_tag.get_text(strip=True)
            if not title_text: continue

            container = item.find_parent(['div', 'article']) or item.parent
            container_text = container.get_text(" ", strip=True)
            event_date = extract_event_date_from_text(container_text)
            
            if not event_date:
                match_url = re.search(r'/(\d{4})/(\d{2})/', full_link)
                if match_url:
                    y, m = int(match_url.group(1)), int(match_url.group(2))
                    event_date = datetime(y, m, 1)

            if event_date and event_date.year >= 2026:
                full_title = f"⛰️ {title_text}"
                if any(e['link'] == full_link for e in events): continue
                pub_date = get_pub_date(full_link)

                events.append({
                    "title": full_title, "link": full_link, "date": pub_date,
                    "summary": f"Evento CAI Massa: {title_text}",
                    "source": source_name, "color": color, "event_date": event_date
                })
    except Exception as e: print(f"Err Massa: {e}")
    return events

def get_carrara_calendar():
    base_url = "https://www.caicarrara.it/login-utenti-cai/lista-eventi.html"
    base_domain = "https://www.caicarrara.it"
    source_name = "CAI Carrara"
    color = "#7f8c8d"
    events = []
    print(f"Scraping DEEP {source_name}...")
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(base_url, headers=headers, timeout=15)
        soup = BeautifulSoup(resp.text, 'html.parser')
        main = soup.find('div', class_='component-content') or soup.body
        links = set()
        for a in main.find_all('a', href=True):
            if "lista-eventi/" in a['href'] and ".html" in a['href']:
                links.add(urllib.parse.urljoin(base_domain, a['href'].strip()))
        
        for link in links:
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
                    t = sub_soup.find('title')
                    if t: event_date = extract_event_date_from_text(t.get_text())
                
                if event_date and event_date.year >= 2026:
                    t_tag = sub_soup.find('title')
                    title = t_tag.string.replace("- CAI Carrara", "").strip() if t_tag else "Evento CAI Carrara"
                    full_title = f"⛰️ {title}"
                    if any(e['link'] == link for e in events): continue
                    
                    get_pub_date(link) 
                    
                    events.append({
                        "title": full_title, "link": link, "date": event_date, 
                        "summary": f"Data: {event_date.strftime('%d/%m/%Y')}",
                        "source": source_name, "color": color, "event_date": event_date
                    })
            except: continue
    except Exception as e: print(f"Err Carrara: {e}")
    return events

def get_garfagnana_events():
    pdf_url = "https://www.garfagnanacai.it/media/754_Calendario%20attivit%C3%A0%202026.pdf"
    source_name = "CAI Garfagnana"
    color = "#2980b9"
    events = []
    fixed_date = datetime(2026, 2, 9)
    
    print(f"Scraping PDF {source_name}...")
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(pdf_url, headers=headers)
        with io.BytesIO(response.content) as f:
            reader = PdfReader(f)
            for i in range(10, min(53, len(reader.pages))):
                try:
                    text = reader.pages[i].extract_text()
                    if not text: continue
                    lines = [l.strip() for l in text.split('\n') if l.strip()]
                    if not lines: continue
                    event_date = extract_event_date_from_text(lines[0])
                    if event_date and event_date.year >= 2026:
                        title = lines[1].strip() if len(lines) > 1 else "Evento CAI Garfagnana"
                        full_title = f"⛰️ {title}"
                        get_pub_date(pdf_url, full_title) 
                        
                        events.append({
                            "title": full_title, "link": pdf_url, "date": fixed_date,
                            "summary": f"Pag {i+1} Calendario 2026. Data: {event_date.strftime('%d/%m/%Y')}",
                            "source": source_name, "color": color, "event_date": event_date
                        })
                except: continue
    except Exception as e: print(f"Err PDF Garfagnana: {e}")
    return events

# (Placeholder Facebook)
def get_facebook_events(u, s, c): return []

def scrape_generic_media(urls, source_name, base_domain, color="#3498db"):
    EXTS = ('.pdf', '.jpg', '.jpeg', '.png', '.webp')
    media_events = []
    seen = set()
    
    # LISTA UNIFICATA DI PAROLE VIETATE (LINK e IMMAGINI)
    bad_keywords = [
        'logo', 'icon', 'caiweb', 'stemma', 'facebook', 'whatsapp',
        'instagram', 'aquila', 'cropped', 'retina', 'button', 'user', 'admin',
        'cropped-aquila'
    ]

    for url in urls:
        print(f"Scraping media {source_name}: {url}...")
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            resp = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # 1. CERCA LINK A FILE PDF/IMG
            for link in soup.find_all('a'):
                href = link.get('href')
                if href and href.lower().endswith(EXTS):
                    full = urllib.parse.urljoin(base_domain, href.strip())
                    
                    # Filtro Unificato
                    if any(bad in full.lower() for bad in bad_keywords): continue
                    if full in seen: continue
                    
                    is_pdf = full.lower().endswith('.pdf')
                    icon = "📄" if is_pdf else "🖼️"
                    type_lbl = "[PDF]" if is_pdf else "[IMG]"
                    
                    title = link.get_text(strip=True)
                    if not title:
                        img = link.find('img')
                        if img: title = img.get('alt')
                    
                    bad_title_words = ['download', 'scarica', 'pdf', 'clicca', 'leggi', 'programma', 'locandina', 'volantino']
                    if not title or any(w in title.lower() for w in bad_title_words): 
                        title = clean_filename(full)
                    
                    seen.add(full)
                    pub_date = get_pub_date(full)
                    full_title = f"{icon} {type_lbl} {title}"
                    
                    if is_recent(pub_date): send_alerts(full_title, full, source_name)
                    
                    media_events.append({
                        "title": full_title, "link": full, "date": pub_date, 
                        "summary": f"Media ({type_lbl}) rilevato su {source_name}.", 
                        "source": source_name, "color": color, "event_date": None
                    })
            
            # 2. CERCA IMMAGINI INCORPORATE
            for img in soup.find_all('img'):
                src = img.get('src')
                if src and src.lower().endswith(EXTS):
                    full = urllib.parse.urljoin(base_domain, src.strip())
                    
                    # Filtro Unificato
                    if any(bad in full.lower() for bad in bad_keywords): continue
                    if full in seen: continue
                    
                    title = img.get('alt')
                    if not title: title = clean_filename(full)
                    
                    seen.add(full)
                    pub_date = get_pub_date(full)
                    full_title = f"🖼️ [IMG] {title}"
                    
                    if is_recent(pub_date): send_alerts(full_title, full, source_name)
                    
                    media_events.append({
                        "title": full_title, "link": full, "date": pub_date, 
                        "summary": "Immagine rilevata nella pagina.", 
                        "source": source_name, "color": color, "event_date": None
                    })
        except Exception as e: print(f"Err media {url}: {e}")
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
            {"url": "https://caigrosseto.it/prossimi-eventi/", "name": "CAI Grosseto", "color": "#16a085"}
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
            {"url": "https://www.caimassa.it/feed/", "name": "CAI Massa", "color": "#2c3e50"}
        ]
    },
    "nord.html": {
        "title": "Toscana Nord (Pistoia, Lucca, Pontremoli, Fivizzano, Barga, Maresca, Castelnuovo, Pescia)",
        "sites": [
            {"url": "https://www.caipistoia.org/feed/", "name": "CAI Pistoia", "color": "#8e44ad"},
            {"url": "https://cailucca.it/wp/feed/", "name": "CAI Lucca", "color": "#34495e"},
            {"url": "https://caipontremoli.it/feed/", "name": "CAI Pontremoli", "color": "#9b59b6"},
            {"url": "https://www.caifivizzano.it/feed/", "name": "CAI Fivizzano", "color": "#27ae60"},
            {"url": "https://www.caibarga.it/", "name": "CAI Barga", "color": "#d35400"},
            {"url": "https://www.caimaresca.it/feed/", "name": "CAI Maresca", "color": "#16a085"},
            {"url": "https://www.caicastelnuovogarfagnana.org/feed/", "name": "CAI Castelnuovo G.", "color": "#2980b9"},
            {"url": "https://www.caipescia.it/feed/", "name": "CAI Pescia", "color": "#e67e22"}
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
            {"url": "https://www.caiscandicci.it/", "name": "CAI Scandicci", "color": "#16a085"}
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
        # RSS STANDARD
        print(f"Scaricando {site['name']}...")
        try:
            feed = feedparser.parse(site['url'])
            if not feed.entries: continue
            for entry in feed.entries:
                if hasattr(entry, 'published_parsed'): dt = datetime.fromtimestamp(time.mktime(entry.published_parsed))
                elif hasattr(entry, 'updated_parsed'): dt = datetime.fromtimestamp(time.mktime(entry.updated_parsed))
                else: dt = datetime.now()
                if dt.year < 2026: continue
                if is_recent(dt): send_alerts(entry.title, entry.link, site['name'])
                summ = clean_html(entry.get("summary", ""))
                event_date = extract_event_date_from_text(entry.title + " " + summ)
                if len(summ) > 250: summ = summ[:250] + "..."
                ev = {"title": entry.title, "link": entry.link, "date": dt, "summary": summ, "source": site["name"], "color": site["color"], "event_date": event_date}
                current_group_events.append(ev)
                if event_date and event_date.date() >= datetime.now().date(): CALENDAR_EVENTS.append(ev)
        except Exception as e: print(f"Err {site['name']}: {e}")

    # SCRAPING EXTRA
    site_names = [s['name'] for s in group_data['sites']]
    extra = []
    if "CAI Sansepolcro" in site_names: extra.extend(get_sansepolcro_media())
    if "CAI Grosseto" in site_names: extra.extend(get_grosseto_media())
    if "CAI Carrara" in site_names: extra.extend(get_carrara_calendar())
    if "CAI Barga" in site_names: extra.extend(get_barga_activities())
    if "CAI Massa" in site_names: extra.extend(get_massa_events())
    if "CAI Scandicci" in site_names: extra.extend(get_scandicci_events()) # SCANDICCI ADDED
    if "CAI Castelnuovo G." in site_names: 
        extra.extend(get_garfagnana_events())
        extra.extend(get_garfagnana_media())

    for ev in extra:
        if ev['date'].year < 2026 and ev['date'].year != 2023: continue
        if not ev.get('event_date'):
            extracted = extract_event_date_from_text(ev['title'])
            if extracted: ev['event_date'] = extracted
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

save_registry()

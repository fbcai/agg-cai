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
    """
    Restituisce la data di 'pubblicazione' (scoperta) del link.
    Se il link è già noto, restituisce la data salvata.
    Se è nuovo:
      - Se è la prima esecuzione assoluta (file json non esistente), usa 09/02/2026.
      - Altrimenti usa datetime.now().
    """
    # Per i PDF o link duplicati, usiamo link + titolo come chiave univoca
    key = link
    if title_discriminator:
        key = f"{link}::{title_discriminator}"

    if key in LINK_REGISTRY:
        return datetime.fromisoformat(LINK_REGISTRY[key])
    else:
        # Nuova scoperta
        if IS_FIRST_RUN:
            # Data fissa per il pregresso
            discovery_date = datetime(2026, 2, 9, 10, 0, 0)
        else:
            # Data attuale per i nuovi inserimenti reali
            discovery_date = datetime.now()
        
        LINK_REGISTRY[key] = discovery_date.isoformat()
        return discovery_date

# Carichiamo il registro all'avvio
load_registry()

def send_telegram_alert(title, link, source):
    """Invia notifica su Telegram."""
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

def send_whatsapp_alert(title, link, source):
    """Invia notifica su WhatsApp a TUTTI i numeri configurati."""
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
    """Wrapper che invia a tutti i canali."""
    send_telegram_alert(title, link, source)
    send_whatsapp_alert(title, link, source)

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
    """Formatta la data in italiano."""
    days = ['Lunedì', 'Martedì', 'Mercoledì', 'Giovedì', 'Venerdì', 'Sabato', 'Domenica']
    months = ['Gennaio', 'Febbraio', 'Marzo', 'Aprile', 'Maggio', 'Giugno', 'Luglio', 'Agosto', 'Settembre', 'Ottobre', 'Novembre', 'Dicembre']
    return f"{days[dt.weekday()]} {dt.day} {months[dt.month-1]} {dt.year}"

# --- ESTRAZIONE INTELLIGENTE DATE EVENTI ---
def extract_event_date_from_text(text):
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

    # 1. PRIORITÀ ALTA: Formato completo dd/mm/yyyy
    match_full = re.search(r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})', text)
    if match_full:
        try:
            d, m, y = int(match_full.group(1)), int(match_full.group(2)), int(match_full.group(3))
            found_date = datetime(y, m, d)
            return found_date
        except: pass

    # 2. PRIORITÀ MEDIA: Formato Testuale
    for m_name, m_num in months.items():
        # A. Cerca PRIMA i range
        range_pattern = r'(\d{1,2})\s*(?:[-/e]|al|&)\s*(?:\d{1,2})\s+(?:di\s+)?' + m_name
        match_range = re.search(range_pattern, text)
        if match_range:
            try:
                d = int(match_range.group(1)) # Prende il PRIMO giorno
                y = today.year
                temp_date = datetime(y, m_num, d)
                if temp_date < today - timedelta(days=60): y += 1
                found_date = datetime(y, m_num, d)
                return found_date
            except: pass

        # B. Data singola
        single_pattern = r'(\d{1,2})\s+(?:di\s+)?' + m_name
        match_single = re.search(single_pattern, text)
        if match_single:
            try:
                d = int(match_single.group(1))
                y = today.year
                temp_date = datetime(y, m_num, d)
                if temp_date < today - timedelta(days=60): y += 1
                found_date = datetime(y, m_num, d)
                return found_date
            except: pass

    # 3. PRIORITÀ BASSA: Formato breve dd/mm
    match_short = re.search(r'(\d{1,2})[/-](\d{1,2})', text)
    if match_short:
        try:
            d, m = int(match_short.group(1)), int(match_short.group(2))
            if m > 12: return None 
            y = today.year
            temp_date = datetime(y, m, d)
            if temp_date < today - timedelta(days=30): y += 1
            found_date = datetime(y, m, d)
            return found_date
        except: pass
            
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

def get_garfagnana_media():
    urls = ["https://organizzazione.cai.it/sez-castelnuovo-garfagnana/news/"]
    return scrape_generic_media(urls, "CAI Castelnuovo G.", "https://organizzazione.cai.it", color="#2980b9")

# --- SCRAPER CAI BARGA FIX (GITE) ---
def get_barga_activities():
    url = "https://www.caibarga.it/Gite.htm"
    base_domain = "https://www.caibarga.it"
    source_name = "CAI Barga"
    color = "#d35400"
    events = []
    
    print(f"Scraping {source_name}...")
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(resp.content, 'html.parser')
        
        for row in soup.find_all(['tr', 'p']):
            text = row.get_text(" ", strip=True)
            
            link_tag = row.find('a', string=re.compile("Programma", re.IGNORECASE))
            if not link_tag: link_tag = row.find('a')
            if not link_tag: continue
            
            href = link_tag.get('href')
            if not href: continue
            
            full_link = urllib.parse.urljoin(base_domain, href)
            event_date = extract_event_date_from_text(text)
            
            if event_date and event_date.year >= 2026:
                clean_title = text
                clean_title = re.sub(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', '', clean_title) 
                clean_title = re.sub(r'\d{1,2}\s+[A-Za-z]+\s+2026', '', clean_title, flags=re.IGNORECASE) 
                clean_title = clean_title.replace("Programma", "").replace("Scarica", "").strip()
                clean_title = clean_title.strip("- ").strip("|").strip()
                if len(clean_title) < 3: clean_title = "Gita Sociale CAI Barga"
                full_title = f"⛰️ {clean_title}"
                
                if any(e['link'] == full_link for e in events): continue

                # USA REGISTRO PER LA DATA DI PUBBLICAZIONE
                pub_date = get_pub_date(full_link)

                events.append({
                    "title": full_title,
                    "link": full_link,
                    "date": pub_date,  # Data di rilevamento (stabile)
                    "summary": f"Gita CAI Barga del {event_date.strftime('%d/%m/%Y')}",
                    "source": source_name,
                    "color": color,
                    "event_date": event_date
                })
    except Exception as e:
        print(f"Errore scraping Barga: {e}")
    
    return events

# --- SCRAPER CAI MASSA (LEGGI TUTTO) ---
def get_massa_events():
    url = "https://www.caimassa.com/"
    base_domain = "https://www.caimassa.com/"
    source_name = "CAI Massa"
    color = "#2c3e50"
    events = []
    
    print(f"Scraping {source_name}...")
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        for link in soup.find_all('a', string=re.compile("leggi tutto", re.IGNORECASE)):
            href = link.get('href')
            if not href: continue
            
            full_link = urllib.parse.urljoin(base_domain, href)
            container = link.find_parent(['div', 'article', 'li'])
            if not container: container = link.parent 
            
            container_text = container.get_text(" ", strip=True)
            event_date = extract_event_date_from_text(container_text)
            
            if event_date and event_date.year >= 2026:
                title_tag = container.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
                if title_tag: title = title_tag.get_text(strip=True)
                else: title = container_text.split("leggi tutto")[0].strip()[:100]
                full_title = f"⛰️ {title}"
                
                if any(e['link'] == full_link for e in events): continue

                # USA REGISTRO
                pub_date = get_pub_date(full_link)

                events.append({
                    "title": full_title,
                    "link": full_link,
                    "date": pub_date,
                    "summary": f"Evento CAI Massa del {event_date.strftime('%d/%m/%Y')}",
                    "source": source_name,
                    "color": color,
                    "event_date": event_date
                })
                
    except Exception as e:
        print(f"Errore scraping Massa: {e}")
        
    return events

def get_carrara_calendar():
    """Scraper DEEP per CAI Carrara"""
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
        
        print(f" -> Trovati {len(links_to_check)} link potenziali CAI Carrara.")

        for link in links_to_check:
            try:
                time.sleep(2) 
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
                    else:
                        title_h = sub_soup.find('h2', class_='item-title') or sub_soup.find('h1')
                        title = title_h.get_text(strip=True) if title_h else "Evento CAI Carrara"
                    full_title = f"⛰️ {title}"
                    
                    if any(e['link'] == link for e in events): continue

                    # USA REGISTRO
                    pub_date = get_pub_date(link)

                    events.append({
                        "title": full_title,
                        "link": link,
                        "date": pub_date, 
                        "summary": f"Data evento: {event_date.strftime('%d/%m/%Y')}",
                        "source": source_name,
                        "color": color,
                        "event_date": event_date
                    })
            except Exception as e: continue
    except Exception as e:
        print(f"Errore scraping principale Carrara: {e}")
        
    return events

# --- SCRAPER PDF GARFAGNANA ---
def get_garfagnana_events():
    pdf_url = "https://www.garfagnanacai.it/media/754_Calendario%20attivit%C3%A0%202026.pdf"
    source_name = "CAI Garfagnana"
    color = "#2980b9"
    events = []
    
    print(f"Scraping PDF {source_name}...")
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(pdf_url, headers=headers)
        response.raise_for_status()
        
        with io.BytesIO(response.content) as f:
            reader = PdfReader(f)
            start_page = 10
            end_page = min(53, len(reader.pages))
            
            for i in range(start_page, end_page):
                try:
                    page = reader.pages[i]
                    text = page.extract_text()
                    if not text: continue
                    
                    raw_lines = text.split('\n')
                    lines = [line.strip() for line in raw_lines if line.strip()]
                    if not lines: continue

                    event_date = extract_event_date_from_text(lines[0])
                    
                    if event_date and event_date.year >= 2026:
                        if len(lines) > 1: title = lines[1].strip()
                        else: title = "Evento CAI Garfagnana"
                        full_title = f"⛰️ {title}"
                        
                        # USA REGISTRO con discriminante (titolo) perché il link è sempre lo stesso PDF
                        pub_date = get_pub_date(pdf_url, title_discriminator=full_title)

                        events.append({
                            "title": full_title,
                            "link": pdf_url,
                            "date": pub_date,
                            "summary": f"Evento estratto da pag. {i+1} del Calendario 2026. Data: {event_date.strftime('%d/%m/%Y')}",
                            "source": source_name,
                            "color": color,
                            "event_date": event_date
                        })
                except Exception as e:
                    print(f"Err pag {i}: {e}")
                    continue
    except Exception as e:
        print(f"Errore PDF Garfagnana: {e}")
        
    return events

# (Funzione Facebook non usata)
def get_facebook_events(page_url, source_name, color):
    return []

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
                    
                    # Usa il registro anche per i media trovati via scraping
                    pub_date = get_pub_date(full_link)
                    
                    dt = extract_date_from_url(full_link)
                    if not dt: dt = datetime(2023, 1, 1) 
                    
                    full_title = f"{icon} {type_lbl} {title}"
                    if is_recent(pub_date): send_alerts(full_title, full_link, source_name)
                    
                    media_events.append({
                        "title": full_title, "link": full_link, "date": pub_date,
                        "summary": f"Media ({type_lbl}) rilevato su {source_name}.",
                        "source": source_name, "color": color,
                        "event_date": None
                    })

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
                    
                    # Usa il registro
                    pub_date = get_pub_date(full_src)
                    
                    dt = extract_date_from_url(full_src)
                    if not dt: dt = datetime(2023, 1, 1)

                    full_title = f"🖼️ [IMG] {title}"
                    
                    if is_recent(pub_date): 
                        send_alerts(full_title, full_src, source_name)

                    media_events.append({
                        "title": full_title, "link": full_src, "date": pub_date,
                        "summary": "Immagine rilevata nella pagina.",
                        "source": source_name, "color": color,
                        "event_date": None
                    })

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
    
    # GESTIONE RSS
    for site in group_data["sites"]:
        
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
                    send_alerts(entry.title, entry.link, site['name'])
                
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
    # SCRAPER GROSSETO (MEDIA)
    if "CAI Grosseto" in site_names_in_group:
        extra_events_list.extend(get_grosseto_media())
    if "CAI Carrara" in site_names_in_group:
        extra_events_list.extend(get_carrara_calendar())
    if "CAI Barga" in site_names_in_group:
        extra_events_list.extend(get_barga_activities())
    if "CAI Massa" in site_names_in_group:
        extra_events_list.extend(get_massa_events())
    if "CAI Castelnuovo G." in site_names_in_group:
        extra_events_list.extend(get_garfagnana_events())
        extra_events_list.extend(get_garfagnana_media())

    for ev in extra_events_list:
        # --- FILTRO ANNO 2026 ---
        if ev['date'].year < 2026: continue
        # ------------------------

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

# --- SALVATAGGIO REGISTRO ---
save_registry()

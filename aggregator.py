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
    if not TG_TOKEN or not TG_CHAT_ID: return 
    message = f"🚨 *Nuovo Evento CAI*\n\n📍 *{source}*\n📝 {title}\n\n🔗 [Leggi di più]({link})"
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    data = {"chat_id": TG_CHAT_ID, "text": message, "parse_mode": "Markdown"}
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
    return (datetime.now() - dt_obj) < timedelta(hours=9)

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
                    try:
                        head = requests.head(href, headers=headers, timeout=5)
                        lmod = head.headers.get('Last-Modified')
                        dt = parsedate_to_datetime(lmod).replace(tzinfo=None) if lmod else datetime.now()
                    except: dt = datetime.now()
                    
                    full_title = f"{icon} {type_lbl} {title}"
                    if is_recent(dt): send_telegram_alert(full_title, href, source_name)
                    
                    media_events.append({
                        "title": full_title, "link": href, "date": dt,
                        "summary": f"Media ({type_lbl}) rilevato su {source_name}.",
                        "source": source_name, "color": color
                    })

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
                    dt = datetime.now()
                    full_title = f"🖼️ [IMG] {title}"
                    
                    media_events.append({
                        "title": full_title, "link": src, "date": dt,
                        "summary": "Immagine rilevata nella pagina.",
                        "source": source_name, "color": color
                    })

        except Exception as e: print(f"Err scraping {url}: {e}")
    return media_events

# --- CONFIGURAZIONE GRUPPI (AGGIORNATA) ---
GROUPS = {
    "index.html": {
        "title": "Toscana Sudest (Arezzo, Siena, Sansepolcro, Stia-Casentino, Valdarno Sup.)",
        "sites": [
            {"url": "https://www.caiarezzo.it/feed/", "name": "CAI Arezzo", "color": "#e74c3c"},
            {"url": "https://caivaldarnosuperiore.it/feed/", "name": "CAI Valdarno Sup.", "color": "#2ecc71"},
            {"url": "https://caistia.it/feed/", "name": "CAI Stia", "color": "#f1c40f"},
            {"url": "https://www.caisansepolcro.it/feed/", "name": "CAI Sansepolcro", "color": "#3498db"},
            {"url": "https://organizzazione.cai.it/sez-siena/feed/", "name": "CAI Siena", "color": "#9b59b6"}
        ]
    },
    "costa.html": {
        "title": "Toscana Ovest (Pisa, Livorno, Grosseto, Pontedera, Viareggio, Pietrasanta, Forte dei Marmi, Massa, Carrara)",
        "sites": [
            {"url": "https://www.caipisa.it/feed/", "name": "CAI Pisa", "color": "#e67e22"},
            {"url": "https://organizzazione.cai.it/sez-livorno/feed/", "name": "CAI Livorno", "color": "#9b59b6"},
            #{"url": "https://rss.app/feeds/uc1xw6gq3SrNFE33.xml/", "name": "FB CAI Livorno", "color": "#9b59b6"},
            #{"url": "https://rss.app/feeds/1z5cCnFgCEsTaTum.xml", "name": "FB CAI Viareggio", "color": "#3b5998"},
            {"url": "https://caiviareggio.it/feed/", "name": "CAI Viareggio", "color": "#3b5998"},
            #{"url": "https://rss.app/feeds/SA5s3stQwPLRLfRu.xml", "name": "FB CAI Forte d. Marmi", "color": "#3498db"},
            {"url": "https://www.caifortedeimarmi.it/feed/", "name": "CAI Forte d. Marmi", "color": "#3498db"}, 
            {"url": "https://www.caipontedera.it/feed/", "name": "CAI Pontedera", "color": "#1abc9c"},
            {"url": "https://www.caicarrara.it/feed/", "name": "CAI Carrara", "color": "#7f8c8d"},
            {"url": "https://www.caigrosseto.it/feed/", "name": "CAI Grosseto", "color": "#16a085"},
            #{"url": "https://rss.app/feeds/4IiuRykrqytZe7u7.xml", "name": "FB CAI Pietrasanta", "color": "#d35400"},
            {"url": "https://www.caipietrasanta.it/feed/", "name": "CAI Pietrasanta", "color": "#d35400"},
            {"url": "https://www.caimassa.it/feed/", "name": "CAI Massa", "color": "#2c3e50"}
        ]
    },
    "nord.html": {
        "title": "Toscana Nord (Pistoia, Luccca, Barga, Castelnuovo G., Maresca, Pescia, Fivizzano, Pontremoli)",
        "sites": [
            {"url": "https://www.caipistoia.org/feed/", "name": "CAI Pistoia", "color": "#8e44ad"},
            {"url": "https://www.cailucca.it/feed/", "name": "CAI Lucca", "color": "#16a085"},
            #{"url": "https://rss.app/feeds/HHym29cwmKAXESDM.xml/", "name": "CAI Pontremoli", "color": "#9b59b6"} 
            {"url": "https://caipontremoli.it/feed/", "name": "CAI Pontremoli", "color": "#9b59b6"} 
         ]
    },
    "firenze.html": {
        "title": "Area Fiorentina (Firenze, Prato, Agliana, Sesto F., Scandicci, Pontassieve, Valdarno Inf.)",
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
    style_all = 'display: inline-block; text-decoration: none; margin: 5px; padding: 8px 15px; border-radius: 20px; font-weight: bold; border: 2px solid #333;'
    if current_page == "tutto.html": style_all += 'background-color: #333; color: white;'
    else: style_all += 'background-color: white; color: #333;'
    nav += f'<a href="tutto.html" style="{style_all}">🌍 TUTTE LE SEZIONI</a> '

    for filename, data in GROUPS.items():
        style = 'display: inline-block; text-decoration: none; margin: 5px; padding: 8px 15px; border-radius: 20px; font-weight: bold;'
        if filename == current_page: style += 'background-color: #2563eb; color: white;'
        else: style += 'background-color: #e5e7eb; color: #333;'
        short_title = data['title'].split('(')[0].strip()
        nav += f'<a href="{filename}" style="{style}">{short_title}</a>'
    nav += '</nav>'
    return nav

def write_html_file(filename, title, events):
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
    if not events: html += "<p style='text-align:center;'>Nessuna notizia trovata.</p>"
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
                <a href="{event['link']}" class="read-more" target="_blank">Apri risorsa &rarr;</a>
            </div>
        """
    html += "</div></body></html>"
    with open(filename, "w", encoding="utf-8") as f: f.write(html)
    print(f"✅ Generato: {filename}")

# --- ESECUZIONE PRINCIPALE ---
GLOBAL_EVENTS = [] 
for filename, group_data in GROUPS.items():
    print(f"\n--- Elaborazione Gruppo: {group_data['title']} ---")
    current_group_events = []
    
    # A. RSS
    for site in group_data["sites"]:
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
                
                if is_recent(dt):
                    print(f"--> Notifica: {entry.title}")
                    send_telegram_alert(entry.title, entry.link, site['name'])
                
                summ = clean_html(entry.get("summary", ""))
                if len(summ) > 250: summ = summ[:250] + "..."
                ev = {"title": entry.title, "link": entry.link, "date": dt, "summary": summ, "source": site["name"], "color": site["color"]}
                current_group_events.append(ev)
        except Exception as e: print(f"Errore {site['name']}: {e}")

    # B. SCRAPING SPECIFICI (Immagini/PDF)
    site_names_in_group = [s['name'] for s in group_data['sites']]
    
    # 1. Sansepolcro
    if "CAI Sansepolcro" in site_names_in_group:
        current_group_events.extend(get_sansepolcro_media())

    # 2. Grosseto
    if "CAI Grosseto" in site_names_in_group:
        current_group_events.extend(get_grosseto_media())

    # C. Salva Gruppo
    current_group_events.sort(key=lambda x: x["date"], reverse=True)
    write_html_file(filename, group_data['title'], current_group_events)
    GLOBAL_EVENTS.extend(current_group_events)

# Totale
print(f"\n--- Generazione Pagina Generale ---")
GLOBAL_EVENTS.sort(key=lambda x: x["date"], reverse=True)
write_html_file("tutto.html", "Tutti gli Eventi CAI (Aggregati)", GLOBAL_EVENTS)

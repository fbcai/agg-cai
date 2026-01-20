import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import time
import re
from email.utils import parsedate_to_datetime

# --- FUNZIONI DI SUPPORTO ---

def clean_html(raw_html):
    """Rimuove i tag HTML per pulire il riassunto."""
    cleanr = re.compile('<.*?>')
    cleantext = re.sub(cleanr, '', raw_html)
    return cleantext

def get_sansepolcro_pdfs():
    """Scarica i PDF dalla pagina specifica di CAI Sansepolcro, evitando duplicati."""
    url = "https://www.caisansepolcro.it/prossima-escursione/"
    pdf_events = []
    seen_urls = set() # Set per memorizzare i link già processati
    
    print(f"Scraping extra: {url}...")
    
    try:
        # Scarica la pagina simulando un browser
        headers = {'User-Agent': 'Mozilla/5.0 (compatible; CAI-Aggregator/1.0)'}
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Cerca tutti i link
        for link in soup.find_all('a'):
            href = link.get('href')
            
            # Controlla se è un PDF
            if href and href.lower().endswith('.pdf'):
                # Normalizza URL (aggiungi dominio se manca)
                if not href.startswith('http'):
                    href = "https://www.caisansepolcro.it" + href.lstrip('/')
                
                # 1. CONTROLLO DUPLICATI: Se abbiamo già visto questo URL, saltalo
                if href in seen_urls:
                    continue
                
                # Ottieni il testo del link
                title_text = link.get_text(strip=True)
                
                # 2. FILTRO TESTI GENERICI
                # Se il titolo è solo "Download" o "PDF", prova a cercare il titolo altrove o salta
                ignore_words = ['download', 'scarica', 'pdf', 'clicca qui', 'leggi']
                if not title_text or title_text.lower() in ignore_words:
                    if link.get('title'):
                        title_text = link.get('title')
                    else:
                        pass 

                # Se dopo i controlli il titolo è ancora troppo generico o vuoto, diamogli un nome standard
                if not title_text or title_text.lower() in ignore_words:
                    title_text = "Programma Escursione (PDF)"

                # Aggiungiamo l'URL ai visti così non lo ripeschiamo
                seen_urls.add(href)

                # Cerca data modifica file
                try:
                    head_req = requests.head(href, headers=headers, timeout=5)
                    last_mod = head_req.headers.get('Last-Modified')
                    if last_mod:
                        dt_obj = parsedate_to_datetime(last_mod).replace(tzinfo=None)
                    else:
                        dt_obj = datetime.now()
                except:
                    dt_obj = datetime.now()

                pdf_events.append({
                    "title": f"📄 [PDF] {title_text}",
                    "link": href,
                    "date": dt_obj,
                    "summary": "Documento scaricabile dalla sezione 'Prossima Escursione'.",
                    "source": "CAI Sansepolcro",
                    "color": "#3498db"
                })
    except Exception as e:
        print(f"Errore scraping Sansepolcro: {e}")
        
    return pdf_events

# --- CONFIGURAZIONE GRUPPI ---
GROUPS = {
    "index.html": {
        "title": "Toscana Est (Arezzo, Sansepolcro, Stia-Casentino, Valdarno Superiore)",
        "sites": [
            {"url": "https://www.caiarezzo.it/feed/", "name": "CAI Arezzo", "color": "#e74c3c"},
            {"url": "https://caivaldarnosuperiore.it/feed/", "name": "CAI Valdarno Sup.", "color": "#2ecc71"},
            {"url": "https://caistia.it/feed/", "name": "CAI Stia", "color": "#f1c40f"},
            {"url": "https://www.caisansepolcro.it/feed/", "name": "CAI Sansepolcro", "color": "#3498db"},
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
                print(f"  ! Nessun articolo o feed non valido per {site['url']}")
                continue

            for entry in feed.entries:
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    dt_obj = datetime.fromtimestamp(time.mktime(entry.published_parsed))
                elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                    dt_obj = datetime.fromtimestamp(time.mktime(entry.updated_parsed))
                else:
                    dt_obj = datetime.now()

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

    # 2. CONTROLLO SPECIALE PER SANSEPOLCRO (SOLO NELLA PAGINA INDEX)
    if filename == "index.html":
        sansepolcro_pdfs = get_sansepolcro_pdfs()
        if sansepolcro_pdfs:
            print(f"  > Aggiunti {len(sansepolcro_pdfs)} PDF da Sansepolcro")
            events.extend(sansepolcro_pdfs)

    # 3. ORDINA TUTTO PER DATA
    events.sort(key=lambda x: x["date"], reverse=True)

    # 4. GENERA HTML
    nav_html = get_nav_html(filename)
    
    # ATTENZIONE: Qui sotto c'è un blocco di codice molto lungo.
    # Assicurati di copiare TUTTO fino alla fine del file.
    
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

       

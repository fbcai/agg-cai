import feedparser
from datetime import datetime
import time
import os

# Configurazione dei siti
SITES = [
    {"url": "https://www.caiarezzo.it/feed/", "name": "CAI Arezzo", "color": "#e74c3c"},
    {"url": "https://www.caisansepolcro.it/feed/", "name": "CAI Sansepolcro", "color": "#3498db"},
    {"url": "https://caivaldarnosuperiore.it/feed/", "name": "CAI Valdarno Sup.", "color": "#2ecc71"},
    # CAI Stia potrebbe non avere un feed standard, proviamo comunque
    {"url": "https://caistia.it/feed/", "name": "CAI Stia", "color": "#f1c40f"}
]

all_events = []
print("--- INIZIO SCANSIONE ---")

for site in SITES:
    print(f"Controllo {site['name']}...")
    try:
        d = feedparser.parse(site['url'])
        if d.entries:
            print(f"  > Trovati {len(d.entries)} articoli.")
            for entry in d.entries:
                # Gestione date
                if hasattr(entry, 'published_parsed'):
                    dt_obj = datetime.fromtimestamp(time.mktime(entry.published_parsed))
                elif hasattr(entry, 'updated_parsed'):
                    dt_obj = datetime.fromtimestamp(time.mktime(entry.updated_parsed))
                else:
                    dt_obj = datetime.now()

                # Pulizia riassunto
                summary = entry.get("summary", "")
                # Rimuovi tag HTML grezzi se presenti nel summary (base)
                summary = summary.replace("<p>", "").replace("</p>", "").replace("[&hellip;]", "...")
                
                all_events.append({
                    "title": entry.title,
                    "link": entry.link,
                    "date": dt_obj,
                    "summary": summary[:250] + "..." if len(summary) > 250 else summary,
                    "source": site["name"],
                    "color": site["color"]
                })
        else:
            print("  > Nessun articolo trovato o feed non valido.")
    except Exception as e:
        print(f"  > Errore: {e}")

# Ordina per data (dal più recente)
all_events.sort(key=lambda x: x["date"], reverse=True)

# Genera HTML
html = f"""
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Eventi CAI Aggregati</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap" rel="stylesheet">
    <style>
        body {{ font-family: 'Inter', sans-serif; background-color: #f3f4f6; color: #1f2937; margin: 0; padding: 20px; }}
        .container {{ max-width: 800px; margin: 0 auto; }}
        header {{ text-align: center; margin-bottom: 40px; }}
        h1 {{ color: #111827; margin-bottom: 5px; }}
        .meta {{ color: #6b7280; font-size: 0.9em; }}
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
        <header>
            <h1>🏔️ Aggregatore CAI Toscana Est</h1>
            <div class="meta">Ultimo aggiornamento: {datetime.now().strftime('%d/%m/%Y alle %H:%M')}</div>
        </header>
"""

for event in all_events:
    date_str = event["date"].strftime("%d/%m/%Y")
    html += f"""
        <div class="card" style="border-left-color: {event['color']}">
            <div>
                <span class="badge" style="background-color: {event['color']}">{event['source']}</span>
                <span class="date">{date_str}</span>
            </div>
            <h2><a href="{event['link']}" target="_blank">{event['title']}</a></h2>
            <div class="desc">{event['summary']}</div>
            <a href="{event['link']}" class="read-more" target="_blank">Leggi sul sito originale &rarr;</a>
        </div>
    """

html += """
    </div>
</body>
</html>
"""

with open("index.html", "w", encoding="utf-8") as f:
    f.write(html)
print("File index.html creato.")

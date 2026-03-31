import datetime, os, gspread, requests, base64, json
from google.oauth2 import service_account

# Load Config globally to be used across the script
with open('scouting_config.json', 'r') as f:
    CONFIG = json.load(f)

def process_portal_screenshot(image_path, api_key, sheet):
    with open(image_path, "rb") as image_file:
        img_data = base64.b64encode(image_file.read()).decode('utf-8')

    # THE STABLE ENGINE: This grabs the 'Brain' instructions directly from your JSON
    # This ensures we don't have to rewrite the code when search rules change.
    system_instruction = CONFIG.get('ai_system_instruction', "Extract player data from image.")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    
    payload = {
        "system_instruction": {"parts": [{"text": system_instruction}]},
        "contents": [{"parts": [
            {"text": "Execute deep search protocol on the players found in this image."},
            {"inline_data": {"mime_type": "image/jpeg", "data": img_data}}
        ]}],
        "tools": [{"google_search": {}}],
        "safetySettings": [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"}
        ],
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 8192
        }
    }

    response = requests.post(url, json=payload)
    result = response.json()

    if 'candidates' not in result:
        print("❌ API ERROR:", json.dumps(result, indent=2))
        return 0

    text_out = result['candidates'][0]['content']['parts'][0]['text']
    rows_added = 0
    
    # Process each line returned by the AI
    for line in text_out.strip().split('\n'):
        # NEW: Lowered to 7 pipes so we don't skip players if the AI misses a URL/Insight
        if line.count('|') >= 7 and "NAME |" not in line:
            data = [s.strip() for s in line.replace("**", "").split('|')]
            
            try:
                # Basic info (Indices 0-5) - Guaranteed by the 'if' above
                name = data[0].title()
                pos = data[1] if len(data) > 1 else "N/A"
                cls = data[2] if len(data) > 2 else "N/A"
                hometown = data[3] if len(data) > 3 else "Unknown"
                school = data[4] if len(data) > 4 else "Unknown"
                div = data[5] if len(data) > 5 else "N/A"
                
                # PPG CLEANER: Handles "8.5 PPG" or missing PPG columns
                try: 
                    ppg_str = "".join(c for c in data[8] if c.isdigit() or c == '.') if len(data) > 8 else "0.0"
                    ppg = float(ppg_str) if ppg_str else 0.0
                except: 
                    ppg = 0.0
                
                # --- FIT LOGIC ---
                is_colorado = any(x in hometown.upper() for x in ["COLORADO", ", CO", " CO "])
                is_d1 = any(x in div.upper() for x in ["I", "1", "D1"])
                
                if is_colorado:
                    fit_status = CONFIG['labels']['fit_yes_local']
                elif is_d1:
                    fit_status = CONFIG['labels']['fit_yes_d1']
                elif ppg >= CONFIG['scouting_rules']['d2_d3_ppg_threshold']:
                    fit_status = CONFIG['labels']['fit_yes_ppg']
                else:
                    fit_status = CONFIG['labels']['fit_no_ppg']
                
                # Message Generation with Safety Check
                if "YES" in fit_status.upper():
                    s = CONFIG['text_script']
                    insight = data[10] if len(data) > 10 else "your play in the portal"
                    hook = f"{s['intro'].format(first_name=name.split()[0])} {s['body'].format(insight=insight)} {s['closing']}"
                else:
                    hook = CONFIG['labels']['msg_no_fit']

                # BUILD THE FINAL ROW (Safety for every single column)
                final_row = [
                    CONFIG['system_version'], 
                    datetime.datetime.now().strftime("%m-%d-%y"), 
                    name, pos, cls, hometown, school, 
                    div, 
                    data[6] if len(data) > 6 else "N/A", # Conf
                    "Scouted", 
                    fit_status, 
                    str(ppg), 
                    data[9] if len(data) > 9 else "2025-26", # Season
                    hook, 
                    data[11] if len(data) > 11 else "N/A", # URL
                    data[12] if len(data) > 12 else "N/A"  # Extra
                ]
                
                sheet.append_row(final_row)
                rows_added += 1
                
            except Exception as e:
                print(f"⚠️ Skipped {line.split('|')[0]} due to error: {e}")
                continue

def get_credentials():
    return service_account.Credentials.from_service_account_file(
        'service_account.json', 
        scopes=['https://www.googleapis.com/auth/spreadsheets']
    )

def get_sheet_connection(creds):
    return gspread.authorize(creds).open_by_key('1Cd3vgZrGCH3yx9Oky7g4O0LGbrw0Syo7ROkK4ENTvaM').sheet1

def clear_master_sheet():
    try:
        sheet = get_sheet_connection(get_credentials())
        if sheet.row_count > 1:
            sheet.delete_rows(2, sheet.row_count)
        return True
    except:
        return False
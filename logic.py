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
        if "|" in line and "NAME |" not in line:
            data = [s.strip() for s in line.replace("**", "").split('|')]
            if len(data) >= 12:
                name = data[0].title()
                hometown = data[3]
                school = data[4]
                div = data[5]
                try: 
                    # Force conversion to float for the Fit Logic check
                    ppg = float(data[8]) 
                except: 
                    ppg = 0.0
                
                # --- PROTECTED PYTHON FIT LOGIC ---
                # This guarantees that if "Colorado" is found in the bio, the player is a YES.
                is_colorado = any(x in hometown.upper() for x in ["COLORADO", ", CO", " CO "])
                is_d1 = any(x in div.upper() for x in ["I", "1", "D1"])
                
                if is_colorado:
                    fit_status = CONFIG['labels']['fit_yes_local']
                elif is_d1:
                    fit_status = CONFIG['labels']['fit_yes_d1']
                elif ppg >= CONFIG['scouting_rules']['d2_d3_ppg_threshold']:
                    fit_status = CONFIG['labels']['fit_yes_ppg']
                elif ppg == 0.0:
                    fit_status = CONFIG['labels']['fit_no_stats']
                else:
                    fit_status = CONFIG['labels']['fit_no_ppg']
                
                # Script generation based on the calculated Fit
                if "YES" in fit_status.upper():
                    s = CONFIG['text_script']
                    # Inserts Name and AI-found insight into Landon's message
                    hook = f"{s['intro'].format(first_name=name.split()[0])} {s['body'].format(insight=data[10])} {s['closing']}"
                else:
                    hook = CONFIG['labels']['msg_no_fit']

                final_row = [
                    CONFIG['system_version'], 
                    datetime.datetime.now().strftime("%m-%d-%y"), 
                    name, data[1], data[2], hometown, school, 
                    div, data[6], "Scouted", fit_status, str(ppg), 
                    data[9], hook, data[11], data[12]
                ]
                sheet.append_row(final_row)
                rows_added += 1
                
    return rows_added

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
import mesop as me
import logic, os, json
from dataclasses import field

# Load Config
with open('scouting_config.json', 'r') as f:
    CONFIG = json.load(f)

@me.stateclass
class State:
  is_scouting: bool = False
  status_message: str = ""
  scout_data: list[list[str]] = field(default_factory=list)
  test_id: int = 0

def load_master_list(state: State):
  try:
    creds = logic.get_credentials()
    sheet = logic.get_sheet_connection(creds)
    rows = sheet.get_all_values()[1:]
    yes = [r for r in rows if "YES" in r[10].upper()]
    no = [r for r in rows if "NO" in r[10].upper()]
    state.scout_data = yes[::-1] + no[::-1]
  except Exception as e:
    state.status_message = f"Error: {str(e)}"

@me.page(path="/", on_load=lambda e: load_master_list(me.state(State)))
def dashboard():
  state = me.state(State)
  table_border = me.Border(bottom=me.BorderSide(width=1, style="solid", color="#eeeeee"))
  
  with me.box(style=me.Style(padding=me.Padding.all(24), background="#f4f7f6", min_height="100vh", font_family="Inter, sans-serif")):
    with me.box(style=me.Style(display="flex", justify_content="space-between", margin=me.Margin(bottom=24))):
      me.text(CONFIG['app_settings']['title'], type="headline-5", style=me.Style(font_weight=800))
      with me.box(style=me.Style(display="flex", gap=12)):
        me.button("Clear View", on_click=lambda e: (setattr(state, 'scout_data', []), setattr(state, 'test_id', state.test_id + 1)), type="stroked")
        me.button("Refresh", on_click=lambda e: load_master_list(state), type="stroked")
        me.uploader(key=f"u_{state.test_id}", label="UPLOAD PORTAL", on_upload=handle_upload, type="flat")

    if state.is_scouting: me.progress_spinner()
    if state.status_message: me.text(state.status_message)

    with me.box(style=me.Style(background="#fff", border_radius=8, box_shadow="0 2px 10px rgba(0,0,0,0.1)", overflow_x="auto")):
      grid = "85px 140px 45px 55px 120px 140px 45px 90px 140px 55px 55px 65px 450px"
      with me.box(style=me.Style(display="grid", grid_template_columns=grid, padding=me.Padding.all(12), background="#1a1a1a", color="#fff", font_size=11, font_weight=700)):
        for h in CONFIG['app_settings']['headers']: me.text(h)

      for row in state.scout_data:
        d = row + [""] * (16 - len(row))
        vals = [d[1], d[2], d[3], d[4], d[5], d[6], d[7], d[8], d[10], d[11], d[12], d[15], d[13]]
        with me.box(style=me.Style(display="grid", grid_template_columns=grid, padding=me.Padding.all(12), border=table_border, font_size=12, align_items="center")):
          for i, v in enumerate(vals):
            style = me.Style(font_weight=700 if i in [1, 8] else 400)
            if i == 8: style.color = "#2e7d32" if "YES" in str(v).upper() else "#d32f2f"
            me.text(str(v), style=style)

def handle_upload(event: me.UploadEvent):
  state = me.state(State)
  state.is_scouting = True
  yield
  try:
    with open("temp.jpg", "wb") as f: f.write(event.file.read())
    logic.process_portal_screenshot("temp.jpg", os.environ.get("GOOGLE_API_KEY"), logic.get_sheet_connection(logic.get_credentials()))
    load_master_list(state)
    state.status_message = "✅ Scouting Complete"
  except Exception as e: state.status_message = f"Error: {e}"
  state.is_scouting = False
  yield
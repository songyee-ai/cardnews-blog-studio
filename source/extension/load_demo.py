from pathlib import Path
import json
from app import Store
root=Path(__file__).resolve().parent
target=root/'data/studio.sqlite3'
if target.exists():raise SystemExit('Existing database preserved. Use a fresh folder for the demo.')
store=Store(target)
with store.db() as db:db.execute('UPDATE state SET body=? WHERE id=1',((root/'demo-state.json').read_text(encoding='utf-8'),))
print('Approved public-data demo loaded. Run python app.py.')

from html.parser import HTMLParser
from pathlib import Path
import json
import re

ROOT=Path(__file__).resolve().parents[1]


class Page(HTMLParser):
    def __init__(self): super().__init__();self.ids=[];self.files=[]
    def handle_starttag(self,tag,attributes):
        attrs=dict(attributes)
        if attrs.get('id'):self.ids.append(attrs['id'])
        if tag in ['script','img'] and attrs.get('src'):self.files.append(attrs['src'])
        if tag=='link' and attrs.get('href'):self.files.append(attrs['href'])


page=Page();page.feed((ROOT/'index.html').read_text(encoding='utf-8'))
assert len(page.ids)==len(set(page.ids)),'Duplicate HTML IDs'
for relative in page.files:
    assert (ROOT/relative).is_file(),f'Missing static asset: {relative}'
for source in (ROOT/'界面').glob('*'):
    if source.suffix in ['.js','.mjs']:
        for relative in re.findall(r"from ['\"](\./[^'\"]+)['\"]",source.read_text(encoding='utf-8')):
            assert (source.parent/relative).is_file(),f'Missing module: {relative}'
raw=(ROOT/'界面/songs.js').read_text(encoding='utf-8')
tracks=json.loads(re.search(r'=\s*(\[.*\])\s*;',raw,re.S)[1])
assert len({str(track['id']) for track in tracks})==len(tracks),'Duplicate catalog IDs'
for track in tracks:
    for key in ['artwork','poster','credits']:
        assert (ROOT/track[key]).is_file(),track[key]
print(f'PASS: {len(page.ids)} unique HTML IDs, module imports and {len(tracks)} sample records; MP4 is optional')

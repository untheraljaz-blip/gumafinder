#!/usr/bin/env python3
"""Convert Awin CSV(.gz) into per-size public JSON. Never publish the feed URL."""
import argparse,csv,gzip,io,json,re,collections,datetime,urllib.request,os,tempfile
from pathlib import Path
RX=re.compile(r'(?<!\d)(\d{3})\s*/\s*(\d{2,3})\s*(?:ZR|R)\s*(\d{2})(?!\d)',re.I)
SEASONS={'Letne pnevmatike':'letne','Zimske pnevmatike':'zimske','Celoletne pnevmatike':'celoletne'}
def convert(path,out):
    groups=collections.defaultdict(list)
    seen=set()
    with gzip.open(path,'rt',encoding='utf-8-sig',newline='') if str(path).endswith('.gz') else open(path,encoding='utf-8-sig',newline='') as f:
        for row in csv.DictReader(f):
            season=SEASONS.get((row.get('merchant_category') or '').strip())
            if not season:continue
            txt=' '.join((row.get('specifications') or '',row.get('product_name') or ''))
            match=RX.search(txt)
            if not match:continue
            w,p,r=map(int,match.groups())
            if not(125<=w<=355 and 25<=p<=95 and 10<=r<=24):continue
            try: price=float((row.get('search_price') or '').replace(',','.'))
            except ValueError:continue
            if not (0<price<10000 and row.get('currency','EUR')=='EUR'):continue
            url=row.get('aw_deep_link','')
            if not url.startswith('https://www.awin1.com/'):continue
            product_id=row.get('aw_product_id') or row.get('merchant_product_id') or ''
            key=(product_id,season,w,p,r)
            if key in seen:continue
            seen.add(key)
            name=(row.get('product_name') or '')[:220]
            brand=(row.get('brand_name') or '').strip()[:80]
            if not brand:brand=name.split(' ')[0]
            try:shipping=float((row.get('delivery_cost') or '').replace(',','.'))
            except ValueError:shipping=None
            try: stock_qty=int(row.get('stock_quantity') or '')
            except ValueError: stock_qty=None
            in_stock=(row.get('in_stock') or '').strip()
            available= (stock_qty > 0 if stock_qty is not None else in_stock=='1')
            item={'stock':stock_qty,'available':available,'name':name,'brand':brand,'season':season,'price':round(price,2),'url':url,
                  'id':str(product_id),'image':row.get('merchant_image_url') or '',
                  'shipping':shipping if shipping is not None and shipping>=0 else None}
            groups[f'{w}-{p}-{r}'].append(item)
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    if not groups:raise SystemExit('No usable tyre offers; refusing empty update.')
    counts={}
    for size,items in groups.items():
        items.sort(key=lambda x:x['price'])
        (out/f'{size}.json').write_text(json.dumps(items,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
        counts[size]=len(items)
    for old in out.glob('*.json'):
        if old.stem != 'meta' and old.stem not in counts: old.unlink()
    metadata={'updated_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
              'source':'Awin · Gume-direkt.com SI','sizes':counts,'total':sum(counts.values()),
              'note':'Prices are feed snapshots; shipping and stock must be confirmed at the store.'}
    (out/'meta.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Converted {metadata["total"]} offers across {len(groups)} dimensions.')
    if not counts:raise SystemExit('No usable tyre offers; refusing empty update.')
if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--file',help='Local .csv.gz file')
    ap.add_argument('--output',default='data')
    a=ap.parse_args()
    if a.file:convert(a.file,a.output)
    else:
        url=os.environ.get('AWIN_FEED_URL','')
        if not url.startswith('https://'):raise SystemExit('Missing HTTPS AWIN_FEED_URL secret')
        req=urllib.request.Request(url,headers={'User-Agent':'GumaFinder/1.0'})
        with urllib.request.urlopen(req,timeout=180) as resp:
            if resp.status!=200:raise SystemExit('Feed request failed')
            payload=resp.read(150_000_001)
        if len(payload)>150_000_000:raise SystemExit('Feed too large')
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/('feed.csv.gz' if payload[:2]==b'\x1f\x8b' else 'feed.csv')
            p.write_bytes(payload)
            convert(p,a.output)

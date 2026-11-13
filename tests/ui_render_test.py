"""UI rendering with stubbed API data because this environment blocks Chromium network navigation.
Actual HTTP authorization/end-to-end API tests are in test_api.py.
"""
import json, os, requests
from pathlib import Path
from playwright.sync_api import sync_playwright
BASE=os.getenv('APP_BASE','http://127.0.0.1:8765'); PWD=os.environ['APP_ADMIN_PASSWORD']
ROOT=Path(__file__).resolve().parents[1]
HTML=(ROOT/'static/index.html').read_text().replace('<link rel="stylesheet" href="/static/style.css">','').replace('<script src="/static/app.js" defer></script>','')
CSS=(ROOT/'static/style.css').read_text();JS=(ROOT/'static/app.js').read_text()
SCREEN=ROOT/'screenshots';SCREEN.mkdir(exist_ok=True)

def snapshot(s):
    data={}
    for route in ['/api/me','/api/boards','/api/documents','/api/activity','/api/users']:
        r=s.get(BASE+route)
        if r.ok:data[route]=r.json()
    for b in data['/api/boards']:
        r=s.get(BASE+f'/api/boards/{b["id"]}')
        if r.ok:data[f'/api/boards/{b["id"]}']=r.json()
    return data

def render(page, data):
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.set_content(HTML)
    page.add_style_tag(content=CSS)
    page.add_script_tag(content='window.fetch = async function(input) {const path=String(input);const data='+json.dumps(data,ensure_ascii=False)+';return new Response(JSON.stringify(data[path] ?? {error:"stub"}), {status:data[path]===undefined?404:200, headers:{"Content-Type":"application/json"}}) }')
    page.add_script_tag(content=JS)
    page.locator('.board-tile').first.wait_for(timeout=10000)
    return errors

with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
    a=requests.Session();assert a.post(BASE+'/api/login',json={'email':'admin@local','password':PWD}).ok
    page=browser.new_page(viewport={'width':1440,'height':950},device_scale_factor=1)
    errs=render(page,snapshot(a))
    page.screenshot(path=str(SCREEN/'01_yonetici_pano_listesi.png'),full_page=True)
    assert page.locator('.board-tile').count()>=3
    page.locator('.board-tile').first.click();page.locator('.sticky').first.wait_for()
    page.screenshot(path=str(SCREEN/'02_gorsel_pano.png'),full_page=True)
    page.locator('.sticky-title').first.click();page.get_by_text('Kart Ayrıntıları').wait_for()
    page.locator('#closeModal').click()
    page.get_by_role('button',name='Görev Akışı').click();assert page.locator('.lane').count()==3
    page.locator('[data-nav="docs"]').click();page.locator('.doc-table').wait_for();page.screenshot(path=str(SCREEN/'03_evraklar.png'),full_page=True)
    page.locator('[data-nav="users"]').click();page.locator('.user-row').first.wait_for();page.screenshot(path=str(SCREEN/'04_yetkiler.png'),full_page=True)
    assert not errs,errs
    viewer=requests.Session();assert viewer.post(BASE+'/api/login',json={'email':'depo@example.org','password':'deneme-Guclu-1234'}).ok
    pview=browser.new_page(viewport={'width':1360,'height':850})
    verr=render(pview,snapshot(viewer))
    assert pview.get_by_text('Salt Okunur').count()==1
    assert pview.locator('[data-nav="users"]').count()==0
    assert pview.get_by_role('button',name='Yeni Pano').count()==0
    pview.locator('.board-tile').first.click()
    assert pview.get_by_role('button',name='Yeni Kart').count()==0
    pview.screenshot(path=str(SCREEN/'05_calisan_sadece_goruntule.png'),full_page=True)
    assert not verr,verr
    print('UI_RENDER_OK: admin dashboard, visual board, kanban, document library, admin users, viewer read-only. Chromium network navigation restricted by environment.')
    browser.close()

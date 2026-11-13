"""Integration coverage with isolated storage; start app in another process and set APP_BASE, APP_ADMIN_PASSWORD."""
import io
import os
import requests

BASE=os.getenv('APP_BASE','http://127.0.0.1:8765')
PASSWORD=os.environ['APP_ADMIN_PASSWORD']

def login(s,email,password):
    r=s.post(BASE+'/api/login',json={'email':email,'password':password})
    assert r.status_code==200,(r.status_code,r.text)
    r=s.get(BASE+'/api/me');assert r.status_code==200
    return r.json()['csrf']

def run():
    a=requests.Session()
    assert requests.get(BASE+'/health').json()['ok']
    assert a.get(BASE+'/api/boards').status_code==401
    csrf=login(a,'admin@local',PASSWORD)
    hdr={'X-CSRF-Token':csrf}
    assert a.post(BASE+'/api/boards',json={'title':'Geçerli pano adı'},headers={}).status_code==403 # CSRF
    boards=a.get(BASE+'/api/boards').json();assert len(boards)>=3
    user=a.post(BASE+'/api/users',json={'name':'Depo Çalışanı','email':'depo@example.org','password':'deneme-Guclu-1234'},headers=hdr)
    assert user.status_code==200,user.text
    uid=user.json()['id']
    board=a.post(BASE+'/api/boards',json={'title':'Özel Etkinlik Dosyası','subtitle':'Sadece depo personeli','project_ref':'P-55','color':'#ED6B43','visible_to_all':False,'member_ids':[]},headers=hdr)
    assert board.status_code==200,board.text
    bid=board.json()['id']
    card=a.post(BASE+f'/api/boards/{bid}/cards',json={'title':'Kurulum kontrolü','body':'İşe giriş 09:00','status':'Yapılacak','tag':'Saha','due_date':'2026-11-20','owner_id':uid,'x':90,'y':100},headers=hdr)
    assert card.status_code==200,card.text
    cid=card.json()['id']
    nested=a.post(BASE+f'/api/cards/{cid}/subboard',headers=hdr)
    assert nested.status_code==200,nested.text
    child=nested.json()['id']
    up=a.post(BASE+'/api/documents',headers=hdr,data={'title':'Kurulum Talimatı','board_id':str(bid),'card_id':str(cid)},files={'file':('talimat.txt',b'BU EVRAK GORUNUR', 'text/plain')})
    assert up.status_code==200,up.text
    did=up.json()['id']
    assert a.get(BASE+f'/api/documents/{did}/file').content==b'BU EVRAK GORUNUR'
    v=a.post(BASE+f'/api/documents/{did}/versions',headers=hdr,files={'file':('talimat_v2.txt',b'GUNCEL EVRAK','text/plain')})
    assert v.status_code==200,v.text
    assert a.get(BASE+f'/api/documents/{did}/file').content==b'GUNCEL EVRAK'
    assert a.get(BASE+f'/api/documents/{did}/file?version=1').content==b'BU EVRAK GORUNUR'
    view=requests.Session();vcsrf=login(view,'depo@example.org','deneme-Guclu-1234')
    assert all(b['id']!=bid for b in view.get(BASE+'/api/boards').json())
    assert view.get(BASE+f'/api/boards/{bid}').status_code==403
    assert view.get(BASE+f'/api/boards/{child}').status_code==403
    assert view.get(BASE+f'/api/documents/{did}/file').status_code==403
    assert view.post(BASE+'/api/boards',headers={'X-CSRF-Token':vcsrf},json={'title':'Kötü'}).status_code==403
    assert view.post(BASE+f'/api/boards/{bid}/cards',headers={'X-CSRF-Token':vcsrf},json={'title':'Kötü'}).status_code==403
    assert view.delete(BASE+f'/api/documents/{did}',headers={'X-CSRF-Token':vcsrf}).status_code==403
    assert view.get(BASE+'/api/users').status_code==403
    grant=a.patch(BASE+f'/api/boards/{bid}',headers=hdr,json={'title':'Özel Etkinlik Dosyası','subtitle':'Sadece depo personeli','project_ref':'P-55','color':'#ED6B43','visible_to_all':False,'member_ids':[uid]})
    assert grant.status_code==200,grant.text
    assert any(b['id']==bid for b in view.get(BASE+'/api/boards').json())
    assert view.get(BASE+f'/api/boards/{bid}').status_code==200
    assert view.get(BASE+f'/api/boards/{child}').status_code==200
    assert view.get(BASE+f'/api/documents/{did}/file').content==b'GUNCEL EVRAK'
    assert view.get(BASE+f'/api/documents/{did}/versions').status_code==200
    assert view.get(BASE+'/api/activity').status_code==403
    revoke=a.patch(BASE+f'/api/boards/{bid}',headers=hdr,json={'title':'Özel Etkinlik Dosyası','subtitle':'','project_ref':'P-55','color':'#ED6B43','visible_to_all':False,'member_ids':[]})
    assert revoke.status_code==200
    assert view.get(BASE+f'/api/documents/{did}/file').status_code==403
    # upload validation
    invalid=a.post(BASE+'/api/documents',headers=hdr,data={'title':'Sahte pdf','board_id':str(bid)},files={'file':('bad.pdf',b'<script>bad</script>','application/pdf')})
    assert invalid.status_code==415,invalid.text
    assert a.get(BASE+'/api/activity').status_code==200
    print('PASS: 28+ authenticated user, board, CSRF, upload, version, permissions, nested-board, and audit assertions')

if __name__=='__main__':run()

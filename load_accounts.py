import requests
import json

BASE = 'http://127.0.0.1:5056'

# Login
login = requests.post(f'{BASE}/api/auth/login', json={
    'email': 'USER_EMAIL',
    'password': 'USER_PASSWORD'
}, timeout=10)
print(f'Login: {login.status_code}')

token = None
if login.status_code == 200:
    data = login.json()
    token = data.get('token') or data.get('access_token')

headers = {'Content-Type': 'application/json'}
if token:
    headers['Authorization'] = f'Bearer {token}'

# Save API Keys
settings = {
    'api_keys': {
        'pexels': '',
        'gemini': '',
        'telegram_token': '',
        'telegram_admin': '',
    }
}
r = requests.post(f'{BASE}/api/settings', json=settings, headers=headers, timeout=10)
print(f'Settings: {r.status_code} - {r.text[:200]}')

# YouTube accounts (id is required!)
yt = [
    {
        'id': 'future_lab',
        'name': 'Future Lab',
        'platform': 'youtube',
        'niche': 'mystery',
        'client_id': 'CLIENT_ID_1',
        'client_secret': 'HIDDEN_SECRET_1'
    },
    {
        'id': 'power_of_money',
        'name': 'The Power Of Money',
        'platform': 'youtube',
        'niche': 'finance',
        'client_id': 'CLIENT_ID_2',
        'client_secret': 'HIDDEN_SECRET_2'
    },
    {
        'id': 'healthy_living',
        'name': 'How is the healthy living',
        'platform': 'youtube',
        'niche': 'health',
        'client_id': 'CLIENT_ID_3',
        'client_secret': 'HIDDEN_SECRET_3'
    },
    {
        'id': 'info_repository',
        'name': 'Information repository',
        'platform': 'youtube',
        'niche': 'mystery',
        'client_id': 'CLIENT_ID_4',
        'client_secret': 'HIDDEN_SECRET_4'
    },
]

for acc in yt:
    r = requests.post(f'{BASE}/api/accounts/add', json=acc, headers=headers, timeout=10)
    print(f'  YT [{acc["name"]}]: {r.status_code} - {r.text[:150]}')

# TikTok accounts
tt = [
    {
        'id': 'tiktok_power_of_money',
        'name': 'The Power Of Money',
        'platform': 'tiktok',
        'niche': 'finance',
        'email': 'HIDDEN_EMAIL',
        'password': 'HIDDEN_PASSWORD'
    },
    {
        'id': 'tiktok_reddithistoriyss',
        'name': 'reddithistoriyss',
        'platform': 'tiktok',
        'niche': 'history',
        'email': 'HIDDEN_EMAIL',
        'password': 'HIDDEN_PASSWORD'
    },
]

for acc in tt:
    r = requests.post(f'{BASE}/api/accounts/add', json=acc, headers=headers, timeout=10)
    print(f'  TT [{acc["name"]}]: {r.status_code} - {r.text[:150]}')

# Verify
r = requests.get(f'{BASE}/api/accounts', headers=headers, timeout=10)
data = r.json()
print(f'\n=== SONUC ===')
print(f'YouTube: {len(data.get("youtube", []))} hesap')
print(f'TikTok: {len(data.get("tiktok", []))} hesap')
for yt_acc in data.get('youtube', []):
    print(f'  - {yt_acc.get("name", "?")}')
for tt_acc in data.get('tiktok', []):
    print(f'  - {tt_acc.get("name", "?")}')

# Verify settings
r = requests.get(f'{BASE}/api/settings', headers=headers, timeout=10)
s = r.json()
keys = s.get('api_keys', {})
print(f'\nAPI Keys:')
print(f'  Gemini: {"OK" if keys.get("gemini") else "EMPTY"}')
print(f'  Pexels: {"OK" if keys.get("pexels") else "EMPTY"}')
print(f'  Telegram: {"OK" if keys.get("telegram_token") else "EMPTY"}')
print('\nDONE!')

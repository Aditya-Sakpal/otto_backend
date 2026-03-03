import requests

def main():
    try:
        r = requests.post('http://127.0.0.1:8005/api/v1/auth/login', json={'email':'kaustarafdar@gmail.com','password':'12345678'}, timeout=10)
        print('login', r.status_code)
        if r.status_code == 200:
            token = r.json().get('access_token')
            h = {'Authorization': f'Bearer {token}'}
            r2 = requests.get('http://127.0.0.1:8005/api/v1/leads?company_id=6d40b509-82bc-4d21-9614-de91cc25dc1b&skip=0&limit=20&status=qualified_booked&search=zx', headers=h, timeout=30)
            print('leads', r2.status_code)
            print(r2.text[:2000])
        else:
            print(r.text)
    except Exception as e:
        print('err', e)

if __name__ == "__main__":
    main()


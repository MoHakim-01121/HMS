import requests
from django.conf import settings


def send_wa(target: str, message: str) -> dict:
    try:
        resp = requests.post(
            'https://api.fonnte.com/send',
            headers={'Authorization': settings.FONNTE_TOKEN},
            data={'target': target, 'message': message},
            timeout=10,
        )
        return resp.json()
    except requests.exceptions.ConnectionError:
        return {'status': False, 'reason': 'Cannot connect to Fonnte API — check network connection'}
    except requests.exceptions.Timeout:
        return {'status': False, 'reason': 'Fonnte API request timed out'}
    except requests.exceptions.RequestException as exc:
        return {'status': False, 'reason': str(exc)}

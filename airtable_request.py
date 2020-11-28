import os
import requests
from funcy import get_in, partial
from dotenv import load_dotenv

# load env variables
load_dotenv()
AIRTABLE_API_KEY = os.getenv('AIRTABLE_API_KEY')
BASE_NAME = os.getenv('BASE_NAME')
TABLE_NAME = os.getenv('TABLE_NAME')
MAX_AIRTABLE_PATCH = 10

headers = {'Authorization': "Bearer " + AIRTABLE_API_KEY}
url = 'https://api.airtable.com/v0/{0}/{1}'.format(BASE_NAME, TABLE_NAME)

airtable_request = partial(requests.request, url=url, headers=headers)


def single_airtable_request(record_id):
    single_url = 'https://api.airtable.com/v0/{0}/{1}/{2}'.format(BASE_NAME, TABLE_NAME, record_id)
    ar = partial(requests.request, url=single_url, headers=headers)
    return ar("get")

def update_payload_state(payload, request_type):
    if len(payload['records']) >= MAX_AIRTABLE_PATCH:
        _ = airtable_request(request_type, json=payload)
        payload = {"records": [], "typecast": True}
    return payload

def send_nonempty_payload(payload, request_type):
    if len(payload['records']) > 0:
        _ = airtable_request(request_type, json=payload)

""" airtable_request.py

This module abstracts and accounts for paging when sending requests to the Airtable API
"""
import os
import requests
from typing import Tuple, Dict
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


def single_airtable_request(record_id) -> Dict:
    """ An Airtable get request for a single record 
    
    Args:
        payload: Airtable API-friendly dictionary with contents of request
        request_type: String denoting what type of request ("get", "post", "patch) etc
    
    Returns:
        Empty Airtable API-friendly payload template
    """
    single_url = 'https://api.airtable.com/v0/{0}/{1}/{2}'.format(BASE_NAME, TABLE_NAME, record_id)
    ar = partial(requests.request, url=single_url, headers=headers)
    return ar("get")

def update_payload_state(payload: dict, request_type: str) -> Dict:
    """ Abstracts paging from airtable requests

    If the payload's record count is at the MAX_AIRTABLE_PATCH number, then
    the method sends the request, and returns an empty payload template.

    Args:
        payload: Airtable API-friendly dictionary with contents of request
        request_type: String denoting what type of request ("get", "post", "patch) etc

    Returns:
        If the payload is sent, returns an empty Airtable API-friendly payload template.
        Else, returns the inputted payload 
    """
    if len(payload['records']) >= MAX_AIRTABLE_PATCH:
        _ = airtable_request(request_type, json=payload)
        payload = {"records": [], "typecast": True}
    return payload

def update_payload_states(patch_payload: dict, create_payload: dict) -> Tuple[dict, dict]:
    """ Method to abstract paging from 2 sets of payloads (patch + post) 
    
    Args:
        patch_payload: Airtable API-friendly dictionary with contents of patch requests
        create_payload: Airtable API-friendly dictionary with contents of post requests

    Returns:
        Tuple of the updated patch_payload and create_payload
    """
    patch_payload = update_payload_state(patch_payload, "patch")
    create_payload = update_payload_state(create_payload, "post")

    return patch_payload, create_payload

def send_nonempty_payload(payload: dict, request_type: str):
    """ Abstracts paging from airtable requests

    If the payload's record count is greater than 0, then
    the method sends the request, and returns an empty payload template. This method is usually
    used at the end when all records are processed.

    Args:
        payload: Airtable API-friendly dictionary with contents of request
        request_type: String denoting what type of request ("get", "post", "patch) etc
    """
    if len(payload['records']) > 0:
        _ = airtable_request(request_type, json=payload)

def send_nonempty_payloads(patch_payload: dict, create_payload: dict):
    """ Method to abstract paging from 2 sets of payloads (patch + post) at the end of paging iteration
    
    Args:
        patch_payload: Airtable API-friendly dictionary with contents of patch requests
        create_payload: Airtable API-friendly dictionary with contents of post requests
    """
    patch_payload = send_nonempty_payload(patch_payload, "patch")
    create_payload = send_nonempty_payload(create_payload, "post")
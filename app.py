""" app.py

This module combines the Flask app, the logic to processing gcal webhooks, and updating the Postgres database
"""
import os
import time
import arrow
from typing import Dict, Tuple
from datetime import datetime, timedelta
from funcy import get_in
from flask import Flask, request, jsonify, Response
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import func
from dotenv import load_dotenv

from calendar_request import Calendar
from airtable_request import airtable_request, update_payload_state, send_nonempty_payload, single_airtable_request
load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
CALENDAR_ID = os.getenv('CALENDAR_ID')
calendar = Calendar(CALENDAR_ID)

GCAL_COLOR_MAPPING = {
    "5": "Done", # yellow ish
    "11": "Abandoned" # red ish
} # some GCAL magic variables here


class Snapshot(db.Model):
    """ Snapshot defines the model for a Postgres database entry

    Attributes:
        id (int): The primary key and unique identifier for the row
        syncToken (str): The syncToken granted by the Gcal API used for keeping track of changes
        time_created (Datetime): Datetime when the record was inserted to Postgres
    """
    __tablename__ = 'snapshot'
    id = db.Column(db.Integer, primary_key=True)
    syncToken = db.Column(db.String(200), unique=True)
    time_created = db.Column(db.DateTime(timezone=True), server_default=func.now())

    def __init__(self, syncToken: str):
        """ Initializes Snapshot by storing the `syncToken` """
        self.syncToken = syncToken


def round_up_15_mins(start: datetime) -> datetime:
    """ Helper method that rounds up to the nearest 15-min interval

    Args:
        start: The starting time
    
    Returns:
        The datetime rounded up to the nearest 15-min interval
    """
    start += timedelta(minutes=14)

    return start - timedelta(minutes=tm.minute % 15,
                          seconds=tm.second,
                          microseconds=tm.microsecond)


def parse_event_description(event: dict) -> Tuple[str, str]:
    """ Parses the Gcal event's description for the `airtable_record_id` and `source`

    Examples:
        >>> event['description'] = "38xfjrf30jxojr33pd201jf s3"
        >>> parse_event_description(event)
        ("38xfjrf30jxojr33pd201jf", "s3")

        >>> event['description'] = "38xfjrf30jxojr33pd201jf"
        >>> parse_event_description(event)
        ("38xfjrf30jxojr33pd201jf", None)

    Args:
        event: Dictionary that stores the event's information
    
    Returns:
        Tuple of `airtable_record_id` and `source`
    """
    string_to_parse = get_in(event, ['description'], "").split(" ")
    airtable_record_id, source = string_to_parse[0], string_to_parse[1:2] or None
    if source:
        source = source[0]
    return airtable_record_id, source


def parse_event_duration(event: dict) -> float:
    """ Parses an Gcal event's start and endtimes to get the event duration

    Args:
        event: Dictionary that stores the event's information

    Returns:
        Duration in hours (float)
    """
    start = get_in(event, ['start', 'dateTime'])
    end = get_in(event, ['end', 'dateTime'])

    return (arrow.get(end) - arrow.get(start)).seconds / 3600


def create_payload_from_event(event: dict) -> Dict:
    """ Builds an Airtable API payload to create/update the record corresponding to a Gcal event

    Args:
        event: Dictionary that stores the event's information

    Returns:
        The Airtable-friendly payload dictionary with the necessary info
    """
    return {
        "fields": {
            "Name": get_in(event, ["summary"]),
            "duration": parse_event_duration(event),
            "Deadline": get_in(event, ["end", "dateTime"], "")[0:10],
            "lastCalendarDeadline": get_in(event, ["end", "dateTime"], "")[0:10],
            "calendarEventId": get_in(event, ['id'])
        }
    }


def process_new_event(event: dict, calendar: Calendar):
    """ Create an Airtable record for the new event, then link the record with the event

    Args:
        event: Dictionary that stores the event's information
        calendar: The :obj:`calendar_request.Calendar` associated with the calendar we're editting
    """
    if get_in(event, ["status"], "cancelled") == "cancelled":
        return

    # Create Airtable Record
    payload = {"records": [create_payload_from_event(event)], "typecast": True}
    response = airtable_request("post", json=payload).json()

    # get airtable id
    airtable_record_id = response['records'][0]['id']

    # attach to airtable_record_id to event description
    calendar_event_id = get_in(event, ['id'])
    calendar.patch_event(calendar_event_id, airtable_record_id)

    return


def process_change(update_fields: dict, calendar_feature, airtable_feature, airtable_field_names: list) -> Dict:
    """ Processes change in `calendar_feature` relative to the airtable record

    If the `calendar_feature` doesn't match the `airtable_feature`, then it updates the `airtable_feature`

    Note:
        If there is a change from the Airtable side and the Gcal webhook side within the same minute,
        the Airtable change will likely win out, since it changes on a minute basis, while the webhook is relatively
        instantaneous, therefore the Airtable change will be acting on top of the Gcal webhook change.

    Args:
        update_fields: The payload dictionary that will be sent in a patch/post request to the Airtable API
        calendar_feature: The feature in the calendar's event to be compared
        airtable_feature: The feature in the Airtable's record to be compared
        airtable_field_names: A list of the fields to be updated in Airtable with the `calendar_feature` value

    Returns:
        An updated-version of `update_fields` to be sent to airtable in a patch/post request
    """
    print(f'{airtable_field_names}: cal({calendar_feature}) and air({airtable_feature})')
    if calendar_feature != airtable_feature:
        for field in airtable_field_names:
            update_fields.update({
                field: calendar_feature,
            })

    return update_fields


def process_deadline_change(update_fields: dict, event: dict, record: dict) -> Dict:
    """ Processes change in `Deadline` relative to the airtable record

    Args:
        update_fields: The payload dictionary that will be sent in a patch/post request to the Airtable API
        event: event: Dictionary that stores the event's information
        record: The individual record being processed

    Returns:
        An updated-version of `update_fields` to be sent to airtable in a patch/post request
    """
    calendar_datetime = get_in(event, ['end',  'dateTime'], "")[0:10]
    airtable_datetime = get_in(record, ['fields', 'Deadline'], "")
    return process_change(update_fields, calendar_datetime, airtable_datetime, ['Deadline', 'lastCalendarDeadline'])

def process_endtime_change(update_fields: dict, event: dict, record: dict) -> Dict:
    """ Processes change in `endTime` relative to the airtable record

    Args:
        update_fields: The payload dictionary that will be sent in a patch/post request to the Airtable API
        event: event: Dictionary that stores the event's information
        record: The individual record being processed

    Returns:
        An updated-version of `update_fields` to be sent to airtable in a patch/post request
    """
    calendar_endtime = get_in(event, ['end', 'dateTime'], "")
    airtable_endtime = get_in(record, ['fields', 'endTime'], "")
    return process_change(update_fields, calendar_endtime, airtable_endtime, ['endTime'])

def process_duration_change(update_fields: dict, event: dict, record: dict) -> Dict:
    """ Processes change in `Duration` relative to the airtable record

    Args:
        update_fields: The payload dictionary that will be sent in a patch/post request to the Airtable API
        event: event: Dictionary that stores the event's information
        record: The individual record being processed

    Returns:
        An updated-version of `update_fields` to be sent to airtable in a patch/post request
    """
    calendar_duration = parse_event_duration(event)
    airtable_duration = get_in(record, ["fields", "duration"], 0)
    return process_change(update_fields, calendar_duration, airtable_duration, ['Duration'])

def process_name_change(update_fields: dict, event: dict, record: dict) -> Dict:
    """ Processes change in `Name` relative to the airtable record

    Args:
        update_fields: The payload dictionary that will be sent in a patch/post request to the Airtable API
        event: event: Dictionary that stores the event's information
        record: The individual record being processed

    Returns:
        An updated-version of `update_fields` to be sent to airtable in a patch/post request
    """
    calendar_name = get_in(event, ['summary'])
    airtable_name = get_in(record, ["fields", "name"], 0)
    return process_change(update_fields, calendar_name, airtable_name, ['Name'])

def transition_done_record(update_fields: dict, event: dict, record: dict) -> Dict:
    """ Detects whether the `color_id` of an event is changed to the color corresponding to `Done` or `Abandoned`

    1. Check if the calendar event's `color_id` is changed
    2. Get the `Status` corresponding to the `color_id`
    3. If this Status doesn't match the airtable, then update the airtable `Status` (and `lastStatus`)

    Note:
        If there is a change from the Airtable side and the Gcal webhook side within the same minute,
        the Airtable change will likely win out, since it changes on a minute basis, while the webhook is relatively
        instantaneous, therefore the Airtable change will be acting on top of the Gcal webhook change.

    Args:
        update_fields: The payload dictionary that will be sent in a patch/post request to the Airtable API
        event: event: Dictionary that stores the event's information
        record: The individual record being processed

    Returns:
        An updated-version of `update_fields` to be sent to airtable in a patch/post request
    """
    color_id = get_in(event, ['colorId'], "")

    if color_id in GCAL_COLOR_MAPPING.keys():
        new_status = GCAL_COLOR_MAPPING[color_id]
        airtable_status = get_in(record, ["fields", "Status"], "")

        print(f'Changed-Color? : new({new_status}) and air({airtable_status})')
        if new_status != airtable_status:
            update_fields.update({
                "Status": new_status,
                "lastStatus": "Done",
            })

    return update_fields

def process_event_change(events):
    """Batching airtable changes with 10 records per request 

    Args:
        events (List[dict]): A single page of events 

    See Also: 
        https://developers.google.com/calendar/v3/reference/events
    """
    if events.get('items'):
        patch_payload = {"records": [], "typecast": True}

        for event in events['items']:
            patch_payload = update_payload_state(patch_payload, "patch")
            airtable_record_id, source = parse_event_description(event)

            if not airtable_record_id:
                print(event)
                process_new_event(event, calendar)
                continue            

            record = single_airtable_request(airtable_record_id).json()
            time.sleep(0.2) # make sure we don't exceed 5 Airtable calls / second
            
            update_fields = dict()
            update_fields = process_deadline_change(update_fields, event, record)
            update_fields = process_endtime_change(update_fields, event, record)
            update_fields = process_duration_change(update_fields, event, record)
            update_fields = process_name_change(update_fields, event, record)
            update_fields = transition_done_record(update_fields, event, record)

            if update_fields:
                patch_payload['records'].append({
                    "id": airtable_record_id,
                    "fields": update_fields
                })

        send_nonempty_payload(patch_payload, "patch")
    return


@app.route('/webhook', methods=['POST'])
def respond_webhook():
    """ API Route that is response for handling Gcal webhooks """
    print(request.json)
    print(request.headers)

    # retrieve sync token and calendar events
    syncToken = db.session.query(Snapshot).order_by(Snapshot.id.desc()).first().syncToken
    events = calendar.service.events().list(calendarId=CALENDAR_ID, syncToken=syncToken).execute()

    # process each page
    while events.get('nextPageToken'):
        print(len(events['items']))

        process_event_change(events)

        time.sleep(1) # to make sure we don't get an error from Gcal for too many requests
        events = events = calendar.service.events().list(calendarId=CALENDAR_ID, pageToken=events['nextPageToken']).execute()

    # process last page
    process_event_change(events)

    # insert sync token into postgres
    new_record = Snapshot(events['nextSyncToken'])
    db.session.add(new_record)
    db.session.commit()

    return Response(status=200)


# A welcome message to test our server
@app.route('/')
def index():
    """ Index route that provides google-site-verification so we can receive webhooks at this URL """
    return '<head><meta name="google-site-verification" content="DXxkFotbs-O1mkGoLjiusZ5wJGFYoM6luH4DCM-x7pU" /></head> <body><h1>Welcome to our server !!</h1></body>'



if __name__ == '__main__':
    # Threaded option to enable multiple instances for multiple user access support
    app.run(threaded=True, port=5000)
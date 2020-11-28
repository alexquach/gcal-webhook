# app.py
import os
import time
import arrow
from funcy import get_in
from flask import Flask, request, jsonify, Response
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import func
from dotenv import load_dotenv

import cal
from airtable_request import airtable_request, update_payload_state, send_nonempty_payload, single_airtable_request
load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
CALENDAR_ID = os.getenv('CALENDAR_ID')
calendar = cal.calendar(CALENDAR_ID)


class Snapshot(db.Model):
    __tablename__ = 'snapshot'
    id = db.Column(db.Integer, primary_key=True)
    syncToken = db.Column(db.String(200), unique=True)
    time_created = db.Column(db.DateTime(timezone=True), server_default=func.now())

    def __init__(self, syncToken):
        self.syncToken = syncToken


def parse_event_description(event):
    string_to_parse = get_in(event, ['description'], "").split(" ")
    airtable_record_id, source = string_to_parse[0], string_to_parse[1:2] or None
    if source:
        source = source[0]
    return airtable_record_id, source


def parse_event_duration(event):
    """

    Returns:
        Duration in hours (float)
    """
    start = get_in(event, ['start', 'dateTime'])
    end = get_in(event, ['end', 'dateTime'])

    return (arrow.get(end) - arrow.get(start)).seconds / 3600


def create_payload_from_event(event):
    return {
        "fields": {
            "Name": get_in(event, ["summary"]),
            "Deadline": get_in(event, ["end", "dateTime"])[0:10],
            "duration": parse_event_duration(event)
        }
    }


def process_new_event(event, calendar):
    """ Create an Airtable record for the new event, then link the record with the event
    """
    # Create Airtable Record
    payload = {"records": [create_payload_from_event(event)], "typecast": True}
    response = airtable_request("post", json=payload).json()

    # get airtable id
    airtable_record_id = response['records'][0]['id']

    # attach to airtable_record_id to event description
    calendar_event_id = get_in(event, ['id'])
    calendar.patch_event(calendar_event_id, airtable_record_id)

    return


def process_deadline_change(update_fields, event, record):
    calendar_datetime = get_in(event, ["end", "dateTime"], "")[0:10]
    airtable_datetime = get_in(record, ["fields", "Deadline"], "")

    if calendar_datetime != airtable_datetime:
        update_fields.update({
            "Deadline": calendar_datetime,
            "lastCalendarDeadline": calendar_datetime
        })

    return update_fields

def process_duration_change(update_fields, event, record):
    calendar_duration = parse_event_duration(event)
    airtable_duration = get_in(record, ["fields", "duration"], 0)

    if calendar_duration != airtable_duration:
        update_fields.update({
            "duration": calendar_duration
        })

    return update_fields

def process_event_change(events):
    """Batching airtable changes with 10 records per request 
    
    Args:
        events (List[dict]): A single page of events
    """
    if events.get('items'):
        patch_payload = {"records": [], "typecast": True}

        for event in events['items']:
            patch_payload = update_payload_state(patch_payload, "patch")
            airtable_record_id, source = parse_event_description(event)

            if not airtable_record_id:
                process_new_event(event, calendar)
                continue            

            record = single_airtable_request(airtable_record_id).json()
            time.sleep(0.2) # make sure we don't exceed 5 Airtable calls / second
            
            update_fields = dict()
            update_fields = process_deadline_change(update_fields, event, record)
            update_fields = process_duration_change(update_fields, event, record)

            if update_fields:
                patch_payload['records'].append({
                    "id": airtable_record_id,
                    "fields": update_fields
                })

        send_nonempty_payload(patch_payload, "patch")
    return


@app.route('/webhook', methods=['POST'])
def respond_webhook():
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
    return '<head><meta name="google-site-verification" content="DXxkFotbs-O1mkGoLjiusZ5wJGFYoM6luH4DCM-x7pU" /></head> <body><h1>Welcome to our server !!</h1></body>'



if __name__ == '__main__':
    # Threaded option to enable multiple instances for multiple user access support
    app.run(threaded=True, port=5000)
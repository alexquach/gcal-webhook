# app.py
import os
import time
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


def get_active_airtable_records():
    """ Queries Airtable for records that have a valid deadline

    Active Records are defined as:
        Deadline set (i.e. 11/27/2020)
        lastStatus not 'Done'
    """
    fields = ["Name", "Deadline", "Status", "setCalendarDate", "Deadline Group", "calendarEventId", "duration", "lastDeadline"]
    maxRecords = 100
    formula = "AND(NOT({Deadline}=''), NOT({lastStatus}='Done'))"
    params = {"maxRecords": maxRecords,
              "fields[]": fields,
              "filterByFormula": formula}

    # TODO: Error Handling
    return airtable_request('get', params=params).json()


def parse_event_description(event):
    string_to_parse = get_in(event, ['description'], "").split(" ")
    airtable_record_id, source = string_to_parse[0], string_to_parse[1:2] or None
    if source:
        source = source[0]
    return airtable_record_id, source


def process_deadline_change(update_fields, event, airtable_record_id):
    calendar_datetime = get_in(event, ['end', 'dateTime'], "")[0:10]
    record = single_airtable_request(airtable_record_id).json()
    airtable_datetime = get_in(record, ['fields', 'Deadline'], "")

    if calendar_datetime != airtable_datetime:
        update_fields.update({
            "Deadline": calendar_datetime
        })

    return update_fields


def processEventChange(events):
    """Batching airtable changes with 10 records per request 
    
    Args:
        events (List[dict]): A single page of events
    """
    if events.get('items'):
        payload = {"records": [], "typecast": True}

        for event in events['items']:
            airtable_record_id, source = parse_event_description(event)

            if not airtable_record_id:
                continue

            payload = update_payload_state(payload, 'patch')

            update_fields = dict()
            update_fields = process_deadline_change(update_fields, event, airtable_record_id)
            time.sleep(0.2) # make sure we don't exceed 5 Airtable calls / second

            if update_fields:
                payload['records'].append({
                    "id": airtable_record_id,
                    "fields": update_fields
                })

        send_nonempty_payload(payload, 'patch')


@app.route('/webhook', methods=['POST'])
def respond_webhook():
    print(request.json)
    print(request.headers)

    # retrieve sync token and calendar events
    syncToken = db.session.query(app.Snapshot).order_by(app.Snapshot.id.desc()).first().syncToken
    events = calendar.service.events().list(calendarId=CALENDAR_ID, syncToken=syncToken).execute()

    # process each page
    while events.get('nextPageToken'):
        print(len(events['items']))

        processEventChange(events)

        time.sleep(1) # to make sure we don't get an error from Gcal for too many requests
        events = events = c.service.events().list(calendarId=CALENDAR_ID, pageToken=events['nextPageToken']).execute()

    # process last page
    processEventChange(events)

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
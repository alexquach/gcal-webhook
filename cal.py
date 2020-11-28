from google.oauth2 import service_account
from googleapiclient.discovery import build

from datetime import datetime, timedelta

SCOPES = ['https://www.googleapis.com/auth/calendar']
SERVICE_ACCOUNT_FILE = './service-account-credentials.json'

TIMEZONE = 'UTC'

class calendar:
    def __init__(self, calendar_id):
        self.calendar_id = calendar_id
        self.credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES)

        self.service = build('calendar', 'v3', credentials=self.credentials)

    def create_event(self, title, start, airtable_record_id, duration=1, timezone=TIMEZONE):
        """ Create a Google Calendar event in the specified calendar object

        Args:
            title (str):
            start (datetime):
            airtable_record_id (str):
            duration (float):
            timezone (str): 
        """
        event_body = {
            'summary': title,
            'description': airtable_record_id + " s3",
            'start': {
                'dateTime': start.isoformat(),
                'timeZone': timezone,
            },
            'end': {
                'dateTime': (start + timedelta(hours=duration)).isoformat(),
                'timeZone': timezone,
            }
        }

        created_event = self.service.events().insert(calendarId=self.calendar_id, body=event_body).execute()
        print('Event created: %s' % (created_event.get('htmlLink')))

        return created_event

    def patch_event(self, event_id, airtable_record_id, color_id=None, title=None, start=None, duration=1, timezone=TIMEZONE):
        """ Patch a Google Calendar event in the specified calendar object

        Args:
            event_id (str):
            color_id (str): string version of number (1-11) based off of Gcal event colors
            title (str):
            start (datetime):
            airtable_record_id (str):
            duration (float):
            timezone (str): 
        """
        if not event_id:
            return None

        event_body = dict()
        if color_id:
            event_body.update({'colorId': color_id})
        if start:
            event_body.update({
                'start': {
                    'dateTime': start.isoformat(),
                    'timeZone': timezone,
                },
                'end': {
                    'dateTime': (start + timedelta(hours=duration)).isoformat(),
                    'timeZone': timezone,
                },
                'description': airtable_record_id + " webhook",
            })

        patched_event = self.service.events().patch(calendarId=self.calendar_id, eventId=event_id, body=event_body).execute()
        print('Event patched: %s' % (patched_event.get('htmlLink')))

        return patched_event
    
    def get_event(self, event_id):
        if not event_id:
            return None

        return self.service.events().get(calendarId=self.calendar_id, eventId=event_id).execute()

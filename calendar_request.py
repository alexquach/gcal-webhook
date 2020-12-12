""" calendar_request.py

This module creates a class for simplified interfacing with the Google Calendar API.
"""
from datetime import datetime, timedelta
from typing import Dict

from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/calendar']
SERVICE_ACCOUNT_FILE = './service-account-credentials.json'

TIMEZONE = 'UTC'

class Calendar:
    """ This class contains the necessary information to interact with the Google Calendar API
    for a specific calendar.

    It proves methods to GET, PATCH, and POST events.
    
    Attributes:
        calendar_id: String containing the Google Calendar UUID 
        credentials: Google Credentials stored in the service-account-credential.json
        service: Instantitated Google Calendar v3 service
    """
    def __init__(self, calendar_id: str):
        """ Creates a :obj:`Calendar` object 
        
        Args:
            calendar_id (str): The string containing the Gcal UUID for which we want to instantiate a :obj:`calendar`
        """
        self.calendar_id = calendar_id
        self.credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES)

        self.service = build('calendar', 'v3', credentials=self.credentials)

    def create_event(self, title, start, airtable_record_id, duration=1, timezone=TIMEZONE) -> Dict:
        """ Create a Google Calendar event in the specified calendar object

        Args:
            title (str): A string containing the event title/name 
            start (datetime): A datetime indicating the start time for the event
            airtable_record_id (str): Id corresponding to the airtable record representation for this event
            duration (float): The duration (in hours) that the event should last
            timezone (str): (optional) The timezone in which the event should be encoded

        Returns:
            Dict with the Gcal API's response to the insert request
        """
        event_body = {
            'summary': title,
            'description': airtable_record_id + " webhook",
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
            event_id (str): String containing the Id for the existing Gcal event to be edited 
            airtable_record_id (str): Id corresponding to the airtable record representation for this event
            color_id (str): string version of number (1-11) based off of Gcal event colors
            title (str): (optional) If present, the string to update the event title/name as
            start (datetime): (optional) If present, the new start time for the event
            duration (float): (optional) If present, the new duration (in hours) for the event
            timezone (str): (optional) If present, the timezone in which the event should be encoded 
        
        Returns:
            Dict with the Gcal API's response to the patch request
        """
        if not event_id:
            return None

        event_body = {'description': airtable_record_id + " webhook"}
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
            })
        if title:
            event_body.update({'summary': title,})

        patched_event = self.service.events().patch(calendarId=self.calendar_id, eventId=event_id, body=event_body).execute()
        print('Event patched: %s' % (patched_event.get('htmlLink')))

        return patched_event
    
    def get_event(self, event_id):
        """ Get a Google Calendar event in the specified calendar object

        Args:
            event_id (str): String containing the Id for the existing Gcal event to retrieve 
        
        Returns:
            Dict with the Gcal API's response to the get request
        """
        if not event_id:
            return None

        return self.service.events().get(calendarId=self.calendar_id, eventId=event_id).execute()

# dependencies:
# googleapiclient
# httplib2
# uritemplate

# https://google-auth.readthedocs.io/en/latest/user-guide.html

from googleapiclient.discovery import build
from google.oauth2 import service_account
import google.auth
import datetime
import pytz

def authenticate(project):  # originally from https://developers.google.com/calendar/quickstart/php
    
    # If modifying these scopes, delete the file token.json.
    #SCOPES = 'https://www.googleapis.com/auth/calendar'

    credentials = service_account.Credentials.from_service_account_file(
        project.get_service_account_private_key())

    service = build('calendar', 'v3', credentials=credentials, cache_discovery=False)

    return service

def sync_project_to_calendar(project, calendar_id):
    n = 20
    service = authenticate(project)
    default_timezone = pytz.timezone(project.settings['default_timezone'])
    for node_id in project.nodes:
        node = project.nodes[node_id]

        date = node.date
        if date.tzinfo == None:
            date = default_timezone.localize(date)

        google_calendar_event = {
            'summary': node_id + ': ' + node.get_title(),
            'description': node.contents(),
            'start': {'dateTime': date.isoformat()},
            'end': {'dateTime': date.isoformat()}, }
        print(google_calendar_event)
        content = project.nodes[node_id].contents()
        service.events().insert(calendarId=calendar_id, body=google_calendar_event).execute()
        n +=1 
        if n > 20:
            return
# dependencies:
# googleapiclient
# httplib2
# uritemplate

# https://google-auth.readthedocs.io/en/latest/user-guide.html

# batch requests:
# http://googleapis.github.io/google-api-python-client/docs/epy/index.html

from googleapiclient.discovery import build
import datetime
import pytz
from google_auth_oauthlib.flow import InstalledAppFlow

def authenticate(project):  # originally from https://developers.google.com/calendar/quickstart/php
    
    # If modifying these scopes, delete the file token.json.
    SCOPES = 'https://www.googleapis.com/auth/calendar'

    flow = InstalledAppFlow.from_client_secrets_file(
                project.get_google_credentials(), SCOPES)

    creds = flow.run_local_server(port=0)

    service = build('calendar', 'v3', credentials=creds, cache_discovery=False)

    return service

def sync_project_to_calendar(project, calendar_id):

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

        content = project.nodes[node_id].contents()
        event = service.events().insert(calendarId=calendar_id, body=google_calendar_event).execute()
        print ('Event created: %s' % (event.get('htmlLink')))
        
from urtext.action import UrtextAction
import os
import datetime

class ICS(UrtextAction):

    name=['ICS']

    def execute(self, 
        param_string, 
        filename=None,
        file_pos=0,
        col_pos=0, 
        node_id=None):

        urtext_node = self.nodes[node_id]
        t = urtext_node.metadata.get_entries('timestamp')

        if not t:
            return
        t = t[0].timestamp.datetime
        ics_start_time = t.strftime('%Y%m%dT%H%M%S')
        t_end = t + datetime.timedelta(hours=2)
        ics_end_time = t_end.strftime('%Y%m%dT%H%M%S')
        text = urtext_node.content_only().encode('utf-8').decode('utf-8')
        ics = ['BEGIN:VCALENDAR',
            'VERSION:2.0',
            'PRODID:-//hacksw/handcal//NONSGML v1.0//EN',
            'BEGIN:VEVENT',
            'METHOD:PUBLISH',
            'SUMMARY:'+urtext_node.title,
            'DTSTART;TZID='+self.settings['timezone']+':'+ics_start_time,
            'DTEND;TZID='+self.settings['timezone']+':'+ics_end_time,
            'ORGANIZER;CN=Test User:MAILTO:test.user@tstdomain.com',
            'DESCRIPTION:'+' '.join(text.split('\n')),
            'END:VEVENT',
            'END:VCALENDAR',
        ]
        with open(os.path.join(self.path,urtext_node.id+'.ics'), 'w', encoding='utf-8') as f:
            f.write('\n'.join(ics))
# -*- coding: utf-8 -*-
"""
This file is part of Urtext.

Urtext is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Urtext is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Urtext.  If not, see <https://www.gnu.org/licenses/>.

"""

import re
import datetime
from pytz import timezone
from .node import UrtextNode 

def _timeline(self, nodes, kind=None):
    """ given an Urtext Project and nodes, generates a timeline """

    found_stuff = []
    for node in nodes:
        
        # metadata datestamps
        if kind in [None, 'meta']:
            id_date = node.date
            contents = self.nodes[node.id].content_only()
            found_thing = {}
            found_thing['filename'] = node.id
            found_thing['kind'] = 'from Node ID'
            found_thing['date'] = id_date
            found_thing['contents'] = contents[:150]
            found_stuff.append(found_thing)

        # inline timestamps
        if kind in [None, 'inline']:
            full_contents = self.nodes[node.id].content_only()
            full_contents = UrtextNode.strip_metadata(contents=full_contents).split('\n')

            for num, line in enumerate(full_contents, 1):

                timestamp_regex = '<.*?>'
                timestamps = re.findall(timestamp_regex, line)

                for timestamp in timestamps:
                    
                    found_thing = {}
                    datetime_obj = self._date_from_timestamp( timestamp)
                    if datetime_obj:

                        # FUTURE: The below should be turned into an option of
                        # how much surrounding text to include.
                        # position = contents.find(timestamp)
                        # lines = contents.split('\n')
                        # for num, line in enumerate(lines, 1):
                        #     if timestamp in line:
                        #         line_number = num

                        # if len(contents) < 150:
                        #     relevant_text = contents
                        # elif position < 150:
                        #     relevant_text = contents[:position + 150]
                        # elif len(contents) < 300:
                        #     relevant_text = contents[position - 150:]
                        # else:
                        #     relevant_text = contents[position - 150:position +
                        #                              150]  # pull the nearby text
                        relevant_text = line.replace('<' + timestamp + '>',
                                                              '[ ...STAMP... ]')

                        found_thing['filename'] = node.id + ':' + str(num)
                        found_thing['kind'] = 'as inline timestamp '
                        found_thing['date'] = datetime_obj
                        found_thing['contents'] = relevant_text
                        found_stuff.append(found_thing)

    sorted_stuff = sorted(found_stuff, key=lambda x: x['date'], reverse=True)
    if not sorted_stuff:
        return 'POSSIBLE ERROR. NO NODES FOUND FOR TIMELINE. timeline.py, line 94'
    start_date = sorted_stuff[0]['contents']
    timeline = []
    for index in range(0, len(sorted_stuff) - 1):
        entry_date = found_stuff[index]['date'].strftime('%a., %b. %d, %Y, %I:%M%p')
        contents = found_stuff[index]['contents'].strip()
        while '\n\n' in contents:
            contents = contents.replace('\n\n', '\n')
        contents = '      ...' + contents.replace('\n', '\n|      ') + '...   '
        timeline.extend([
            '|<----', 
            entry_date, 
            ' ', 
            found_stuff[index]['kind'],
            ' >',
            found_stuff[index]['filename'],
            '\n|\n|',
            contents,
            '\n|\n'])


    return ''.join(timeline)

timeline_functions = [ _timeline]
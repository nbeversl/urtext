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
import pprint

def _timeline(self, nodes, dynamic_definition, amount=150):
    """ given an Urtext Project and nodes, generates a timeline """

    found_stuff = []
    for node in nodes:

        if node.dynamic:
            # don't put contents of dynamic nodes into collection contents
            continue

        if node.id == self.settings['log_id']:
            # exclude log from timeline
            continue

        # metadata datestamps
        if dynamic_definition.timeline_type in [ None, 'meta']:
            contents = self.nodes[node.id].content_only()
            found_thing = {}
            found_thing['filename'] = node.id
            found_thing['kind'] = 'from Node ID'
            found_thing['value'] = node.date.strftime('%a., %b. %d, %Y, %I:%M%p')
            found_thing['sort_value'] = node.date
            found_thing['contents'] = contents[:amount]
            if len(contents) > amount:
                found_thing['contents'] = '...   ' + found_thing['contents'] +  '      ...'
            else:
                found_thing['contents'] = '      ' + found_thing['contents']
            found_stuff.append(found_thing)

            keyname = 'timestamp?? '

        # inline metavalues
        elif dynamic_definition.timeline_type == 'inline':

            amount = 100
            if not dynamic_definition.timeline_meta_key:
                return 'NOTHING'

            entries = node.metadata.get_meta_entries(
                dynamic_definition.timeline_meta_key,
                inline_only=True)
            for entry in entries:
                found_thing = {}
                value = entry.values[0]
                full_contents = node.content_only()

                start_pos = entry.position - amount
                end_pos = entry.end_position + amount
                if entry.position < amount: 
                    start_pos = 0
                if entry.end_position + amount > len(full_contents):
                    end_pos = len(full_contents)

                #     relevant_text = '...   ' + relevant_text +  '      ...'
                # else:
                #     relevant_text = '      ' + relevant_text

                relevant_text = full_contents[start_pos:end_pos]
                found_thing['filename'] = node.id + ':' + str(entry.position)
 
                # TODO : abstract this for numbers / other sortable values also:
                if dynamic_definition.timeline_meta_key == 'timestamp':
                    found_thing['value'] = entry.dt_string
                    found_thing['sort_value'] = entry.dt_stamp
                else:
                    found_thing['sort_value'] = found_thing['value'] = value
                found_thing['contents'] = relevant_text
                found_stuff.append(found_thing)

            keyname = dynamic_definition.timeline_meta_key

    sorted_stuff = sorted(found_stuff, key=lambda x: x['sort_value']) 
    # TODO : re-add reverse flag
            
    if not sorted_stuff:
        return ''
    if dynamic_definition.limit:
        sorted_stuff = sorted_stuff[0:dynamic_definition.limit]
    start_date = sorted_stuff[0]['contents']
    timeline = []
    for index in range(0, len(sorted_stuff)):
        contents = sorted_stuff[index]['contents'].strip()
        while '\n\n' in contents:
            contents = contents.replace('\n\n', '\n')
        contents = '      ' + contents.replace('\n', '\n|      ')
        
        timeline.extend([
            '|<---- ', 
            keyname, ': ',
            sorted_stuff[index]['value'], 
            ' >',
            sorted_stuff[index]['filename'],
            '\n|\n|',
            contents,
            '\n|\n'])


    return ''.join(timeline)

timeline_functions = [ _timeline]
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
from .dynamic_output import DynamicOutput

def _collection(self, 
    nodes, 
    project, 
    dynamic_definition):
    """ generates a collection of context-aware metadata anchors """

    keys = {}
    for group in dynamic_definition.collect:
        for entry in group:
            k, v, operator = entry
            keys.setdefault(k, [])            
            if v not in keys[k]:
                keys[k].append(v)

    found_stuff = []
    for node in nodes:

        for k in keys:

            use_timestamp = k in self.settings['use_timestamp']

            for v in keys[k]:

                if v == '*':
                    entries = node.metadata.get_entries(k)

                else:
                    entries = node.metadata.get_matching_entries(k, v)

                for entry in entries:

                     found_item = {}
                     
                     if v == '*':
                        if use_timestamp:
                            values = [entry.dt_stamp]
                        else:
                            values = [ve for ve in entry.values]

                     else:
                        if use_timestamp and entry.dt_stamp == v:
                            values = [entry.dt_stamp]
                        else:
                            values = [ve for ve in entry.values if ve == v]

                     for value in values:
                         found_item['node_id'] = node.id
                         found_item['title'] = node.title
                         found_item['dt_string'] = entry.dt_string

                         if use_timestamp:
                             found_item['value'] = entry.dt_string
                             found_item['sort_value'] = entry.dt_stamp
                       
                         else:
                             found_item['value'] = value
                             sort_value = value
                             if dynamic_definition.sort_numeric:
                                 try:
                                    sort_value = float(value)
                                 except ValueError: 
                                    sort_value = 99999999
                             else:
                                sort_value = str(sort_value)
        
                             found_item['sort_value'] = sort_value

                         found_item['keyname'] = k
                         
                         # get context and position
                         # lines = 1 # FUTURE

                         # get content with full meta.
                         full_contents = node.content_only().split('\n')
                         
                         context = []
                         length = 0
                         for i in range(len(full_contents)):

                            line = full_contents[i]
                            if line.strip():
                                context.append(line.strip())
                            if entry.position in range(length, length+len(line)+1):
                                 if line.strip(): 
                                    context = [ line.strip() ]
                                    break
                                 elif context: 
                                    break
                            if not entry.position:
                                entry.log()
                            if entry.position < length:
                                if line.strip(): 
                                    context.append(line.strip())
                                    break
                            length += len(line)

                         if len(context) > 1:
                            context = [context[-1]]

                         found_item['context'] = '\n'.join(context)
                         found_item['context'] = UrtextNode.strip_metadata(contents=found_item['context'])

                         # this will be position in NODE, not FILE:
                         found_item['position'] = str(entry.position)                         

                         found_stuff.append(found_item)

    if not found_stuff:
         return ''

    sorted_stuff = sorted(found_stuff, 
         key=lambda x: x['sort_value'], 
         reverse=dynamic_definition.sort_reverse) 
           
    if dynamic_definition.limit:
         sorted_stuff = sorted_stuff[0:dynamic_definition.limit]

    collection = []

    for index in range(0, len(sorted_stuff)):

         item = sorted_stuff[index]

         next_content = DynamicOutput(dynamic_definition.show)
              
         if next_content.needs_title:
             next_content.title = item['title']

         if next_content.needs_entry:
            next_content.entry = item['keyname'] + ' :: ' +  str(item['value'])
            next_content.key = item['keyname']
            next_content.values = item['value']

         if next_content.needs_link:            
             next_content.link = '>'+item['node_id']+':'+item['position']

         if next_content.needs_date:
             next_content.date = item['dt_string']

         if next_content.needs_meta:
              next_content.meta = project.nodes[item['node_id']].consolidate_metadata()

         if next_content.needs_contents: 
             contents = item['context']
             while '\n\n' in contents:
                 contents = contents.replace('\n\n', '\n')
             next_content.contents = contents

         for meta_key in next_content.needs_other_format_keys:
             values = project.nodes[item['node_id']].metadata.get_values(meta_key, substitute_timestamp=True)
             replacement = ''
             if values:
                 replacement = ' '.join(values)
             next_content.other_format_keys[meta_key] = values

         collection.extend([next_content.output()])

    return ''.join(collection)

collection_functions = [ _collection]

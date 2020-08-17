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

def _collection(self, nodes, project, dynamic_definition, amount=150):
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

            for v in keys[k]:
                if v == '*':
                    entries = node.metadata.get_entries(k)
                else:
                    entries = node.metadata.get_matching_entries(k, v)

                for entry in entries:

                     found_item = {}
                     
                     if v == '*':
                        values = [ve for ve in entry.values]
                     else:
                        values = [ve for ve in entry.values if ve == v]
                   
                     for value in values:

                         # get surrounding text
                         full_contents = node.content_only()
                         start_pos = entry.position - amount
                         end_pos = entry.end_position + amount
                         if entry.position < amount: 
                             start_pos = 0
                         if entry.end_position + amount > len(full_contents):
                             end_pos = len(full_contents)

                         found_item['node_id'] = node.id
                         found_item['title'] = node.title
                         found_item['dt_string'] = entry.dt_string

                         if dynamic_definition.sort_date:
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
        
                             found_item['sort_value'] = sort_value

                         found_item['keyname'] = k
                         found_item['position'] = str(start_pos)
                         found_item['context'] = full_contents[start_pos:end_pos]
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
            next_content.entry = item['keyname'] + ' :: ' + item['value']
      
         if next_content.needs_link:            
             next_content.link = '>'+item['node_id']+':'+item['position']

         if next_content.needs_date:
             next_content.date = item['dt_string']

         if next_content.needs_meta:
              next_content.meta = project.nodes[item['node_id']].consolidate_metadata()

         if next_content.needs_contents: 
             contents = item['context'].strip()
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

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
    """ generates a collection of context-aware metadata anchros """

    found_stuff = []
    
    for node in nodes:

        # refine?
        keys = [r[0] for r in dynamic_definition.include_and]
        keys.extend([r[0] for r in dynamic_definition.include_or])

        for k in keys:

            for entry in node.metadata.get_entries(k):

                 #wtf it this?
                 found_item = {}
               
                 for value in entry.values:

                     # if value not in dynamic_definition.keys:
                     #    continue

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
                         if dynamic_definition.sort_numeric:
                             # TODO: error catching
                             sort_value = float(value)
    
                         found_item['sort_value'] = node.metadata.get_first_value(k)

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

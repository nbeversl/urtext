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
import pytz
from urtext.utils import force_list
from urtext.dynamic import UrtextDynamicDefinition
from urtext.timestamp import UrtextTimestamp, default_date
timestamp_match = re.compile('<([^-/<\s][^=<]+?)>')
meta_entry = re.compile('\*{0,2}\w+\:\:[^\n@};]+;?(?=>:})?')
node_title_regex = re.compile('^[^\n_]*?(?= _)', re.MULTILINE)

class NodeMetadata:

    def __init__(self, 
        node,
        contents,
        node_id=None, 
        settings=None):

        self.node = node
        self.entries = []
        self.dynamic_entries = []
        self.parse_contents(contents, settings=settings)
        self.settings = settings
        self.add_system_keys()
        self._last_accessed = 0
       
    def parse_contents(self, full_contents, settings=None):

        parsed_contents = full_contents
    
        for m in meta_entry.finditer(full_contents):

            parsed_contents = parsed_contents.replace(m.group(),'', 1)

            keyname, contents = m.group().strip(';').split('::', 1)
            keyname = keyname.lower()
            value_list = contents.split('|')

            children=False
            recursive=False

            if keyname[0] == '*' :
                children = True
                keyname = keyname[1:] #cdr
                if keyname[0] == '*' :
                    recursive = True
                    keyname = keyname[1:] #cdr

            for value in value_list:
                value = value.strip()
                entry = MetadataEntry(
                        keyname, 
                        value, 
                        recursive=recursive,
                        position=m.start(), 
                        end_position=m.start() + len(m.group()))    
                if children or recursive:
                    self.dynamic_entries.append(entry)
                self.entries.append(entry)

            parsed_contents = parsed_contents.replace(m.group(),'X'*len(m.group()))

        # parse shorthand meta:
        if settings and settings['hash_key']:

            hash_meta = re.compile(r'(?:^|\s)#[A-Z,a-z].*?\b')
            for m in hash_meta.finditer(parsed_contents):
                value = m.group().replace('#','').strip()
                key = settings['hash_key']
                position = m.start()
                end_position = position + len(m.group())
                self.entries.append(
                MetadataEntry(
                    key, 
                    value,    
                    position=position, 
                    end_position=end_position)
                    )

        # parse inline timestamps:
        for m in timestamp_match.finditer(parsed_contents):
            stamp = m.group()
            position = m.start()
            end_position = position + len(m.group())
            e = MetadataEntry(
                    'inline-timestamp', 
                    stamp,
                    position=position, 
                    end_position=end_position)
            if e.timestamps:
                self.entries.append(e)
     
        # parse title
        s = node_title_regex.search(parsed_contents)
        if s:
           title = s.group(0).strip()
           self.add_meta_entry(
            MetadataEntry('title', 
                title,
                position=s.start(),
                end_position=s.end()
                )
            )

        return parsed_contents

    def add_system_keys(self):

        t = self.get_entries('inline-timestamp')
        # if t:
        #     t = sorted(t, key=lambda i: i.timestamps[0].datetime) 
        #     print (t[0].timestamps[0].string)
        #     print (t[-1].timestamps[0].string)
        #     self.add_meta_entry(MetadataEntry('_oldest_timestamp', '<'+t[0].timestamps[0].string+'>'))
        #     self.add_meta_entry(MetadataEntry('_newest_timestamp', '<'+t[-1].timestamps[0].string+'>'))

    def get_first_value(self, 
        keyname, 
        use_timestamp=False,
        substitute_timestamp=False):

        def empty(keyname):
            if keyname =='title':
                return self.node.title
            if keyname in self.settings['numerical_keys']:
                return '999999'
            if use_timestamp or keyname in self.settings['use_timestamp']:
                return default_date
            return ''

        keyname = keyname.lower()

        # if keyname == '_last_accessed':
        #     m = MetadataValue('_last_accessed', '')
        #     m.timestamps=[UrtextTimestamp(self._last_accessed)]
        #     return m

        entries = self.get_entries(keyname)

        if not entries:
            return empty(keyname)        

        if use_timestamp or keyname in self.settings['use_timestamp'] : 
            if entries[0].timestamps:
                return entries[0].timestamps[0].datetime
            return default_date

        if not entries[0].value:
            return empty(keyname)

        return entries[0].value

    def get_values(self, 
        keyname,
        use_timestamp=False,
        substitute_timestamp=False,
        lower=False
        ):

        keyname = keyname.lower()
        values = []
        entries = self.get_entries(keyname)
       
        for e in entries:
            if use_timestamp:
                values.extend(e.timestamps)
            else:
                values.append(e.value)        

        if not values and substitute_timestamp == True:
            for e in entries:
                # if e.timestamps[0] != default_date:
                values.append(e.timestamps)            

        if lower:
            return strings_to_lower(values)
        return values
    
    def get_keys(self, exclude=[]):
        if self._entries:
            return list(set([e.keyname for e in self.entries if e.keyname not in exclude]))
        return []

    def get_entries(self, keyname):
        keyname = keyname.lower()
        return [e for e in self.entries if e.keyname == keyname]

    def get_matching_entries(self, keyname, value):
    
        entries = self.get_entries(keyname)
        matching_entries = []
        if entries:
            use_timestamp = True if isinstance(value, UrtextTimestamp) else False
            for e in entries:
                if not use_timestamp and value == e.value:
                    matching_entries.append(e)
                # TODO FIX
                # elif value.timestamps and e.contains_timestamp(value.timestamps[0]):
                #     matching_entries.append(e)
        return matching_entries

    def get_date(self, keyname):
        """
        Returns the timestamp of the FIRST matching metadata entry with the given key.
        """
        entries = self.get_entries(keyname)
        if entries and entries[0].timestamps:
            return entries[0].timestamps[0].datetime
        return default_date

    # Set
    
    def add_meta_entry(self, entry,
        dt_string=None,
        from_node=None,
        position=0):
        entry.from_node=from_node
        self.entries.append(entry)
      
    def clear_from_source(self, source_node_id):
        for entry in list(self.entries):
            if entry.from_node == source_node_id:
                self.entries.remove(entry)

    def log(self):
        for entry in self.entries:
            entry.log()

class MetadataEntry:  # container for a single metadata entry
    def __init__(self, 
        keyname, 
        contents, 
        as_int=False,
        position=None,
        recursive=False,
        end_position=None, 
        from_node=None):

        self.keyname = keyname.strip().lower() # string
        self.string_contents = contents
        self.value = ''
        self.recursive=recursive
        self.timestamps = []
        self.from_node = from_node
        self.position = position
        self.end_position = end_position
        self._parse_values(contents)
        
    def log(self):
        print('key: %s' % self.keyname)
        print(self.value)
        print('from_node: %s' % self.from_node)
        print('recursive: %s' % self.recursive)
        print(self.timestamps)

    def _parse_values(self, contents):

        for timestamp in timestamp_match.finditer(contents):
            dt_string = timestamp.group(0).strip()
            contents = contents.replace(dt_string, '').strip()
            self.timestamps.append(UrtextTimestamp(dt_string[1:-1]))        
        self.value = contents 
   
    def ints(self):
        parts = self.value.split[' ']
        ints = []
        for b in parts:
            try:
                ints.append(int(b))
            except:
                continue
        return ints

    def as_int(self):
        try:
            return int(self.value)
        except:
            return None 

""" Helpers """

def strings_to_lower(list):
    for i in range(len(list)):
        if isinstance(list[i], str):
            list[i] = list[i].lower()
    return list 


"""
CONTEXT:
Here we want to get, in this order:
The text after the entry on the same line but before the next entry
The text before the entry on the same line
The next non-blank line(s), up to a certain length
"""
# context code originally from COLLECT()
# if entry.index + 1 < len(self.nodes[entry.node].metadata._entries):
#    stop = self.nodes[entry.node].metadata._entries[entry.index+1].position

# poss_context = full_contents[start:stop].split('\n')
# for i in range(len(poss_context)):

#    line = poss_context[i]

#    if line.strip():
#        context.append(line.strip())

#    if len('\n'.join(context)) > 300:
#        break

# if not context:
#    start = 0
#    stop = entry.position
#    if entry.index > 0:
#        start = self.nodes[entry.node].metadata._entries[entry.index-1].end_position

#    poss_context = full_contents[start:stop].split('\n')
#    for i in range(len(poss_context)):
#        line = poss_context[i]
#        if line.strip():
#            context.append(line.strip())
#        if len('\n'.join(context)) > 300:
#            break

#found_item['context'] = '\n'.join(context)





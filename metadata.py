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
from dateutil.parser import *
from urtext.dynamic import UrtextDynamicDefinition
from urtext.timestamp import UrtextTimestamp, default_date

timestamp_match = re.compile('(?:<)([^-/<\s][^=<]*?)(?:>)')
inline_meta = re.compile('\*{0,2}\w+\:\:[^\n@};]+;?(?=>:})?')
node_title_regex = re.compile('^[^\n_]*?(?= _)', re.MULTILINE)
dynamic_def_regexp = re.compile(r'\[\[[^\]]*?\]\]', re.DOTALL)


"""
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




class NodeMetadata:

    def __init__(self, 
        node,
        entries,
        dynamic_entries,
        node_id=None, 
        settings=None):

        self.node = node
        self._entries = entries
        self.dynamic_entries = dynamic_entries
        self._sort()       
        self.add_system_keys()
        self._last_accessed = 0

    def _sort(self):
        """ from extant entries, populate a dict by key"""
        
        self.entries = {}
        for e in self._entries:
            self.entries.setdefault(e.keyname, [])
            if e not in self.entries[e.keyname]:
               self.entries[e.keyname].append(e)

        if self.node.id:
            self._entries = sorted(self._entries, key = lambda entry: entry.position)
            for i in range(len(self._entries)):
                self._entries[i].index = i
                self._entries[i].node = self.node.id

    def add_system_keys(self):

        t = self.get_entries('inline-timestamp')
        if t:
            t = sorted(t, key=lambda i: i.timestamp.datetime)    
            self.add_meta_entry(
                '_oldest_timestamp',
                [t[0].timestamp.string])
            self.add_meta_entry(
                '_newest_timestamp',
                [t[-1].timestamp.string])
            self._sort() 

    def get_first_value(self, 
        keyname, 
        use_timestamp=False,
        substitute_timestamp=False):

        keyname = keyname.lower()

        if keyname == '_last_accessed':
            return self.node.last_accessed

        entries = self.entries.get(keyname)

        if not entries:
            return ''

        if use_timestamp:
            return entries[0].timestamp.datetime

        if not entries[0].values or entries[0].values[0] == '': 
            if substitute_timestamp and entries[0].timestamp.datetime:
                return entries[0].timestamp.datetime
            else:
                return ''

        return entries[0].values[0]
        
    def get_values(self, 
        keyname,
        use_timestamp=False,
        substitute_timestamp=False,
        lower=False
        ):


        keyname = keyname.lower()
        values = []
        entries = []
        if keyname in self.entries:
            entries = self.entries[keyname]
        if not entries:
            return values
        for e in entries:
            if use_timestamp:
                values.append(e.timestamp)
            else:
                values.extend(e.values)        
        if not values and substitute_timestamp == True:
            for e in entries:
                if e.timestamp.datetime != default_date:
                    values.append(e.timestamp)            

        if lower:
            return strings_to_lower(values)
        return values
    
    def get_keys(self, exclude=[]):
        if self._entries:
            return list(set([e.keyname for e in self._entries if e.keyname not in exclude]))
        return []

    def get_entries(self, keyname):
        keyname = keyname.lower()
        return self.entries[keyname] if keyname in self.entries else []

    def get_matching_entries(self, 
        keyname, 
        value):
    
        entries = self.get_entries(keyname)
        matching_entries = []
        if entries:
            use_timestamp = True if isinstance(value, UrtextTimestamp) else False
            for e in entries:
                if not use_timestamp and value in e.values:
                    matching_entries.append(e)
                elif value == e.timestamp.string:
                    matching_entries.append(e)
        return matching_entries

    def get_date(self, keyname):
        """
        Returns the timestamp of the FIRST matching metadata entry with the given key.
        """
        entries = self.get_entries(keyname)
        if entries:
            return entries[0].timestamp.datetime

        return default_date

    # Set
    
    def add_meta_entry(self, 
        key, 
        values,
        dt_string=None,
        from_node=None,
        position=0):

        new_entry = MetadataEntry(
            key, 
            values, 
            UrtextTimestamp(dt_string), 
            from_node=from_node, 
            position=position)

        self._entries.append(new_entry)
        self._sort()

    def clear_from_source(self, source_node_id):
        for entry in list(self._entries):
            if entry.from_node == source_node_id:
                self._entries.remove(entry)
        self._sort()

    # Debug

    def log(self):
        for entry in self._entries:
            entry.log()

class MetadataEntry:  # container for a single metadata entry
    def __init__(self, 
        keyname, 
        value, 
        timestamp,
        children=False,
        recursive=False,
        position=None,
        end_position=None, 
        from_node=None):

        self.keyname = keyname.strip().lower() # string
        self.values = value         # always a list
        self.timestamp = timestamp
        self.from_node = from_node
        self.position = position
        self.end_position = end_position
        self.children = children
        self.recursive = recursive

    def log(self):
        print('key: %s' % self.keyname)
        print('value: %s' % self.values)
        print('datetimestring: %s' % self.timestamp.string)
        print('datetimestamp: %s' % self.timestamp.datetime)
        print('from_node: %s' % self.from_node)
        print('children: %s' % self.children)
        print('recursive: %s' % self.recursive)

def parse_contents(full_contents, settings=None):

    parsed_contents = full_contents
    dynamic_definitions = []
    
    for d in dynamic_def_regexp.finditer(full_contents):
        parsed_contents = parsed_contents.replace(d.group(),'', 1)
        dynamic_definitions.append(UrtextDynamicDefinition(d.group(0)[2:-2]))
        
    # parse inline metadata:
    entries = []
    dynamic_entries = []
    for m in inline_meta.finditer(full_contents):

        parsed_contents = parsed_contents.replace(m.group(),'', 1)

        key, value = m.group().strip(';').split('::', 1)
        key = key.lower()
        """
        For lines containing a timestamp
        """
        timestamp = timestamp_match.search(value)
        dt_string = ''
        if timestamp:
            dt_string = timestamp.group(1).strip()
            value = value.replace(timestamp.group(0), '').strip()

        values = []
        value_list = value.split('|')

        for value in value_list:
            value = value.strip()
            if key in settings['numerical_keys']:
                try:
                    value = int(value)
                except ValueError:
                    value = 9999999
            if value:
                values.append(value)

        recursive = False
        children = False
        if key[0] == '*' :
            children = True
            key = key[1:] #cdr
            if key[0] == '*' :
                recursive = True
                key = key[1:] #cdr

        end_position = m.start() + len(m.group())

        entry = MetadataEntry(
                key, 
                values, 
                UrtextTimestamp(dt_string), 
                children=children,
                recursive=recursive,       
                position=m.start(), 
                end_position=end_position)    

        if children or recursive:
            dynamic_entries.append(entry)
        entries.append(entry)

        parsed_contents = parsed_contents.replace(m.group(),'X'*len(m.group()))

    # parse shorthand meta:
    if settings and settings['hash_key']:

        hash_meta = re.compile(r'(?:^|\s)#[A-Z,a-z].*?\b')
        for m in hash_meta.finditer(parsed_contents):
            value = m.group().replace('#','').strip()
            key = settings['hash_key']
            position = m.start()
            end_position = position + len(m.group())
            entries.append(
            MetadataEntry(
                key, 
                [value], 
                UrtextTimestamp(''),     
                position=position, 
                end_position=end_position)
                )

    # parse inline timestamps:
    for m in timestamp_match.finditer(parsed_contents):
        stamp = m.group()
        position = m.start()
        end_position = position + len(m.group())
        inline_timestamp = MetadataEntry(
                'inline-timestamp', 
                '', 
                UrtextTimestamp(stamp[1:-1]),     
                position=position, 
                end_position=end_position)
        if inline_timestamp.timestamp and inline_timestamp.timestamp.datetime != None:
            entries.append(inline_timestamp)
 
    # parse title
    s = node_title_regex.search(parsed_contents)
    if s:
       title = s.group(0).strip()
       entries.append( 
            MetadataEntry(
                'title',
                [title],
                UrtextTimestamp(''),
                position=s.start(),
                end_position=s.end())
            )

    return entries, dynamic_entries, dynamic_definitions, parsed_contents


""" Helpers """


def strings_to_lower(list):
    for i in range(len(list)):
        if isinstance(list[i], str):
            list[i] = list[i].lower()
    return list 

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
from .dynamic import key_value_timestamp


default_date = pytz.timezone('UTC').localize(datetime.datetime(1970,1,1))
timestamp_match = re.compile('(?:<)([^-/<][^=<]*?)(?:>)')
inline_meta = re.compile('\w+\:\:[^\n};]+;?(?=>:}})?')

class NodeMetadata:

    def __init__(self, full_contents, settings=None):
            
        self.entries = []
        self.case_sensitive_values = [ 
                'title',
                'notes',
                'comments',
                'project_title',
                'timezone',
                'timestamp_format',
                'filenames',
                'weblink',
                'timestamp',
                ]
        self.numeric_values = [
                'index'
                ]

        parsed_contents = full_contents

        # parse inline metadata:
        inline_metadata = []
        for m in inline_meta.finditer(full_contents):

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

                if key not in self.case_sensitive_values:
                    value = value.lower()
                value = value.strip()
                if key in self.numeric_values:
                    try:
                        value = int(value)
                    except ValueError:
                        value = -1
                if value:
                    values.append(value)
            
            end_position = m.start() + len(m.group())
            self.entries.append(
                MetadataEntry(
                    key, 
                    values, 
                    dt_string, 
                    position=m.start(), 
                    end_position=end_position)
                )    

            parsed_contents = parsed_contents.replace(m.group(),'')

        # parse inline timestamps:
        for m in timestamp_match.finditer(parsed_contents):
            stamp = m.group()
            position = m.start()
            end_position = position + len(m.group())
            self.entries.append(
                MetadataEntry(
                    'inline-timestamp', 
                    '', 
                    stamp[1:-1], 
                    position=position, 
                    end_position=end_position)
                    )    

    ## Getting

    def get_first_meta_entry(self, keyname):
        entries = self.get_meta_entries(keyname)
        return entries[0] if entries else None

    def get_meta_entries(self, keyname):
        """ returns a list of values for the given key """
        keyname = keyname.lower().strip()
        return [entry for entry in self.entries if entry.keyname == keyname]

    def get_first_meta_value(self, keyname):
        values = self.get_meta_value(keyname)
        return values[0] if values else ''

    def get_meta_value(self, 
        keyname,
        substitute_timestamp=False  # substitutes the timestamp as a string if no value
        ):

        """ returns a list of values for the given key """
        entries = self.get_meta_entries(keyname)
        values = []
        for entry in self.entries:
            if entry.keyname == keyname:
                values.extend(entry.values)        
        if values == [] and substitute_timestamp:
            for entry in entries:
                if entry.keyname == keyname and entry.dt_stamp != default_date:
                        return [entry.dt_string]
        return values
        
    def get_timestamp(self, keyname):
        entry = self.get_first_meta_entry(keyname)
        if not entry:            
            return default_date
        return entry.dt_stamp

    def get_date(self, keyname):
        """
        Returns the timestamp of the FIRST matching metadata entry with the given key.
        Requires the project be parsed (dt_stamp set from dt_string)
        """
        keyname = keyname.lower()
        for entry in self.entries:
            if entry.keyname == keyname:
                return entry.dt_stamp
        return default_date

    # Setting
    
    def add_meta_entry(self, 
        key, 
        value,
        from_node=None):

        existing_entries = self.get_meta_entries(key)
        for entry in existing_entries:
            if value in entry.values:
                return
        new_entry = MetadataEntry(key, [value], None, from_node=from_node)
        self.entries.append(new_entry)

    def remove_dynamic_meta_from_source_node(self, source_node_id):
        for entry in list(self.entries):
            if entry.from_node == source_node_id:
                self.entries.remove(entry)
    
    # Debug

    def log(self):
        for entry in self.entries:
            entry.log()

    def _is_id(self, node_id): # debug only
        if self.get_first_meta_entry('id') == node_id:
            return True

class MetadataEntry:  # container for a single metadata entry
    def __init__(self, 
        keyname, 
        value, 
        dt_string,
        position=None,
        end_position=None, 
        from_node=None):

        self.keyname = keyname.strip().lower() # string
        self.values = value         # always a list
        self.dt_string = dt_string
        self.dt_stamp = default_date # default or set by project        
        self.from_node = from_node
        self.position = position
        self.end_position = end_position


    def log(self):
        print('key: %s' % self.keyname)
        print('value: %s' % self.values)
        print('datetimestring: %s' % self.dt_string)
        print('datetimestamp: %s' % self.dt_stamp)
        print('from_node: %s' % self.from_node)

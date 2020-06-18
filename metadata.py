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

meta = re.compile(r'(\/--)((?:(?!\/--).)*?)(--\/)',re.DOTALL) 
default_date = pytz.timezone('UTC').localize(datetime.datetime(1970,1,1))
timestamp_match = re.compile('(?:<)(.*?)(?:>)')

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
                ]
        self.numeric_values = [
                'index'
                ]

        # Parse out all the metadata blocks  
        metadata_blocks = []
        for meta_block in re.findall(meta, full_contents):
            metadata_blocks.append(meta_block[1])

        for block in metadata_blocks:

            meta_lines = re.split(';|\n', block)

            for line in meta_lines:
                if line.strip() == '':
                    continue
                
                """
                For lines containing a timestamp
                """
                timestamp = timestamp_match.search(line)
                dt_string = ''
                if timestamp:
                    dt_string = timestamp.group(1).strip()
                    line = line.replace(timestamp.group(0), '').strip()

                values = []
                if ':' in line:
                    key = line.split(":", 1)[0].strip().lower()
                    value_list = ''.join(line.split(":", 1)[1:]).split('|')
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
                else:
                    key = 'comment'
                    values = [ line ]
 
                self.entries.append(MetadataEntry(key, values, dt_string))

        ids = []
        for entry in self.entries:
            if entry.keyname == 'id':
                ids.append(entry.values)
    
    def get_meta_value(self, 
        keyname,
        substitute_timestamp=False  # substitutes the timestamp as a string if no value
        ):
        """ returns a list of values for the given key """
        values = []
        keyname = keyname.lower()
        for entry in self.entries:
            if entry.keyname == keyname:
                values.extend(entry.values)  # allows for multiple keys of the same name
        
        if values == [] and substitute_timestamp == True:
            for entry in self.entries:
                if entry.keyname == keyname:
                    if entry.dt_stamp != default_date:
                        return [entry.dtstring]

        return values

    def get_first_meta_value(self, keyname):
        values = self.get_meta_value(keyname)
        if values:
            return values[0]
        return ''

    def add_meta_entry(self, 
        key, 
        value,
        from_node=None):
        new_entry = MetadataEntry(key, [value], None, from_node=from_node)
        if new_entry not in self.entries:
            self.entries.append(new_entry)

    def remove_dynamic_meta_from_source_node(self, source_node_id):
        for entry in list(self.entries):
            if entry.from_node == source_node_id:
                self.entries.remove(entry)

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

    def log(self):
        for entry in self.entries:
            entry.log()

    def groups(self):  # not used?
        groups_list = []
        for entry in self.entries:
            if entry.keyname[0] == '_':
                groups_list.append(entry.keyname)
        return groups_list

class MetadataEntry:  # container for a single metadata entry
    def __init__(self, keyname, value, dtstring, from_node=None):
        self.keyname = keyname.strip().lower() # string
        self.values = value         # always a list
        self.dtstring = dtstring
        self.dt_stamp = default_date # default or set by project
        self.from_node = from_node

    def log(self):
        print('key: %s' % self.keyname)
        print('value: %s' % self.values)
        print('datetimestring: %s' % self.dtstring)
        print('datetimestamp: %s' % self.dt_stamp)
        print('from_node: %s' % self.from_node)

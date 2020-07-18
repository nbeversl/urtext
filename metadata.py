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
default_date = pytz.timezone('UTC').localize(datetime.datetime(1970,5,1))
timestamp_match = re.compile('(?:<)([^-/<][^=<]*?)(?:>)')
inline_meta = re.compile('\w+\:\:\w+')

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

        # parse inline metadata:
        inline_metadata = []
        for m in inline_meta.finditer(full_contents):
            position = m.start()
            entry = m.group().split('::')
            key = entry[0].strip().lower()
            if len(entry) == 1:
                continue
            value = entry[1]
            if key not in self.case_sensitive_values:
                value = value.lower()
            value = value.strip()
            if key in self.numeric_values:
                try:
                    value = int(value)
                except ValueError:
                    value = -1
            end_position = position + len(m.group())
            self.entries.append(
                MetadataEntry(
                    key, 
                    [value], 
                    '', 
                    position=position, 
                    end_position=end_position,
                    inline=True)
                )    

        # parse inline timestamps:
        for m in timestamp_match.finditer(full_contents):
            stamp = m.group()
            position = m.start()
            end_position = position + len(m.group())
            self.entries.append(
            MetadataEntry(
                'timestamp', 
                '', 
                stamp[1:-1], 
                position=position, 
                end_position=end_position,
                inline=True)
                )    

        ids = []
        for entry in self.entries:
            if entry.keyname == 'id':
                ids.append(entry.values)
    
    def get_meta_value(self, 
        keyname,
        inline_only=False,
        substitute_timestamp=False  # substitutes the timestamp as a string if no value
        ):

        """ returns a list of values for the given key """
        entries = self.get_meta_entries(
            keyname, 
            inline_only=inline_only)

        values = []
        for entry in entries:
            if entry.keyname == keyname:
                values.extend(entry.values)  # allows for multiple keys of the same name
        
        if values == [] and substitute_timestamp:
            for entry in entries:
                if entry.keyname == keyname and entry.dt_stamp != default_date:
                        return [entry.dtstring]
        return values

    def get_meta_entries(self, 
        keyname,
        inline_only=False,
        ):
        """ returns a list of values for the given key """
        entries = []

        keyname = keyname.lower()
        for entry in self.entries:
            if inline_only and not entry.inline:
                continue
            if entry.keyname == keyname:
                entries.append(entry)  # allows for multiple keys of the same name
        return entries

    def get_first_meta_value(self, keyname):
        values = self.get_meta_value(keyname)
        if values:
            return values[0]
        return ''

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
    def __init__(self, 
        keyname, 
        value, 
        dtstring,
        position=None,
        end_position=None, 
        from_node=None,
        inline=False):

        self.keyname = keyname.strip().lower() # string
        self.values = value         # always a list
        self.dtstring = dtstring
        self.dt_stamp = default_date # default or set by project        
        self.from_node = from_node
        self.inline = inline
        self.position = position
        self.end_position = end_position


    def log(self):
        print('key: %s' % self.keyname)
        print('value: %s' % self.values)
        print('datetimestring: %s' % self.dtstring)
        print('datetimestamp: %s' % self.dt_stamp)
        print('from_node: %s' % self.from_node)

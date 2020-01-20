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

meta = re.compile(r'(\/--(?:(?!\/--).)*?--\/)',
                          re.DOTALL)  # \/--((?!\/--).)*--\/

class NodeMetadata:
    def __init__(self, full_contents, settings=None):
        
        self.entries = []
        self.case_sensitive_values = [ 
                'title',
                'notes',
                'project_title',
                'timezone',
                'timestamp_format',
                'filenames' ]

        self.raw_meta_data = ''
        for section in re.findall(meta, full_contents):
            meta_block = section.replace('--/', '')
            meta_block = meta_block.replace('/--', '')
            self.raw_meta_data += meta_block + '\n'

        title_set = False
        meta_lines = re.split(';|\n', self.raw_meta_data)

        for line in meta_lines:

            if line.strip() == '':
                continue

            value = ''
            
            """
            For lines containing a datestamp
            """
            
            date_match = re.search('(?:<)(.*?)(?:>)', line)
            if date_match:
                dt_string = date_match.group(0)
                line = line.replace(dt_string, '').strip()
            else:
                dt_string = ''

            # strip the datestamp for parsing
            line_without_datestamp = line.replace('<' + dt_string + '>', '')

            if ':' in line_without_datestamp:
                key = line_without_datestamp.split(":", 1)[0].strip().lower()
                if key == "timestamp":
                    value = dt_string

                else:
                    value = ''.join(line.split(":", 1)[1:]).strip()
                    if key not in self.case_sensitive_values:
                        value = value.lower()
                    if '|' in value:
                        items = value.split('|')
                        value = []
                        for item in items:
                            if item.strip() != '':
                                value.append(item.strip())
            else:
                key = '(no_key)'
                value = line.strip('--/')

            if value:
                self.entries.append(MetadataEntry(key, value, dt_string))

    def get_tag(self, tagname):
        """ returns an array of values for the given tagname """
        values = []
        tagname = tagname.lower()
        for entry in self.entries:
            if entry.tag_name.lower() == tagname.lower():
                value = entry.value
                if tagname not in self.case_sensitive_values:

                    value = value.lower()
                values.append(value)  # allows for multiple tags of the same name
        return values

    def set_tag(self, key, value):
        self.entries.append(MetadataEntry(key, value, None))

    def get_date(self, tagname):
        """only works after the project has set the dt_stamp from dt_string"""
        tagname = tagname.lower()
        for entry in self.entries:
            if entry.tag_name.lower() == tagname:
                return entry.dtstamp

    def log(self):
        for entry in self.entries:
            entry.log()

    def groups(self):  # not used?
        groups_list = []
        for entry in self.entries:
            if entry.tag_name[0] == '_':
                groups_list.append(entry.tag_name)
        return groups_list

class MetadataEntry:  # container for a single metadata entry
    def __init__(self, tag, value, dtstring):
        self.tag_name = tag.strip()
        self.value = value
        self.dtstring = dtstring
        self.dtstamp = None

    def log(self):
        print('tag: %s' % self.tag_name)
        print('value: %s' % self.value)
        print('datetimestring: %s' % self.dtstring)
        print('datetimestamp: %s' % self.dtstamp)

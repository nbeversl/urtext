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
import os
import inspect
import pprint

parent_dir = os.path.dirname(__file__)
node_id_regex = r'\b[0-9,a-z]{3}\b'
function_regex = re.compile('([A-Z_]+)(\(.*?\))')
key_value_regex = re.compile('(.+):(.+)')
string_meta_regex = re.compile('(.+:)("[^"]+")')

class UrtextDynamicDefinition:
    """ Urtext Dynamic Definition """
    def __init__(self, contents):

        self.spaces = 0
        self.target_id = None
        self.target_file = None
        self.include_or = []
        self.include_and = []
        self.exclude_or = []
        self.exclude_and = []
        self.tree = None
        self.sort_keyname = None
        self.metadata = {}
        self.oneline_meta = True
        self.interlinks = None
        self.omit=[]
        self.mirror = None
        self.mirror_include_all = None
        self.export = None
        self.tag_all_key = None
        self.tag_all_value = None
        self.recursive = False
        self.reverse = False
        self.timeline_type = None
        self.search = None
        self.show = '$title $link\n' # default
        self.preformat = False
        self.display = 'list'
        self.limit = None
        self.sort_type = 'alpha'
        self.access_history = 0
        self.export_source = None
        self.source_id = 'EMPTY'
        
        self.init_new_way(contents)
    
    def init_new_way(self, contents):

        for match in re.findall(function_regex,contents):
           
            func = match[0]
            inside_parentheses = match[1][1:-1]
            params = []

            for string_meta in re.findall(string_meta_regex, inside_parentheses):
                string_meta_match = ''.join(string_meta)
                params.append(string_meta_match)
                inside_parentheses = inside_parentheses.replace(string_meta_match,'',1)
            
            params.extend([param.strip() for param in inside_parentheses.split(' ')])
           
            if func == 'ACCESS_HISTORY':
                
                if params:
                    self.access_history = self.assign_as_int(params[0], self.access_history)
                else:
                    self.access_history = -1 # all
                continue
                
            if not params:
                continue

            if func == 'ID':
                self.target_id = params[0]
                continue

            if func == 'SHOW':
                self.show = ' '.join(params)
                continue

            if func == 'TREE':
                self.tree = params[0]
                continue

            if func == 'TIMELINE':
                self.timeline = True
                for param in params:
                    if param == 'meta':
                        self.timeline_type = 'meta'
                        break
                    if param == 'inline':
                        self.timeline_type = 'inline'
                        break
                continue

            if func == 'INCLUDE':
                group = []
                add_to_group = 'or'

                for param in params:
                    
                    if param == 'all': 
                        self.include_or = 'all'
                        break

                    if param == 'indexed':
                        #TODO this shouldn't actually break.
                        # should be combinable.
                        self.include_or = 'indexed'
                        break

                    if param == 'and':
                        add_to_group = 'and'
                        continue

                    key, value, timestamp = key_value_timestamp(param)
                    if key:
                        group.append((key,value))
                
                if group and add_to_group == 'and':
                    self.include_and.extend(group)
                elif group:
                    self.include_or.extend(group)
                continue

            if func == 'EXCLUDE':
                group = []
                add_to_group = 'or'  

                for param in params:

                    if param == 'all': 
                        self.exclude_or = 'all'
                        break

                    if param == 'indexed':
                        self.exclude_or = 'indexed'
                        #TODO this shouldn't actually break.
                        # should be combinable.
                        break

                    if param == 'and':
                        add_to_group = 'and'
                        continue

                    key, value, timestamp = key_value_timestamp(param)
                    if key:
                        group.append((key,value))

                if group and add_to_group == 'and':
                    self.exclude_and.extend(group)
                elif group:
                    self.exclude_or.extend(group)
                continue

            if func == "FORMAT":

                for param in params:
  
                    if param == 'preformat':
                        self.preformat = True
                        continue

                    if param == 'multiline_meta':
                        self.oneline_meta = False
                        continue
                    
                    key, value, timestamp = key_value_timestamp(param)
                    if key_value:
                        if key == 'indent':
                            self.spaces = self.assign_as_int(value, self.spaces)
                    continue
                
                continue

            if func == 'SEARCH':
                self.search = ' '.join(params)
                continue

            if func == 'LIMIT':
                self.max = assign_as_int(params[0], self.max)
                continue

            if func == 'SORT':

                for param in params:

                    if param == 'reverse':
                        self.reverse = True
                        continue

                    if param == 'timestamp':
                        self.sort_type = True
                        continue
                    
                    key, value, timestamp = key_value_timestamp(param)
                    if key:
                        self.sort_keyname = key
                        if value == 'timestamp':
                            self.sort_type = 'timestamp'
                        continue

                    self.sort_keyname = params[0]

                continue

            if func == 'EXPORT':

                for param in params:

                    if param in ['markdown','html','plaintext']:
                        self.export = param

                    key, value, timestamp = key_value_timestamp(param)

                    if key:
                        if key == 'source':
                            self.export_source = value
                continue

            if func == 'FILE':
                self.target_file = params[0]
                continue

            if func == 'TAG_ALL':

                for param in params:

                    if param == 'recursive':
                        self.recursive = True
                        continue
                    key, value, timestamp = key_value_timestamp(param)
                    if key:
                        self.tag_all_key = key
                        self.tag_all_value = value
                
                continue

            if func == 'METADATA':
                
                for param in params:

                    key, value, timestamp = key_value_timestamp(param)
                    if key:
                        self.metadata[key] = value + ' '

                    #TODO add timestamp

                continue

    def assign_as_int(self, value, default):
        try:
            number = int(value)
            return number
        except ValueError:
            return default

def key_value_timestamp(param):

    key = None
    value = None
    timestamp = None
    key_value = re.match(key_value_regex, param)
    if key_value:
        key = key_value.group(1)
        value = key_value.group(2)
        if len(key_value.groups()) > 2:
            timestamp = key_value.group(3)
    if value:
        value = value.strip('"') # strip quotation marks off string meta fields
    return key, value, timestamp


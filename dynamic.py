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

 
parent_dir = os.path.dirname(__file__)
node_id_regex = r'\b[0-9,a-z]{3}\b'
function_regex = re.compile('([A-Z_]+)(\(.*?\))')
key_value_regex = re.compile('([^\s]+?):([^\s"]+)')
string_meta_regex = re.compile('([^\s]+?):("[^"]+?")')

class UrtextDynamicDefinition:
    """ Urtext Dynamic Definition """
    def __init__(self, contents):

        self.spaces = 0
        self.target_id = None
        self.target_file = None
        self.include_all = False
        self.include_meta_type = None
        self.include_or = []
        self.include_and = []
        self.exclude_or = []
        self.exclude_and = []
        self.links_to = []
        self.links_from = []
        self.tree = None
        self.sort_keyname = None
        self.metadata = {}
        self.oneline_meta = True
        self.interlinks = None
        self.omit=[]
        self.export = None
        self.tag_all = {}
        self.timeline_meta_key = None
        self.timeline_sort_numeric = False
        self.recursive = False
        self.reverse = False
        self.timeline = False
        self.timeline_type = 'inline'
        self.search = None
        self.show = '$title $link\n' # default
        self.preformat = False
        self.display = 'list'
        self.limit = None
        self.sort_type = 'alpha'
        self.access_history = 0
        self.export_source = None
        self.source_id = 'EMPTY'
        self.include_other_projects = False
        self.init_self(contents)
    
    def init_self(self, contents):

        for match in re.findall(function_regex,contents):

            func = match[0]
            inside_parentheses = match[1][1:-1]
            params = []

            for string_meta in re.findall(string_meta_regex, inside_parentheses):

                string_meta_match = ':'.join(string_meta)
                params.append(string_meta_match)
                inside_parentheses = inside_parentheses.replace(string_meta_match,'',1)
            params.extend([param.strip() for param in inside_parentheses.split(' ')])
            
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

            if func == 'COLLECTION':
                self.timeline = True

                for param in params:

                    key, value, timestamp = key_value_timestamp(param)
                    if key == 'key':
                        self.timeline_meta_key = value

                    if key == 'sort' and value.lower() == 'num':
                        self.timeline_sort_numeric = True

                continue

            if func == 'INCLUDE':
                group = []
                operator = 'or' # default

                for param in params:
                    
                    if param == 'all': 
                        self.include_all = True
                        # no need to continue
                        break

                    if param == 'indexed':
                        self.include_or.append('indexed')
                        continue

                    if param == 'and':
                        # and overrides or if it appears at all
                        operator = 'and'
                        continue

                    if param == 'inline':
                        # and overrides or if it appears at all
                        self.include_meta_type = 'inline'
                        continue

                    if param == 'wrapped':
                        # and overrides or if it appears at all
                        self.include_meta_type = 'wrapped'
                        continue


                    if param == 'all_projects':
                        self.include_other_projects = True
                        continue

                    key, value, timestamp = key_value_timestamp(param)
                    if key:
                        group.append((key,value))
                
                if group and operator == 'and':
                    self.include_and.extend(group)
                elif group:
                    self.include_or.extend(group)
                continue

            if func == 'EXCLUDE':
                group = []
                operator = 'or'  

                for param in params:

                    if param == 'all': 
                        self.exclude_or = 'all'
                        break

                    if param == 'indexed':
                        self.exclude_or.append('indexed')
                        continue

                    if param == 'and':
                        add_to_group = 'and'
                        continue
                   
                    key, value, timestamp = key_value_timestamp(param)
                    if key:
                        group.append((key,value))

                if group and operator == 'and':
                    self.exclude_and.extend(group)
                elif group:
                    self.exclude_or.extend(group)
                continue

            if func == "LINKS_TO":
                self.links_to = params

            if func == "LINKS_FROM":
                self.links_from = params

            if func == "FORMAT":

                for param in params:
  
                    if param == 'preformat':
                        self.preformat = True
                        continue

                    if param == 'multiline_meta':
                        self.oneline_meta = False
                        continue
                    
                    key, value, timestamp = key_value_timestamp(param)
                    if key:
                        if key == 'indent':
                            self.spaces = self.assign_as_int(value, self.spaces)
                    continue
                
                continue

            if func == 'SEARCH':
                self.search = ' '.join(params)
                continue

            if func == 'LIMIT':
                self.limit = self.assign_as_int(params[0], self.limit)
                continue

            if func == 'SORT':

                for param in params:

                    if param == 'reverse':
                        self.reverse = True
                        continue

                    if param == 'use_timestamp':
                        self.sort_type = 'use_timestamp'
                        continue

                    if param == 'last_accessed':
                        self.sort_type = 'last_accessed'
                        self.reverse = True
                        continue
                    
                    # TODO: Add multiple sort fallbacks
                    if param and param[0] == '$': 
                        self.sort_keyname = param[1:]

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
                        if key not in self.tag_all:
                            self.tag_all[key] = []
                        self.tag_all[key].append(value)

                continue

            if func == 'METADATA':
                
                for param in params:

                    key, value, timestamp = key_value_timestamp(param)

                    if key:
                        self.metadata[key] = value + ' '

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
    if not key_value:
        key_value = re.match(string_meta_regex, param)
    if key_value:
        key = key_value.group(1)
        value = key_value.group(2)
        if len(key_value.groups()) > 2:
            timestamp = key_value.group(3)
    if value:
        value = value.strip('"') # strip quotation marks off string meta fields

    return key, value, timestamp


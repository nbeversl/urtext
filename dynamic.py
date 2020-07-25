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
function_regex = re.compile('([A-Z_]+)(\(.*?\))', re.DOTALL)
key_value_regex = re.compile('([^\s]+?):([^\s"]+)')
string_meta_regex = re.compile('([^\s]+?):("[^"]+?")')
entry_regex = re.compile('\w+\:\:[^\n;]+[\n;]?')

valid_flags = [re.compile(r'(^|[ ])'+f+r'\b') for f in [ 

        '-rr', 
        '-recursive',

        '-use-timestamp',
        '-t',

        '-last-accessed',
        '-la',

        '-r',
        '-reverse',

        '-and',
        '-&',

        '-all-projects',
        '-*p',

        '-markdown',
        '-md',

        '-html',

        '-plaintext',
        '-txt',

        '-preformat',
        '-p',

        '-multiline-meta',
        '-mm',

        '-num',
        '-n',

        '-alpha',
        '-a'
    ]   
]



class UrtextDynamicDefinition:
    """ Urtext Dynamic Definition """
    def __init__(self, contents):

        self.spaces = 0
        self.target_id = None
        self.target_file = None
        self.include_all = False
        self.comparison_type = None
        self.include_or = []
        self.include_and = []
        self.exclude_or = []
        self.exclude_and = []
        self.links_to = []
        self.links_from = []
        self.tree = None
        self.sort_keyname = None
        self.metadata = {}
        self.interlinks = None
        self.omit=[]
        self.export = None
        self.tag_all = {}
        self.timeline_meta_key = None
        self.timeline_sort_numeric = False
        self.timeline = False
        self.search = None
        self.show = '$title $link\n' # default
        self.preformat = False
        self.display = 'list'
        self.recursive = False
        self.limit = None
        self.sort_type = 'alpha'
        self.access_history = 0
        self.export_source = None
        self.source_id = 'EMPTY'
        self.all_projects = False
        self.export_kind = None
        self.last_accessed = False
        self.use_timestamp = False
        self.reverse = False
        self.multiline_meta = False
        self.init_self(contents)

    def init_self(self, contents):

        for match in re.findall(function_regex,contents):

            func = match[0]
            inside_parentheses, flags = get_flags(match[1][1:-1])

            if func == 'ID':
                self.target_id = inside_parentheses
                continue

            if func == 'SHOW':
                self.show = inside_parentheses
                continue

            if func == 'TREE':
                self.tree = inside_parentheses
                continue

            if func == 'COLLECTION':
                
                self.timeline = True

                if has_flags(['-n','-num'], flags):
                        self.timeline_sort_numeric = True

                for param in separate(inside_parentheses, delimiter=' '):

                    key, value, delimiter = key_value(param)
                    if key == 'key':
                        self.timeline_meta_key = value[0]

                continue

            if func == 'INCLUDE':
                group = []
                operator = 'or' # default

                if has_flags(['-all-projects','-*p'], flags):
                    self.all_projects = True

                for param in separate(inside_parentheses):
                    
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

                    key, value, delimiter = key_value(param, ['=','?','~'])
                    if value:
                        for v in value:
                            group.append((key,v))
                        self.comparison_type = delimiter
                
                if group and operator == 'and':
                    self.include_and.extend(group)
                elif group:
                    self.include_or.extend(group)

                continue

            if func == 'EXCLUDE':
                group = []
                operator = 'or'

                for param in separate(inside_parentheses):

                    if param == 'all': 
                        self.exclude_or = 'all'
                        break

                    if param == 'indexed':
                        self.exclude_or.append('indexed')
                        continue

                    if param == 'and':
                        operator = 'and'
                        continue
                   
                    key, value, delimiter = key_value(param, ['=','?','~'])
                    if value:
                        for v in value:
                            group.append((key,v))
                        self.comparison_type = delimiter
                        
                if group and operator == 'and':
                    self.exclude_and.extend(group)
                elif group:
                    self.exclude_or.extend(group)
                continue

            if func == "LINKS_TO":
                self.links_to = separate(inside_parentheses)

            if func == "LINKS_FROM":
                self.links_from = separate(inside_parentheses)

            if func == "FORMAT":
                if has_flags(['-multiline-meta','-mm'], flags):
                    self.multiline_meta = True

                for param in separate(inside_parentheses):                      
                    key, value, delimiter = key_value(param)
                    if value and key == 'indent':
                        self.spaces = self.assign_as_int(value[0], self.spaces)
                        continue
                
                continue

            if func == 'SEARCH':
                self.search = inside_parentheses
                continue

            if func == 'LIMIT':
                self.limit = self.assign_as_int(inside_parentheses, self.limit)
                continue

            if func == 'SORT':
                
                if has_flags(['-last_accessed','-la'], flags):
                    self.last_accessed = True

                if has_flags(['-use-timestamp','-t'], flags):
                    self.use_timestamp = True

                if has_flags(['-reverse','-r'], flags):
                    self.reverse = True

                for param in separate(inside_parentheses):
                    # TODO: Add multiple sort fallbacks
                    if param and param[0] == '$': 
                        self.sort_keyname = param[1:]

                continue

            if func == 'EXPORT':

                if has_flags(['-preformat','-p'], flags):
                    self.preformat = True

                self.export_kind = get_export_kind(flags)

                for param in separate(inside_parentheses, delimiter=' '):

                    self.export = param

                    key, value, delimiter = key_value(param)
                    if value and key == 'source':
                        self.export_source = value[0]
                continue

            if func == 'FILE':
               
                self.target_file = inside_parentheses
                continue

            if func == 'TAG_ALL':

                if has_flags(['-recursive','r'], flags):
                    self.recursive = True

                for param in separate(inside_parentheses):

                    key, value, delimiter = key_value(param, delimiters=['::'])
                    if value:
                        if key not in self.tag_all:
                            self.tag_all[key] = []
                        self.tag_all[key].extend(value)

                continue

            if func == 'METADATA':
                
                for param in separate(inside_parentheses):

                    key, value, delimiter = key_value(param, delimiters=['::'])

                    if key:
                        if key not in self.metadata:
                            self.metadata[key] = []
                        self.metadata[key].extend(value)

                continue

    def assign_as_int(self, value, default):
        try:
            number = int(value)
            return number
        except ValueError:
            return default

def has_flags(flags, flag_list):
    for f in flag_list:
        if f in flags:
            return True
    return False

def key_value(param, delimiters=[':']):

    if isinstance(delimiters, str):
        delimiters = [delimiters]
    
    for delimiter in delimiters:

        if delimiter in param:
            key,value = param.split(delimiter,1)
            key = key.lower().strip()
            value = [v.strip() for v in value.split('|')]
            return key, value, delimiter

    return None, None, None

def get_flags(contents):
    this_flags = []
    for f in valid_flags:
        m = f.search(contents)
        if m:
            m = m.group(0).replace('(','').strip()
            if m not in this_flags:
                this_flags.append(m)
            contents=re.sub(f,';',contents)
    return contents, this_flags

def get_export_kind(flgs):

    kinds = {   'markdown' :    ['-markdown','-md'],
                'html' :        ['-html'],
                'plaintext' :   ['-plaintext','-txt']}

    for k in kinds:
        for v in kinds[k]:
            if v in flgs:
                return k

    return None

def separate(param, delimiter=';'):
    return [r.strip() for r in re.split(delimiter+'|\n', param)]

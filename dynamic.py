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

        '-date',
        '-d'

        '-alpha',
        '-a',

        '-collection',
        '-list',
        '-tree',
        '-interlinks'
    ]   
]



class UrtextDynamicDefinition:
    """ Urtext Dynamic Definition """
    def __init__(self, contents):


        # TARGET()
        self.target_id = None
        self.target_file = None
        self.output_type = '-list' # default
         
        # inclusions / exclusions
        self.include_all = False
        self.comparison_type = None
        self.include_or = []
        self.include_and = []
        self.exclude_or = []
        self.exclude_and = []
        self.omit=[]
        self.limit = None
        self.all_projects = False
        self.keys = []

        # SORT()
        self.sort_type = 'alpha'
        self.sort_reverse = False
        self.sort_keyname = None
        self.sort_numeric = False
        self.sort_date = False
        
        # formatting
        self.spaces = 0
        self.preformat = False

        # show        
        self.show = '$title $link\n' # default

        self.root = None
        # to be removed or reviewed
        self.export = None
        self.export_source = None
        self.source_id = 'EMPTY'
        
        self.export_kind = None
        self.use_timestamp = False
        self.multiline_meta = False

        # METADATA()
        self.metadata = {}
       
        self.init_self(contents)

    def init_self(self, contents):

        for match in re.findall(function_regex,contents):

            func = match[0]
            inside_parentheses, flags = get_flags(match[1][1:-1])

            if func in ['ID','TARGET']:
                
                if flags and flags[0] in ['-tree','-list','-collection', '-interlinks']:
                    self.output_type = flags[0]
                
                if self.output_type == '-collection':
                    # different default output
                    self.show = "$entry $link \n $contents\n\n"

                for param in separate(inside_parentheses):                      
                    key, value, delimiter = key_value(param)
                    if key == 'root':
                        self.root = value[0]
                
                #TODO FIX
                self.target_id = inside_parentheses[:3]
                continue

            if func == 'SHOW':
                self.show = inside_parentheses
                continue

            if func == 'KEYS':
                keys = separate(inside_parentheses, delimiter=" ")
                self.keys.extend(keys)

            if func == 'INCLUDE':

                parse_group(self,
                    self.include_and, 
                    self.include_or,
                    inside_parentheses)
                continue

            if func == 'EXCLUDE':
                parse_group(self,
                    self.exclude_and, 
                    self.exclude_or,
                    inside_parentheses)
                continue

            if func == 'SORT':

                if has_flags(['-n','-num'], flags):
                    self.sort_numeric = True

                if has_flags(['-use-timestamp','-t'], flags):
                    self.use_timestamp = True

                if has_flags(['-reverse','-r'], flags):
                    self.sort_reverse = True

                if has_flags(['-date','-d'], flags):
                    self.sort_date = True
                for param in separate(inside_parentheses):
                    # TODO: Add multiple sort fallbacks
                    if param and param[0] == '$': 
                        self.sort_keyname = param[1:]
                continue
        
            if func == "FORMAT":
                if has_flags(['-multiline-meta','-mm'], flags):
                    self.multiline_meta = True

                for param in separate(inside_parentheses):                      
                    key, value, delimiter = key_value(param)
                    if value and key == 'indent':
                        self.spaces = assign_as_int(value[0], self.spaces)
                        continue
                
                continue

            if func == 'LIMIT':
                self.limit = assign_as_int(inside_parentheses, self.limit)
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

            if func == 'METADATA':
                
                for param in separate(inside_parentheses):

                    key, value, delimiter = key_value(param, delimiters=['::'])

                    if key:
                        if key not in self.metadata:
                            self.metadata[key] = []
                        self.metadata[key].extend(value)

                continue


def assign_as_int(value, default):
    try:
        number = int(value)
        return number
    except ValueError:
        return default

def parse_group(definition, and_group, or_group, inside_parentheses):

    group = []
    operator = 'or'

    for param in separate(inside_parentheses):

        if param == '-all': 
            or_group = '-all'
            return

        if param == 'and':
            operator = 'and'
            continue
       
        key, value, delimiter = key_value(param, ['=','?','~'])
        if value:
            for v in value:
                group.append((key,v,delimiter))
            
    if group and operator == 'and':
        and_group.extend(group)
    elif group:
        or_group.extend(group)

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

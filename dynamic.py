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
node_id_regex = r'>[0-9,a-z]{3}\b'
filename_regex = r'f>[^;]*'
function_regex = re.compile('([A-Z_\-\+]+)(\(.*?\))', re.DOTALL)
key_value_regex = re.compile('([^\s]+?):([^\s"]+)')
string_meta_regex = re.compile('([^\s]+?):("[^"]+?")')
entry_regex = re.compile('\w+\:\:[^\n;]+[\n;]?')

class UrtextDynamicDefinition:
    """ Urtext Dynamic Definition """
    def __init__(self, contents):

        # TARGET()
        self.target_id = None
        self.target_file = None
        self.output_type = '-list' # default
         
        # inclusions / exclusions
        self.include_groups = []
        self.exclude_groups = []
        self.limit = None
        self.include_all = False
        self.all_projects = False
        self.other_params = []

        # SORT()
        self.sort_type = 'alpha'
        self.sort_reverse = False
        self.sort_keyname = []
        self.sort_numeric = False
        self.sort_date = False
        
        # FORMAT
        self.spaces = 0
        self.preformat = False

        # SHOW        
        self.show = '$title $link\n' # default
        self.header = ''
        self.footer = ''
        self.use_timestamp = False
        self.multiline_meta = True

        # COLLECT
        self.collect=[]
       
        self.init_self(contents)

    def init_self(self, contents):

        for match in re.findall(function_regex,contents):

            func = match[0]
            inside_parentheses, flags = get_flags(match[1][1:-1])
            if func in ['ID','TARGET']:
                
                if flags and flags[0] in [
                        '-tree',
                        '-list',
                        '-collection',
                        '-interlinks',
                        '-plaintext',
                        '-txt',
                        '-markdown',
                        '-search',
                        '-md',
                        '-html']:

                    self.output_type = flags[0]
                
                if self.output_type == '-collection':
                    self.show = "$entry $link \n $contents\n\n"
               
                node_id_match = re.search(node_id_regex, inside_parentheses)
                if node_id_match:
                    self.target_id = node_id_match.group(0)[1:]
                    continue

                filename_match = re.search(filename_regex, inside_parentheses)
                if filename_match:
                    self.target_file = filename_match.group(0)[2:]
                    continue

            if func in ['SHOW','$']:
                self.show = inside_parentheses
                continue

            if func in ['INCLUDE','+']:
                if has_flags(['-all_projects'], flags):
                    self.all_projects = True

                if has_flags(['*'], flags):
                    self.include_all = True

                parse_group(self,
                    self.include_groups, 
                    self.other_params,
                    inside_parentheses,
                    flags=flags)
                continue

            if func in ['COLLECT','C']:

                parse_group(self,
                    self.collect, 
                    [], #discard
                    inside_parentheses)
                continue

            if func in ['EXCLUDE','-']:
                parse_group(self,
                    self.exclude_groups, 
                    self.other_params,
                    inside_parentheses,
                    flags=flags)
                continue

            if func in ['SORT','S']:

                if has_flags(['-n','-num'], flags):
                    self.sort_numeric = True

                if has_flags(['-timestamp','-t'], flags):
                    self.use_timestamp = True

                if has_flags(['-reverse','-r'], flags):
                    self.sort_reverse = True

                if has_flags(['-date','-d'], flags):
                    self.sort_date = True

                for param in separate(inside_parentheses):
                    if param:
                        self.sort_keyname.append(param)
    
                continue
        
            if func == "FORMAT":
                if has_flags(['-multiline-meta','-mm'], flags):
                    self.multiline_meta = True
                
                if has_flags(['-preformat','-p'], flags):
                    self.preformat = True


                for param in separate(inside_parentheses):                      
                    key, value, delimiter = key_value(param)
                    if value and key == 'indent':
                        self.spaces = assign_as_int(value[0], self.spaces)
                        continue
                
                continue

            if func == 'LIMIT':
                self.limit = assign_as_int(inside_parentheses, self.limit)
                continue

 
            if func == 'HEADER':
                self.header += inside_parentheses

            if func == 'FOOTER':
                self.footer += inside_parentheses

def assign_as_int(value, default):
    try:
        number = int(value)
        return number
    except ValueError:
        return default

def parse_group(definition, group, other_params, inside_parentheses, flags=[]):

    new_group = []

    for param in separate(inside_parentheses):

        key, value, delimiter = key_value(param, ['=','?','~'])
        if value:
            for v in value:
                new_group.append((key,v,delimiter))
        else:
            other_params.append(param)
        
    group.append(new_group)

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
            contents=contents.replace(m,';')
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

valid_flags = [re.compile(r'(^|[ ])'+f+r'\s?') for f in [ 


        '(^|[\s])\*($|[\s])', 
        
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
        '-d',
        '-search',

        '-alpha',
        '-a',

        '-collection',
        '-list',
        '-tree',
        '-interlinks'
    ]   
]
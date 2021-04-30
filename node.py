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

#/Users/n_beversluis/Library/Mobile Documents/iCloud~com~omz-software~Pythonista3/Documents/archive_new_ID_style/nate-big-project
import os
import json
from urtext.metadata import NodeMetadata
from anytree.exporter import JsonExporter
from urtext.dynamic import UrtextDynamicDefinition
from urtext.utils import strip_backtick_escape
import re
import datetime
import logging
import pytz
from anytree import Node, PreOrderIter
from urtext.metadata import MetadataEntry

dynamic_definition_regex = re.compile('(?:\[\[)([^\]]*?)(?:\]\])', re.DOTALL)
dynamic_def_regexp = re.compile(r'\[\[[^\]]*?\]\]', re.DOTALL)
subnode_regexp = re.compile(r'(?<!\\){(?!.*(?<!\\){)(?:(?!}).)*}', re.DOTALL)
default_date = pytz.timezone('UTC').localize(datetime.datetime(1970,2,1))
node_link_regex = r'>{1,2}[0-9,a-z]{3}\b'
timestamp_match = re.compile('(?:<)([^-/<\s`][^=<]+?)(?:>)', flags=re.DOTALL)
inline_meta = re.compile('\*{0,2}\w+\:\:([^\n};]+;?(?=>:})?)?', flags=re.DOTALL)
embedded_syntax = re.compile('%%-[^E][A-Z-]*.*?%%-END-[A-Z-]*', flags=re.DOTALL)
short_id = re.compile(r'(?:\s?)@[0-9,a-z]{3}\b')
shorthand_meta = re.compile(r'(?:^|\s)#[A-Z,a-z].*?\b')
preformat_syntax = re.compile('\`.*?\`', flags=re.DOTALL)
tree_elements = ['├──','└──','│','┌──',]

class UrtextNode:
    """ Urtext Node object"""
    def __init__(self, 
        filename, 
        contents,
        settings=None,
        root=False, 
        compact=False):

        self.filename = os.path.basename(filename)
        self.project_path = os.path.dirname(filename)
        self.project = None
        self.position = 0
        self.ranges = [[0, 0]]
        self.tree = None
        self.is_tree = False
        self.export_points = {}
        self.dynamic = False
        self.id = None
        self.links = []
        self.root_node = root
        self.tz = pytz.timezone('UTC')
        self.project_settings = False
        self.compact = compact
        self.parent_project = None
        self.last_accessed = 0
        self.dynamic_definitions = []
        self.target_nodes = []
        self.blank = False
        self.title = None
        self.keywords = {}
        self.errors = False
        self.display_meta = ''
        self.parent = None

        contents = strip_wrappers(contents, compact=compact)
        contents = strip_errors(contents)
        contents = strip_embedded_syntaxes(contents)
        contents = parse_dynamic_definitions(contents, self.dynamic_definitions)
        contents = strip_dynamic_definitions(contents)
        contents = strip_backtick_escape(contents)
    
        self.metadata = NodeMetadata(self)        
        contents = self.metadata.parse_contents(contents, settings=settings)

        r = re.search(r'(^|\s)@[0-9,a-z]{3}\b', contents)
        if r:
            self.id = r.group(0).strip()[1:]
            self.tree_node = Node(self.id)
            contents = contents.replace(r.group(0),'',1)
            for d in self.dynamic_definitions:
                d.source_id = self.id

        if not contents:
            self.blank = True
    
        self.title = self.set_title(contents)    
        if self.title == 'project_settings':
            self.project_settings = True

        self.parent = None

        self.get_links(contents=contents)

    def start_position(self):
        return self.ranges[0][0]
    
    def get_date(self, date_keyword):
        return self.metadata.get_date(date_keyword)

    def contents(self):
   
        with open(os.path.join(self.project_path, self.filename),
                  'r',
                  encoding='utf-8') as theFile:
            file_contents = theFile.read()
        node_contents = []
        for segment in self.ranges:
            this_range = file_contents[segment[0]:segment[1]]
            if this_range and this_range[0] in ['}','{']:
                this_range = this_range[1:]
            if this_range and this_range[-1] in ['}','{']:
                this_range = this_range[:-1]
            node_contents.append(this_range)
        node_contents = ''.join(node_contents)
        node_contents = strip_wrappers(node_contents)
        node_contents = strip_embedded_syntaxes(contents=node_contents)
        return node_contents

    def date(self):
        return self.metadata.get_date(self.project.settings['node_date_keyname'])

    def strip_syntax_elements(self, contents=None):
        if contents == None:
            contents=self.contents()
        stripped_contents = re.sub(node_link_regex, '', contents)
        tree_elements = ['├──','└──','│']
        for el in tree_elements:
            stripped_contents= stripped_contents.replace(el,'')
        return stripped_contents
        

    def strip_inline_nodes(self, contents='', preserve_length=False):
        r = ' ' if preserve_length else ''
        if contents == '':
            #contents = self.contents
            contents = self.contents()
        
        stripped_contents = contents
        for inline_node in subnode_regexp.finditer(stripped_contents):
            stripped_contents = stripped_contents.replace(inline_node.group(), r*len(inline_node.group()))
        return stripped_contents

    def get_links(self, contents=None):
        if contents == None:
            contents = self.content_only()
        nodes = re.findall(node_link_regex, contents)  # link RegEx
        for node in nodes:
            self.links.append(node[-3:])

    def content_only(self, contents=None, preserve_length=False):

        if contents == None:
            contents = self.contents()
        return strip_contents(contents)

    def set_title(self, contents):

        t = self.metadata.get_first_value('title')
        if t: 
            return t
  
        stripped_contents_lines = strip_metadata(contents).strip().split('\n')
       
        line = None
        for line in stripped_contents_lines:
            line = line.strip()
            if line:
                break
            
        if not line:
            return '(untitled)'

        first_line = line
        first_line = re.sub('>{1,2}[0-9,-z]{3}', '', first_line, re.DOTALL)    
        first_line = first_line.replace('┌──','')
        first_line = first_line.replace('|','') # pipe character cannot be in node names

        # TODO : WHY DOES THIS HAPPEN?
        first_line = first_line.strip().strip('{').strip()

        if '•' in first_line:
            first_line = re.sub(r'^[\s]*\•','',first_line)           
        
        first_line=first_line.strip().strip('\n').strip()

        first_line = sanitize_escape(first_line)
        self.metadata.entries.append(MetadataEntry('title', first_line))
        return first_line
   
    def log(self):
        logging.info(self.id)
        logging.info(self.filename)
        logging.info(self.metadata.log())

    def consolidate_metadata(self, one_line=True, separator='::'):
        
        keynames = {}
        for entry in self.metadata._entries:
            if entry.keyname not in keynames:
                keynames[entry.keyname] = []
            timestamp = ''
            if entry.timestamp.string:
                timestamp = '<'+entry.timestamp.string+'>'
            if not entry.values:
                keynames[entry.keyname].append(timestamp)
            for value in entry.values:
                keynames[entry.keyname].append(str(value)+timestamp)

        return self.build_metadata(keynames, one_line=one_line, separator=separator)

    @classmethod
    def build_metadata(self, 
        metadata, 
        one_line=None, 
        separator='::'
        ):

        if not metadata:
            return ''

        line_separator = '\n'
        if one_line:
            line_separator = '; '
  
        new_metadata = ''

        nid = ''
        for keyname in metadata:
            if keyname.lower() == 'id':
                nid = metadata[keyname]
                continue
            new_metadata += keyname + separator
            if isinstance(metadata[keyname], list):
                new_metadata += ' | '.join(metadata[keyname])
            else:
                new_metadata += metadata[keyname]
            new_metadata += line_separator

        if nid:
            new_metadata += '@'+nid

        return new_metadata.strip()

    def set_content(self, contents, preserve_metadata=False, bypass_check=False):
        
        file_contents = self.get_file_contents()
        start_range = self.ranges[0][0]
        end_range = self.ranges[-1][1]

        new_file_contents = ''.join([
            file_contents[0:start_range],
            contents,
            file_contents[end_range:]]) 
        
        return self.set_file_contents(new_file_contents)

def parse_dynamic_definitions(contents, dynamic_definitions): 
    for d in dynamic_def_regexp.finditer(contents):
        dynamic_definitions.append(UrtextDynamicDefinition(d.group(0)[2:-2]))
    return contents


def strip_contents(contents, preserve_length=False):
    contents = strip_metadata(contents=contents, preserve_length=preserve_length)
    contents = strip_dynamic_definitions(contents=contents, preserve_length=preserve_length)
    contents = strip_embedded_syntaxes(contents=contents, preserve_length=preserve_length)
    contents = contents.strip().strip('{').strip()

    return contents

def strip_syntax_elements(contents):
    stripped_contents = re.sub(node_link_regex, '', contents)
    
    for el in tree_elements:
        stripped_contents= stripped_contents.replace(el,'')
    return stripped_contents

def strip_wrappers(contents, compact=False, outside_only=False):
        wrappers = ['{','}']
        if contents and contents[0] in wrappers:
            contents = contents[1:]
        if contents and contents[-1] in wrappers:
            contents = contents[:-1]
        if not outside_only:
            contents = contents.replace('{','')
            contents = contents.replace('}','')
        if compact: # don't include the compact marker
             contents = contents.lstrip().replace('•','',1)        
        return contents

def strip_metadata(contents, preserve_length=False):

        r = ' ' if preserve_length else ''
        
        replacements = re.compile("|".join([
            '(?:<)([^-/<\s`][^=<]+?)(?:>)', # timestamp
            '\*{0,2}\w+\:\:([^\n};]+;?(?=>:})?)?', # inline_meta
            r'(?:\s?)@[0-9,a-z]{3}(\b|$)', # short_id
            r'(?:^|\s)#[A-Z,a-z].*?(\b|$)', # shorthand_meta
            ]))

        for e in replacements.finditer(contents):
            contents = contents.replace(e.group(), r*len(e.group()))       
        contents = contents.replace('• ',r*2)
        return contents.strip()

def strip_dynamic_definitions(contents, preserve_length=False):

        r = ' ' if preserve_length else ''
        if not contents:
            return contents
        stripped_contents = contents
      
        for dynamic_definition in dynamic_definition_regex.finditer(stripped_contents):
            stripped_contents = stripped_contents.replace(dynamic_definition.group(), r*len(dynamic_definition.group()))
        return stripped_contents.strip()

def strip_embedded_syntaxes(contents, preserve_length=False):

    r = ' ' if preserve_length else ''
    stripped_contents = contents
    for e in embedded_syntax.findall(stripped_contents):
        stripped_contents = stripped_contents.replace(e,''*len(e))
    return stripped_contents

def strip_errors(contents):
    return re.sub('<!!.*?!!>', '', contents, flags=re.DOTALL)

def sanitize_escape(string):
    if string.count('`') == 1:
        return string.replace('`','')
    return string


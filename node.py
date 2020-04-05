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
import os
from .metadata import NodeMetadata
from .dynamic import UrtextDynamicDefinition
import re
import datetime
import logging
import pytz

from anytree import Node
from anytree import PreOrderIter

dynamic_definition_regex = re.compile('(?:\[\[)([^\]]*?)(?:\]\])', re.DOTALL)
subnode_regexp = re.compile(r'{{(?!.*{{)(?:(?!}}).)*}}', re.DOTALL)
dynamic_def_regexp = re.compile(r'\[\[[^\]]*?\]\]', re.DOTALL)
default_date = pytz.timezone('UTC').localize(datetime.datetime(1970,2,1))

def create_urtext_node(
    filename, 
    contents='', 
    root=False, 
    compact=False,
    split=False):
    
    stripped_contents = UrtextNode.strip_dynamic_definitions(contents)
    metadata = NodeMetadata(stripped_contents)
    new_node = UrtextNode(filename, metadata, root=root, compact=compact, split=split)
    new_node.title = UrtextNode.set_title(stripped_contents, metadata=metadata)

    possible_defs = ['[['+section for section in contents.split('[[') ]
    dynamic_definitions = []
    for possible_def in possible_defs:
        match = re.match(dynamic_definition_regex, possible_def)        
        if match:
            match = match.group(0).strip('[[').strip(']]')
            dynamic_definition = UrtextDynamicDefinition(match)
            dynamic_definition.source_id = new_node.id
            dynamic_definitions.append(dynamic_definition)

    new_node.dynamic_definitions = dynamic_definitions

    return new_node

class UrtextNode:
    """ Urtext Node object"""
    def __init__(self, 
        filename, 
        metadata, 
        root=False, 
        compact=False, 
        split=False):

        self.filename = os.path.basename(filename)
        self.project_path = os.path.dirname(filename)
        self.position = 0
        self.ranges = [[0, 0]]
        self.tree = None
        self.is_tree = False
        self.dynamic = False
        self.id = None
        self.root_node = root
        self.tz = pytz.timezone('UTC')
        self.date = default_date # default, modified by the project
        self.prefix = None
        self.project_settings = False
        self.dynamic_definitions = {}
        self.compact = compact
        self.split = split
        self.metadata = metadata
        self.points = {}
 
        if self.metadata.get_first_meta_value('id'):
            node_id = self.metadata.get_first_meta_value('id').lower().strip()
            if re.match('^[a-z0-9]{3}$', node_id):
                self.id = node_id

        title_value = self.metadata.get_first_meta_value('title')
        if title_value and title_value == 'project_settings':
            self.project_settings = True

        self.parent = None
        self.index = self.metadata.get_first_meta_value('index')
        self.reset_node()

    def reset_node(self):
        self.tree_node = Node(self.id)

    def duplicate_tree(self):
        return duplicate_tree(self.tree_node)
    
    def get_date(self, format_string=''):
        return self.date.strftime(format_string)

    def contents(self):
        with open(os.path.join(self.project_path, self.filename),
                  'r',
                  encoding='utf-8') as theFile:
            file_contents = theFile.read()
            theFile.close()
        node_contents = []
        for segment in self.ranges:
            node_contents.append(file_contents[segment[0]:segment[1]])
        node_contents = ''.join(node_contents)

        # Strip out all Urtext node marker  Syntax.
        # FUTURE: There may be a cleaner way to accomplish this at parse-time.
        node_contents = node_contents.replace('{{','')
        node_contents = node_contents.replace('}}','')
        if self.split: # don't include the split marker
            node_contents = node_contents.replace('%','',1)
        if self.compact: # don't include the split marker
             node_contents = node_contents.lstrip().replace('^','',1)
        return node_contents

    @classmethod
    def strip_metadata(self, contents=''):
        if contents == '':
            return contents
        stripped_contents = re.sub(r'(\/--(?:(?!\/--).)*?--\/)',
                                   '',
                                   contents,
                                   flags=re.DOTALL)
        return stripped_contents

    @classmethod
    def strip_inline_nodes(self, contents=''):
        if contents == '':
            contents = self.contents()
        
        stripped_contents = contents
        while subnode_regexp.search(stripped_contents):
            for inline_node in subnode_regexp.findall(stripped_contents):
                stripped_contents = stripped_contents.replace(inline_node, '')
        return stripped_contents

    @classmethod
    def strip_dynamic_definitions(self, contents=''):
        if not contents:
            return contents
             
        stripped_contents = contents
        while dynamic_def_regexp.search(stripped_contents):
            for dynamic_definition in dynamic_def_regexp.findall(
                    stripped_contents):
                stripped_contents = stripped_contents.replace(
                    dynamic_definition, '')
        return stripped_contents

    def content_only(self, contents=''):
        contents = self.strip_metadata(contents=self.contents())
        contents = self.strip_dynamic_definitions(contents=contents)
        return contents

    @classmethod
    def strip_contents(self, contents):
        contents = self.strip_metadata(contents=contents)
        contents = self.strip_dynamic_definitions(contents=contents)
        return contents

    def set_index(self, new_index):
        self.index = new_index

    @classmethod
    def set_title(self, contents, metadata=None):

        #
        # check for title metadata
        #
        if metadata:
            title_value = metadata.get_first_meta_value('title')
            if title_value: 
                return title_value
        #
        # otherwise, title is the first non white-space line
        #
        stripped_contents_lines = self.strip_metadata(contents=contents).strip().split('\n')

        index = 0
        last_line = len(stripped_contents_lines) - 1
        while stripped_contents_lines[index].strip() in ['','%']:
            if index == last_line:
                return '(untitled)'
            index += 1

        first_line = stripped_contents_lines[index][:100].replace('{{','').replace('}}', '')
        first_line = re.sub('\/-.*(-\/)?', '', first_line, re.DOTALL)
        first_line = re.sub('>{1,2}[0-9,-z]{3}', '', first_line, re.DOTALL)
        first_line = re.sub('┌──','',first_line, re.DOTALL)
        first_line = re.sub('\|','',first_line, re.DOTALL) # pipe character cannot be in node names
       
        # make conditional?
        first_line = re.sub(r'^[\s]*\^','',first_line)           # compact node opening wrapper
        first_line = re.sub(r'^\%(?!%)','',first_line)
        return first_line.strip().strip('\n').strip()

    def get_ID(self):
        if len(self.metadata.get_first_meta_value('ID')):  # title is the first many lines if not set
            return self.metadata.get_first_meta_value('ID')
        return self.id  # don't include links in the title, for traversing files clearly.

    def log(self):
        logging.info(self.id)
        logging.info(self.index)
        logging.info(self.filename)
        logging.info(self.metadata.log())

    def consolidate_metadata(self, one_line=False):
        
        if one_line:
            line_separator = '; '
        else:
            line_separator = '\n'

        keynames = {}
        for entry in self.metadata.entries:
            if entry.keyname not in keynames:
                keynames[entry.keyname] = []
            timestamp = ''
            if entry.dtstring:
                timestamp = ' '+entry.dtstring
            for value in entry.values:
                keynames[entry.keyname].append(value+timestamp)
        new_metadata = '\n/-- '
        
        if not one_line: 
            new_metadata += '\n'
            new_metadata += line_separator

        for keyname in keynames:
            new_metadata += keyname + ': '
            new_metadata += ' | '.join(keynames[keyname])
            new_metadata += line_separator
        if one_line:
            new_metadata = new_metadata[:-2] + ' '

        new_metadata += '--/'
        return new_metadata
    

    def get_all_meta_keynames(self):
        keynames = []
        for entry in self.metadata.entries:
            if entry.keyname not in keynames:
                keynames.append(entry.keyname)
        return keynames

    def set_content(self, contents):

        if contents == self.contents():
            return False

        with open(os.path.join(self.project_path, self.filename),
                  'r',
                  encoding='utf-8') as theFile:
            file_contents = theFile.read()
            theFile.close()

        start_range = self.ranges[0][0]
        end_range = self.ranges[-1][1]

        new_file_contents = ''.join([
            file_contents[0:start_range],
            contents,
            file_contents[end_range:]]) 
        
        with open(os.path.join(self.project_path, self.filename),
                  'w',
                  encoding='utf-8') as theFile:
            theFile.write(new_file_contents)
            theFile.close()

        return True
        """ MUST re-parse now """

def duplicate_tree(original_node):

    new_root = Node(original_node.name)

    # iterate immediate children only
    all_nodes = PreOrderIter(original_node, maxlevel=2)  

    for node in all_nodes:

        if node == original_node:
            continue

        if node.name in [ancestor.name for ancestor in node.ancestors]:

            new_node = Node('! RECURSION :' + node.name)
            new_node.parent = new_root
            continue

        if node.parent == original_node:
            """ Recursively apply this function to children's children """
            new_node = duplicate_tree(node)
            new_node.parent = new_root
    
    return new_root

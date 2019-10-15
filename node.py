# -*- coding: utf-8 -*-
import os
from .metadata import NodeMetadata
from .dynamic import UrtextDynamicDefinition
import re
import datetime
import logging
import pytz
PACKAGE_FOLDER = __name__.split('.')[0]

from anytree import Node
from anytree import PreOrderIter


"""
Dynamic definitions in the form:
{ target_id : definition, ..., ... }
"""
dynamic_definition_regex = re.compile('(?:\[\[)(.*?)(?:\]\])', re.DOTALL)
subnode_regexp = re.compile(r'{{(?!.*{{)(?:(?!}}).)*}}', re.DOTALL)
dynamic_def_regexp = re.compile(r'\[\[.*?\]\]', re.DOTALL)

class UrtextNode:
    """ Urtext Node object"""
    def __init__(self, filename, contents='', root=False):
        self.filename = os.path.basename(filename)
        self.project_path = os.path.dirname(filename)
        self.position = 0
        self.ranges = [[0, 0]]
        self.tree = None
        self.dynamic = False
        self.id = None
        self.new_id = None
        self.root_node = root
        self.tz = pytz.timezone('UTC')
        self.date = self.tz.localize(datetime.datetime(1970,1,1))  # default
        self.prefix = None
        self.project_settings = False
        self.dynamic_definitions = {}
        self.compact = False
        stripped_contents = self.strip_dynamic_definitions(contents)
        self.metadata = NodeMetadata(stripped_contents)
        
        if self.metadata.get_tag('ID'):
            node_id = self.metadata.get_tag('ID')[0].lower().strip()
            if re.match('^[a-z0-9]{3}$', node_id):
                self.id = node_id
        if self.metadata.get_tag('title') == ['project_settings']:
            self.project_settings = True

        self.parent = None
        self.index = self.metadata.get_tag('index')
        self.reset_node()
        
        for match in dynamic_definition_regex.findall(contents):
            dynamic_definition = UrtextDynamicDefinition(match)
            dynamic_definition.source_id = self.id
            if dynamic_definition.target_id != None:
                self.dynamic_definitions[dynamic_definition.target_id] = dynamic_definition

        self.set_title(stripped_contents)

    def reset_node(self):
        self.tree_node = Node(self.id)

    def duplicate_tree(self):
        return duplicate_tree(self.tree_node)

    def contents(self):
        with open(os.path.join(self.project_path, self.filename),
                  'r',
                  encoding='utf-8') as theFile:
            file_contents = theFile.read()
            theFile.close()
        node_contents = []
        for segment in self.ranges:
            node_contents.append(file_contents[segment[0]:segment[1]])
        return ''.join(node_contents)

    def strip_metadata(self, contents=''):
        if contents == '':
            contents = self.contents()
        stripped_contents = re.sub(r'(\/--(?:(?!\/--).)*?--\/)',
                                   '',
                                   contents,
                                   flags=re.DOTALL)
        return stripped_contents

    def strip_inline_nodes(self, contents=''):
        if contents == '':
            contents = self.contents()
        
        stripped_contents = contents
        while subnode_regexp.search(stripped_contents):
            for inline_node in subnode_regexp.findall(stripped_contents):
                stripped_contents = stripped_contents.replace(inline_node, '')
        return stripped_contents

    def strip_dynamic_definitions(self, contents=''):
        if contents == '':
            contents = self.contents()
        
        stripped_contents = contents
        while dynamic_def_regexp.search(stripped_contents):
            for dynamic_definition in dynamic_def_regexp.findall(
                    stripped_contents):
                stripped_contents = stripped_contents.replace(
                    dynamic_definition, '')
        return stripped_contents

    def content_only(self):

        contents = self.strip_metadata(contents=self.contents())
        contents = self.strip_dynamic_definitions(contents=contents)
        return contents

    def set_index(self, new_index):
        self.index = new_index

    def set_title(self, stripped_contents):
        #
        # check for title metadata
        #
        title_tag = self.metadata.get_tag('title')
        if len(title_tag) > 0: 
            self.title = title_tag[0]
            return
        #
        # otherwise, title is the first non white-space line
        #
        stripped_contents = self.strip_metadata(contents=stripped_contents).strip().split('\n')

        index = 0
        last_character = len(stripped_contents) - 1
        while stripped_contents[index] == r'\s':
            if index == last_character:
                self.title = '(untitled)'
                return
            index += 1

        first_line = stripped_contents[index][:100].replace('{{','').replace('}}', '')
        first_line = re.sub('\/-.*(-\/)?', '', first_line, re.DOTALL)
        self.title = first_line.strip().strip('\n').strip()

    def get_ID(self):
        if len(self.metadata.get_tag(
                'ID')) > 0:  # title is the first many lines if not set
            return self.metadata.get_tag('ID')[0]
        return self.id  # don't include links in the title, for traversing files clearly.

    def log(self):
        logging.info(self.id)
        logging.info(self.index)
        logging.info(self.filename)
        logging.info(self.metadata.log())

    def consolidate_metadata(self, one_line=False):
        
        if one_line == True:
            line_separator = '; '
        else:
            line_separator = '\n'

        tags = {}
        for entry in self.metadata.entries:
            if entry.tag_name not in tags:
                tags[entry.tag_name] = []
            entry_value = entry.value
            if isinstance(entry.value, str):
                entry_value = [entry_value]
            for value in entry_value:
                tags[entry.tag_name].append(value)
        new_metadata = '\n/-- '
        if not one_line: 
            new_metadata += '\n'
            new_metadata += line_separator

        for tag in tags:
            new_metadata += tag + ': '
            if isinstance(tags[tag], list):
                new_metadata += ' | '.join(tags[tag])
            else:
                new_metadata += tags[tag]
            new_metadata += line_separator
        if one_line:
            new_metadata = new_metadata[:-2] + ' '

        new_metadata += '--/'
        return new_metadata

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

    all_nodes = PreOrderIter(original_node,
                             maxlevel=2)  # iterate immediate children only

    for node in all_nodes:
        if node == original_node:
            continue

        if node.name in [ancestor.name for ancestor in node.ancestors]:

            recursion_name = 'RECURSION ' + node.name
            new_node = Node(recursion_name)
            new_node.parent = new_root
            continue

        if node.parent == original_node:
            new_node = duplicate_tree(node)
            new_node.parent = new_root
    
    return new_root

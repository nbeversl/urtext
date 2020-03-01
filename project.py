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
import itertools
import platform
import logging
import json
import os
import random
import time
import pickle
from time import strftime
from pytz import timezone
import pytz
import concurrent.futures
from anytree import Node, RenderTree, PreOrderIter

from whoosh.fields import Schema, TEXT, KEYWORD, ID, STORED
from whoosh.index import create_in, exists_in, open_dir
from whoosh.analysis import StandardAnalyzer
from whoosh.writing import AsyncWriter

from .timeline import timeline
from .file import UrtextFile
from .interlinks import Interlinks
from .node import UrtextNode 
from .compile import compile_functions
from .trees import trees_functions
from .meta_handling import metadata_functions
from .search import search_functions
from .reindex import reindex_functions
from .watchdog import watchdog_functions

node_pointer_regex = r'>>[0-9,a-z]{3}\b'
node_link_regex = r'>[0-9,a-z]{3}\b'
title_marker_regex = r'\|.*?\s>{1,2}[0-9,a-z]{3}\b'
node_id_regex = r'\b[0-9,a-z]{3}\b'

functions = []
functions.extend(trees_functions)
functions.extend(compile_functions)
functions.extend(metadata_functions)
functions.extend(search_functions)
functions.extend(reindex_functions)
functions.extend(watchdog_functions)

def add_functions_as_methods(functions):
    def decorator(Class):
        for function in functions:
            setattr(Class, function.__name__, function)
        return Class
    return decorator

@add_functions_as_methods(functions)
class UrtextProject:
    """ Urtext project object """
    
    def __init__(self,
                 path,
                 rename=False,
                 recursive=False,
                 import_project=False,
                 init_project=False,
                 watchdog=False):

        self.path = path
        self.log = None
        self.nodes = {}
        self.files = {}
        self.tagnames = {}
        self.zero_page = ''
        self.other_projects = []
        self.navigation = []  # Stores, in order, the path of navigation
        self.nav_index = -1  # pointer to the CURRENT position in the navigation list
        self.to_import = []
        self.settings_initialized = False
        self.dynamic_nodes = []  # { target : definition, etc.}
        self.dynamic_tags = {} # source_id : [ target_id, ... ]
        self.compiled = False
        self.alias_nodes = []
        self.ix = None
        self.loaded = False
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.settings = {  # defaults
            'logfile':'urtext_log.txt',
            'home': None,
            'timestamp_format':
                [   
                '%a., %b. %d, %Y, %I:%M %p', 
                '%B %-d, %Y', 
                '%B %Y', 
                '%m-%d-%Y',
                '%a., %b. %d, %Y, %I:%M %p %z', 
                '%a., %b. %d, %Y, %I:%M %p',
                '%A, %B %d, %Y, %I:%M %p',
                '%B %d, %Y, %I:%M %p',
                '%B %d, %Y, %I:%M%p',
                '%B %Y',
                '%Y',
                '%B %d, %Y',
                '%A, %B %d, %Y, %I:%M%p'
                ],
            'filenames': ['PREFIX', 'DATE %m-%d-%Y', 'TITLE'],
            'console_log':'false',
            'google_auth_token' : 'token.json',
            'google_calendar_id' : None,
            'timezone' : ['UTC'] 
        }
        self.default_timezone = None
        self.title = self.path # d
        # if os.path.exists(os.path.join(self.path, "save.p")):
        #     self._log_item('Loading project from pickle')
        #     saved_state = pickle.load(open( os.path.join(self.path, "save.p"), "rb" ) )
           
        #     self.nodes = saved_state.nodes
        #     self.files = saved_state.files
        #     self.tagnames = saved_state.tagnames
        #     self.settings = saved_state.settings
        #     self.dynamic_nodes = saved_state.dynamic_nodes
        #     self.alias_nodes = saved_state.alias_nodes
                
        #     self.executor.submit(self._initialize_project, import_project=import_project, init_project=init_project) 
        
        self._initialize_project(import_project=import_project, init_project=init_project)

        self.log = self.setup_logger('urtext_log', os.path.join(self.path, 'urtext_log.txt'))

        if not exists_in(os.path.join(self.path, "index"), indexname="urtext"):
            if not os.path.exists(os.path.join(self.path, "index")):
                os.mkdir(os.path.join(self.path, "index"))
            schema = Schema(
                title=TEXT(stored=True),
                path=ID(unique=True, stored=True),
                content=TEXT(stored=True, analyzer=StandardAnalyzer()))
            create_in(os.path.join(self.path, "index"), schema, indexname="urtext")
        
        self.ix = open_dir(os.path.join(self.path, "index"), indexname="urtext")

        self.loaded = True

    def _initialize_project(self, 
        import_project=False, 
        init_project=False):

        filelist = os.listdir(self.path)
        
        for file in filelist:
            if self._filter_filenames(file) == None:
                continue            
            self._parse_file(file)
        
        if import_project:
            for file in self.to_import:
                self.import_file(file)

        self.default_timezone = timezone(self.settings['timezone'][0])

        if self.nodes == {}:
            if init_project == True:
                self._log_item('Initalizing a new Urtext project in ' + self.path)
                self.new_file_node()
            else:
                raise NoProject('No Urtext nodes in this folder.')

        elif init_project:
            print('Urtext project already exists here.')
            return None            
        
        # must be done once manually on project init
        for node_id in list(self.nodes):  
            self._parse_meta_dates(node_id)
        
        self._update()

    def _node_id_generator(self):
        chars = [
            '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'a', 'b', 'c',
            'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p',
            'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z'
        ]
        return itertools.product(chars, repeat=3)

    def _update(self, 
        compile_project=True, 
        update_lists=True,
        modified_files=[]):

        """ 
        Main method to keep the project updated. 
        Should be called whenever file or directory content changes
        """

        # Build copies of trees wherever there are Node Pointers (>>)
        self._build_alias_trees()  
        self._rewrite_recursion()

        if compile_project:
            modified_files = self._compile(modified_files=modified_files)
            self.compiled = True

        if update_lists:
            self.update_node_list()
            self._update_metadata_list()

        #pickle = PickledUrtextProject(self)
        
        return modified_files

    def _parse_file(self, 
        filename,
        re_index=False,
        ):
    
        if self._filter_filenames(os.path.basename(filename)) == None:
            return

        # clear all node_id's defined from this file in case the file has changed
        if os.path.basename(filename) in self.files:
            self._remove_file(os.path.basename(filename))

        """
        Parse the file
        """
        new_file = UrtextFile(os.path.join(self.path, filename), search_index=self.ix)
        if not new_file.nodes: 
            self.to_import.append(filename)
            return

        """
        re-add the filename and all its nodes to the project
        """
        
        self.files[new_file.basename] = new_file
        for node_id in new_file.nodes:
            if self._is_duplicate_id(node_id, filename):
                self._remove_file(new_file.basename)
                return None
            self._add_node(new_file.nodes[node_id])
        
        """
        If this is not the initial load of the project, parse the timestamps in the file
        """
        if self.compiled:
            for node_id in new_file.nodes:
                self._parse_meta_dates(node_id)
        
        self._set_tree_elements(new_file.basename)

        for node_id in new_file.nodes:
            self._rebuild_node_tag_info(node_id)

        return filename

    def _rewrite_titles(self,filename):
        
        original_contents = self._full_file_contents(filename=filename)
        new_contents = original_contents
        matches = re.findall(title_marker_regex, new_contents)
        if matches:
            for match in matches:
                node_id = match[-3:]
                if node_id in self.nodes:
                    title = self.nodes[node_id].title
                else:
                    title = ' ? '
                bracket = '>'
                if re.search(node_pointer_regex, match):
                    bracket += '>'
                new_contents = new_contents.replace(match, '| '+title+' '+bracket+node_id)
        if new_contents != original_contents:
            return new_contents 

        return False

    def _target_id_defined(self, check_id):
        for definition in self.dynamic_nodes:
            if definition.target_id and definition.target_id == check_id:
                return definition.source_id
        return

    def _target_file_defined(self, file):
        for definition in self.dynamic_nodes:
            if definition.target_file and definition.target_file == file:
                return definition.source_id
        return

    """
    Parsing helpers
    """
    def _add_node(self, new_node):
        """ Adds a node to the project object """

        for definition in new_node.dynamic_definitions:
            
            if definition.target_id:
                defined = self._target_id_defined(definition.target_id)
                if defined and defined != new_node.id:
                    self._log_item('Node >' + definition.target_id +
                                  ' has duplicate definition in >' + new_node.id +
                                  '. Keeping the definition in >' +
                                  defined + '.')
                else:
                    self.dynamic_nodes.append(definition)
                
            if definition.target_file:

                defined = self._target_file_defined(definition.target_file)
                if defined and defined != new_node.id:
                    self._log_item('File ' + definition.file +
                                  ' has duplicate definition in >' + new_node.id +
                                  '. Keeping the definition in >' +
                                  defined + '.')
                else:
                    self.dynamic_nodes.append(definition)

        if len(new_node.metadata.get_tag('ID')) > 1:
            self._log_item('Multiple ID tags in >' + new_node.id +
                          ', '+', '.join(new_node.metadata.get_tag('ID'))+' ( using the first one found.')
        
        self.nodes[new_node.id] = new_node
        if new_node.project_settings:
            self._get_settings_from(new_node)

    def _parse_meta_dates(self, node_id):
        """ Parses dates (requires that timestamp_format already be set) """

        for entry in self.nodes[node_id].metadata.entries:
            if entry.dtstring:
                dt_stamp = self._date_from_timestamp(entry.dtstring) 
                if dt_stamp:
                    self.nodes[node_id].metadata.dt_stamp = dt_stamp
                    if entry.tag_name == 'timestamp':
                        self.nodes[node_id].date = dt_stamp
                else:
                    self._log_item('Timestamp ' + entry.dtstring +
                                  ' not in any specified date format in >' +
                                  node_id)

    def _date_from_timestamp(self, datestamp_string):
        dt_stamp = None
        for this_format in self.settings['timestamp_format']:
            try:
                dt_stamp = datetime.datetime.strptime(datestamp_string, '<' + this_format + '>')
                if not dt_stamp:
                    continue
                if dt_stamp.tzinfo == None:
                    dt_stamp = self.default_timezone.localize(dt_stamp) 

                return dt_stamp                
            except ValueError:
                continue
        return None

    def export_from_root_node(self, root_node_id):
        export = UrtextExport(self)
        contents = export.export_from(
            root_node_id, 
            kind='plaintext',
            as_single_file=True)
        return contents[0]
    

    def get_source_node(self, filename, position):
        if filename not in self.files:
            return None, None
        exported_node_id = self.get_node_id_from_position(filename, position)
        points = self.nodes[exported_node_id].points
        if not points:
            return None, None
        node_start_point = self.nodes[exported_node_id].ranges[0][0]

        indexes = sorted(points)
        for index in range(0, len(indexes)):
            if position >= indexes[index] and position < indexes[index+1]:
                node, target_position = self.nodes[exported_node_id].points[indexes[index]]
                offset = position - indexes[index]
                return node, target_position+offset

    def _set_node_contents(self, node_id, contents):
        """ project-aware alias for the Node set_content() method """
        content_changed = self.nodes[node_id].set_content(contents)
        if content_changed:
            self._parse_file(self.nodes[node_id].filename)
            return self.nodes[node_id].filename
        return False

    """
    Refreshers
    """
    def update_node_list(self):
        """ Refreshes the Node List file, if it exists """
        if 'zzz' in self.nodes:
            node_list_file = self.nodes['zzz'].filename
            contents = self.list_nodes() + '/--\nid:zzz\ntitle: Node List\n--/'
            self._set_node_contents('zzz', contents)

    def _update_metadata_list(self):
        """ Refreshes the Metadata List file """

        root = Node('Metadata Keys')
        for key in sorted([
                k for k in self.tagnames
                if k.lower() not in ['defined in', 'id', 'timestamp', 'index']
        ]):
            s = Node(key)
            s.parent = root
            for value in sorted(self.tagnames[key]):
                t = Node(value)
                t.parent = s
                if value in self.tagnames[key]:
                    for node_id in sorted(self.tagnames[key][value]):
                        if node_id in self.nodes:
                            n = Node(self.nodes[node_id].title + ' >' +
                                     node_id)
                            n.parent = t
                        else: # debugging
                            print(node_id+ ' WAS LOST (DEBUGGING)')
                
        if 'zzy' in self.nodes:
            metadata_file = self.nodes['zzy'].filename
            contents = []           
            for pre, _, node in RenderTree(root):
                contents.append("%s%s\n" % (pre, node.name))
            contents.append('/--\nid:zzy\ntitle: Metadata List\n--/')
            self._set_node_contents('zzy', ''.join(contents))


    def _adjust_ranges(self, filename, from_position, amount):
        """ 
        adjust the ranges of all nodes in the given file 
        a given amount, from a given position
        """
        for node_id in self.files[os.path.basename(filename)].nodes:
            number_ranges = len(self.nodes[node_id].ranges)
            for index in range(number_ranges):
                this_range = self.nodes[node_id].ranges[index]
                if from_position >= this_range[0]:
                    self.nodes[node_id].ranges[index][0] -= amount
                    self.nodes[node_id].ranges[index][1] -= amount

    def _full_file_contents(self, filename='', node_id=''):
        if node_id:
            filename = self.nodes[node_id].filename
        if not filename:
            return
        with open(os.path.join(self.path, filename), 'r',
                  encoding='utf-8') as theFile:
            file_contents = theFile.read()
            theFile.close()
        return file_contents

    def _set_file_contents(self, filename, contents):
        with open(os.path.join(self.path, filename),
                  'w', encoding='utf-8') as theFile:
            theFile.write(contents)
            theFile.close()
        return


    def import_file(self, filename):
        with open(
                os.path.join(self.path, filename),
                'r',
                encoding='utf-8',
        ) as theFile:
            full_file_contents = theFile.read()
            theFile.close()

        date = creation_date(os.path.join(self.path, filename))
        now = datetime.datetime.now()
        contents = '\n\n'
        contents += "/-- ID:" + self.next_index() + '\n'
        contents += 'timestamp:' + self.timestamp(date) + '\n'
        contents += 'imported:' + self.timestamp(now) + '\n'
        contents += " --/"

        full_file_contents += contents

        self._set_file_contents(filename,full_file_contents)

        return self._parse_file(filename)

    def get_node_relationships(self, 
        node_id, 
        omit=[]):

        return Interlinks(self, 
            node_id, 
            omit=omit).render_tree()

    """
    Removing and renaming files
    """
    def _remove_file(self, filename):
    
        if filename in self.files:
            for node_id in self.files[filename].nodes:
                for index, definition in enumerate(self.dynamic_nodes):
                    if definition.source_id == node_id:
                        del self.dynamic_nodes[index]

                for tagname in list(self.tagnames):
                    for value in list(self.tagnames[tagname]):
                        if value in self.tagnames[tagname]:  
                            # in case it's been removed
                            if node_id in self.tagnames[tagname][value]:
                                self.tagnames[tagname][value].remove(node_id)
                            if len(self.tagnames[tagname][value]) == 0:
                                del self.tagnames[tagname][value]
                if node_id in self.nodes:
                    del self.nodes[node_id]
                if node_id in self.dynamic_tags:
                    for target_id in self.dynamic_tags[node_id]:
                        if target_id in self.nodes:
                            self.nodes[target_id].metadata.remove_dynamic_tags_from_node(node_id)

            del self.files[filename]

        return None

    def delete_file(self, filename):
    	  
        self._remove_file(os.path.basename(filename))
        os.remove(os.path.join(self.path, filename))
        future = self.executor.submit(self._update) 

    def _handle_renamed(self, old_filename, new_filename):
        new_filename = os.path.basename(new_filename)
        old_filename = os.path.basename(old_filename)
        self.files[new_filename] = self.files[old_filename]
        for node_id in self.files[new_filename].nodes:
            self.nodes[node_id].filename = new_filename
            self.nodes[node_id].full_path = os.path.join(
                self.path, new_filename)
        if new_filename != old_filename:
            del self.files[old_filename]

    """ 
    Methods for filtering files to skip 
    """
    def _filter_filenames(self, filename):
        """ Filters out files to skip altogether """
        """ Omit system files """
        if filename[0] == '.':
            return None
        if 'urtext_log' in filename:
            return None
        if not filename.endswith('.txt'):
            # FUTURE:
            # save and check these in an optional list of other extensions 
            # set from project_settings 
            return None
        """ Omit the log file """
        skip_files = [self.settings['logfile'][0]]
        if filename in skip_files:
            return None

        return filename
    
    def new_file_node(self, date=None, metadata = {}, node_id=None):
        """ add a new FILE-level node programatically """

        if date == None:
            date = datetime.datetime.now()

        if not node_id:
            node_id = self.next_index()            
        contents = "\n\n\n"
        contents += "/-- ID:" + node_id + '\n'
        contents += 'timestamp:' + self.timestamp(date) + '\n'
        contents += 'from: '+ platform.node() + '\n'
        for key in metadata:
            contents += key + ": " + metadata[key] + '\n'
        contents += "--/"

        filename = node_id + '.txt'

        self._set_file_contents( filename, contents )  
        self._parse_file(filename)
        return { 
                'filename':filename, 
                'id':node_id
                }
 
    def add_inline_node(self, 
            date=None, 
            contents='', 
            metadata={},
            one_line=False,
            include_timestamp=False):
            
        if contents == '':
            contents = ' '
        
        node_id = self.next_index()
        metadata['id']=node_id
        if include_timestamp:
            if date == None:
                date = datetime.datetime.now()
            metadata['timestamp'] = self.timestamp(date)
        new_node_contents = "{{ " + contents 
        metadata_block = build_metadata(metadata, one_line=one_line)
        new_node_contents += metadata_block + " }}"
        metadata={}
        return (new_node_contents, node_id)

    def insert_interlinks(self, node_id, one_line=True):
        new_node = self.add_inline_node()
        insertion = new_node[0]
        new_node_id = new_node[1]
        dynamic_def =   '[[ id:'+ new_node_id +'; '
        dynamic_def +=  'interlinks:'+node_id
        dynamic_def += ' ]]'

        return '\n'.join([insertion, dynamic_def])

    def add_compact_node(self, 
            date=None, 
            contents='', 
            metadata={},
        ):
        if date == None:
            date = datetime.datetime.now()
        metadata['id']=self.next_index()
        metadata['timestamp'] = self.timestamp(date)
        metadata_block = build_metadata(metadata, one_line=True)
        return '^ '+contents + metadata_block



    def _prefix_length(self):
        """ Determines the prefix length for indexing files (requires an already-compiled project) """

        prefix_length = 0
        num_files = len(self.files)
        while num_files > 1:
            prefix_length += 1
            num_files /= 10
        return prefix_length

    """
    Project Navigation
    """

    def nav_advance(self):
        if not self.check_nav_history():
            return None

        # return if the index is already at the end
        if self.nav_index == len(self.navigation) - 1:
            self._log_item('index is at the end.')
            return None
        
        self.nav_index += 1
        return self.navigation[self.nav_index]


    def nav_new(self, node_id):

        # don't re-remember consecutive duplicate links
        if self.nav_index > -1 and node_id == self.navigation[self.nav_index]:
            return

        # add the newly opened file as the new "HEAD"
        del self.navigation[self.nav_index+1:]
        self.navigation.append(node_id)
        self.nav_index += 1

    def nav_reverse(self):
        if not self.check_nav_history():
            return None

        if self.nav_index == 0:
            self._log_item('index is already at the beginning.')
            return None

        last_node = self.navigation[self.nav_index - 1]
        self.nav_index -= 1
        return last_node

    def nav_current(self):
        if not self.check_nav_history():
            return None
        if self.nav_index in self.navigation:
            return self.navigation[self.nav_index]
        return None

    def check_nav_history(self):

        if len(self.navigation) == 0:
            self._log_item('There is no nav history')
            return None

        return True

    """ 
    Cataloguing Nodes
    """

    def list_nodes(self):
            
        output = ''
        for node_id in list(self.indexed_nodes()):
            title = self.nodes[node_id].title
            output += title + ' >' + node_id + '\n-\n'
        for node_id in list(self.unindexed_nodes()):
            title = self.nodes[node_id].title
            output += title + ' >' + node_id + '\n-\n'
        return output

    def unindexed_nodes(self):
        """ 
        returns an array of node IDs of unindexed nodes, 
        in reverse order (most recent) by date 
        """

        unindexed_nodes = []
        for node_id in list(self.nodes):   
            if self.nodes[node_id].metadata.get_tag('index') == []:
                unindexed_nodes.append(node_id)
                
        sorted_unindexed_nodes = sorted(
            unindexed_nodes,
            key=lambda node_id: self.nodes[node_id].date,
            reverse=True)
        return sorted_unindexed_nodes

    def indexed_nodes(self):
        """ returns an array of node IDs of indexed nodes, in indexed order """

        #self.update_lock.acquire()
        indexed_nodes_list = []
        for node_id in list(self.nodes):
            if self.nodes[node_id].metadata.get_tag('index') != []:
                indexed_nodes_list.append([
                    node_id,
                    int((self.nodes[node_id].metadata.get_first_tag('index')))
                ])
        sorted_indexed_nodes = sorted(indexed_nodes_list,
                                      key=lambda item: item[1])
        for index, node in enumerate(sorted_indexed_nodes):
            sorted_indexed_nodes[index] = node[0] 
        return sorted_indexed_nodes

    def root_nodes(self, primary=False):
        """
        Returns the IDs of all the root (file level) nodes
        """
        root_nodes = []        
        for filename in self.files:
            if not primary:
                root_nodes.extend(self.files[filename].root_nodes)
            else:
                root_nodes.append(self.files[filename].root_nodes[0])
        return root_nodes


    def get_parent(self, child_node_id):
        """ Given a node ID, returns its parent, if any """
        
        filename = self.nodes[child_node_id].filename
        start_of_node = self.nodes[child_node_id].ranges[0][0]
        distance_back = 1
        if start_of_node == 0 and self.nodes[child_node_id].compact:
            return self.files[filename].root_nodes[0]

        parent_node = self.get_node_id_from_position(filename, start_of_node - distance_back)
        while not parent_node and distance_back < start_of_node:
            distance_back += 1
            parent_node = self.get_node_id_from_position(filename, start_of_node - distance_back)

        # if this is a split node, keep getting the parent until we're out of a split.
        if self.nodes[child_node_id].split:
            while self.nodes[parent_node].split:
                if self.nodes[parent_node].root_node:
                    break
                parent_node = self.get_parent(parent_node)

        return parent_node

    def _is_in_node(self, position, node_id):
        """ 
        private
        Given a position, and node_id, returns whether the position is in the node 
        """

        for this_range in self.nodes[node_id].ranges:
            if position >= this_range[0] and position <= this_range[1]:
                return True
        return False

    def get_node_id_from_position(self, filename, position):
        """ 
        public
        Given a position, returns the Node ID it's in 
        """
        filename = os.path.basename(filename)
        if filename in self.files:
            for node_id in self.files[os.path.basename(filename)].nodes:
                if self._is_in_node(position, node_id):
                    return node_id
        return None

    def get_link(self, string, position=0):
        """ Given a line of text passed from an editor, returns finds a node or web link """
        url_scheme = re.compile('http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\), ]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')

        if re.search(url_scheme, string[position:]):
            url = re.search(url_scheme, string).group(0)
            return ('HTTP', url)
        link = None
        # first try looking around where the cursor is positioned
        for index in range(0, 4):
            if re.search(node_link_regex,
                         string[position - index:position - index + 5]):
                link = re.search(
                    node_link_regex,
                    string[position - index:position - index + 5]).group(0)
                break

        # next try looking ahead:
        if not link:
            after_cursor = string[position:]
            if re.search(node_link_regex, after_cursor):
                link = re.search(node_link_regex, after_cursor).group(0)

        # then behind:
        if not link:
            before_cursor = string[:position]
            if re.search(node_link_regex, before_cursor):
                link = re.search(node_link_regex, before_cursor).group(0)

        if not link:
            return None

        node_id = link.split(':')[0].strip('>')
        if node_id.strip() in self.nodes:
            file_position = self.nodes[node_id].ranges[0][0]
            return ('NODE', node_id, file_position)
        else:
            self._log_item('Node ' + node_id + ' is not in the project')
            return None
        self._log_item('No node ID found on this line.')
        return None

    def build_timeline(self, nodes):
        """ Given a list of nodes, returns a timeline """
        return timeline(self, nodes)

    def _is_duplicate_id(self, node_id, filename):
        """ private method to check if a node id is already in the project """
        if node_id in self.nodes:
            self._log_item('Duplicate node ID ' + node_id + ' in ' + filename +
                          ' -- already used in ' +
                          self.nodes[node_id].filename + ' (>' + node_id + ')')
            return True
        return False

    def _log_item(self, item):
        if self.log:
            self.log.info(item + '\n')
            if self.settings['console_log'].lower() == 'true':          
                print(item)
        else:
            print(item)
        
    def timestamp(self, date):
        """ Given a datetime object, returns a timestamp in the format set in project_settings, or the default """

        if date.tzinfo == None:
            date = self.default_timezone.localize(date)             
        timestamp_format = '<' + self.settings['timestamp_format'][0] + '>'
        return date.strftime(timestamp_format)

    def _get_settings_from(self, node):
        for entry in node.metadata.entries:
            self.settings[entry.tag_name.lower()] = entry.values
        if 'project_title' in self.settings:
            self.title = self.settings['project_title'][0]
        if 'console_log' in self.settings:
            self.settings['console_log'] = self.settings['console_log'][0]

        self.default_timezone = timezone(self.settings['timezone'][0])

    def get_home(self):
        if self.settings['home']:
            return self.settings['home'][0]
        return None

    def next_index(self):
        index = random.choice(list(self._node_id_generator()))
        while ''.join(index) in self.nodes:
            index = random.choice(list(self._node_id_generator()))
        return ''.join(index)

    def pop_node(self, position=None, filename=None, node_id=None):
        if not node_id:
            node_id = self.get_node_id_from_position(filename, position)
        if not node_id:
            return
        if self.nodes[node_id].root_node:
            print(node_id + ' is already a root node.')
            return None

        start = self.nodes[node_id].ranges[0][0]
        end = self.nodes[node_id].ranges[-1][1]

        file_contents = self._full_file_contents(node_id=node_id)
        
        popped_node_id = node_id

        filename = self.nodes[node_id].filename
        popped_node_contents = file_contents[start:end].strip()
        
        if self.nodes[node_id].split:
            popped_node_contents = popped_node_contents[1:] # strip the '%'

        if self.nodes[node_id].compact:
            # Strip whitspace + '^'
            popped_node_contents = popped_node_contents.lstrip()
            popped_node_contents = popped_node_contents[1:]

        remaining_node_contents = ''.join([
            file_contents[0:start - 2],
            '\n| ',
            self.nodes[popped_node_id].title,
             ' >>',
            popped_node_id,
            '\n',
            file_contents[end + 2:]])

        with open (os.path.join(self.path, filename), 'w', encoding='utf-8') as f:
            f.write(remaining_node_contents)
            f.close()
        self.executor.submit(self._parse_file, filename) 

        with open(os.path.join(self.path, popped_node_id+'.txt'), 'w',encoding='utf-8') as f:
            f.write(popped_node_contents)
            f.close()

        self.executor.submit(self._parse_file, popped_node_id+'.txt') 

        return start - 2 # returns where to put the cursor at the new marker

    def titles(self):
        title_list = {}
        for node_id in self.nodes:
            title_list[self.nodes[node_id].title] = (self.title, node_id)
        return title_list

    def complete_tag(self, fragment):
        fragment = fragment.lower().strip()
        length = len(fragment)
        for tag in self.tagnames['tags'].keys():
            if fragment == tag[:length].lower():
                return tag
        return u''

    def random_node(self):
        node_id = random.choice(list(self.nodes))
        return node_id
    
    def replace_links(self, original_id, new_id='', new_project=''):
        if not new_id and not new_project:
            return None
        replacement = '>'+original_id
        if new_id:
            replacement = '>'+new_id
        if new_project:
            replacement = '{"'+new_project+'"}'+replacement
        patterns_to_replace = [
            r'\|.*?\s>{1,2}',   # replace title markers before anything else
            r'[^\}]>>',         # then node pointers
            r'[^\}]>' ]         # finally node links

        for filename in list(self.files):
            contents = self._full_file_contents(filename)
            new_contents = contents
            for pattern in patterns_to_replace:
                links = re.findall(pattern + original_id, new_contents)
                for link in links:
                    new_contents = new_contents.replace(link, replacement, 1)
            if contents != new_contents:
                self._set_file_contents(filename, new_contents)
                self.executor.submit(self._file_update, filename)

    def on_modified(self, 
            filename,
            watchdog=False):
    
        if watchdog:
            unlocked, lock_name = self.check_lock()
            if not unlocked:
                return (False, lock_name)
        do_not_update = [
            'index', 
            os.path.basename(self.path),
            self.settings['logfile'],
            ]

        for node_id in ['zzz','zzy']:
            if node_id in self.nodes:
               do_not_update.append(self.nodes[node_id].filename)
        filename = os.path.basename(filename)
        if filename in do_not_update or '.git' in filename:
            return (True,'')
        
        self._log_item('MODIFIED ' + filename +' - Updating the project object')
        return self.executor.submit(self._file_update, filename)

    def add_file(self, filename):
        self.executor.submit(self._parse_file, filename) 
        return self.executor.submit(self._update)

    def remove_file(self, filename):
        self._remove_file(filename) 
        return self.executor.submit(self._update)
         
    def _file_update(self, filename):
        rewritten_contents = self._rewrite_titles(filename)
        modified_files = []
        if rewritten_contents:
            self._set_file_contents(filename, rewritten_contents)
            modified_files.append(filename)     
        self._parse_file(filename, re_index=True)
        return self._update(modified_files=modified_files)
    
    def get_file_name(self, node_id):
        if node_id in self.nodes:
            return self.nodes[node_id].filename
        return None

    def setup_logger(self, name, log_file, level=logging.INFO):
        if not os.path.exists(os.path.join(self.path, log_file)):
            with open(os.path.join(self.path, log_file), "w") as f:
                f.write('URTEXT LOG')
                f.close()
        formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
        if not os.path.exists(log_file):
            with open(log_file, 'w', encoding='utf-8') as theFile:
                theFile.close()
        logger = logging.getLogger(name)
        handler = logging.FileHandler(log_file, mode='a')
        handler.setFormatter(formatter)
        logger.setLevel(level)
        logger.addHandler(handler)
        return logger




class NoProject(Exception):
    """ no Urtext nodes are in the folder """
    pass

class PickledUrtextProject:

    def __init__(self, project):
        
        self.nodes = project.nodes
        self.files = project.files
        self.tagnames = project.tagnames
        self.settings = project.settings
        self.dynamic_nodes = project.dynamic_nodes
        self.alias_nodes = project.alias_nodes
        pickle.dump( self, open( os.path.join(project.path, "save.p"), "wb" ) )

""" 
Helpers 
"""


def build_metadata(tags, one_line=False):
    """ Note this is a method from node.py. Could be refactored """

    if one_line:
        line_separator = '; '
    else:
        line_separator = '\n'
    new_metadata = '/-- '
    if not one_line: 
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
def creation_date(path_to_file):
    """
    Try to get the date that a file was created, falling back to when it was
    last modified if that isn't possible.
    See http://stackoverflow.com/a/39501288/1709587 for explanation.
    """
    if platform.system() == 'Windows':
        return datetime.datetime.fromtimestamp(os.path.getctime(path_to_file))
    else:
        stat = os.stat(path_to_file)
        try:
            return datetime.datetime.fromtimestamp(stat.st_birthtime)
        except AttributeError:
            # We're probably on Linux. No easy way to get creation dates here,
            # so we'll settle for when its content was last modified.
            return datetime.datetime.fromtimestamp(stat.st_mtime)

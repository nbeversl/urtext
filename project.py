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
import pprint

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
import diff_match_patch as dmp_module
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

functions = trees_functions
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

        self.async = True # development
        self.path = path
        self.log = None
        self.nodes = {}
        self.files = {}
        self.keynames = {}
        self.navigation = []  # Stores, in order, the path of navigation
        self.nav_index = -1  # pointer to the CURRENT position in the navigation list
        self.to_import = []
        self.settings_initialized = False
        self.dynamic_nodes = []  # { target : definition, etc.}
        self.dynamic_meta = {} # source_id : [ target_id, ... ]
        self.compiled = False
        self.alias_nodes = []
        self.ix = None
        self.loaded = False
        self.other_projects = [] # propagates from UrtextProjectList, permits "awareness" of list context
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.aux_executor = concurrent.futures.ThreadPoolExecutor(max_workers=10)
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
            'console_log': True,
            'google_auth_token' : 'token.json',
            'google_calendar_id' : None,
            'timezone' : ['UTC'],
            'search_index' : ['yes'],
            'always_oneline_meta' : True,
            'format_string': '$title\n-\n',
        }
        self.default_timezone = None
        self.title = self.path # default
        
        self._initialize_project(import_project=import_project, init_project=init_project)

        self.log = self.setup_logger('urtext_log', 'urtext_log.txt')

        if not exists_in(os.path.join(self.path, "index"), indexname="urtext"):
            if not os.path.exists(os.path.join(self.path, "index")):
                os.mkdir(os.path.join(self.path, "index"))
            schema = Schema(
                title=TEXT(stored=True),
                path=ID(unique=True, stored=True),
                content=TEXT(stored=True, analyzer=StandardAnalyzer()))
            create_in(os.path.join(self.path, "index"), schema, indexname="urtext")
        
        if not os.path.exists(os.path.join(self.path, "history")):
            os.mkdir(os.path.join(self.path, "history"))

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
        for node_id in self.nodes:  
            self._parse_meta_dates(node_id, initial=True)
        
        self.access_history = self._get_access_history()

        self._update()
            
    def _node_id_generator(self):
        chars = [
            '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'a', 'b', 'c',
            'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p',
            'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z'
        ]
        return itertools.product(chars, repeat=3)


    def _assign_node_parent_title(self):
        """
        Only has to be called once on project init
        """

        for node_id in self.nodes:
            self.nodes[node_id].parent_project = self.title

    def _parse_file(self, filename):
        """
        Parses a single file into the project.
        Returns None if successful, or a list of duplicate nodes found
        if duplicate nodes were found.
        FUTURE: Should be cleaned up. Currently returns None, False or list.
        """
        if self._filter_filenames(os.path.basename(filename)) == None:
            return

        search_index = None
        if self.settings['search_index'][0] == 'yes':
            search_index=self.ix
        
        already_in_project = False
        old_hash = None
        if os.path.basename(filename) in self.files:
            already_in_project = True
            old_hash = self.files[filename].hash

        """
        Parse the file
        """
        new_file = UrtextFile(
            os.path.join(self.path, filename), 
            previous_hash=old_hash,

            # temporarily disable search index.
            # too many freaking problems.
            #search_index=search_index
            )
        
        if not new_file.changed:
            return False

        if not new_file.is_parseable: 
            if already_in_project:
                self._log_item('Unable to re-parse '+filename+ ', dropping it from the project.')
                return False
            self.to_import.append(filename)

        # clear all node_id's defined from this file since the file has changed
        self._remove_file(os.path.basename(filename))
        """
        Check the file for duplicate nodes
        """
        duplicate_nodes = self._check_file_for_duplicates(new_file)
        if duplicate_nodes:
            """ return list of duplicate nodes if duplicate nodes """
            return duplicate_nodes
        """
        re-add the filename and all its nodes to the project
        """
        self.files[new_file.basename] = new_file  

        for node_id in new_file.nodes:
            self._add_node(new_file.nodes[node_id])
        """
        If this is not the initial load of the project, parse the timestamps in the file
        """
        if self.compiled:
            for node_id in new_file.nodes:
                self._parse_meta_dates(node_id)
        
        self._set_tree_elements(new_file.basename)

        for node_id in new_file.nodes:
            self._rebuild_node_meta(node_id)

        """ returns None if successful """
        return None

    def _check_file_for_duplicates(self, file_obj):
        duplicate_nodes = {}
        for node_id in file_obj.nodes:
            duplicate_filename = self._is_duplicate_id(node_id, file_obj.filename)
            if duplicate_filename:
                duplicate_nodes[node_id] = duplicate_filename

        if duplicate_nodes:
            self._log_item('Duplicate node ID(s) found in '+file_obj.filename)
            for node_id in duplicate_nodes:
                self._log_item(''.join(['ID >',node_id,' exists in ',duplicate_nodes[node_id]]))
            return duplicate_nodes

        return False

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
                    self._log_item('File ' + definition.target_file +
                                  ' has duplicate definition in >' + new_node.id +
                                  '. Keeping the definition in >' +
                                  defined + '.')
                else:
                    self.dynamic_nodes.append(definition)

        if len(new_node.metadata.get_meta_value('ID')) > 1:
            self._log_item('Multiple ID tags in >' + new_node.id +
                          ', '+', '.join(new_node.metadata.get_meta_value('ID'))+' ( using the first one found.')
        
        new_node.parent_project = self.title

        self.nodes[new_node.id] = new_node
        if new_node.project_settings:
            self._get_settings_from(new_node)

    def _parse_meta_dates(self, node_id, initial=False):
        """ Parses dates (requires that timestamp_format already be set) """

        for entry in self.nodes[node_id].metadata.entries:
            if entry.dtstring:
                dt_stamp = self._date_from_timestamp(entry.dtstring)
                if dt_stamp:
                    entry.dt_stamp = dt_stamp
                    if entry.keyname == 'timestamp':
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


    def _get_metadata_list(self, keys=[]):
        """ Refreshes the Metadata List file """

        if not keys:
            keys = sorted([
                k for k in self.keynames
                if k.lower() not in ['defined in', 'id', 'timestamp', 'index']
            ])

        root = Node('Metadata Keys')
        for key in keys:
            s = Node(key)
            s.parent = root
            for value in sorted(self.keynames[key]):
                t = Node(value)
                t.parent = s
                if value in self.keynames[key]:
                    for node_id in sorted(self.keynames[key][value]):
                        if node_id in self.nodes:
                            n = Node(self.nodes[node_id].title + ' >' +
                                     node_id)
                            n.parent = t
                        else: # debugging
                            print(node_id+ ' WAS LOST (DEBUGGING)')
                
        contents = []           
        for pre, _, node in RenderTree(root):
            contents.append("%s%s\n" % (pre, node.name))
            
        return ''.join(contents)

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
        with open(os.path.join(self.path, filename), 'r', encoding='utf-8') as theFile:
            file_contents = theFile.read()
            theFile.close()
        return file_contents

    def _set_file_contents(self, filename, contents):
        with open(os.path.join(self.path, filename), 'w', encoding='utf-8') as theFile:
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
        contents += "/-- id:" + self.next_index() + '\n'
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

                # remove this node's dynamic definitions
                for index, definition in enumerate(self.dynamic_nodes):
                    if definition.source_id == node_id:
                        del self.dynamic_nodes[index]

                # remove the node's metadata from the project
                self._unbuild_node_meta(node_id)

                # remove the dynamic tags defined by TAG_ALL()
                # (also rebuilds the meta for the target nodes)
                self._remove_sub_tags(node_id)
                
                del self.nodes[node_id]

            del self.files[filename]

        return None

    def _unbuild_node_meta(self, node_id):
        
        for keyname in list(self.keynames):

            for value in list(self.keynames[keyname]):

                #  ( in case it's been removed during the iteration ): 
                if value not in self.keynames[keyname]:  
                    continue

                if node_id in self.keynames[keyname][value]:
                    self.keynames[keyname][value].remove(node_id)
                
                # delete the key if it's empty
                if not len(self.keynames[keyname][value]):
                    del self.keynames[keyname][value] 

    def delete_file(self, filename):
        """
        Deletes a file, removes it from the project,
        and returns a future of modified files.
        """
        filename = os.path.basename(filename)
        node_ids = list(self.files[filename].nodes)
        self._remove_file(filename)
        os.remove(os.path.join(self.path, filename))
        future = self.executor.submit(self._update)
        for node_id in node_ids:
            while node_id in self.navigation:
                index = self.navigation.index(node_id)
                del self.navigation[index]
                if self.nav_index > index: # >= ?
                    self.nav_index -= 1
        
        return future

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
    
    def new_file_node(self, 
        date=None, 
        metadata = {}, 
        node_id=None,
        one_line=None
        ):
        
        """ add a new FILE-level node programatically """

        if date == None:
            date = datetime.datetime.now()

        if one_line == None:
            one_line = self.settings['always_oneline_meta']

        if not node_id:
            node_id = self.next_index()   
        metadata['id'] = node_id
        metadata['timestamp'] = self.timestamp(date)
        metadata['from'] = platform.node()
        metadata_block = UrtextNode.build_metadata(metadata, one_line=one_line)
        contents = '\n\n\n' +metadata_block
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
            one_line=None,
            include_timestamp=False):
        
        if contents == '':
            contents = ' '
        
        if one_line == None:
            one_line = self.settings['always_oneline_meta']
            
        node_id = self.next_index()
        metadata['id']=node_id
        if include_timestamp:
            if date == None:
                date = datetime.datetime.now()
            metadata['timestamp'] = self.timestamp(date)
        new_node_contents = "{{ " + contents 
        metadata_block = UrtextNode.build_metadata(metadata, one_line=one_line)
        new_node_contents += metadata_block + " }}"
        metadata={}
        return (new_node_contents, node_id)

    def insert_interlinks(self, node_id, one_line=True):
        new_node = self.add_inline_node()
        insertion = new_node[0]
        new_node_id = new_node[1]
        dynamic_def =   '[[ id('+ new_node_id +'); '
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
        metadata_block = UrtextNode.build_metadata(metadata, one_line=True)
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
        if not self.navigation:
            return None
        
        # return if the index is already at the end
        if self.nav_index == len(self.navigation) - 1:
            self._log_item('project index is at the end.')
            return None
        
        self.nav_index += 1
       
        return self.navigation[self.nav_index]


    def nav_new(self, node_id):

        # don't re-remember consecutive duplicate links
        if -1 < self.nav_index < len(self.navigation) and node_id == self.navigation[self.nav_index]:
            return

        # add the newly opened file as the new "HEAD"
        self.nav_index += 1
        del self.navigation[self.nav_index:]
        self.navigation.append(node_id)
        self.executor.submit(self._push_access_history, node_id)
         
    def nav_reverse(self):
        if not self.navigation:
            return None

        if self.nav_index == 0:
            self._log_item('project index is already at the beginning.')
            return None

        self.nav_index -= 1
        last_node = self.navigation[self.nav_index]
        
        return last_node

    def nav_current(self):

        if self.navigation:
            return self.navigation[self.nav_index]
        alternative = self.get_home()
        if not alternative:
            alternative = self.random_node()
        return alternative

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
            if not self.nodes[node_id].index:
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
            if self.nodes[node_id].index:
                indexed_nodes_list.append([
                    node_id,
                    self.nodes[node_id].index
                ])
        sorted_indexed_nodes = sorted(indexed_nodes_list,
                                      key=lambda item: item[1])
        for index, node in enumerate(sorted_indexed_nodes):
            sorted_indexed_nodes[index] = node[0] 
        return sorted_indexed_nodes

    def all_nodes(self):
        all_nodes = self.indexed_nodes()
        all_nodes.extend(self.unindexed_nodes())
        return all_nodes

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

        filename = os.path.basename(filename)
        if filename in self.files:
            for node_id in self.files[filename].nodes:
                if self._is_in_node(position, node_id):
                    return node_id
        else:
            return None
        return None

    def get_link(self, string, position=0):
        """ 
        Given a line of text passed from an editor, 
        opens a web link, file, or returns a node,
        in that order.
        Returns a tuple of type and success/failure or node ID
        """
        
        link = None
        
        # first try looking around where the cursor is positioned
        for index in range(0, 4):
            if re.search(node_link_regex, string[position - index:position - index + 5]):
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

        if link:

            node_id = link.split(':')[0].strip('>')
            if node_id.strip() in self.nodes:
                file_position = self.nodes[node_id].ranges[0][0]
                return ('NODE', node_id, file_position)
            else:
                self._log_item('Node ' + node_id + ' is not in the project')
                return None


        url_scheme = re.compile('http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\), ]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')
        file_path = re.compile('(\\\\?([^\\/]*[\\/])*)([^\\/]+)')

        if re.search(url_scheme, string[position:]):
            url = re.search(url_scheme, string).group(0)
            return ('HTTP', url)

        
        if re.search(file_path, string):
            file_link = re.search(file_path, string).group(0)
            return ('FILE', os.path.join(self.path, file_link))

        self._log_item('No node ID, web link, or file found on this line.')
        return None

    def build_timeline(self, nodes):
        """ Given a list of nodes, returns a timeline """
        return timeline(self, nodes)

    def _is_duplicate_id(self, node_id, filename):
        """ private method to check if a node id is already in the project """
        if node_id in self.nodes:
            return self.nodes[node_id].filename
        return False

    def _log_item(self, item):
        if self.log:
            self.log.info(item + '\n')
            if self.settings['console_log']:          
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
        single_values = [
            'format_string',
            'home',
            'project_title',
            'logfile',
            'google_auth_token',
            'google_calendar_id',
        ]
        single_boolean_values = [
            'always_oneline_meta',
            'preformat',
            'console_log',
        ]

        for entry in node.metadata.entries:
            key = entry.keyname
            values = entry.values
           
            if key == 'project_title':
                # this one sets a project object property, not the settings dict
                self.title = values[0]
                continue

            if key == 'timestamp_format':
                formats = []
                for value in values:
                    if value:
                        formats.append(value)
                formats.extend(self.settings['timestamp_format'])
                self.settings['timestamp_format'] = formats
                continue

            if key == 'filenames':
                #always a list
                self.settings['filenames'] = values
                continue

            if key in single_boolean_values:
                self.settings[key] = True if values[0].lower() == 'true' else False
                continue

            if key in single_values:
                self.settings[key] = values[0]
                continue

            if key not in self.settings:
                self.settings[key] = []                                

            self.settings[key].extend(values)

        self.default_timezone = timezone(self.settings['timezone'][0])

    def get_home(self):
        return self.settings['home']

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

    def complete_meta_value(self, fragment):
        fragment = fragment.lower().strip()
        length = len(fragment)

        for keyname in self.keynames:
            for value in keyname:
                if fragment == value[:length].lower():
                    return (keyname, value)
        return u''        

    def get_all_meta_pairs(self):
        pairs = []
        ignore = [ 'id', 'timestamp' ]
        for keyname in self.keynames: 
            if keyname.lower() in ignore:
                continue
            for value in self.keynames[keyname]:
                meta_string = ''.join([keyname, ': ', value ])
                if meta_string not in pairs:
                    pairs.append(meta_string)
        return pairs

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

    def on_modified(self, filename):
    
        do_not_update = [
            'index', 
            'history',
            os.path.basename(self.path),
            self.settings['logfile'],
            ]
        
        filename = os.path.basename(filename)
        if filename in do_not_update or '.git' in filename:
            return (True, '')
        
        self._log_item('MODIFIED ' + filename +' - Updating the project object')

        if self.async:
            return self.executor.submit(self._file_update, filename)
        return self._file_update(filename)
    
    def _file_update(self, filename):
        modified_files = []
        rewritten_contents = self._rewrite_titles(filename)
        if rewritten_contents:
            self._set_file_contents(filename, rewritten_contents)
            modified_files.append(filename)

        # re-parse the file
        any_duplicate_ids = self._parse_file(filename)

        #update the project
        return self._update(modified_files=modified_files)

    def _update(self, 
        compile_project=True,
        modified_files=None
        ):
        
        """ 
        Main method to keep the project updated. 
        Should be called whenever file or directory content changes
        """
        if modified_files is None:
            modified_files = []

        modified_files.extend(self._check_for_new_files())

        if compile_project:
            modified_files = self._compile(modified_files=modified_files)
            self.compiled = True

        if self.ix:
            self.ix.refresh()

        return modified_files

    def _check_for_new_files(self):
        filelist = os.listdir(self.path)
        new_files = []
        for file in filelist:
            if self._filter_filenames(file) == None:
                continue
            if os.path.basename(file) not in self.files:
                duplicate_node_ids = self._parse_file(file)
                if not duplicate_node_ids:
                    new_files.append(os.path.basename(file))
        for filename in self.files:
            if filename not in filelist:
                self.log(filename+' no longer seen in project path. Dropping it from the project.')
                self.remove_file(filename)
        return new_files

    def add_file(self, filename):
        """ 
        parse syncronously for now, so we can raise an exception
        if moving files between projects.
        """
        any_duplicate_ids = self._parse_file(filename)
        
        if any_duplicate_ids:
            print('File moved but not added to destination project. Duplicate Nodes IDs shoudld be printed above.')
            self.log('File moved but not added to destination project. Duplicate Nodes IDs shoudld be printed above.')
            raise DuplicateIDs()
        else:
            return self.executor.submit(self._update)

    def remove_file(self, filename):
        self._remove_file(filename) 
        return self.executor.submit(self._update)
    
    def get_file_name(self, node_id, absolute=False):
        filename = None
        if node_id in self.nodes:
            filename = self.nodes[node_id].filename
        else:
            return None
        if absolute:
            filename = os.path.join(self.path, filename)
        return filename

    def setup_logger(self, name, log_file, level=logging.INFO):
        log_file = os.path.join(self.path, log_file)
        if not os.path.exists(log_file):
            with open(log_file, "w") as f:
                f.write('URTEXT LOG')
                f.close()
        formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
        logger = logging.getLogger(name)
        handler = logging.FileHandler(log_file, mode='a')
        handler.setFormatter(formatter)
        logger.setLevel(level)
        logger.addHandler(handler)
        return logger

    """
    File History
    """
    def snapshot_diff(self, filename, contents):
        dmp = dmp_module.diff_match_patch()
        filename = os.path.basename(filename)
        if filename not in self.files:
            return None
        now = int(time.time())
        history_file = filename.replace('.txt','.pkl')
        file_history = self.get_history(filename)
        if not file_history:
            file_history = {}
            file_history[now] = contents
            with open( os.path.join(self.path, 'history', history_file), "wb") as f:
                pickle.dump(file_history, f )
            return
        else:

            latest_history = self.apply_patches(file_history)
            if contents != latest_history:
                #print(latest_history)
                file_history[now] = dmp.patch_make(latest_history, contents)
                with open( os.path.join(self.path, 'history', history_file), "wb") as f:
                    pickle.dump(file_history, f )

    def apply_patches(self, history, distance_back=0):
        dmp = dmp_module.diff_match_patch()
        timestamps = sorted(history.keys())
        original = history[timestamps[0]]
        for index in range(1,len(timestamps)-distance_back):
            next_patch = history[timestamps[index]]
            original = dmp.patch_apply(next_patch, original)[0]

        return original

    def get_version(self, filename, distance_back=0):
        history = self.get_history(filename)
        version = self.apply_patches(history, distance_back)
       
        return version

    def get_history(self, filename):
        filename = os.path.basename(filename)
        history_file = os.path.join(self.path, 'history', filename.replace('.txt','.pkl'))
        if os.path.exists(history_file):
            with open(history_file, "rb") as f:
                file_history = pickle.load(f)
            return file_history
        return None

    def most_recent_history(self, history):
        times = sorted(history.keys())
        return times[-1]

    """
    Access History
    """

    def _get_access_history(self):

        accessed_file = os.path.join(self.path, "history", "URTEXT_accessed.json")
        if os.path.exists(accessed_file):
            with open(accessed_file,"r") as f:
                try:
                    contents = f.read()
                    f.close()
                    if contents:
                        access_history = json.loads(contents)
                        return access_history
                except EOFError as error:
                    print(error)
        return {}

    def _save_access_history(self):
        accessed_file = os.path.join(self.path, "history", "URTEXT_accessed.json")
        with open(accessed_file,"w") as f:
            f.write(json.dumps(self.access_history))
            f.close()

    def _show_access_history(self, number):
        access_times = [int(i) for i in self.access_history.keys()]
        dates = sorted(access_times, reverse=True)
        display = ''
        if number == -1 or number >= len(self.access_history):
             number = len(self.access_history) - 1
        index = 0
        while index < number:
            if str(dates[index]) in self.access_history: 
                node = self.access_history[str(dates[index])]
                if node in list(self.nodes):
                    date = datetime.datetime.fromtimestamp(int(dates[index]))
                    date = self.default_timezone.localize(date) 
                    display += date.strftime(self.settings['timestamp_format'][0])
                    display += ' ' + self.nodes[node].title + ' >'+node + '\n'
            index += 1
        return display
        
    def _push_access_history(self, node_id, duplicate=False):

        if not duplicate:
            for access_time in list(self.access_history):
                if node_id == self.access_history[access_time]:
                    del self.access_history[access_time]
        self.access_history[int(time.time())] = node_id
        self._save_access_history()

    def is_in_export(self, filename, position):

        node_id = self.get_node_id_from_position(filename, position)
        if not node_id:
            return False
        export_points = self.nodes[node_id].export_points
        if export_points:
            for export_range in export_points:
                if position in range(export_range[0],export_range[1]):
                    # returns tuple (id, starting_position)
                    return export_points[export_range]
        return False

    def get_file_and_position(self, node_id):
        filename = self.get_file_name(node_id, absolute=True)
        position = self.nodes[node_id].start_position()
        return filename, position

    """
    Calendar
    """
    def export_to_ics(self):
        c = Calendar()
        for node_id in self.nodes:
            e = Event()
            urtext_node = self.nodes[node_id]
            e.name = urtext_node.title
            e.begin = urtext_node.date.isoformat()
            c.add(e)
        with open('my.ics', 'w') as f:
            f.write(c)

    
class NoProject(Exception):
    """ no Urtext nodes are in the folder """
    pass

class DuplicateIDs(Exception):
    """ duplicate IDS """
    def __init__(self):
        pass

""" 
Helpers 
"""



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

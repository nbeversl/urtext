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
import json
import os
import random
import time
import sys
from time import strftime
import concurrent.futures
from pytz import timezone
from anytree import Node, PreOrderIter, RenderTree

from urtext.file import UrtextFile
from urtext.node import UrtextNode, strip_contents
from urtext.compile import compile_functions
from urtext.meta_handling import metadata_functions

from urtext.dynamic import UrtextDynamicDefinition
from urtext.timestamp import date_from_timestamp, default_date, UrtextTimestamp
from urtext.utils import strip_backtick_escape
from urtext.directive import UrtextDirective
from urtext.action import UrtextAction
from urtext.extension import UrtextExtension


from importlib import import_module

node_pointer_regex = r'>>[0-9,a-z]{3}\b'
title_marker_regex = r'\|.*?\s>{1,2}[0-9,a-z]{3}\b'
node_id_regex = r'\b[0-9,a-z]{3}\b'
node_link_regex = re.compile(r'(\|?[^\|]*?[^f]>{1,2})(\w{3})(\:\d{1,10})?')
action_regex = re.compile(r'>>>([A-Z_]+)\((.*?)\)', re.DOTALL)
editor_file_link_regex = re.compile('(f>{1,2})([^;]+)')
url_scheme = re.compile(r'http[s]?:\/\/(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\), ]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')

functions = compile_functions
functions.extend(metadata_functions)

def all_subclasses(cls):
    return set(cls.__subclasses__()).union(
        [s for c in cls.__subclasses__() for s in all_subclasses(c)])

for i in os.listdir(os.path.join(os.path.dirname(__file__),'extensions')):
    if '.py' in i:
        i = os.path.basename(os.path.splitext(i)[0])
        import_module('urtext.extensions.'+i)

for i in os.listdir(os.path.join(os.path.dirname(__file__),'directives')):
    if '.py' in i:
        i = os.path.basename(os.path.splitext(i)[0])
        import_module('urtext.directives.'+i)

for i in os.listdir(os.path.join(os.path.dirname(__file__),'actions')):
    if '.py' in i:
        i = os.path.basename(os.path.splitext(i)[0])
        import_module('urtext.actions.'+i)


def add_functions_as_methods(functions):
    def decorator(Class):
        for function in functions:
            setattr(Class, function.__name__, function)
        return Class
    return decorator
    
all_extensions = all_subclasses(UrtextExtension)
all_directives = all_subclasses(UrtextDirective)
all_actions = all_subclasses(UrtextAction)

single_values = [
    'home',
    'project_title',
    'node_date_keyname',
    'log_id',
    'timestamp_format',
    'device_keyname',
    'breadcrumb_key',
    'title',
    'id',
    'hash_key',
    'file_node_leading_contents',
    'filename_datestamp_format',
    'timezone' ]

single_boolean_values = [
    'always_oneline_meta',
    'preformat',
    'console_log',
    'atomic_rename',
    'autoindex',
    'keyless_timestamp',
    'file_node_timestamp',
    'inline_node_timestamp',
    'contents_strip_outer_whitespace',
    'contents_strip_internal_whitespace',]

replace = [
    'file_index_sort',
    'filenames',
    'node_browser_sort',
    'tag_other',
    'filename_datestamp_format' ]




@add_functions_as_methods(functions)
class UrtextProject:
    """ Urtext project object """

    urtext_file = UrtextFile
    urtext_node = UrtextNode
    

    def __init__(self,
                 path,
                 rename=False,
                 recursive=False,
                 import_project=False,
                 init_project=False):
        
        self.is_async = True 
        #self.is_async = False # development only
        self.path = path
        self.reset_settings()
        self.nodes = {}
        self.files = {}
        self.navigation = []  # Stores, in order, the path of navigation
        self.nav_index = -1  # pointer to the CURRENT position in the navigation list
        self.to_import = []
        self.extensions = {}
        self.actions = {}
        self.directives = {}
        self.compiled = False
        self.other_projects = [] # propagates from UrtextProjectList, permits "awareness" of list context
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=50)
        self.messages = {}
        self.default_timezone = timezone('UTC')
        self.title = self.path # default
        if self.is_async:
            future = self.executor.submit(self._initialize_project,
                    import_project=import_project, 
                    init_project=init_project)
        else:    
            self._initialize_project(
                 import_project=import_project, 
                 init_project=init_project)

        # TODO -- node date timezones have to be localized
        # do this from UrtextNode.date() method

    def _initialize_project(self, 
        import_project=False, 
        init_project=False):

        for c in all_extensions:
            for n in c.name:
                self.extensions[n] = c(self)

        for c in all_actions:
            for n in c.name:
                self.actions[n] = c

        for c in all_directives:
            for n in c.name:
                self.directives[n] = c

        for file in os.listdir(self.path):
            self._parse_file(file, import_project=import_project)

        if import_project:
            for file in self.to_import:
                self.import_file(file)
        
        self.default_timezone = timezone(self.settings['timezone'])
        
        if self.nodes == {}:
            if init_project == True:
                self._log_item('Initalizing a new Urtext project in ' + self.path)
                self.new_file_node()
            else:
                raise NoProject('No Urtext nodes in this folder.')

        elif init_project:
            print('Urtext project already exists here.')
            return None            
        
        for node_id in self.nodes:
            self.nodes[node_id].metadata.convert_hash_keys()

        #necessary?
        for node_id in self.nodes:
            for e in self.nodes[node_id].metadata.dynamic_entries:                
                self._add_sub_tags( 
                    self.nodes[node_id].tree_node, 
                    self.nodes[node_id].tree_node, 
                    e)
    
        self._compile()
        self.compiled = True
        print('"'+self.title+'" compiled from '+self.path )
    
    def reset_settings(self):

        self.settings = {  
            'home': None,
            'timestamp_format':'%a., %b. %d, %Y, %I:%M %p', 
            'use_timestamp': [ 'updated','timestamp', 'inline-timestamp', '_oldest_timestamp', '_newest_timestamp'],
            'filenames': ['PREFIX', 'title'],
            'filename_datestamp_format':'%m-%d-%Y',
            'console_log': True,
            'timezone' : 'UTC',
            'always_oneline_meta' : False,
            'strict':False,
            'node_date_keyname' : 'timestamp',
            'log_id': '',
            'numerical_keys': ['_index' ,'index'],
            'atomic_rename' : False,
            'tag_other': [],
            'device_keyname' : '',
            'breadcrumb_key' : '',
            'new_file_node_format' : '$datestamp $id',
            'new_file_line_pos' : 2,
            'keyless_timestamp' : True,
            'inline_node_timestamp' :False,
            'file_node_timestamp' : True,
            'file_node_leading_contents': '',
            'hash_key': '#',
            'contents_strip_outer_whitespace' : True,
            'contents_strip_internal_whitespace' : True,
            'node_browser_sort' : ['_oldest_timestamp'],
            'open_with_system' : ['pdf'],
            'exclude_from_star': [
                'title', 
                '_newest_timestamp', 
                '_oldest_timestamp', 
                '_breadcrumb',
                 'def'],
            'file_index_sort': ['_oldest_timestamp'],
            'case_sensitive': [
                'title',
                'notes',
                'comments',
                'project_title',
                'timezone',
                'timestamp_format',
                'filenames',
                'weblink',
                'timestamp',],
        }
    def _node_id_generator(self):
        chars = [
            '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'a', 'b', 'c',
            'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p',
            'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z'
        ]
        return itertools.product(chars, repeat=3)


    def get_file_position(self, node_id, position): 
        if node_id in self.nodes:
            node_length = 0
            offset_position = position
            for r in self.nodes[node_id].ranges:
                range_length = r[1] - r[0]
                node_length += range_length
                if position < node_length:
                    break
                offset_position -= range_length
            file_position = r[0] + offset_position + 1
            return file_position
        return None

    def _parse_file(self, 
            filename, 
            import_project=False):
    
        filename = os.path.basename(filename)
        if self._filter_filenames(filename) == None:
            return

        new_file = self.urtext_file(os.path.join(self.path, filename), self)
                
        if not new_file.is_parseable:
            self.to_import.append(filename)
            return

        self._remove_file(filename)
 
        duplicate_nodes = self._check_file_for_duplicates(new_file)
        if duplicate_nodes:
            return duplicate_nodes
 
        self.files[new_file.basename] = new_file  
        for node_id in new_file.nodes:
            self._add_node(new_file.nodes[node_id])
    
        for ext in self.extensions:
             self.extensions[ext].on_file_modified(filename)
              
        for node_id in new_file.nodes:
            for dd in self.dynamic_defs(target=node_id):
                self.nodes[dd.target_id].dynamic = True
            for e in self.nodes[node_id].metadata.dynamic_entries:
                self._add_sub_tags( self.nodes[node_id].tree_node, 
                    self.nodes[node_id].tree_node, 
                    e)
            # for child in self.nodes[node_id].tree_node.children:
            #     child_node = child.name.strip('ALIAS')
            #     self._reassign_sub_tags(child_node)
        
        # TODO: Needs optimization
        for node_id in list(self.nodes):
            for e in self.nodes[node_id].metadata.dynamic_entries:                
                self._add_sub_tags( 
                    self.nodes[node_id].tree_node, 
                    self.nodes[node_id].tree_node, 
                    e)
                
    def _check_file_for_duplicates(self, file_obj):

        duplicate_nodes = {}
        for node_id in file_obj.nodes:
            duplicate_filename = self._is_duplicate_id(node_id, file_obj.filename)
            if duplicate_filename:
                duplicate_nodes[node_id] = duplicate_filename

        if duplicate_nodes:
            basename = os.path.basename(file_obj.filename)
            if basename not in self.messages:
                self.messages[basename] = []    
            self.messages[basename].append('Duplicate node ID(s) found')

            messages = []
            for node_id in duplicate_nodes:
                messages.append(''.join([
                    'node ID >',
                    node_id,
                    ' exists in f>',
                    duplicate_nodes[node_id]]) )

            file_obj.write_errors( self.settings, messages=messages)
            return duplicate_nodes

        return False

    def _rewrite_titles(self, filename=None, contents=""):

        if contents:
            original_contents = contents
        elif filename:
            original_contents = self.files[filename]._get_file_contents()
        else:
            return
        new_contents = original_contents
        offset = 0        
        for match in re.finditer(title_marker_regex, new_contents):
            start = match.start() + offset
            end = match.end() + offset   
            match_contents = new_contents[start:end]
            node_id = match_contents[-3:]
            if node_id in self.nodes:
                title = self.nodes[node_id].title
            else:
                title = ' ? '
            bracket = '>'
            if re.search(node_pointer_regex, match_contents):
                bracket += '>'
            replaced_contents = ''.join([new_contents[:start],
                '| ', title, ' ', bracket, node_id,
                new_contents[end:]
                ])
            offset += len(replaced_contents) - len(new_contents)
            new_contents = replaced_contents
        if contents:
            return new_contents
        if "\n".join(new_contents.splitlines()) != "\n".join(original_contents.splitlines()):            
            print('YEP')
            print("OLD")
            print(original_contents)
            print("NEW")
            print(new_contents)
            self.files[filename]._set_file_contents(new_contents)
            return True
        return False

    def _target_id_defined(self, check_id):
        for nid in list(self.nodes):
            if nid in self.nodes and check_id in [t.target_id for t in self.nodes[nid].dynamic_definitions]:
                return nid

    def _target_file_defined(self, file):
        for nid in list(self.nodes):
            for e in self.nodes[nid].dynamic_definitions:
                for r in e.exports:
                    if file in r.to_files:
                        return nid

    """
    Parsing helpers
    """
    def _add_node(self, new_node):
        """ Adds a node to the project object """

        for definition in new_node.dynamic_definitions:
            
            if definition.target_id:
                defined = self._target_id_defined(definition.target_id)
                
                if defined and defined != new_node.id:

                    message = ''.join([ 'Node >', definition.target_id,
                                ' has duplicate definition in >' , new_node.id ,
                                  '. Keeping the definition in >',
                                  defined, '.'
                                  ])

                    self.messages[new_node.filename].append(message)
                    self._log_item(message)

                    definition = None
                       
        if len(new_node.metadata.get_values('ID')) > 1:
            message = ''.join([ 
                    'Multiple ID tags in >' , new_node.id ,': ',
                    ', '.join(new_node.metadata.get_first_value('ID')),' - using the first one found.'])
            if new_node.filename not in self.messages: #why?
                self.messages[new_node.filename] = []
            self.messages[new_node.filename].append(message)
            self._log_item(message)

        new_node.parent_project = self.title
        new_node.project = self
        self.nodes[new_node.id] = new_node

        if new_node.contains_project_settings:
            self._get_settings_from(new_node)            
        
    def get_source_node(self, filename, position):
        if filename not in self.files:
            return None, None
        exported_node_id = self.get_node_id_from_position(filename, position)
        points = self.nodes[exported_node_id].export_points
        if not points:
            return None, None
        node_start_point = self.nodes[exported_node_id].ranges[0][0]

        indexes = sorted(points)
        for index in range(0, len(indexes)):
            if position >= indexes[index] and position < indexes[index+1]:
                node, target_position = self.nodes[exported_node_id].export_points[indexes[index]]
                offset = position - indexes[index]
                return node, target_position+offset

    def _set_node_contents(self, node_id, contents, parse=True):
        """ 
        project-aware alias for the Node set_content() method 
        returns filename if contents has changed.
        """
        if parse:
            self._parse_file(self.nodes[node_id].filename)
        if node_id in self.nodes:
            if self.nodes[node_id].set_content(contents, preserve_metadata=True):
                self._parse_file(self.nodes[node_id].filename)
                if node_id in self.nodes:
                    return self.nodes[node_id].filename
        return False

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
        contents += "@" + self.next_index() + '\n'
        if 'node_date_keyname' in self.settings:
            contents += self.settings['node_date_keyname']+'::'
        else:
            contents += '\n'
        contents += self.timestamp(date) + '\n'
        contents += 'imported::' + self.timestamp(now) + '\n'

        full_file_contents += contents

        self.files[filename].set_file_contents(full_file_contents)

        return self._parse_file(filename)

 
    """
    Removing and renaming files
    """
    def _remove_file(self, filename):
       
        if filename in self.files:
            
            for dd in self.dynamic_defs():
                for op in dd.operations:
                    op.on_file_removed(filename)

            for node_id in self.files[filename].nodes:    
                if node_id not in self.nodes:
                    continue             
                self._remove_sub_tags(node_id)                
                del self.nodes[node_id]

            del self.files[filename]

    def delete_file(self, filename, open_files=[]):
        if self.is_async:
            return self.executor.submit(self._delete_file, filename, open_files=open_files)
        else:
            return self._delete_file(filename, open_files=open_files)

    def _delete_file(self, filename, open_files=[]):
        """
        Deletes a file, removes it from the project,
        and returns a future of modified files.
        """
        filename = os.path.basename(filename)
        if filename in self.files:
            for node_id in list(self.files[filename].nodes):
                while node_id in self.navigation:
                    index = self.navigation.index(node_id)
                    del self.navigation[index]
                    if self.nav_index >= index:
                        self.nav_index -= 1            
            self.remove_file(filename, is_async=False)
            os.remove(os.path.join(self.path, filename))
        
        if open_files:
            return self.on_modified(open_files)
        return []
    
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
        if not filename.endswith('.txt'):
            # FUTURE:
            # save and check these in an optional list of other extensions 
            # set from project_settings 
            return None
            
        return filename
    
    def new_file_node(self, 
        date=None, 
        contents=None,
        metadata = {}, 
        node_id=None,
        one_line=None
        ):
        
        if contents == None:
            contents = bytes(self.settings['file_node_leading_contents'], "utf-8").decode("unicode_escape")

        contents, node_id = self._new_node(
            date=date,
            contents=contents,
            metadata=metadata,
            node_id=node_id,
            include_timestamp=self.settings['file_node_timestamp'])
        
        filename = node_id + '.txt'
        with open(os.path.join(self.path, filename), "w") as f:
            f.write(contents)  
        self._parse_file(filename)
        return { 
                'filename':filename, 
                'id':node_id
                }

    def new_inline_node(self, 
        date=None, 
        metadata = {}, 
        node_id=None,
        contents='',
        one_line=None,
        ):

        contents, node_id = self._new_node(
            date=date,
            contents=contents,
            metadata=metadata,
            node_id=node_id,
            include_timestamp=self.settings['inline_node_timestamp'])

        return {
            'contents' : ''.join(['{ \n', contents, '}']),
            'id':node_id
        }
    
    def _new_node(self, 
            date=None, 
            contents='',
            node_id=None,
            metadata=None,
            one_line=None,
            include_timestamp=False):

        if one_line == None:
            one_line = self.settings['always_oneline_meta']
        
        if not node_id:
            node_id = self.next_index()

        if not metadata:
            metadata = {}

        if  self.settings['device_keyname']:
            metadata[self.settings['device_keyname']] = platform.node()

        metadata['id']=node_id

        new_node_contents = contents

        if include_timestamp:
            if date == None:
                date = datetime.datetime.now() 
            if self.settings['keyless_timestamp'] == True:
                new_node_contents += self.timestamp(date) + ' '
            elif self.settings['node_date_keyname']:
                metadata[self.settings['node_date_keyname']] = self.timestamp(date)

        new_node_contents += self.urtext_node.build_metadata(metadata, one_line=one_line)
        return new_node_contents, node_id

    def add_compact_node(self,  
            contents='', 
            metadata={},
        ):
            metadata['id']=self.next_index()
            metadata_block = self.urtext_node.build_metadata(metadata, one_line=True)
            return '•  '+contents + ' ' + metadata_block

    def dynamic_defs(self, target=None):
        dd = []
        for nid in list(self.nodes):
            if nid in self.nodes:
                if not target:
                    dd.extend([d for d in self.nodes[nid].dynamic_definitions if d])
                else:
                    dd.extend([d for d in self.nodes[nid].dynamic_definitions if d and d.target_id == target])
        return dd

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
        next_node = self.navigation[self.nav_index]
        self.visit_node(next_node)
        return next_node 

    def nav_new(self, node_id):
        if node_id in self.nodes:
            # don't re-remember consecutive duplicate links
            if -1 < self.nav_index < len(self.navigation) and node_id == self.navigation[self.nav_index]:
                return     
            # add the newly opened file as the new "HEAD"
            self.nav_index += 1
            del self.navigation[self.nav_index:]
            self.navigation.append(node_id)
            self.visit_node(node_id)
               
    def nav_reverse(self):
        if not self.navigation:
            return None

        if self.nav_index == 0:
            self._log_item('project index is already at the beginning.')
            return None

        self.nav_index -= 1
        last_node = self.navigation[self.nav_index]
        self.visit_node(last_node)
        return last_node

    def nav_current(self):
        if self.navigation and self.nav_index > -1:
            return self.navigation[self.nav_index]
        alternative = self.get_home()
        if not alternative:
            alternative = self.random_node()
        return alternative

    def all_nodes(self):

        def sort(nid, return_type=False):
            return self.nodes[nid].metadata.get_first_value(
                k, 
                use_timestamp=use_timestamp,
                return_type=return_type)

        remaining_nodes = list(self.nodes)
        sorted_nodes = []
        for k in self.settings['node_browser_sort']:
            use_timestamp= k in self.settings['use_timestamp']
            as_int = k in self.settings['numerical_keys']
            k = k.lower()

            node_group = [r for r in remaining_nodes if r in self.nodes and self.nodes[r].metadata.get_first_value(k)]
            for r in node_group:
                if use_timestamp:
                    self.nodes[r].display_meta = k + ': <'+  str(self.nodes[r].metadata.get_first_value(k, use_timestamp=use_timestamp))+'>'
                else:
                    self.nodes[r].display_meta = k + ': '+  str(self.nodes[r].metadata.get_first_value(k))
            node_group = sorted(node_group, key=lambda nid: sort(nid, return_type=True), reverse=k in self.settings['use_timestamp'] )
            sorted_nodes.extend(node_group)
            remaining_nodes = list(set(remaining_nodes) - set(node_group))
        sorted_nodes.extend(remaining_nodes)
        return sorted_nodes

    def all_files(self):
        files=list(self.files)
        prefix = 0
        sorted_files = []
        for k in self.settings['file_index_sort']:
            k = k.lower()
            use_timestamp= True if k in self.settings['use_timestamp'] else False
            file_group = [f for f in files if self.files[f].root_nodes and self.nodes[self.files[f].root_nodes[0]].metadata.get_first_value(k, use_timestamp=use_timestamp)]
            file_group = sorted(file_group, 
                key=lambda f:  self.nodes[self.files[f].root_nodes[0]].metadata.get_first_value(k, use_timestamp=use_timestamp),
                reverse=use_timestamp)
            sorted_files.extend(file_group)
            files = list(set(files) - set(sorted_files))
        sorted_files.extend(files)
        return sorted_files

    def root_nodes(self, primary=False):
        """
        Returns the IDs of all the root (file level) nodes
        """
        root_nodes = []        
        for filename in self.files:
            if not primary:
                root_nodes.extend(self.files[filename].root_nodes)
            else:
                if not self.files[filename].root_nodes:
                    self._log_item('DEBUGGING (project.py): No root nodes in f>'+filename)
                else:
                    root_nodes.append(self.files[filename].root_nodes[0])
        return root_nodes

    def get_node_id_from_position(self, filename, position):
        filename = os.path.basename(filename)
        if filename in self.files:
            for node_id in self.files[filename].nodes:
                for r in self.files[filename].nodes[node_id].ranges:
                    if position in range(r[0],r[1]+1): # +1 in case the cursor is in the last position of the node.
                        return node_id
        return None

    def get_links_to(self, to_id):
        return [i for i in self.nodes if to_id in self.nodes[i].links]
       
    def get_links_from(self, from_id):
        if from_id in self.nodes:
            return self.nodes[from_id].links
        return []

    def get_link(self, 
        string, 
        filename, 
        col_pos=0,
        file_pos=0):
        """ 
        Given a line of text passed from an editor, 
        opens a web link, file, or returns a node,
        in that order. Returns a tuple of type and success/failure or node ID
        """
        
        link = self.find_link(
            string, 
            filename, 
            col_pos=col_pos,
            file_pos=file_pos)

        if not link:
            return

        # work backwards along the line
        if not link['kind']:
            while col_pos > -1:
                link = self.find_link(
                    string[col_pos:], 
                    filename, 
                    col_pos=col_pos,
                    file_pos=file_pos)
                if link['kind']:
                    break
                col_pos -= 1

        if not link['kind']:
            if not self.compiled:
               return self._log_item('Project is still compiling')
            return self._log_item('No node ID, web link, or file found on this line.')

        if link['kind'] == 'NODE' and link['link'] not in self.nodes:
            if not self.compiled:
               return self._log_item('Project is still compiling')
            self._log_item('Node ' + link['link'] + ' is not in the project')
            return None

        return link

    def find_link(self, 
        string,
        filename, 
        col_pos=0,
        file_pos=0):
      
        kind = ''
        link = ''
        dest_position = None
        link_match = None
        result = action_regex.search(string)

        if result:
            action = result.group(1)
            for name in self.actions:
                if name == action:
                    r = self.actions[name](self)
                    return r.execute(
                        result.group(2),
                        filename, 
                        col_pos=col_pos,
                        file_pos=file_pos)

        result = re.search(
            node_link_regex, 
            string[col_pos:] # look only to the right of the click point
            )        
        link_location = None
        
        if result:
            kind = 'NODE'
            link_match = result.group()
            link_location = file_pos + result.span()[1] - 3
            link = result.group(2) # node id
            if len(result.groups()) > 2:
                dest_position = result.group(3) 
                if dest_position:
                    dest_position = int(dest_position[1:])
                else:
                    dest_position = 0
                dest_position = self.get_file_position(link, dest_position)
        else:
            result = re.search(editor_file_link_regex, string)            
            if result:
                link = os.path.join(self.path, result.group(2)).strip()
                kind = 'EDITOR_LINK'              
                if os.path.splitext(link)[1][1:] in self.settings['open_with_system']:
                    kind = 'SYSTEM'              
            else:
                result = re.search(url_scheme, string)                
                if result:
                    kind ='HTTP'
                    link = result.group().strip()
        return {
            'kind' : kind, 
            'link' : link, 
            'link_match' : link_match,
            'file_pos': file_pos, 
            'link_location' : link_location, 
            'dest_position' : dest_position }

    def _is_duplicate_id(self, node_id, filename):
        """ private method to check if a node id is already in the project """
        if node_id in self.nodes:
            return self.nodes[node_id].filename
        return False

    def _log_item(self, item):
        if self.settings['console_log']:
            print(item)
        
    def timestamp(self, date):
        """ Given a datetime object, returns a timestamp in the format set in project_settings, or the default """

        if date.tzinfo == None:
            date = self.default_timezone.localize(date)    
        timestamp_format = '<' + self.settings['timestamp_format'] + '>'
        return date.strftime(timestamp_format)

    def get_log_node(self):
        return self.settings['log_id']

    def _get_settings_from(self, node):
      
        self.reset_settings()
        replacements = {}
        for entry in node.metadata.entries:
            key = entry.keyname
            value = entry.value
   
            if key in replace:
                if key not in replacements:
                    replacements[key] = []
                replacements[key].append(value)
                continue

            if key == 'project_title':
                # this one sets a project object property, not the settings dict
                self.title = value
                continue

            if key == 'numerical_keys':
                self.settings['numerical_keys'].append(value)
                self.settings['numerical_keys'] = list(set(self.settings['numerical_keys']))
                continue

            if key in single_values:
                self.settings[key] = value
                continue

            if key in single_boolean_values:
                self.settings[key] = True if value.lower() == 'true' else False
                continue            

            if key not in self.settings:
                self.settings[key] = []
                
            self.settings[key].append(value)
            self.settings[key] = list(set(self.settings[key]))

        self.default_timezone = timezone(self.settings['timezone'])

        for k in replacements.keys():
            if k in single_values:
                self.settings[k] = replacements[k][0]
            else:   
                self.settings[k] = replacements[k]

    def run_action(self, action, string, filename, col_pos=0, file_pos=0):
        instance = self.actions[action](self)
        return instance.execute(
            string, 
            filename, 
            col_pos=col_pos,
            file_pos=file_pos)

    def get_home(self):
        return self.settings['home']

    def next_index(self):
        index = random.choice(list(self._node_id_generator()))
        while ''.join(index) in self.nodes:
            index = random.choice(list(self._node_id_generator()))
        return ''.join(index)

    def titles(self):
        title_list = {}
        for node_id in self.nodes:
            title_list[self.nodes[node_id].title] = (self.title, node_id)
        return title_list

    def get_all_meta_pairs(self):
        pairs = []
        for n in list(self.nodes):
            for k in self.nodes[n].metadata.get_keys():
               values = self.nodes[n].metadata.get_values(k)
               for v in values:
                    pairs.append(''.join([k, '::', str(v) ])  )
        return list(set(pairs))

    def get_all_for_hash(self):
        hashes = []
        for n in self.get_by_meta(self.settings['hash_key'], '*' ,'='):
            hashes.extend(self.nodes[n].metadata.get_values(self.settings['hash_key']))
        return list(set(hashes))

    def random_node(self):
        if self.nodes:
            node_id = random.choice(list(self.nodes))
            return node_id
        return None
    
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
            contents = self.files[filename]._get_file_contents()
            new_contents = contents
            for pattern in patterns_to_replace:
                links = re.findall(pattern + original_id, new_contents)
                for link in links:
                    new_contents = new_contents.replace(link, replacement, 1)
            if contents != new_contents:
                self.files[filename]._set_file_contents(new_contents, compare=False)
                if self.is_async:
                    self.executor.submit(self._file_update, filename)
                else:
                    self._file_update(filename)
                    
    def on_modified(self, filenames):
        # Method to be called by the editor when a file is modified.
        # Accepts a file or list of modified files, 
        # returns a list of modified files.
        if not isinstance(filenames, list):
            filenames = [filenames]
        do_not_update = ['history','files','.git']
        filenames = [os.path.basename(f) for f in filenames if f not in do_not_update and '.git' not in f]
        if self.is_async:
            return self.executor.submit(self._file_update, filenames)
        return self._file_update(filenames)

    def visit_node(self, node_id):
        if self.is_async:
            self.executor.submit(self._visit_node, node_id)
        else:
            self._visit_node(node_id)

    def _visit_node(self, node_id):
        self.nodes[node_id].metadata.access() # ?
        for ext in self.extensions:
            self.extensions[ext].on_node_visited(node_id)
        for dd in self.dynamic_defs():
            for op in dd.operations:
                op.on_node_visited(node_id)

    def visit_file(self, filename):
        filename = os.path.basename(filename)
        if self.is_async:
            return self.executor.submit(self._visit_file, filename)
        else:
            return self._visit_file(filename)

    def _visit_file(self, filename):
        if filename in self.files and self.compiled:
            if self._rewrite_titles(filename=filename):
                self._parse_file(filename)
            return self._compile_file(filename)

    def _file_update(self, filenames):
        if self.compiled:
            modified_files = []
            for f in filenames:            
                self._rewrite_titles(filename=f)
                self._parse_file(f)
                modified_file = self._compile_file(f)   
                if modified_file:
                    modified_files.append(modified_file)
            return modified_files
        
    def _sync_file_list(self):
        new_files = []
        for file in [f for f in os.listdir(self.path) if os.path.basename(f) not in self.files]:
            if self._filter_filenames(file) == None:
                continue
            duplicate_node_ids = self._parse_file(file)
            if not duplicate_node_ids:
                self._log_item(file+' found. Adding to "'+self.title+'"')    
                new_files.append(os.path.basename(file))
        lost_files = [f for f in self.files if os.path.join(self.path,f) not in os.listdir(self.path)]
        for f in lost_files:
            self._log_item(f+' no longer seen in project path. Dropping it from the project.')
            self.remove_file(f)

    def add_file(self, filename):
        """ 
        parse syncronously so we can raise an exception
        if moving files between projects.
        """
        any_duplicate_ids = self._parse_file(filename)
        
        if any_duplicate_ids:
            self._log_item('File moved but not added to destination project. Duplicate Nodes IDs shoudld be printed above.')
            raise DuplicateIDs()
        else:
            if self.is_async:
                return self.executor.submit(self._compile)
            else:
                self._compile()

    def remove_file(self, filename, is_async=True):
        if self.is_async and is_async:
            self.executor.submit(self._remove_file, os.path.basename(filename))
        else:
            self._remove_file(os.path.basename(filename)) 
    
    def get_file_name(self, node_id, absolute=False):
        filename = None
        if node_id in self.nodes:
            filename = self.nodes[node_id].filename
        else:
            return None
        if absolute:
            filename = os.path.join(self.path, filename)
        return filename

    def title_completions(self):
        return [(self.nodes[n].title, ''.join(['| ',self.nodes[n].title,' >',self.nodes[n].id])) for n in list(self.nodes)]

    def get_first_value(self, node, keyname):
        value = node.metadata.get_first_value(keyname)
        if keyname in self.settings['numerical_keys']:
            try:
                value = float(value)
            except ValueError:
                return 0
        return value

    def get_all_keys(self):
        keys = []
        exclude = self.settings['exclude_from_star']
        exclude.extend(self.settings.keys())
        for nid in self.nodes:
            keys.extend(self.nodes[nid].metadata.get_keys(exclude=exclude)
            )
        return list(set(keys))

    def get_all_values_for_key(self, key, lower=False):
        values = []
        for nid in self.nodes:
            values.extend(self.nodes[nid].metadata.get_values(key))
        if lower:
            return list(set([v.lower() for v in values]))
        return list(set(values))

    def get_by_meta(self, key, values, operator):
        
        if isinstance(values,str):
            values = [values]
        results = []

        if operator in ['before','after']:
            
            compare_date = date_from_timestamp(values[0][1:-1])
            
            if compare_date:
                if operator == 'before':
                    results = [n for n in self.nodes if default_date != self.nodes[n].metadata.get_date(key) < compare_date]
                if operator == 'after':
                    results = [n for n in self.nodes if self.nodes[n].metadata.get_date(key) > compare_date != default_date ]

                return set(results)

            return set([])

        if key == '_contents' and operator == '?': # `=` not currently implemented
            for node_id in list(self.nodes):
                if self.nodes[node_id].dynamic:
                    continue
                matches = []
                contents = self.nodes[node_id].content_only()
                lower_contents = contents.lower()           

                for v in values:
                    if v.lower() in lower_contents:
                        results.append(node_id)

            return results

        if key == '_links_to':
            for v in values:
                results.extend(self.get_links_to(v))
            return results

        if key == '_links_from':
            for v in values:
                results.extend(self.get_links_from(v))
            return results

        results = set([])
        
        if key == '*':
            keys = self.get_all_keys()
        
        else:
            keys = [key]

        for k in keys:
            for value in values:

                if value in ['*']:
                    results = results.union(set(n for n in list(self.nodes) if self.nodes[n].metadata.get_values(k))) 
                    continue

                use_timestamp = False
                if isinstance(value, UrtextTimestamp):
                    use_timestamp = True

                if k in self.settings['numerical_keys']:
                    try:
                        value = float(value)
                    except ValueError:
                        value = 99999999
                
                if k in self.settings['case_sensitive']:
                    results = results.union(set(
                        n for n in list(self.nodes) if value in self.nodes[n].metadata.get_values(
                            k, use_timestamp=use_timestamp)))
                else:
                    if isinstance(value, str):
                        value=value.lower()
                    results = results.union(set(
                        n for n in list(self.nodes) if value in self.nodes[n].metadata.get_values(
                            k, use_timestamp=use_timestamp, lower=True)))
        
        return results

    def get_file_and_position(self, node_id):
        if node_id in self.nodes:
            filename = self.get_file_name(node_id, absolute=True)
            position = self.nodes[node_id].start_position()
            return filename, position
        return None, None

    def _list_messages(self):
        pass
        output = []
        for filename in self.messages:
            if self.messages[filename]:
                output.append('f>./'+filename)
                output.extend(self.messages[filename])
        return '\n'.join(output)

    def _populate_messages(self):
        if self.settings['log_id'] and self.settings['log_id'] in self.nodes:
            output = self._list_messages()
            output += '\n'+self.urtext_node.build_metadata(
                {   'id':self.settings['log_id'],
                    'title':'Log',
                    'timestamp' : self.timestamp(datetime.datetime.now())
                })
            self.messages = {}
            if self._set_node_contents(self.settings['log_id'], output):
                return self.nodes[self.settings['log_id']].filename

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


def soft_match_compact_node(selection):
    if re.match(r'^[^\S\n]*•.*?@\b[0-9,a-z]{3}\b.*', selection):
        return True
    return False

def convert_dict_values_to_int(old_dict):
    new_dict = {}
    for key, value in old_dict.items():
        new_dict[key] = int(value)
    return new_dict

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

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
import diff_match_patch as dmp_module
from pytz import timezone
import pprint
from anytree import Node, PreOrderIter, RenderTree

from anytree import Node, PreOrderIter, RenderTree
from urtext.file import UrtextFile
from urtext.node import UrtextNode, strip_contents
from urtext.compile import compile_functions
from urtext.functions.tree import trees_functions
from urtext.meta_handling import metadata_functions

from urtext.dynamic import UrtextDynamicDefinition
from urtext.timestamp import date_from_timestamp, default_date, UrtextTimestamp
from urtext.utils import strip_backtick_escape
from urtext.hooks.nodehook import NodeHook
from urtext.triggers.trigger import UrtextTrigger
from importlib import import_module

node_pointer_regex = r'>>[0-9,a-z]{3}\b'
title_marker_regex = r'\|.*?\s>{1,2}[0-9,a-z]{3}\b'
node_id_regex = r'\b[0-9,a-z]{3}\b'
node_link_regex = re.compile(r'(\|?.*?[^f]>{1,2})(\w{3})(\:\d{1,10})?')
trigger_regex = re.compile(r'>>>([A-Z_]+)\((.*?)\)', re.DOTALL)
editor_file_link_regex = re.compile('(f>{1,2})([^;]+)')
url_scheme = re.compile(r'http[s]?:\/\/(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\), ]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')

functions = trees_functions
functions.extend(compile_functions)
functions.extend(metadata_functions)

for i in os.listdir(os.path.join(os.path.dirname(__file__),'hooks')):
    if '.py' in i:
        i = os.path.basename(os.path.splitext(i)[0])
        import_module('urtext.hooks.'+i)

for i in os.listdir(os.path.join(os.path.dirname(__file__),'triggers')):
    if '.py' in i:
        i = os.path.basename(os.path.splitext(i)[0])
        import_module('urtext.triggers.'+i)

def all_subclasses(cls):
    return set(cls.__subclasses__()).union(
        [s for c in cls.__subclasses__() for s in all_subclasses(c)])

print("HOOKS LOADED")
all_node_hooks = all_subclasses(NodeHook);
print(all_node_hooks)

print("TRIGGERS LOADED")
all_triggers = all_subclasses(UrtextTrigger);
print(all_triggers)


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
        
        self.is_async = True 
        #self.is_async = False # development only
        self.path = path
        self.nodes = {}
        self.h_content = {}
        self.files = {}
        self.navigation = []  # Stores, in order, the path of navigation
        self.nav_index = -1  # pointer to the CURRENT position in the navigation list
        self.to_import = []
        self.settings_initialized = False
        self.dynamic_memo = {}
        self.watchdog = watchdog
        self.quick_loaded = False
        self.compiled = False
        self.loaded = False
        self.other_projects = [] # propagates from UrtextProjectList, permits "awareness" of list context
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=50)
        self.access_history = {}
        self.messages = {}
        self.default_timezone = timezone('UTC')
        self.title = self.path # default
        self._initialize_settings()
        if self.is_async:
            future = self.executor.submit(self.quick_load, import_project=import_project)
            future = self.executor.submit(self._initialize_project,
                    import_project=import_project, 
                    init_project=init_project)
        else:
            self.quick_load(import_project=import_project)
            self._initialize_project(
                 import_project=import_project, 
                 init_project=init_project)


        # TODO -- node date timezones have to be localized
        # do this from UrtextNode.date() method

    def _initialize_settings(self):
        
        self.settings = {  # defaults
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
            'keyless_timestamp' : True,
            'inline_node_timestamp' :True,
            'file_node_timestamp' : True,
            'file_node_leading_contents': '',
            'hash_key': '',
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
                'timestamp',]
        }

    def quick_load(self, import_project=False):

        self.retrieve()
        
        if self.ql and 'last_accessed' in self.ql:
            for file in [t for t in self.ql['last_accessed'] if t in os.listdir(self.path)]:
                self._parse_file(file)
        self.quick_loaded = True
        
    def retrieve(self):
        if os.path.exists(os.path.join(self.path,'_store.json')):
            with open(os.path.join(self.path, '_store.json'), 'r') as f:
                self.ql = json.loads(f.read())
                self.settings=self.ql['project_settings']
                self.title = self.ql['title']
        else:
            self.ql = { 'last_accessed': [], 'title': '', 'path': self.path}

    def store(self):
        if self.compiled:
            self.ql['title'] = self.title
            self.ql['project_settings'] = self.settings       
            with open(os.path.join(self.path,'_store.json'), "w", encoding='utf-8') as f:
                f.write(json.dumps(self.ql))

    def _initialize_project(self, 
        import_project=False, 
        init_project=False):

        for file in [f for f in os.listdir(self.path) if f not in self.ql['last_accessed']]:
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
        
        if not os.path.exists(os.path.join(self.path, "history")):
            os.mkdir(os.path.join(self.path, "history"))

        # build sub tags
        for node_id in self.nodes:
            for e in self.nodes[node_id].metadata.dynamic_entries:                
                self._add_sub_tags( node_id, node_id, e)

        self._get_access_history()        
        self._compile()
        self.compiled = True
        self.store()
        print('"'+self.title+'" compiled from '+self.path )
    
    def _node_id_generator(self):
        chars = [
            '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'a', 'b', 'c',
            'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p',
            'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z'
        ]
        return itertools.product(chars, repeat=3)


    def get_file_position(self, node_id, position):
        if node_id in self.nodes:
            last_position = 0
            for r in self.nodes[node_id].ranges:
                position += r[0] - last_position
                if position in range(r[0],r[1]):
                    return position
                last_position = r[1]
        return None

    def _assign_node_parent_title(self):
        """
        Only has to be called once on project init
        """

        for node_id in self.nodes:
            self.nodes[node_id].parent_project = self.title


    def _file_changed(self, filename, strict=False):
        
        old_hash = None
        if filename in self.files:
            already_in_project = True
            old_hash = self.files[filename].hash

        """
        Parse the file
        """
        new_file = UrtextFile(
            os.path.join(self.path, filename), 
            settings=self.settings,
            previous_hash=old_hash,
            strict=strict
            )
        
        if new_file.changed == False:
            return False

        return new_file

    def _parse_file(self, 
            filename, 
            import_project=False):
        """
        Parses a single file into the project.
        Returns None if successful, or a list of duplicate nodes found
        if duplicate nodes were found.
        FUTURE: return value should be sanitized Currently returns None, False or list.
        """
        filename = os.path.basename(filename)
        if self._filter_filenames(filename) == None:
            return
        
        already_in_project = False

        new_file = self._file_changed(filename)
        if not new_file:
            return False

        self.messages[filename] = []
        if new_file.messages:
            self.messages[filename] = new_file.messages 
        
        if not new_file.is_parseable:
            if already_in_project:
                self._log_item('Unable to re-parse >f'+filename+ ', dropping it from the project.')
                return False
            self.to_import.append(filename)
            return

        self._remove_file(filename)
        """
        Check the file for duplicate nodes
        """
        duplicate_nodes = self._check_file_for_duplicates(new_file)
        if duplicate_nodes:
            return duplicate_nodes
 
        """
        re-add the filename and all its nodes to the project
        """
        self.files[new_file.basename] = new_file  

        for node_id in new_file.nodes:
            self._add_node(new_file.nodes[node_id])
        
        self._set_tree_elements(new_file.basename)

        """
        If this is not the initial load of the project rebuild sub-tags
        """        
        if self.compiled:
             for node_id in new_file.nodes:
                for e in self.nodes[node_id].metadata.dynamic_entries:
                    self._add_sub_tags( node_id, node_id, e)
    
        """ returns None if successful """
        return None

    def _check_file_for_duplicates(self, file_obj):
        duplicate_nodes = {}
        for node_id in file_obj.nodes:
            duplicate_filename = self._is_duplicate_id(node_id, file_obj.filename)
            if duplicate_filename:
                duplicate_nodes[node_id] = duplicate_filename

        if duplicate_nodes:
            basename = os.path.basename(file_obj.filename)
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

    def _rewrite_titles(self, filename):

        original_contents = self.files[filename]._get_file_contents()
        new_contents = original_contents
        offset = 0        
        for match in re.finditer(title_marker_regex, new_contents):
            start = match.start() + offset
            end = match.end() + offset
            location_node_id = self.get_node_id_from_position(filename, start)
            if not location_node_id:
                continue
            if not self.nodes[location_node_id].dynamic:          
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
        if new_contents != original_contents:
            return new_contents 
        return False

    def _target_id_defined(self, check_id):
        for nid in list(self.nodes):
            if check_id in [t.target_id for t in self.nodes[nid].dynamic_definitions]:
                return nid
        return

    def _target_file_defined(self, file):
        for nid in list(self.nodes):
            for e in self.nodes[nid].dynamic_definitions:
                for r in e.exports:
                    if file in r.to_files:
                        return nid
        return

    """
    Parsing helpers
    """
    def _add_node(self, new_node):
        """ Adds a node to the project object """

        for definition in new_node.dynamic_definitions:
            
            if definition.target_id:
                definition.add_projects(self)
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
        if new_node.id in self.access_history:
            new_node.last_accessed = self.access_history[new_node.id]

        self.h_content[new_node.id] = new_node.hashed_contents
        new_node.project = self
        # TODO : it's not necessary to keep a copy of this
        # inside the node. do it at the project level only. 
        self.nodes[new_node.id] = new_node

        if new_node.project_settings:
            self._get_settings_from(new_node)            

        self._run_node_hooks(new_node)

    def _run_node_hooks(self, node):
        for c in all_node_hooks:
            hook = c(node)
            hook.run()

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

    def _set_node_contents(self, node_id, contents):
        """ 
        project-aware alias for the Node set_content() method 
        returns filename if contents has changed.

        """
        self._parse_file(self.nodes[node_id].filename)
        if node_id in self.nodes:
            file_changed = self.nodes[node_id].set_content(contents, preserve_metadata=True)       
            if file_changed:
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
            output += '\n'+UrtextNode.build_metadata(
                {   'id':self.settings['log_id'],
                    'title':'Log',
                    'timestamp' : self.timestamp(datetime.datetime.now())
                })
            self.messages = {}
            changed = self._set_node_contents(self.settings['log_id'], output)     
            if changed:
                return self.nodes[self.settings['log_id']].filename
    """
    Removing and renaming files
    """
    def _remove_file(self, filename):
       
        if filename in self.files:
            
            for node_id in self.files[filename].nodes:                 
                self.nodes[node_id].tree_node.parent = None
                self.nodes[node_id].tree_node = None
                self._remove_sub_tags(node_id)                
                del self.nodes[node_id]
                del self.h_content[node_id]

            for a in self.files[filename].alias_nodes:
                a.parent = None
                a.children = []

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
            f.write(contents )  
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
            'contents' : ''.join(['{ ', contents, '}']),
            'id':node_id
        }
    
    def _new_node(self, 
            date=None, 
            contents='\n',
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
                new_node_contents += '  ' + self.timestamp(date) + ' '
            elif self.settings['node_date_keyname']:
                metadata[self.settings['node_date_keyname']] = self.timestamp(date)
            
        new_node_contents += UrtextNode.build_metadata(metadata, one_line=one_line)

        return new_node_contents, node_id

    def add_compact_node(self,  
            contents='', 
            metadata={},
        ):
        	metadata['id']=self.next_index()
        	metadata_block = UrtextNode.build_metadata(metadata, one_line=True)
        	return '•  '+contents + ' ' + metadata_block

    def dynamic_defs(self, target=None):
        dd = []
        for nid in self.nodes:

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
       
        return self.navigation[self.nav_index]


    def nav_new(self, node_id):

        # don't re-remember consecutive duplicate links
        if -1 < self.nav_index < len(self.navigation) and node_id == self.navigation[self.nav_index]:
            return

        if node_id in self.nodes and self.nodes[node_id].filename not in self.ql['last_accessed']:
            self.ql.setdefault('last_accessed',[])
            self.ql['last_accessed'].insert(0, self.nodes[node_id].filename)
            self.ql['last_accessed'] = self.ql['last_accessed'][:20]
            self.store()
            
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
            node_group = [r for r in remaining_nodes if self.nodes[r].metadata.get_first_value(k)]
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

    def get_link(self, string, position=0):
        """ 
        Given a line of text passed from an editor, 
        opens a web link, file, or returns a node,
        in that order. Returns a tuple of type and success/failure or node ID
        """
        link = self.find_link(string[position:])

        if not link:
            return

        # work backwards along the line
        if not link[0]:
            while position > -1:
                link = self.find_link(string[position:])
                if link[0]:
                    break
                position -= 1

        if not link[0]:
            if not self.compiled:
               return self._log_item('Project is still compiling')
            return self._log_item('No node ID, web link, or file found on this line.')

        if link[0] == 'NODE' and link[1] not in self.nodes:
            if not self.compiled:
               return self._log_item('Project is still compiling')
            self._log_item('Node ' + link[1] + ' is not in the project')
            return None

        return link

    def find_link(self, string):

        kind, result, link, position = '', None, '', 0
        result = trigger_regex.search(string)
        if result:
            trigger = result.group(1)
            for t in all_triggers:
                if t.name == trigger:
                    r = t(result.group(2))
                    r.execute(self)
                    return None

        result = re.search(node_link_regex, string)        
        link_location = None
        if result:
            kind = 'NODE'
            link_location = result.span()
            link = result.group(2) # node id
            if len(result.groups()) > 2:
                position = result.group(3) 
                if position:
                    position = int(position[1:])
                else:
                    position = 0
                position = self.get_file_position(link, position)
                if link in self.nodes:
                     self.executor.submit(self._compile_file, self.nodes[link].filename)
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

        return (kind, link, position, link_location)

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
            'timezone'
        ]
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
            'contents_strip_internal_whitespace',
        ]
        replace = [
            'file_index_sort',
            'filenames',
            'node_browser_sort',
            'tag_other',
            'filename_datestamp_format'
        ]

        self._initialize_settings() # reset defaults
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
 
    def get_home(self):
        return self.settings['home']

    def next_index(self):
        index = random.choice(list(self._node_id_generator()))
        while ''.join(index) in self.nodes:
            index = random.choice(list(self._node_id_generator()))
        return ''.join(index)

    def pop_node(self, position=None, filename=None, node_id=None):
        """
        Pops a node asyncronously, making sure that if the file was saved and on_modified
        was called in the same calling function, this completes before evaluating
        the node_id from the position.

        Returns a future containing a list of modified files as the result.
        """
        return self._pop_node( position=position, filename=filename, node_id=node_id)

    def _pop_node(self, position=None, filename=None, node_id=None):
 
        if not node_id:
            node_id = self.get_node_id_from_position(filename, position)
 
        if not node_id:
            print('No node ID or duplicate Node ID')
            return None

        if self.nodes[node_id].root_node:
            print(node_id+ ' is already a root node.')
            return None

        start = self.nodes[node_id].ranges[0][0]
        end = self.nodes[node_id].ranges[-1][1]
        file_contents = self.nodes[node_id].filename._get_file_contents()
        

        popped_node_id = node_id

        filename = self.nodes[node_id].filename

        popped_node_contents = file_contents[start:end].strip()
        parent_id = self.nodes[node_id].tree_node.parent

        if self.settings['breadcrumb_key']:
            popped_node_contents += '\n'+self.settings['breadcrumb_key']+'::>'+parent_id.name+ ' '+self.timestamp(datetime.datetime.now());

        remaining_node_contents = ''.join([
            file_contents[0:start - 1],
            '\n| ',
            self.nodes[popped_node_id].title,
             ' >>',
            popped_node_id,
            '\n',
            file_contents[end + 1:]])
       
        with open (os.path.join(self.path, filename), 'w', encoding='utf-8') as f:
            f.write(remaining_node_contents)
        self._parse_file(filename) 

        # new file
        with open(os.path.join(self.path, popped_node_id+'.txt'), 'w',encoding='utf-8') as f:
            f.write(popped_node_contents)
        self._parse_file(popped_node_id+'.txt') 
        
    def pull_node(self, string, current_file, current_position):
        """ File must be saved in the editor first for this to work """
        if self.is_async:
            return self.executor.submit(
                self._pull_node, 
                string, 
                os.path.basename(current_file), 
                current_position) 
        else:
            self._pull_node(string, os.path.basename(current_file), current_position)
    
    def _pull_node(self, string, current_file, current_position):

        link = self.get_link(string)
        
        if not link or link[0] != 'NODE': 
            return None
        
        node_id = link[1]
        if node_id not in self.nodes: 
            return None

        current_node = self.get_node_id_from_position(current_file, current_position)
        if not current_node:
            return None

        start = self.nodes[node_id].ranges[0][0]
        end = self.nodes[node_id].ranges[-1][1]
        
        contents =self.nodes[node_id].filename._get_file_contents()

        replaced_file_contents = ''.join([contents[0:start-1],contents[end+1:len(contents)]])

        if self.nodes[node_id].root_node:
            self.delete_file(self.nodes[node_id].filename)  
        else:
            self.nodes[node_id].filename.set_file_contents(replaced_file_contents)
            self._parse_file(self.nodes[node_id].filename)
        pulled_contents = contents[start:end]
        full_current_contents = self.files[current_file]._get_file_contents()

        # here we need to know the exact location of the returned link within the file
        span = link[3]
        replacement = string[span[0]:span[1]]
        wrapped_contents = ''.join(['{',pulled_contents,'}'])
        replacement_contents = full_current_contents.replace(replacement, wrapped_contents)
        self.files[current_file].set_file_contents(replacement_contents)
        self._parse_file(current_file)

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
        for k in [kn for kn in self.keynames]: 
            for value in list(self.keynames[k]):
                meta_string = ''.join([k, '::', str(value) ])            
                pairs.append(meta_string)
        return list(set(pairs))

    def get_all_for_hash(self):
        hashes = []
        if self.settings['hash_key']in self.keynames:
            for value in list(self.keynames[self.settings['hash_key']]):
                hashes.append(value)
        return hashes

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
                self.files[filename].set_file_contents( new_contents)
                if self.is_async:
                    self.executor.submit(self._file_update, filename)
                else:
                    self._file_update(filename)
                    
    def on_modified(self, filenames):
        if not isinstance(filenames, list):
            filenames = [filenames]
        if self.is_async:
            return self.executor.submit(self._on_modified, filenames)
        return self._on_modified(filenames)

    def _on_modified(self, filenames):

        #self._sync_file_list() #?
        do_not_update = ['history','files']
        filenames = [o for o in filenames if os.path.basename(o) in self.files]
        return self._file_update([os.path.basename(f) for f in filenames if f not in do_not_update and '.git' not in f])

    def _file_update(self, filenames):

        modified_files = []
        for f in filenames:
            rewritten_contents = self._rewrite_titles(f)
            if rewritten_contents:
                self.files[f]._set_file_contents(rewritten_contents)
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
        lost_files = [f for f in self.files if f not in os.listdir(self.path)]
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

    """
    File History
    """
    def snapshot_diff(self, filename, contents):
        dmp = dmp_module.diff_match_patch()
        filename = os.path.basename(filename)
        if filename not in self.files:
            return None
        history_file = os.path.join(self.path, 'history',filename.replace('.txt','.diff'))
        file_history = self.get_history(filename)
        if not file_history:
            file_history = { int(time.time()) : contents}
            with open( history_file, "w") as f:
            	f.write(json.dumps(file_history))
        else:
            latest_history = self.apply_patches(file_history)
            if contents != latest_history:
                file_history[int(time.time())] = dmp.patch_toText(dmp.patch_make(latest_history, contents))
                # prevent duplicate files on cloud storage
                os.remove(history_file)
                with open( history_file, "w") as f:
                    f.write(json.dumps(file_history))

    def apply_patches(self, history, distance_back=0):
        dmp = dmp_module.diff_match_patch()
        timestamps = sorted(history.keys())
        original = history[timestamps[0]]
        for index in range(1,len(timestamps)-distance_back):
            next_patch = history[timestamps[index]]
            original = dmp.patch_apply(dmp.patch_fromText(next_patch), original)[0]
        return original

    def get_version(self, filename, distance_back=0):
        history = self.get_history(filename)
        return self.apply_patches(history, distance_back)       

    def get_history(self, filename):
        dmp = dmp_module.diff_match_patch()
        filename = os.path.basename(filename)
        history_file = os.path.join(self.path, 'history', filename.replace('.txt','.diff'))
        if os.path.exists(history_file):
            with open(history_file, "r") as f:
                file_history = f.read()
            return json.loads(file_history)
        return None

    def most_recent_history(self, history):
        times = sorted(history.keys())
        return times[-1]

    def title_completions(self):
        return [(self.nodes[n].title, ''.join(['| ',self.nodes[n].title,' >',self.nodes[n].id])) for n in list(self.nodes)]

    """
    Access History
    """

    def _get_access_history(self):

        accessed_file = os.path.join(self.path, "history", "URTEXT_accessed.json")
        if os.path.exists(accessed_file):
            with open(accessed_file,"r") as f:
                try:
                    contents = f.read()
                    if contents:
                        try:
                            access_history = json.loads(contents)
                            self.access_history = convert_dict_values_to_int(access_history)
                        except:
                            print('Could not parse access history for '+accessed_file)
                            print(contents)
                except EOFError as error:
                    print(error)
         
        self._propagate_access_history()    

    def _propagate_access_history(self):

        for node_id, access_time in self.access_history.items():
            if node_id in self.nodes:
                self.nodes[node_id].last_accessed = access_time

    def _save_access_history(self):

        accessed_file = os.path.join(self.path, "history", "URTEXT_accessed.json")
        # prevent duplicate files on cloud storage
        if os.path.exists(accessed_file):
            os.remove(accessed_file)
        with open(accessed_file,"w") as f:
            f.write(json.dumps(self.access_history))
    
    def _push_access_history(self, node_id, duplicate=False):
        if node_id not in self.nodes: return
        access_time = int(time.time()) # UNIX timestamp
        self.nodes[node_id].last_accessed = access_time
        self.access_history[node_id] = access_time
        self._save_access_history()

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
                    results = results.union(set(n for n in self.nodes if self.nodes[n].metadata.get_values(k))) 
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
    """
    Free Association
    """
    def get_keywords(self):
        keywords = []
        for i in self.nodes:
            keywords.extend(self.nodes[i].keywords)
        return list(set(keywords))

    def get_by_keyword(self, keyword):
        nodes = []
        for i in self.nodes:
            if self.nodes[i].has_keyword(keyword):
                nodes.append(i)
        return nodes
        
    def get_assoc_nodes(self, string, filename, position):
        node_id = self.get_node_id_from_position(filename, position)
        r = Rake()
        string = strip_contents(string)
        keywords = [t[0] for t in r.run(string)]
        assoc_nodes = []
        for k in keywords:
             assoc_nodes.extend(self.get_by_keyword(k))
        assoc_nodes = list(set(assoc_nodes))
        if node_id in assoc_nodes:
            assoc_nodes.remove(node_id)
        for node_id in assoc_nodes:
            if self.nodes[node_id].dynamic:
                assoc_nodes.remove(node_id)
        return assoc_nodes

    def get_file_and_position(self, node_id):
        if node_id in self.nodes:
            filename = self.get_file_name(node_id, absolute=True)
            position = self.nodes[node_id].start_position()
            return filename, position
        return None, None

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

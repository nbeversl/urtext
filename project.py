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
import platform
import os
import random
import time
from time import strftime
import concurrent.futures
import threading

if os.path.exists(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'sublime.txt')):
    from ..anytree import Node, PreOrderIter, RenderTree
    from .file import UrtextFile, UrtextBuffer
    from .node import UrtextNode
    from .dynamic import UrtextDynamicDefinition
    from .timestamp import date_from_timestamp, default_date, UrtextTimestamp
    from .directive import UrtextDirective
    from .extension import UrtextExtension
    import Urtext.urtext.syntax as syntax
    from Urtext.urtext.project_settings import *
    import Urtext.urtext.directives     
    import Urtext.urtext.extensions
    from Urtext.urtext.utils import get_id_from_link
else:
    from anytree import Node, PreOrderIter, RenderTree
    from urtext.file import UrtextFile, UrtextBuffer
    from urtext.node import UrtextNode
    from urtext.dynamic import UrtextDynamicDefinition
    from urtext.timestamp import date_from_timestamp, default_date, UrtextTimestamp
    from urtext.directive import UrtextDirective
    from urtext.extension import UrtextExtension
    import urtext.syntax as syntax
    from urtext.project_settings import *
    import urtext.directives     
    import urtext.extensions
    from urtext.utils import get_id_from_link

def all_subclasses(cls):
    return set(cls.__subclasses__()).union(
        [s for c in cls.__subclasses__() for s in all_subclasses(c)])

class UrtextProject:

    urtext_file = UrtextFile
    urtext_node = UrtextNode

    def __init__(self, entry_point, project_list=None, editor_methods={}):

        self.settings = default_project_settings()
        self.project_list = project_list
        self.entry_point = entry_point
        self.entry_path = None
        self.settings['project_title'] = self.entry_point # default
        self.editor_methods = editor_methods
        self.is_async = True
        self.is_async = False # development
        self.time = time.time()
        self.last_compile_time = 0
        self.nodes = {}
        self.files = {}
        self.exports = {}
        self.messages = {}
        self.dynamic_definitions = []
        self.dynamic_metadata_entries = []
        self.extensions = {}
        self.directives = {}
        self.compiled = False
        self.excluded_files = []
        self.home_requested = False
        self.executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1)        
        self.message_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1) 
        self.execute(self._initialize_project)
    
    def _initialize_project(self):

        self._collect_extensions_directives()

        num_file_extensions = len(self.settings['file_extensions'])
        num_paths = len(self.settings['paths'])
        
        if os.path.exists(self.entry_point) and os.path.isdir(self.entry_point):
            self.entry_path = self.entry_point
            self.settings['paths'].append({
                'path' : self.entry_point,
                'recurse' : False
                })
            for file in self._get_included_files():
                self._parse_file(file)
        elif os.path.exists(self.entry_point):
            self.entry_path = os.path.dirname(self.entry_point)            
            self._parse_file(self.entry_point)    

        while len(self.settings['paths']) > num_paths or len(self.settings['file_extensions']) > num_file_extensions:
            num_paths = len(self.settings['paths'])
            num_file_extensions = len(self.settings['file_extensions'])
            for file in self._get_included_files():
                if file not in self.files:
                    self._parse_file(file)

        for node_id in self.nodes:
            self.nodes[node_id].metadata.convert_hash_keys()
            self.nodes[node_id].metadata.convert_node_links()

        self._mark_dynamic_nodes()
        
        self._compile() ## TODO fix
        if len(self.extensions) > 0 or len(self.directives) > 0:
            self._collect_extensions_directives()
            self._compile()

        self.compiled = True
        self.last_compile_time = time.time() - self.time
        self.time = time.time()
        for ext in self.extensions.values():
            ext.after_project_initialized()
        self.handle_message(
            '"'+self.settings['project_title']+'" compiled')
    
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
            file_position = r[0] + offset_position
            return file_position

    def _parse_file(self, filename):
    
        if self._filter_filenames(filename) == None:
            return self._add_to_excluded_files(filename)

        old_node_ids = []
        if filename in self.files:
            old_node_ids = [n.id for n in self.files[filename].get_ordered_nodes()]
        self._drop_file(filename)
        
        new_file = self.urtext_file(filename, self)
        if not new_file.root_node:
            print('%s has no root node, dropping' % filename)
            self.excluded_files.append(filename)
            return False

        self.messages[new_file.filename] = new_file.messages

        changed_ids = self._check_file_for_duplicates(new_file)

        if old_node_ids:
            new_node_ids = [n.id for n in new_file.get_ordered_nodes()]
            if len(old_node_ids) == len(new_node_ids):
                for index in range(0, len(old_node_ids)): # existing links are all we care about
                    if old_node_ids[index] == new_node_ids[index]:
                        continue # id stayed the same
                    else:
                        if new_node_ids[index] in old_node_ids:
                            # proably only the order changed.
                            # don't have to do anything
                            continue
                        else:
                            # check each new id for similarity to the old one
                            changed_ids[old_node_ids[index]] = new_node_ids[index]
                            # else:
                            # try to map old to new. This is the hard part
        
        for node in new_file.nodes:
            self._add_node(node)

        self.files[new_file.filename] = new_file
        for ext in self.extensions.values():
            ext.on_file_added(filename)

        for node in new_file.nodes:
            if node.parent:
                node.parent.children.append(node)

        for entry in new_file.meta_to_node:
            keyname = entry.group(1)
            source_node = self.get_node_id_from_position(
                filename, 
                entry.span()[0])
            target_node = self.get_node_id_from_position(
                filename, 
                entry.span()[1])
            self.nodes[source_node].metadata.add_entry(
                keyname,
                self.nodes[target_node],
                is_node=True)
            self.nodes[target_node].is_meta = True

        for node in new_file.nodes:            
            if node.title == 'project_settings':
                self._get_settings_from(node)     

            for dd in node.dynamic_definitions:
                dd.source_id = node.id
                self.dynamic_definitions.append(dd)

            for entry in node.metadata.dynamic_entries:
                entry.from_node = node.id
                self._add_sub_tags(entry)
                self.dynamic_metadata_entries.append(entry)

        if self.compiled and changed_ids:
            self._rewrite_changed_links(changed_ids)

    def _verify_links_globally(self):
        links = self.get_all_links()
        for filename in links:
            self._reverify_links(filename)

    def _reverify_links(self, filename):
        
        links = []
        for node in self.files[filename].nodes:
            links.extend(node.links)
        
        rewrites = {}
        for link in links:
            node_id = get_id_from_link(link)
            if node_id not in self.nodes:
                id_only = node_id.split(syntax.parent_identifier)[0]
                if id_only not in self.nodes and link not in rewrites:
                    rewrites[link] = '|? ' + id_only + ' >'
                elif link not in rewrites:
                    rewrites[link] = '| ' + id_only + ' >'
            elif '|? ' in link:
                rewrites[link] = '| ' + node_id + ' >'

        if rewrites:
            contents = self.files[filename]._get_file_contents()
            for old_link in rewrites:
                contents = contents.replace(old_link, rewrites[old_link])
            self.files[filename]._set_file_contents(contents)
            if self.compiled:
                self._parse_file(filename)

    def _collect_extensions_directives(self):
        
        num_extensions = len(self.extensions)
        num_directives = len(self.directives)

        for c in all_subclasses(UrtextExtension):
            for n in [x for x in c.name if x not in self.extensions]:
                self.extensions[n] = c(self)

        for c in all_subclasses(UrtextDirective):
            for n in [x for x in c.name if x not in self.directives]:
                self.directives[n] = c

        if len(self.extensions) > num_extensions or len(self.directives) > num_directives:
            self._collect_extensions_directives()

    def _add_all_sub_tags(self):
        for entry in self.dynamic_metadata_entries:
            self._add_sub_tags(entry)

    def _rewrite_changed_links(self, changed_ids):
        for old_id in list(changed_ids.keys()):
            new_id = changed_ids[old_id]
            if new_id in list(self.nodes):
                for project_node in list(self.nodes):
                    links_to_change = {}
                    if project_node not in self.nodes: continue
                    for link in self.nodes[project_node].links:
                        link = get_id_from_link(link)
                        if link == old_id:
                            links_to_change[link] = new_id
                    if links_to_change:
                        filename = self.nodes[project_node].filename
                        contents = self.files[filename]._get_file_contents()
                        for node_id in list(links_to_change.keys()):
                            replaced_contents = contents
                            node_id_regex = re.escape(node_id)
                            replaced_contents = re.sub(                        
                                syntax.node_link_opening_wrapper_match + node_id_regex + syntax.link_closing_wrapper,
                                make_link(links_to_change[node_id]),
                                replaced_contents)
                            if replaced_contents != contents:
                                self.files[filename]._set_file_contents(replaced_contents)
                                self._parse_file(filename)

    def _check_file_for_duplicates(self, file_obj):

        duplicate_nodes = {}
        changed_ids = {}
        
        # first resolve duplicates in file
        file_node_ids = [n.id for n in file_obj.nodes]
        for node in list(file_obj.nodes):
            if file_node_ids.count(node.id) > 1:
                resolved_new_id = node.resolve_duplicate_id()
                if not resolved_new_id:
                    duplicate_nodes[node.id] = file_obj.filename
                    print('Cannot resolve duplicate ID %s' % node.id)
                    print(file_obj.filename)
                    continue
                changed_ids[node.id] = resolved_new_id
                node.apply_id(resolved_new_id)

        for node in file_obj.nodes:
            
            duplicated_id = self._is_duplicate_id(node.id) # in project
            if duplicated_id:
                resolved_existing_id = None
                if syntax.parent_identifier not in duplicated_id:
                    resolved_existing_id = self.nodes[duplicated_id].resolve_duplicate_id()
                    if not resolved_existing_id:
                        continue
                    self.nodes[duplicated_id].apply_id(resolved_existing_id)
                    self.nodes[resolved_existing_id] = self.nodes[duplicated_id]
                    changed_ids[duplicated_id] = resolved_existing_id
                    for ext in self.extensions.values():
                        ext.on_node_id_changed(
                            duplicated_id,
                            resolved_existing_id)
                    del self.nodes[duplicated_id]

                resolved_new_id = node.resolve_duplicate_id()
                if not resolved_new_id:
                    duplicate_nodes[node.id] = file_obj.filename
                    continue

                if resolved_existing_id == resolved_new_id:
                    continue           

                changed_ids[node.id] = resolved_new_id
                node.apply_id(resolved_new_id)

        if duplicate_nodes:
            messages = []
            self._log_item(file_obj.filename, 
                'Duplicate node ID(s) found in ' + ''.join([
                    ''.join(['\n\t',
                                syntax.link_opening_wrapper, 
                                n,
                                syntax.link_closing_wrapper,
                                '\n(also in): ',
                                syntax.link_opening_wrapper,
                                #self.nodes[n].filename,
                                syntax.link_closing_wrapper,
                                '\n'
                            ]) for n in duplicate_nodes]))

        return changed_ids

    def _target_id_defined(self, check_id):
        if check_id in self.nodes:
            for dd in self.dynamic_defs():
                if check_id in dd.target_ids:
                    return dd.source_id

    def _target_file_defined(self, file):
        for nid in list(self.nodes):
            for e in self.nodes[nid].dynamic_definitions:
                for r in e.exports:
                    if file in r.to_files:
                        return nid

    def _add_node(self, new_node):
        """ Adds a node to the project object """
        for definition in new_node.dynamic_definitions:
            
            for target_id in definition.target_ids:
                defined_in = self._target_id_defined(target_id)
                if defined_in and defined_in != new_node.id:

                        message = ''.join(['Dynamic node ', 
                                    syntax.link_opening_wrapper,
                                    target_id,
                                    syntax.link_closing_wrapper,
                                    ' has duplicate definition in ', 
                                    syntax.link_opening_wrapper,
                                    new_node.id,
                                    syntax.link_closing_wrapper,
                                    '; Keeping the definition in ',
                                    syntax.link_opening_wrapper,
                                    defined_in,
                                    syntax.link_closing_wrapper])

                        self._log_item(new_node.filename, message)

        new_node.project = self
        self.nodes[new_node.id] = new_node  
        if self.compiled:
            new_node.metadata.convert_node_links()   
        for ext in self.extensions.values():
            ext.on_node_added(new_node)
        
    def get_source_node(self, filename, position): # future
        if filename not in self.files:
            return None, None
        exported_node_id = self.get_node_id_from_position(filename, position)
        points = self.nodes[exported_node_id].export_points
        if not points:
            return None, None
        node_start_point = self.nodes[exported_node_id].start_position()

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
        if parse and self._parse_file(self.nodes[node_id].filename) == -1:
            return
        if node_id in self.nodes:
             if self.nodes[node_id].set_content(contents):
                self._parse_file(self.nodes[node_id].filename)
                if node_id in self.nodes:
                    return self.nodes[node_id].filename
        return False

    def _adjust_ranges(self, filename, from_position, amount): # future
        """ 
        adjust the ranges of all nodes in the given file 
        a given amount, from a given position
        """
        for node_id in self.files[filename].nodes:
            number_ranges = len(self.nodes[node_id].ranges)
            for index in range(number_ranges):
                this_range = self.nodes[node_id].ranges[index]
                if from_position >= this_range[0]:
                    self.nodes[node_id].ranges[index][0] -= amount
                    self.nodes[node_id].ranges[index][1] -= amount

    def _mark_dynamic_nodes(self):
        for dd in self.dynamic_defs():
            for node_id in dd.target_ids:
                if node_id in self.nodes:
                    self.nodes[node_id].dynamic = True


    """
    Removing and renaming files
    """
    def _drop_file(self, filename):

        if filename in self.files:
            for dd in self.dynamic_defs():
                for op in dd.operations:
                    op.on_file_dropped(filename)

            for ext in self.extensions.values():
                ext.on_file_dropped(filename)

            for node in list(self.files[filename].nodes):    
                if node.id not in self.nodes:
                    continue
                self._remove_sub_tags(node.id)
                self.remove_dynamic_defs(node.id)
                self.remove_dynamic_metadata_entries(node.id)
                del self.nodes[node.id]
            del self.files[filename]

        if filename in self.messages:
            del self.messages[filename]

    def delete_file(self, filename, open_files=[]):
        return self.execute(
            self._delete_file, 
            filename, 
            open_files=open_files)

    def _delete_file(self, filename, open_files=[]):
        """
        Deletes a file, removes it from the project,
        and returns modified files.
        """
        if filename in self.files:         
            self._drop_file(filename)
            os.remove(filename)
        if filename in self.messages:
            del self.messages[filename]
        for ext in list(self.extensions.values()):
            ext.on_file_deleted(filename)
        if open_files:
            for f in open_files:
                self._on_modified(f)
    
    def _handle_renamed(self, old_filename, new_filename):
        if new_filename != old_filename:
            self.files[new_filename] = self.files[old_filename]
            for node in self.files[new_filename].nodes:
                self.nodes[node.id].filename = new_filename
                self.files[new_filename].filename = new_filename
            del self.files[old_filename]
            for ext in self.extensions.values():
                ext.on_file_renamed(old_filename, new_filename)
    
    """ 
    filtering files to skip 
    """
    def _filter_filenames(self, filename):
        if filename in ['urtext_files','.git']:
            return None            
        if filename in self.settings['exclude_files']:
            return None
        return filename
    
    def new_file_node(self, 
        date=None,
        path=None,
        contents=None,
        metadata={}, 
        one_line=None):

        contents_format = None
        if contents == None:
            contents_format = bytes(
                self.settings['new_file_node_format'], 
                "utf-8"
                ).decode("unicode_escape")

        filename = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        contents, node_id, cursor_pos = self._new_node(
            date=date,
            contents=contents,
            contents_format=contents_format,
            metadata=metadata,
            include_timestamp=self.settings['file_node_timestamp'])
        
        filename = filename + '.urtext'
        if path:
            filename = os.path.join(path, filename)
        with open(filename, "w") as f:
            f.write(contents)  
        self._parse_file(filename)
        for ext in self.extensions.values():
            ext.on_new_file_node(
                self.files[filename].root_node.id)

        return { 
                'filename' : filename, 
                'id' : self.files[filename].root_node.id,
                'cursor_pos' : cursor_pos
                }

    def new_inline_node(self, 
        date=None, 
        metadata = {}, 
        contents='',
        one_line=None,
        ):

        contents_format = None
        contents, cursor_pos = self._new_node(
            date=date,
            contents=contents,
            contents_format=contents_format,
            metadata=metadata)

        return {
            'contents' : ''.join(['{', contents, '}']),
            'cursor_pos' : cursor_pos
        }
    
    def _new_node(self, 
        date=None, 
        contents=None,
        title='',
        contents_format=None,
        metadata=None,
        one_line=None,
        include_timestamp=False):

        cursor_pos = 0
        if contents == None:
            contents = ''

        if contents_format:
            new_node_contents = contents_format.replace('$timestamp', self.timestamp().wrapped_string)
            new_node_contents = new_node_contents.replace('$device_keyname', platform.node() )

            if '$cursor' in new_node_contents:
                new_node_contents = new_node_contents.split('$cursor')
                cursor_pos = len(new_node_contents[0])
                new_node_contents = title + ''.join(new_node_contents)
        else:
            if one_line == None:
                one_line = self.settings['always_oneline_meta']
            
            if not metadata:
                metadata = {}

            if self.settings['device_keyname']:
                metadata[self.settings['device_keyname']] = platform.node()

            new_node_contents = contents

            if include_timestamp:
                if date == None:
                    date = datetime.datetime.now() 
                if self.settings['keyless_timestamp'] == True:
                    new_node_contents += self.timestamp(date) + ' '
                elif self.settings['node_date_keyname']:
                    metadata[self.settings['node_date_keyname']] = self.timestamp(date)

            new_node_contents += self.urtext_node.build_metadata(metadata, one_line=one_line)

        return new_node_contents, title, cursor_pos

    def add_compact_node(self,  
            contents='',
            metadata={}):
            metadata_block = self.urtext_node.build_metadata(metadata, one_line=True)
            if metadata_block:
                metadata_block = ' ' + metadata_block
            return '• ' + contents.strip() + metadata_block

    def dynamic_defs(self, target=None, source=None):
        if target or source:
            return [dd for dd in self.dynamic_definitions if target in dd.target_ids or dd.source_id == source]
        return self.dynamic_definitions

    def remove_dynamic_defs(self, node_id):
        for dd in list(self.dynamic_definitions):
            if dd.source_id == node_id:
                self.dynamic_definitions.remove(dd)

    def remove_dynamic_metadata_entries(self, node_id):
        for entry in list(self.dynamic_metadata_entries):
            if entry.from_node == node_id:
                self.dynamic_metadata_entries.remove(entry)

    def open_node(self, node_id):
        if node_id not in self.nodes:
            if self.compiled:
                message = node_id + ' not in current project'
            else:
                message = 'Project is still compiling' 
            return self.handle_message(message)

        if 'open_file_to_position' in self.editor_methods:
            self.editor_methods['open_file_to_position'](
                self.nodes[node_id].filename,
                self.nodes[node_id].start_position()
                )
            return self.visit_node(node_id)

        return 'no editor method available'

    def open_home(self):
        if not self.get_home():
            if not self.compiled:
                if not self.home_requested:
                    self.message_executor.submit(
                        self.handle_message,
                        'Project is compiling. Home will be shown when found.')
                    self.home_requested = True
                timer = threading.Timer(.5, self.open_home)
                return timer.start()
            else:
                self.home_requested = False
                return self.handle_message(
                    'Project compiled. No home node for this project')
        self.home_requested = False
        return self.open_node(self.settings['home'])
 
    def handle_message(self, message):
        print(message)
        if 'popup' in self.editor_methods:
            self.editor_methods['popup'](message)

    def all_nodes(self, as_nodes=False):

        def sort(nid, return_type=False):
            return self.nodes[nid].metadata.get_first_value(
                k, 
                use_timestamp=use_timestamp,
                return_type=return_type)

        remaining_nodes = list(self.nodes)
        sorted_nodes = []
        for k in self.settings['node_browser_sort']:
            use_timestamp = k in self.settings['use_timestamp']
            as_int = k in self.settings['numerical_keys']
            node_group = [
                r for r in remaining_nodes if (
                    r in self.nodes and self.nodes[r].metadata.get_first_value(k))]
            node_group = sorted(
                node_group, 
                key=lambda nid: sort(
                    nid, 
                    return_type=True), 
                reverse=k in self.settings['use_timestamp'])
            sorted_nodes.extend(node_group)
            remaining_nodes = list(set(remaining_nodes) - set(node_group))
        sorted_nodes.extend(remaining_nodes)
        if as_nodes:
            sorted_nodes = [
            self.nodes[nid] for nid in sorted_nodes if nid in self.nodes]
        return sorted_nodes

    def all_files(self):
        self._sync_file_list()
        files = list(self.files)
        prefix = 0
        sorted_files = []
        for k in self.settings['file_index_sort']:
            k = k.lower()
            use_timestamp = True if k in self.settings['use_timestamp'] else False
            file_group = [f for f in files if self.files[f].root_node and (
                    self.files[f].root_node.id in self.nodes) and (
                    self.nodes[self.files[f].root_node.id].metadata.get_first_value(
                        k, use_timestamp=use_timestamp))]
            file_group = sorted(file_group,
                key=lambda f: self.files[f].root_node.metadata.get_first_value(
                            k, use_timestamp=use_timestamp),
                            reverse=use_timestamp)
            sorted_files.extend(file_group)
            files = list(set(files) - set(sorted_files))
        sorted_files.extend(files)
        return sorted_files

    def get_node_id_from_position(self, filename, position):
        if filename in self.files:
            for node in self.files[filename].nodes:
                for r in node.ranges:           
                    if position in range(r[0],r[1]+1): # +1 in case the cursor is in the last position of the node.
                        return node.id

    def get_links_to(self, to_id):
        return [i for i in list(self.nodes) if to_id in self.nodes[i].links_ids()]

    def get_links_from(self, from_id):
        if from_id in self.nodes:
            return self.nodes[from_id].links_ids()
        return []

    def get_all_links(self):
        links = {}
        for node in self.nodes.values():
            links.setdefault(node.filename, [])
            links[node.filename].extend(node.links)
        return links

    def handle_link(self, 
        string, 
        col_pos=0,
        file_pos=0,
        return_target_only=False):

        link = self.parse_link(
            string, 
            col_pos=col_pos,
            file_pos=file_pos)
        
        if return_target_only: # for manual handling, e.g. Sublime Traverse, etc.
            return link

        if not link:
            if not self.compiled: message = "Project is still compiling"
            else: message = "No link"
            if 'error_message' in self.editor_methods:                
                return self.editor_methods['error_message'](message)
            return message

        if not link['kind']:
            if not self.compiled: return print('Project is still compiling')
            return print('No node ID, web link, or file found on this line.')

        if link['kind'] == 'NODE':
            if link['link'] not in self.nodes:
                if not self.compiled:
                    return print('Project is still compiling')
                else:
                    return print('Node ' + link['link'] + ' is not in the project')
            else:
                if 'open_file_to_position' in self.editor_methods:
                    self.editor_methods['open_file_to_position'](
                        link['filename'], link['dest_position'])
                    return self.visit_node(link['link'])

        if return_target_only:
            return link

        if link['kind'] == 'ACTION':

            if link['node_id'] not in self.nodes:
                if not self.compiled: return print('Project is still compiling')
                return print('Node ' + link['node_id'] + ' is not in the project')
            else:
                for dd in self.dynamic_defs(source=link['node_id']):
                    if dd.source_id == link['node_id']:
                        output = dd.process(flags=['-link_clicked'])
                        if output not in [False, None]:
                            for target in dd.targets:
                                target_output = dd.preserve_title_if_present(target) + output
                                self._direct_output(target_output, target, dd)
                            # TODO
                            # if modified_file:
                            #     modified_files.append(modified_file)
        if link['kind'] == 'SYSTEM':
            if 'open_external_file' in self.editor_methods:
                return self.editor_methods['open_external_file'](link['link'])

        if link['kind'] == 'EDITOR_LINK':
            if 'open_file_in_editor' in self.editor_methods:
                return self.editor_methods['open_file_in_editor'](link['link'])
        
        if link['kind'] == 'HTTP':
            if 'open_http_link' in self.editor_methods:
                return self.editor_methods['open_http_link'](link['link'])

        
        return link

    def parse_link(self, 
        string, 
        col_pos=0,
        file_pos=0):
      
        kind = ''
        link = ''
        dest_position = None
        result = None
        full_match = None
        filename = None
        
        action_only = syntax.node_action_link_c.search(string)
        if action_only:
            node_id = get_id_from_link(action_only.group())
            return {
                'kind' : 'ACTION', 
                'link' : link, 
                'node_id' : node_id,
                }

        link = syntax.node_link_or_pointer_c.search(string)
        if link:
            full_match = link.group()
            link = get_id_from_link(full_match)
            if link in self.nodes: result = link
            else:
                for node_id in self.nodes:
                    if node_id == link:
                        result = node_id
                        break
        node_id = ''
        if result:
            kind = 'NODE'
            node_id = result
            filename = self.nodes[node_id].filename
            link = result # node id
            dest_position = self.nodes[node_id].start_position()
        else:
            result = syntax.file_link_c.search(string)            
            if result:
                link = result.group(1).strip()
                kind = 'EDITOR_LINK'
                if os.path.splitext(link)[1][1:] in self.settings['open_with_system']:
                    kind = 'SYSTEM'           
            else:
                result = syntax.http_link_c.search(string)
                if result:
                    kind ='HTTP'
                    link = result.group(1).strip()
                    full_match = result.group()
        if result:
            return {
                'kind' : kind, 
                'link' : link, 
                'filename' : filename,
                'node_id' : node_id,
                'file_pos': file_pos, 
                'dest_position' : dest_position,
                'full_match' : full_match,
                }

    def get_node_contents(self, node_id):
        if node_id in self.nodes:
            return self.nodes[node_id].contents()
            
    def _is_duplicate_id(self, node_id):
        """ private method to check if a node id is already in the project """
        if node_id in self.nodes:
            return node_id
        for nid in list(self.nodes):
            if node_id == nid.split(syntax.parent_identifier)[0]:
                return nid
        return False

    def _log_item(self, filename, message):
        if filename and filename in self.files:
            self.messages.setdefault(filename, [])
            self.messages[filename].append(message)
        if self.settings['console_log']: print(str(filename)+' : '+ message)
        
    def timestamp(self, date=None, as_string=False):
        """ 
        Returns a timestamp in the format set in project_settings, or the default 
        """
        if date == None:
            date = datetime.datetime.now(
                datetime.timezone.utc
                ).astimezone()
        if as_string:
            return ''.join([
                syntax.timestamp_opening_wrapper,
                date.strftime(self.settings['timestamp_format']),
                syntax.timestamp_closing_wrapper,
                ])

        return UrtextTimestamp(
            date.strftime(self.settings['timestamp_format']))

    def _get_settings_from(self, node):
      
        replacements = {}
        for entry in node.metadata.all_entries():
   
            if entry.keyname in replace_settings:
                replacements.setdefault(entry.keyname, [])
                replacements[entry.keyname].append(entry.value)
                continue

            if entry.keyname == 'numerical_keys':
                self.settings['numerical_keys'].append(entry.value)
                continue

            if entry.keyname == 'file_extensions':
                value = entry.value
                if value[0] != '.':
                    value = '.' + value
                self.settings['file_extensions'] = ['.urtext'].append(value)
                continue

            if entry.keyname == 'recurse_subfolders':
                self.settings['paths'][0]['recurse_subfolders'] = True if entry.value.lower() in ['yes', 'true'] else False
                continue

            if entry.keyname == 'paths':
                if entry.is_node:
                    for n in entry.value.children:
                        path = n.metadata.get_first_value('path')
                        recurse = n.metadata.get_first_value('recurse_subfolders')
                        if path and path not in [entry['path'] for entry in self.settings['paths']]:
                            self.settings['paths'].append({
                                'path' : path,
                                'recurse_subfolders': True if recurse.lower() in ['yes', 'true'] else False
                                })
                continue

            if entry.keyname == 'other_entry_points':
                self.project_list.add_project(entry.value)

            if entry.keyname in single_values_settings:
                if entry.keyname in integers_settings:
                    try:
                        self.settings[entry.keyname] = int(entry.value)
                    except:
                        print(entry.value + ' not an integer')
                else:
                    self.settings[entry.keyname] = entry.value
                continue

            if entry.keyname in single_boolean_values_settings:
                self.settings[entry.keyname] = True if entry.value.lower() in ['true','yes'] else False
                continue          

            if entry.keyname not in self.settings:
                self.settings[str(entry.keyname)] = []

            self.settings[str(entry.keyname)].append(entry.value)
            self.settings[str(entry.keyname)] = list(set(self.settings[entry.keyname]))

        for k in replacements.keys():
            if k in single_values_settings:
                self.settings[k] = replacements[k][0]
            else:
                self.settings[k] = replacements[k]
            
    def get_home(self):
        if self.settings['home'] in self.nodes:
            return self.settings['home']

    def get_all_meta_pairs(self):
        pairs = []
        for n in list(self.nodes):
            for k in self.nodes[n].metadata.get_keys():
               values = self.nodes[n].metadata.get_values(k)
               if k == '#':
                    k = self.settings['hash_key']
               for v in values:
                    pairs.append(''.join([k, syntax.metadata_assignment_operator, str(v) ])  )

        return list(set(pairs))

    def random_node(self):
        if self.nodes:
            node_id = random.choice(list(self.nodes))
            self.open_node(node_id)
        return None
    
    def replace_links(self, original_id, new_id='', new_project=''):
        if not new_id and not new_project:
            return None
        replacement = '>'+original_id
        if new_id:
            replacement = '>'+new_id
        if new_project:
            replacement = '=>"'+new_project+'"'+replacement
        
        #TODO factor regexes out into syntax.py
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
                return self.execute(self._on_modified, filename)

    def on_modified(self, filename):
        if self.compiled:
            return self.execute(self._on_modified, filename)
        return []
    
    def _on_modified(self, filename):
        modified_files = []
        modified_files.append(filename)
        self._parse_file(filename)
        self._reverify_links(filename)
        if filename in self.files:
            modified_files.extend(
                self._compile_file(
                filename,
                events=['-file_update']))
        self._sync_file_list()
        if filename in self.files:
            for ext in self.extensions.values():
                ext.on_file_modified(filename)
        self._refresh_modified_files(modified_files)
        return modified_files
        
    def visit_node(self, node_id):
        return self.execute(self._visit_node, node_id)

    def _visit_node(self, node_id):
        for ext in list(self.extensions.values()):
            ext.on_node_visited(node_id)
        for dd in list(self.dynamic_definitions):
            for op in dd.operations:
                op.on_node_visited(node_id)        
        modified_files = self.visit_file(self.nodes[node_id].filename)
        self._refresh_modified_files(modified_files)
        return modified_files

    def visit_file(self, filename):
        return self.execute(self._visit_file, filename)

    def _visit_file(self, filename):
        """
        Call whenever a file requires dynamic updating
        """        
        if filename in self.files and self.compiled:
            modified_files = self._compile_file(
                filename, 
                events=['-file_visited'])
            self._refresh_modified_files(modified_files)
            return modified_files

    def _sync_file_list(self):
        included_files = self._get_included_files()
        current_files = list(self.files)
        for file in [f for f in included_files if f not in current_files]:
            self._parse_file(file)
        for file in [f for f in list(self.files) if f not in included_files]: # now list of dropped files
            self._log_item(file, file+' no longer seen in project path. Dropping it from the project.')
            self._drop_file(file)

    def _get_included_files(self):
        files = []
        for path in self.settings['paths']:
            files.extend([os.path.join(path['path'], f) for f in os.listdir(path['path'])])
            if 'recurse_subfolders' in path and path['recurse_subfolders']:
                for dirpath, dirnames, filenames in os.walk(path['path']):
                    files.extend([os.path.join(dirpath, f) for f in filenames])
        return [f for f in files if self._include_file(f)]

    def _include_file(self, filename):
        if filename in self.excluded_files:
            return False
        if os.path.splitext(filename)[1] not in self.settings['file_extensions']:
            return False
        return True
    
    def _add_to_excluded_files(self, filename):
        if filename not in self.excluded_files:
            self.excluded_files.append(filename)    
    
    def add_file(self, filename):
        """ 
        parse syncronously so we can raise an exception
        if moving files between projects.
        """
        any_duplicate_ids = self._parse_file(filename)
        
        if any_duplicate_ids:
            self._log_item(filename, 'File moved but not added to destination project. Duplicate Nodes IDs shoudld be printed above.')
            raise DuplicateIDs()

        return self.execute(self._compile)

    def drop_file(self, filename):
        self.execute(self._drop_file, filename)
    
    def get_file_name(self, node_id):
        filename = None
        if node_id in self.nodes:
            filename = self.nodes[node_id].filename
        else:
            return None
        return filename

    def title_completions(self):
        return [
            (self.nodes[n].id, 
                ''.join(
                    [syntax.link_opening_wrapper,
                    self.nodes[n].id,
                    syntax.link_closing_wrapper,
                    ])) 
                for n in list(self.nodes)]

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
        for node in list(self.nodes.values()):
            keys.extend(node.metadata.get_keys(exclude=exclude)
            )
        return list(set(keys))

    def get_all_values_for_key(self, key, lower=False):
        entries = []
        for node in self.nodes.values():
            entries.extend(node.metadata.get_entries(key))
        values = [e.value_as_string() for e in entries]
        if lower:
            return list(set([v.lower() for v in values]))
        return list(set(values))

    def go_to_dynamic_definition(self, target_id):
        for dd in self.dynamic_definitions:
            if target_id in dd.target_ids:
                if 'open_file_to_position' in self.editor_methods:
                    self.editor_methods[
                        'open_file_to_position'](
                            self.nodes[dd.source_id].filename, 
                            self.get_file_position(
                                dd.source_id,
                                dd.position))
                    return self.visit_node(dd.source_id)

    def get_by_meta(self, key, values, operator):
        
        if isinstance(values,str):
            values = [values]
        results = []

        if operator in ['before','after']:
            
            compare_date = date_from_timestamp(values[0][1:-1])
            
            if compare_date:
                if operator == 'before':
                    results = [n for n in self.nodes.values() if default_date != n.metadata.get_date(key) < compare_date]
                if operator == 'after':
                    results = [n for n in self.nodes.values() if n.metadata.get_date(key) > compare_date != default_date ]

                return set(results)

            return set([])

        if key == '_contents' and operator == '?': # `=` not currently implemented
            for node in list(self.nodes.values()):
                if node.dynamic:
                    continue
                matches = []
                contents = node.content_only()
                lower_contents = contents.lower()           

                for v in values:
                    if v.lower() in lower_contents:
                        results.append(node.id)

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
                    results = results.union(
                        set(n for n in list(self.nodes) if n in self.nodes 
                            and self.nodes[n].metadata.get_values(k))
                        ) 
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
                        n for n in list(self.nodes) if (
                            n in self.nodes) and (
                            value in self.nodes[n].metadata.get_values(
                                k,
                                use_timestamp=use_timestamp))
                        ))
                else:
                    if isinstance(value, str):
                        value = value.lower()
                    results = results.union(set(
                        n for n in list(self.nodes) if n in self.nodes and value in self.nodes[n].metadata.get_values(
                            k,
                            use_timestamp=use_timestamp, 
                            lower=True)))
        
        return results

    def get_file_and_position(self, node_id):
        if node_id in self.nodes:
            filename = self.get_file_name(node_id)
            position = self.nodes[node_id].start_position()
            return filename, position
        return None, None

    def execute(self, function, *args, **kwargs):
        if self.compiled and not self.nodes:
            return
        if self.is_async:
            future = self.executor.submit(function, *args, **kwargs)
            return future
        else:    
            return function(*args, **kwargs)

    """ Project Compile """

    def _compile(self, events=['-project_compiled']):

        self._verify_links_globally()
        self._add_all_sub_tags()
        for file in list(self.files):
            self._compile_file(file, events=events)
        self._add_all_sub_tags()

    def _compile_file(self, filename, events=[]):
        modified_targets = []
        modified_files = []

        for node in self.files[filename].nodes:
            for dd in self.dynamic_defs(target=node.id, source=node.id):
                output = dd.process(flags=events)
                if output not in [False, None]:
                    for target in dd.targets:
                        targeted_output = dd.post_process(target, output)
                        modified_target = self._direct_output(targeted_output, target, dd)
                        modified_targets.append(modified_target)

        for target in modified_targets:
            if target in self.nodes:
                self.nodes[target].dynamic = True
                if self.nodes[target].filename not in modified_files:
                    modified_files.append(self.nodes[target].filename)

        return modified_files

    def _refresh_modified_files(self, files):
        if 'refresh_open_file' in self.editor_methods:
            for file in files:
                self.editor_methods['refresh_open_file'](file)

    def _direct_output(self, output, target, dd):

        node_link = syntax.node_link_or_pointer_c.match(target)
        if node_link:
            node_id = get_id_from_link(node_link.group())
            if node_id in self.nodes:
                self._set_node_contents(node_id, output)
                return node_id

        target_file = syntax.file_link_c.match(target)
        if target_file:
            filename = get_id_from_link(target_file)
            filename = os.path.join(self.entry_point, filename)
            #? TODO -- If the file is an export, need to make sure it is remembered
            # when parsed so duplicate titles can be avoided
            #self.exports[filename] = dynamic_definition
            with open(filename, 'w', encoding='utf-8' ) as f:
                f.write(output)
            return filename
        virtual_target = syntax.virtual_target_match_c.match(target)
        if virtual_target:
            virtual_target = virtual_target.group()
            if virtual_target == '@self':
                if self._set_node_contents(dd.source_id, output):
                    return dd.source_id
            if virtual_target == '@clipboard':
                if 'set_clipboard' in self.editor_methods:
                    return self.editor_methods['set_clipboard'](output)
            if virtual_target == '@next_line':
                if 'insert_at_next_line' in self.editor_methods:
                    return self.editor_methods['insert_at_next_line'](output)
            if virtual_target == '@log':
                return self._log_item(
                    None, 
                    output)
            if virtual_target == '@console':
                if 'write_to_console' in self.editor_methods:
                    return self.editor_methods['write_to_console'](output)
            if virtual_target == '@popup':
                if 'popup' in self.editor_methods:
                    return self.editor_methods['popup'](output)

        if target in self.nodes: #fallback
            self._set_node_contents(target, output)
            return target
        
    """ Metadata Handling """

    def tag_other_node(self, full_line, cursor, metadata={}, open_files=[]):
        return self.execute(
            self._tag_other_node, 
            full_line,
            cursor, 
            metadata=metadata, 
            open_files=open_files)
        
    def _tag_other_node(self, full_line, cursor, metadata={}, open_files=[]):
        """adds a metadata tag to a node programmatically"""
        
        link = self.parse_link(full_line, col_pos=cursor)
        if not link: return

        if metadata == {}:
            if len(self.settings['tag_other']) < 2: return None
            metadata = { self.settings['tag_other'][0] : self.settings['tag_other'][1] + ' ' + self.timestamp().wrapped_string }
        territory = self.nodes[link['node_id']].ranges
        metadata_contents = UrtextNode.build_metadata(metadata)

        filename = self.nodes[link['node_id']].filename
        full_file_contents = self.files[filename]._get_file_contents()
        tag_position = territory[-1][1]

        separator = '\n'
        if self.nodes[link['node_id']].compact:
            separator = ' '

        new_contents = ''.join([
            full_file_contents[:tag_position],
            separator,
            metadata_contents,
            separator,
            full_file_contents[tag_position:]])
        self.files[filename]._set_file_contents(new_contents)
        s = self.on_modified(filename)
        return s
 
    def _add_sub_tags(self, 
        entry,
        next_node=None,
        visited_nodes=None):

        if visited_nodes == None:
            visited_nodes = []
        if next_node:
            source_node_id = next_node
        else:
            source_node_id = entry.from_node

        if source_node_id not in self.nodes:
            return

        for child in self.nodes[source_node_id].children:
            
            uid = source_node_id + child.id
            if uid in visited_nodes:
                continue
            node_to_tag = child.id
            if node_to_tag not in self.nodes:
                visited_nodes.append(uid)
                continue

            if uid not in visited_nodes and not self.nodes[node_to_tag].dynamic:
                self.nodes[node_to_tag].metadata.add_entry(
                    entry.keyname, 
                    entry.value, 
                    from_node=entry.from_node, 
                    recursive=entry.recursive)
                if node_to_tag not in self.nodes[entry.from_node].target_nodes:
                    self.nodes[entry.from_node].target_nodes.append(node_to_tag)
            
            visited_nodes.append(uid)        
            
            if entry.recursive:
                self._add_sub_tags(
                    entry,
                    next_node=node_to_tag, 
                    visited_nodes=visited_nodes)

        for ext in self.extensions.values():
            ext.on_sub_tags_added(source_node_id, entry)

    def _remove_sub_tags(self, source_id):
        for target_id in self.nodes[source_id].target_nodes:
             if target_id in self.nodes:
                 self.nodes[target_id].metadata.clear_from_source(source_id) 

    def title(self):
        return self.settings['project_title'] 

    """ Editor Methods """

    def editor_insert_timestamp(self):
        if 'insert_text' in self.editor_methods:
            self.editor_methods['insert_text'](self.timestamp(as_string=True))

    def editor_copy_link_to_node(self, node_id):
        link = self.project_list.build_contextual_link(node_id) 
        if 'set_clipboard' in self.editor_methods:
            self.editor_methods['set_clipboard'](link)

class DuplicateIDs(Exception):
    """ duplicate IDS """
    def __init__(self):
        pass

""" 
Helpers 
"""

def make_link(string):
    return ''.join([
        syntax.link_opening_wrapper,
        string,
        syntax.link_closing_wrapper])

def match_compact_node(selection):
    return True if syntax.compact_node_c.match(selection) else False


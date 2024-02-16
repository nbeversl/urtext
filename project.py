import re
import datetime
import platform
import os
import random
import time
from time import strftime
import concurrent.futures
import threading
import importlib
import sys
from .url import url_match

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
    import Urtext.urtext.utils as utils
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
    import urtext.utils as utils

class UrtextProject:

    urtext_file = UrtextFile
    urtext_node = UrtextNode
    urtext_buffer = UrtextBuffer

    def __init__(self, 
        entry_point, 
        project_list=None, 
        editor_methods={},
        new_file_node=False):

        self.settings = default_project_settings()
        self.project_list = project_list
        self.entry_point = entry_point
        self.entry_path = None
        self.settings['project_title'] = self.entry_point # default
        self.editor_methods = editor_methods
        self.is_async = True
        #self.is_async = False # development
        self.time = time.time()
        self.last_compile_time = 0
        self.nodes = {}
        self.files = {}
        self.exports = {}
        self.messages = {}
        self.dynamic_definitions = {}
        self.virtual_outputs = {}
        self.dynamic_metadata_entries = []
        self.project_settings_nodes = {}
        self.extensions = {}
        self.directives = {}
        self.compiled = False
        self.excluded_files = []
        self.home_requested = False
        self.variables = {}
        self.executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1)        
        self.message_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1)
        self.execute(self._initialize_project, new_file_node=new_file_node)
    
    def _initialize_project(self, new_file_node=False):
        self.handle_info_message('Compiling Urtext project from %s' % self.entry_point)

        self._get_features_from_folder(os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'features'), None)
        self._get_features_from_folder(os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            'core'), None)
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
        else:
            return self.handle_error_message('Project path does not exist: %s' % self.entry_point)

        while len(self.settings['paths']) > num_paths or len(self.settings['file_extensions']) > num_file_extensions:
            num_paths = len(self.settings['paths'])
            num_file_extensions = len(self.settings['file_extensions'])
            for file in self._get_included_files():
                if file not in self.files:
                    self._parse_file(file)

        if len(self.nodes) == 0 and not new_file_node:
            return self.handle_error_message(
                '\n'.join([
                    'No Urtext files are in this folder.',
                    'To create one, press Ctrl-Shift-;'
                    ]))

        for node in self.nodes.values():
            node.metadata.convert_hash_keys()
            node.metadata.convert_node_links()

        self._mark_dynamic_nodes()
        
        self._compile() ## TODO fix
        if len(self.extensions) > 0 or len(self.directives) > 0:
            self._compile()

        self.compiled = True
        self.last_compile_time = time.time() - self.time
        self.time = time.time()
        self._run_hook('after_project_initialized')
        self.handle_info_message('"%s" compiled' % self.settings['project_title'])

    def _parse_file(self, filename, try_buffer=False):
        if self._filter_filenames(filename) == None:
            self._add_to_excluded_files(filename)
            return False

        buffer_contents = None
        if self.compiled and try_buffer:
            buffer_contents = self.run_editor_method(
                'get_buffer',
                filename)

        existing_file_ids = []
        if filename in self.files:
            existing_file_ids = [n.id for n in self.files[filename].get_ordered_nodes()]

        allocated_ids = []
        if try_buffer and buffer_contents:
            new_file = UrtextBuffer(self, filename, buffer_contents)
            new_file.filename = filename
            new_file.clear_messages_and_parse()
            for node in new_file.nodes:
                node.filename = filename
        else:
            new_file = self.urtext_file(filename, self)
        self._drop_file(filename)

        if not new_file.root_node:
            self._log_item(filename, '%s has no root node, dropping' % filename)
            self.excluded_files.append(filename)
            return False

        changed_ids = self._check_file_for_duplicates(
            new_file, 
            existing_file_ids=existing_file_ids)

        self.messages[new_file.filename] = new_file.messages

        if new_file.errors:
            return False

        if existing_file_ids:
            new_node_ids = [n.id for n in new_file.get_ordered_nodes()]
            if len(existing_file_ids) == len(new_node_ids):
                for index in range(0, len(existing_file_ids)): # existing links are all we care about
                    if existing_file_ids[index] == new_node_ids[index]:
                        continue # id stayed the same
                    else:
                        if new_node_ids[index] in existing_file_ids:
                            # proably only the order changed.
                            # don't have to do anything
                            continue
                        else:
                            # check each new id for similarity to the old one
                            changed_ids[existing_file_ids[index]] = new_node_ids[index]
                            # else:
                            #TODO try to map old to new.
        for node in new_file.nodes:
            self._add_node(node)

        for node in new_file.nodes:
            for child in node.children:
                child.parent = node

        self.files[new_file.filename] = new_file
        self._run_hook('on_file_added', filename)

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
                [self.nodes[target_node]],
                self.nodes[source_node],
                start_position=self.nodes[target_node].start_position,
                end_position=self.nodes[target_node].end_position,
                is_node=True)
            self.nodes[target_node].is_meta = True

        for node in new_file.nodes:            
            if node.title == 'project_settings':
                self._get_settings_from(node)     

            for dd in node.dynamic_definitions:
                dd.source_node = node
                self._add_dynamic_definition(dd)

            for entry in node.metadata.entries():
                entry.from_node = node
                if entry.tag_children:
                    self._add_sub_tags(entry)
                    self.dynamic_metadata_entries.append(entry)

        if self.compiled and changed_ids:
            for node_id in changed_ids:
                self._run_hook('on_node_id_changed',
                    node_id,
                    changed_ids[node_id])
            self._rewrite_changed_links(changed_ids)

        return new_file

    def _verify_links_globally(self):
        links = self.get_all_links()
        for filename in links:
            self._reverify_links(filename)

    def _reverify_links(self, filename):
        if filename in self.files:
            for node in [n for n in self.files[filename].nodes if not n.dynamic]:
                rewrites = {}
                for link in node.links:
                    if syntax.project_link_with_node_c.match(link):
                        # skip links to other projects
                        continue
                    node_id = utils.get_id_from_link(link)
                    suffix = ' ' +link[-2:].strip() # preserve link/pointer                        
                    if node_id not in self.nodes:
                        title_only = node_id.split(syntax.resolution_identifier)[0]                
                        if title_only not in self.nodes and link not in rewrites:
                            rewrites[link] = ''.join([
                                syntax.missing_link_opening_wrapper,
                                title_only,
                                suffix
                            ])
                        elif link not in rewrites:
                            rewrites[link] = ''.join([
                                syntax.link_opening_wrapper,
                                title_only,
                                suffix])
                    elif syntax.missing_link_opening_wrapper in link:
                        rewrites[link] = ''.join([
                                syntax.link_opening_wrapper,
                                node_id,
                                suffix
                            ])
                if rewrites:
                    contents = self.files[filename]._get_contents()
                    for old_link in rewrites:
                        contents = contents.replace(old_link, rewrites[old_link])
                    self.files[filename]._set_contents(contents)

    def _add_all_sub_tags(self):
        for entry in self.dynamic_metadata_entries:
            self._add_sub_tags(entry)

    def _rewrite_changed_links(self, changed_ids):
        for old_id in list(changed_ids.keys()):
            new_id = changed_ids[old_id]
            if new_id in self.nodes:
                for project_node in [n for n in self.nodes.values() if not n.dynamic]:
                    if project_node.id not in self.nodes:
                        continue
                    links_to_change = {}
                    for link in project_node.links:
                        link = utils.get_id_from_link(link)
                        if link == old_id:
                            links_to_change[link] = new_id
                    if links_to_change:
                        contents = self.files[project_node.filename]._get_contents()
                        for node_id in list(links_to_change.keys()):
                            replaced_contents = contents
                            node_id_regex = re.escape(node_id)
                            replaced_contents = re.sub(''.join([
                                    syntax.node_link_opening_wrapper_match,
                                    node_id_regex,
                                    syntax.link_closing_wrapper
                                ]),
                                make_link(links_to_change[node_id]), replaced_contents)
                            if replaced_contents != contents:
                                self._run_hook(
                                    'on_node_id_changed',
                                    node_id,
                                    links_to_change[node_id])
                                self.files[project_node.filename]._set_contents(
                                    replaced_contents)

    def _check_file_for_duplicates(self, file_obj, existing_file_ids=[]):
        messages = []
        changed_ids = {}

        # resolve '(untitled)' nodes
        for node in [f for f in file_obj.nodes if f.title == '(untitled)']:
            resolved_id = node.resolve_id()
            if not resolved_id:
                message = ''.join([
                    'Dropping untitled ID. ',
                    'Cannot be resolved; timestamp or parent title exists in another node',
                    ])
                self._log_item(file_obj.filename, message)
                messages.append(message)
                file_obj.nodes.remove(node)
                continue
            changed_ids[node.id] = resolved_id
            node.id = resolved_id

        # resolve duplicate titles within file/buffer
        new_file_node_ids = [file_node.id for file_node in file_obj.nodes]
        nodes_to_resolve = [n for n in file_obj.nodes if new_file_node_ids.count(n.title) > 1]
        for n in nodes_to_resolve:
            resolved_id = n.resolve_id(allocated_ids=[file_node.id for file_node in file_obj.nodes])
            if not resolved_id:
                message = ''.join([
                    'Dropping duplicate node title "',
                    n.title,
                    '"',
                    ' duplicated in the same file. Unable to resolve.'
                    ])
                self._log_item(file_obj.filename, message)
                messages.append(message)
                file_obj.nodes.remove(n)
                continue
            changed_ids[n.id] = resolved_id
            n.id = resolved_id

        # resolve duplicate titles in project
        new_file_node_ids = [file_node.id for file_node in file_obj.nodes]
        allocated_ids = [n for n in self.nodes if n not in new_file_node_ids]
        for node in file_obj.get_ordered_nodes():
            duplicate_titled_node = self._find_duplicate_title(node)
            if duplicate_titled_node:
                resolved_id = node.resolve_id(
                    allocated_ids=allocated_ids)
                if not resolved_id:
                    message = ''.join([
                            'Dropping duplicate node ID "',
                            node.id,
                            '"',
                            ' already exists in file ',
                            syntax.file_link_opening_wrapper,
                            duplicate_titled_node.filename,
                            syntax.link_closing_wrapper,
                            ])
                    file_obj.nodes.remove(node)
                    self._log_item(file_obj.filename, message)
                    messages.append(message)
                else:
                    changed_ids[node.id] = resolved_id
                    node.id = resolved_id
        if messages:
            file_obj.write_messages(messages=messages)
            file_obj.errors = True
        else:
            file_obj.errors = False
        return changed_ids

    def _add_dynamic_definition(self, definition):
        for target_id in definition.target_ids:
            if target_id in self.dynamic_definitions:
                self._reject_definition(target_id, definition)
            else:
                self.dynamic_definitions[target_id] = definition 

        for target in definition.targets:
            if target in self.nodes: # allow not using link syntax
                if target in self.dynamic_definitions:
                    self._reject_definition(target, definition)
                else:
                    self.dynamic_definitions[target] = definition
                    continue
            virtual_target = syntax.virtual_target_match_c.match(target)
            if virtual_target:
                target = virtual_target.group()
                if target == "@self":
                    if definition.source_node.id in self.dynamic_definitions:
                        self._reject_definition(definition.source_node.id, definition)
                    else:
                        self.dynamic_definitions[definition.source_node.id] = definition
                else:
                    self.virtual_outputs.setdefault(target, [])
                    self.virtual_outputs[target].append(definition)

    def _reject_definition(self, target_id, definition):
        message = ''.join([
                '\nDynamic node ', 
                syntax.link_opening_wrapper,
                target_id,
                syntax.link_closing_wrapper,
                '\nalready has a definition in ', 
                syntax.link_opening_wrapper,
                self.dynamic_definitions[target_id].source_node.id,
                syntax.link_closing_wrapper,
                '\n in file ',
                syntax.file_link_opening_wrapper,
                self.dynamic_definitions[target_id].source_node.filename,
                syntax.link_closing_wrapper,
                '\nskipping the definition in ',
                syntax.link_opening_wrapper,
                definition.source_node.id,
                syntax.link_closing_wrapper,
            ])
        self._log_item(
            self.nodes[definition.source_node.id].filename, 
            message)

    def _add_node(self, new_node):
        new_node.project = self
        self.nodes[new_node.id] = new_node  
        if self.compiled:
            new_node.metadata.convert_node_links()   
        self._run_hook('on_node_added', new_node)
        
    def get_source_node(self, filename, position): # future
        if filename not in self.files:
            return None, None
        exported_node_id = self.get_node_id_from_position(filename, position)
        points = self.nodes[exported_node_id].export_points
        if not points:
            return None, None
        node_start_point = self.nodes[exported_node_id].start_position

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
        if node_id in self.nodes:
            if self.nodes[node_id].set_content(contents, run_on_modified=False):
                if node_id in self.nodes:
                    self._parse_file(self.nodes[node_id].filename)
                    if node_id in self.nodes:
                        return self.nodes[node_id].filename
        return False



    def _mark_dynamic_nodes(self):
        for target in self.dynamic_definitions:
            if target in self.nodes:
                self.nodes[target].dynamic = True

    """
    Removing and renaming files
    """
    def _drop_file(self, filename):
        if filename in self.files:
            for dd in self.dynamic_definitions.values():
                for op in dd.operations:
                    op.on_file_dropped(filename)

            self._run_hook('on_file_dropped', filename)

            for node in list(self.files[filename].nodes):
                self._drop_node(node)
                
            del self.files[filename]

        if filename in self.messages:
            self.messages[filename] = []

    def _drop_node(self, node):
        if node.id in self.nodes:
            self._remove_sub_tags(node.id)
            self._remove_dynamic_defs(node.id)
            self._remove_dynamic_metadata_entries(node.id)
            self._clear_settings_from(node)
            del self.nodes[node.id]


    def delete_file(self, filename):
        return self.execute(
            self._delete_file, 
            filename)

    def _delete_file(self, filename):
        """
        Deletes a file, removes it from the project,
        """
        self.run_editor_method('close_file', filename)
        self._drop_file(filename)
        os.remove(filename)
        if filename in self.messages:
            del self.messages[filename]
        self._run_hook('on_file_deleted', filename)

    def _handle_renamed(self, old_filename, new_filename):
        if new_filename != old_filename:
            self.files[new_filename] = self.files[old_filename]
            for node in self.files[new_filename].nodes:
                self.nodes[node.id].filename = new_filename
                self.files[new_filename].filename = new_filename
            del self.files[old_filename]
            self._run_hook(
                'on_file_renamed', 
                old_filename, 
                new_filename)
    
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
        one_line=None,
        open_file=True):

        contents_format = None
        if contents == None:
            contents_format = bytes(
                self.settings['new_file_node_format'], 
                "utf-8"
                ).decode("unicode_escape")

        filename = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        new_node_contents, node_id, cursor_pos = self._new_node(
            date=date,
            contents=contents,
            contents_format=contents_format,
            metadata=metadata)
        
        filename = filename + '.urtext'
        if path:
            filename = os.path.join(path, filename)
        else:
            filename = os.path.join(self.entry_path, filename)
        utils.write_file_contents(filename, new_node_contents)
        new_file = self.urtext_file(filename, self)
        
        duplicates = self._check_file_for_duplicates(new_file)
        if new_file.errors and 'timestamp or parent title exists in another node' in new_file.messages[0]:
            if contents == None:
                new_node_contents, node_id, cursor_pos = self._new_node(
                    date=date,
                    contents=contents,
                    add_seconds_to_timestamp=True,
                    contents_format=contents_format,
                    metadata=metadata)
            utils.write_file_contents(filename, new_node_contents)
            new_file = self.urtext_file(filename, self)
            duplicates = self._check_file_for_duplicates(new_file)

        self._parse_file(filename)

        if filename in self.files:
            #TODO possibly should be sent in a thread:
            self._run_hook('on_new_file_node', 
                self.files[filename].root_node.id)

            if open_file:
                self.open_node(self.files[filename].root_node.id,
                    position=cursor_pos)

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
        add_seconds_to_timestamp=False,
        metadata=None,
        one_line=None):

        cursor_pos = 0
        if contents == None:
            contents = ''

        if contents_format:
            new_node_contents = contents_format.replace(
                '$timestamp',
                self.timestamp(add_seconds=add_seconds_to_timestamp).wrapped_string)
            new_node_contents = new_node_contents.replace(
                '$device_keyname',
                platform.node())
            if '$cursor' in new_node_contents:
                new_node_contents = new_node_contents.split('$cursor')
                cursor_pos = len(new_node_contents[0]) -1
                new_node_contents = title + ''.join(new_node_contents)
                if cursor_pos < len(new_node_contents) - 1:
                    new_node_contents += ' ' 
        else:
            if one_line == None:
                one_line = self.settings['always_oneline_meta']
            
            if not metadata:
                metadata = {}

            if self.settings['device_keyname']:
                metadata[self.settings['device_keyname']] = platform.node()

            new_node_contents = contents
            new_node_contents += self.urtext_node.build_metadata(metadata, one_line=one_line)

        return new_node_contents, title, cursor_pos

    def add_compact_node(self,  
            contents='',
            metadata={}):
            metadata_block = self.urtext_node.build_metadata(metadata, one_line=True)
            if metadata_block:
                metadata_block = ' ' + metadata_block
            return '• ' + contents.strip() + metadata_block

    def get_dynamic_defs(self, 
        target_node=None, 
        source_node=None):
        defs = []
        if target_node and target_node.id in self.dynamic_definitions:
            defs.append(self.dynamic_definitions[target_node.id])
        if source_node:
            for dd in self.dynamic_definitions.values():        
                if dd.source_node.id == source_node.id:
                    defs.append(dd)
        for target in self.virtual_outputs:
            for dd in self.virtual_outputs[target]:
                if source_node and dd.source_node.id == source_node.id:
                    defs.append(dd)
                elif not source_node:
                    defs.append(dd)
        return defs

    def _remove_dynamic_defs(self, node_id):
        for target in list(self.dynamic_definitions):
            if self.dynamic_definitions[target].source_node.id == node_id:
                del self.dynamic_definitions[target]
        for target in self.virtual_outputs:
            for dd in self.virtual_outputs[target]:
                if dd.source_node.id == node_id:
                    self.virtual_outputs[target].remove(dd)

    def _remove_dynamic_metadata_entries(self, node_id):
        for entry in list(self.dynamic_metadata_entries):
            if entry.from_node == self.nodes[node_id]:
                self.dynamic_metadata_entries.remove(entry)

    def open_node(self, node_id, position=None):
        if node_id not in self.nodes:
            if self.compiled:
                message = node_id + ' not in current project'
            else:
                message = 'Project is still compiling' 
            return self.handle_info_message(message)

        node_range = (
            self.nodes[node_id].ranges[0][0],
            self.nodes[node_id].ranges[-1][1])
        
        if position == None:
            position = self.nodes[node_id].start_position

        self.run_editor_method(
            'open_file_to_position',
            self.nodes[node_id].filename,
            position,
            node_range=node_range
            )
        return self.visit_node(node_id)

    def open_home(self):
        if not self.get_home():
            if not self.compiled:
                if not self.home_requested:
                    self.message_executor.submit(
                        self.handle_info_message,
                        'Project is compiling. Home will be shown when found.')
                    self.home_requested = True
                timer = threading.Timer(.5, self.open_home)
                return timer.start()
            else:
                self.home_requested = False
                return self.handle_info_message(
                    'Project compiled. No home node for this project')
        self.home_requested = False
        return self.open_node(self.settings['home'])
 
    def handle_info_message(self, message):
        self.run_editor_method('popup', message)

    def handle_error_message(self, message):
        self.run_editor_method('error_message', message)

    def sort_for_node_browser(self, nodes=None, as_nodes=False):
        if not nodes:
            nodes = list(self.nodes.values())
        return self._sort_nodes(
            nodes,
            self.settings['node_browser_sort'],
            as_nodes=as_nodes)

    def has_meta_browser_key(self):
        return 'meta_browser_key' in self.settings and self.settings['meta_browser_key']

    def sort_for_meta_browser(self, nodes, as_nodes=False):
        if self.has_meta_browser_key():
            nodes = [n for n in nodes if n.metadata.get_first_value(
                self.settings['meta_browser_key'])]
            return self._sort_nodes(
                nodes,
                [self.settings['meta_browser_key']],
                as_nodes=as_nodes)
        return self._sort_nodes(
            nodes,
            self.settings['meta_browser_sort'],
            as_nodes=as_nodes)

    def _sort_nodes(self, nodes, keys, as_nodes=False):
        remaining_nodes = nodes
        sorted_nodes = []
        for k in keys:
            use_timestamp = k in self.settings['use_timestamp']
            node_group = [
                r for r in remaining_nodes if r.metadata.get_first_value(
                    k,
                    use_timestamp=use_timestamp) != None]
            if node_group:
                node_group = sorted(
                    node_group,
                    key=lambda node: node.metadata.get_first_value(
                        k,
                        use_timestamp=use_timestamp),
                    reverse=use_timestamp)
                for node in node_group:
                    detail = node.metadata.get_first_value(
                        k,
                        use_timestamp=use_timestamp)
                    if use_timestamp:
                        node.display_detail = detail.wrapped_string
                    else:
                        node.display_detail = k+'::'+str(detail)
                sorted_nodes.extend(node_group)
        sorted_nodes.extend([r for r in remaining_nodes if r not in sorted_nodes])  
        if not as_nodes:
            return [n.id for n in sorted_nodes]      
        return sorted_nodes

    def get_node_id_from_position(self, filename, position):
        if filename in self.files:
            for node in self.files[filename].nodes:
                for r in node.ranges:           
                    if position in range(r[0],r[1]+1): # +1 in case the cursor is in the last position of the node.
                        return node.id

    def get_links_to(self, to_id, as_nodes=False):
        links_to = [i for i in list(self.nodes) if to_id in self.nodes[i].links_ids()]
        if as_nodes:
            return [self.nodes[n] for n in links_to]
        return links_to

    def get_links_from(self, from_id, as_nodes=False):
        if from_id in self.nodes:
            links = self.nodes[from_id].links_ids()
            links_from = [l for l in links if l in self.nodes]
            if as_nodes:
                return [self.nodes[n] for n in links_from]
            return links_from
        return []

    def get_all_links(self):
        links = {}
        for node in self.nodes.values():
            links[node.filename] = links.get(node.filename, [])
            links[node.filename].extend(node.links)
        return links

    def handle_link(self, 
        string,
        filename,
        col_pos=0):

        link = self.parse_link(
            string,
            filename,
            col_pos=col_pos)

        if not link:
            if not self.compiled:
                message = "Project is still compiling"
            else:
                message = "No link"
            return self.handle_info_message(message)

        if not link['kind']:
            if not self.compiled:
                return self.handle_info_message(
                    'Project is still compiling')
            return self.handle_info_message(
                'No link found')

        if link['kind'] == 'MISSING':
            if not self.compiled:
                self.handle_info_message(
                    'Project is still compiling')
            return self.handle_info_message( 
                'Link is not in the project.')

        if link['kind'] == 'NODE':
            return self.open_node(
                link['node_id'],
                position=link['dest_position'])

        if link['kind'] == 'ACTION':
            if link['node_id'] not in self.nodes:
                if not self.compiled:
                    return self.handle_info_message(
                        'Project is still compiling')
                return self.handle_info_message(
                    'Node ' + link['node_id'] + ' is not in the project')
            else:
                if link['node_id'] in self.nodes:
                    for dd in self.get_dynamic_defs(source_node=self.nodes[link['node_id']]):
                        if dd.source_node.id == link['node_id']:
                            output = dd.process(flags=['-link_clicked'])
                            if output not in [False, None]:
                                for target in dd.targets:
                                    target_output = dd.preserve_title_if_present(target) + output
                                    self._direct_output(target_output, target, dd)
        if link['kind'] == 'FILE':
            if os.path.exists(link['link']):
                return self.run_editor_method(
                    'open_external_file', 
                    link['link'])            
            else:
                return self.run_editor_method(
                    'open_external_file', 
                    os.path.join(self.entry_path, link['link']))
        
        if link['kind'] == 'HTTP':
            return self.run_editor_method('open_http_link', link['link'])

        return link

    def parse_link(self, 
        string,
        filename,
        col_pos=0,
        try_buffer=True,
        file_pos=None):

        kind = None
        urtext_link = None
        http_link = None
        node_id = None
        dest_position = None
        full_match = None
        return_link = None
        link_start = None
        link_end = None

        self._parse_file(filename, try_buffer=try_buffer)

        http_link_present = False
        http_link = url_match(string)
        if http_link:
            if col_pos <= http_link.end():
                http_link_present = True
                link_start = http_link.start()
                link_end = http_link.end()
                http_link = full_match = http_link.group().strip()

        for match in syntax.any_link_or_pointer_c.finditer(string):
            if col_pos <= match.end():
                if http_link_present and (
                    link_end < match.end()) and (
                    link_end < match.start()):
                    break
                urtext_link = match.group()
                link_start = match.start()
                link_end = match.end()
                full_match = match.group()
                break

        if http_link and not urtext_link:
            kind ='HTTP'
            return_link = http_link

        if urtext_link:
            return_link = urtext_link
            if urtext_link[1] in syntax.link_modifiers.values():
                for kind in syntax.link_modifiers:
                    if urtext_link[1] == syntax.link_modifiers[kind]:
                        kind = kind.upper()
                        break
            else:
                kind = 'NODE'
                node_id = utils.get_id_from_link(full_match)
                if node_id in self.nodes:
                    if match.group(8):
                        dest_position = self.nodes[node_id].start_position + int(match.group(8)[1:])
                    else:
                        dest_position = self.nodes[node_id].start_position
                    filename = self.nodes[node_id].filename
                else:
                    kind = 'MISSING'
            if kind == 'FILE':
                return_link = return_link[2:-2].strip()
                if return_link[0] == '~':
                    return_link = os.path.expanduser(return_link)

        return {
            'kind' : kind, 
            'link' : return_link, 
            'filename' : filename,
            'node_id' : node_id,
            'link_start_position': link_start,
            'link_end_position': link_end,
            'dest_position' : dest_position,
            'full_match' : full_match,
            }
            
    def _is_duplicate_id(self, node_id):
        return node_id in self.nodes

    def _find_duplicate_title(self, node):
        for n in list(self.nodes):
            if n.title == node.title:
                return node

    def _log_item(self, filename, message):
        self.messages.setdefault(filename, [])
        if message not in self.messages[filename]:
            self.messages[filename].append(message)
        if self.compiled and self.settings['console_log']:
            print(str(filename)+' : '+ message)

    def timestamp(self, date=None, as_string=False, add_seconds=False):
        """ 
        Returns a timestamp in the format set in project_settings, or the default 
        """
        if date == None:
            date = datetime.datetime.now(
                datetime.timezone.utc
                ).astimezone()
        ts_format = self.settings['timestamp_format']
        if add_seconds:
            if '%' in self.settings['timestamp_format'] and '%S' not in self.settings['timestamp_format']:
                ts_format = ts_format.replace('%M', '%M:%S')
        if as_string:
            return ''.join([
                syntax.timestamp_opening_wrapper,
                date.strftime(ts_format),
                syntax.timestamp_closing_wrapper,
                ])

        return UrtextTimestamp(
            date.strftime(ts_format))

    def _get_settings_from(self, node):

        self._clear_settings_from(node)
        self.project_settings_nodes[node] = {}
        replacements = {}
        for entry in node.metadata.entries():
   
            if self.compiled and entry.keyname in evaluated_only_at_compile:
                continue

            self.project_settings_nodes[node][entry.keyname] = entry.text_values()

            if entry.keyname in replace_settings:
                replacements[entry.keyname] = [e for e in entry.text_values()]
                continue

            if entry.keyname == 'numerical_keys':
                self.settings['numerical_keys'].extend([ 
                    e for e in entry.text_values() if e not in self.settings['numerical_keys']])
                continue

            if entry.keyname == 'file_extensions':
                for value in entry.text_values():
                    if value[0] != '.':
                        value = '.' + value
                    self.settings['file_extensions'] = ['.urtext'].append(value)
                continue

            if entry.keyname == 'recurse_subfolders':
                values = entry.text_values()
                if values and self.settings['paths']:
                    self.settings['paths'][0]['recurse_subfolders'] = to_boolean(values[0])
                continue

            if entry.keyname == 'paths':
                if entry.is_node:
                    for n in entry.meta_values[0].children:
                        path = n.metadata.get_first_value('path')
                        recurse = n.metadata.get_first_value('recurse_subfolders')
                        if path and path not in [entry['path'] for entry in self.settings['paths']]:
                            self.settings['paths'].append({
                                'path': path,
                                'recurse_subfolders': True if recurse.lower() in ['yes', 'true'] else False
                            })
                continue

            if entry.keyname == 'other_entry_points':
                for v in entry.text_values():
                    self.project_list.add_project(v)
                continue

            if entry.keyname == 'features':
                for v in entry.text_values():
                    self._get_features_from_folder(
                        v,
                        self.nodes[node.id].filename)
                continue

            if entry.keyname in single_values_settings:
                for v in entry.text_values():
                    if entry.keyname in integers_settings:
                        try:
                            self.settings[entry.keyname] = int(v)
                        except:
                            self._log_item(
                                entry.filename,
                                'In dynamic definition, "' + v + '" is not an integer')
                    else:
                        self.settings[entry.keyname] = v
                continue

            if entry.keyname in single_boolean_values_settings:
                values = entry.text_values()
                if values:
                    self.settings[entry.keyname] = to_boolean(values[0])
                continue

            if entry.keyname not in self.settings:
                self.settings[str(entry.keyname)] = []
                if entry.meta_values[0].is_node:
                    self.settings[str(entry.keyname)] = entry.meta_values[0]
                else:
                    self.settings[str(entry.keyname)].extend(entry.text_values())
                continue

        for k in replacements.keys():
            if k in single_values_settings:
                self.settings[k] = replacements[k][0]
            else:
                self.settings[k] = replacements[k]

    def _clear_settings_from(self, node):
        if node in self.project_settings_nodes:
            for setting in self.project_settings_nodes[node]:
                if setting in not_cleared:
                    continue
                for value in self.project_settings_nodes[node][setting]:
                    if not self._setting_is_elsewhere(
                        setting,
                        node) and ( 
                        setting in self.settings):
                            if setting in single_values_settings:
                                del self.settings[setting]                     
                            elif type(value) not in [str, int, float]:
                                del self.settings[setting]
                            elif isinstance(self.settings[setting], UrtextNode):
                                del self.settings[setting]
                            elif value in self.settings[setting]:
                                self.settings[setting].remove(value)                        
                            if setting == 'features':
                                for v in entry.text_values():
                                    self._remove_features_from_folder(v)
                            if (setting not in self.settings or 
                                not self.settings[setting]) and (
                                setting in default_project_settings().keys()):
                                self.settings[setting] = default_project_settings()[setting]
            del self.project_settings_nodes[node]

    def _setting_is_elsewhere(self, setting, omit_node):
        for node_id in [n for n in self.project_settings_nodes if n != omit_node]:
            if setting in self.project_settings_nodes[node_id]:
                return True

        return False

    def _get_features_from_folder(self, folder, filename):
        if os.path.exists(folder):
            sys.path.append(folder)
            for module_file in [f for f in os.listdir(folder) if f.endswith(".py")]:
                try:
                    s = importlib.import_module(module_file.replace('.py',''))
                    if 'urtext_directives' in dir(s):
                        directives = s.urtext_directives
                        if not isinstance(directives, list):
                            directives = [directives]
                        for d in directives:
                            self.add_directive(d, folder=folder)
                    if 'urtext_extensions' in dir(s):
                        extensions = s.urtext_extensions
                        if not isinstance(extensions, list):
                            extensions = [extensions]
                        for e in extensions:
                            self.add_extension(e, folder=folder)
                except Exception as e:
                    message = ''.join([
                            '\nFeature in file ',
                            syntax.file_link_opening_wrapper,
                            os.path.join(folder, module_file),
                            syntax.link_closing_wrapper,
                            ' encountered the following error: \n', 
                            str(e),
                            ])
                    print(message)
                    self._log_item(
                        filename, 
                        message)

    def _remove_features_from_folder(self, folder):
        for directive in self.directives.values():
            if directive.folder == folder:
                for n in directive.name:
                    self.directives.remove(n)
        for extension in self.extensions.values():
            if extension.folder == folder:
                for n in extension.name:
                    self.extensions.remove(n)

    def get_home(self):
        if self.settings['home'] in self.nodes:
            return self.settings['home']

    def get_all_meta_pairs(self):
        pairs = []
        for n in self.nodes.values():
            for k in n.metadata.get_keys().keys():
                values = n.metadata.get_values(k)
                assigner = syntax.metadata_assignment_operator
                if k == self.settings['hash_key']:
                    k = '#'
                    assigner = ''                 
                for v in values:
                    if v.is_node:
                        pairs.append(make_link(v.id))
                    else:
                        pairs.append(''.join([
                            k,
                            assigner,
                            v.text, # num would need to be converted to text anyway
                            ]))

        return list(set(pairs))

    def random_node(self):
        if self.nodes:
            node_id = random.choice(list(self.nodes))
            self.open_node(node_id)
        return None
    
    def replace_links(self, original_id, new_id='', new_project=''):
        if not new_id and not new_project:
            return None
        if not new_id:
            new_id = original_id
        pattern_to_replace = r''.join([
                syntax.node_link_opening_wrapper_match,
                original_id,
                syntax.link_closing_wrapper
            ])
        if new_id:
            replacement = ''.join([
                syntax.link_opening_wrapper,
                new_id,
                syntax.link_closing_wrapper
                ])
        if new_project:
            replacement = ''.join([
                syntax.other_project_link_prefix,
                '"',new_project,'"',
                syntax.link_opening_wrapper,
                new_id,
                syntax.link_closing_wrapper,
            ])
        for filename in list(self.files):
            to_replace = pattern_to_replace
            new_contents = self.files[filename]._get_contents()
            for pointer in re.finditer(to_replace+'>', new_contents):
                new_contents = new_contents.replace(pointer.group(), replacement, 1)
            for link in re.finditer(to_replace, new_contents):
                new_contents = new_contents.replace(link.group(), replacement, 1)
            self.files[filename]._set_contents(new_contents)

    def on_modified(self, filename, bypass=False):
        return self.execute(self._on_modified, filename, bypass=bypass)
    
    def _on_modified(self, filename, bypass=False):
        if self.compiled and filename in self._get_included_files():
            if self._parse_file(filename):
                modified_files = [filename]
                if filename in self.files:
                    modified_files.extend(
                        self._compile_file(
                        filename,
                        events=['-file_update']))
                self._reverify_links(filename)
                self._sync_file_list()
                if filename in self.files:
                    self._run_hook('on_file_modified', filename)
                return modified_files
        
    def visit_node(self, node_id):
        return self.execute(self._visit_node, node_id)

    def _visit_node(self, node_id):
        if node_id in self.nodes and self.compiled:
            filename = self.nodes[node_id].filename
            self._run_hook('on_node_visited', node_id)
            for dd in list(self.dynamic_definitions.values()):
                for op in dd.operations:
                    op.on_node_visited(node_id)
            self._visit_file(filename)
            self.run_editor_method('status_message',
                ''.join([
                    'UrtextProject:',
                    self.title(),
                    ' (compiled)'
                    ]))

    def visit_file(self, filename):
        return self.execute(
            self._visit_file, 
            filename)

    def _visit_file(self, filename):
        if filename in self.files and self.compiled:
            modified_files = self._compile_file(
                filename, 
                events=['-file_visited'])
            return modified_files

    def _sync_file_list(self):
        included_files = self._get_included_files()
        for file in included_files:
            if file not in self.files:
                self._parse_file(file)
        for file in [f for f in list(self.files) if f not in included_files]:
            self._log_item(
                file,
                file+' no longer seen in project path. Dropping it from the project.')
            self._drop_file(file)

    def _get_included_files(self):
        files = []
        for path in self.settings['paths']:
            files.extend([os.path.join(path['path'], f) for f in os.listdir(path['path'])])
            if 'recurse_subfolders' in path and path['recurse_subfolders']:
                for dirpath, dirnames, filenames in os.walk(path['path']):
                    if '/.git' in dirpath or '/_diff' in dirpath:
                        continue
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
            self._log_item(
                filename, 
                'File moved but not added to destination project. Duplicate Nodes IDs shoudld be printed above.')
            return
        return self.execute(self._compile_file(filename))

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

    def get_keys_with_frequency(self):
        key_occurrences = {}
        exclude = self.settings['exclude_from_star']
        exclude.extend(self.settings.keys())

        for node in list(self.nodes.values()):
            node_keys = node.metadata.get_keys(exclude=exclude)
            for key in node_keys:
                key_occurrences[key] = key_occurrences.get(key, 0)
                key_occurrences[key] += node_keys[key]

        return key_occurrences

    def get_all_keys(self):
        key_occurrences = self.get_keys_with_frequency()
        unique_keys = key_occurrences.keys()

        if self.settings['meta_browser_sort_keys_by'] == 'frequency':
            return sorted(
                unique_keys,
                key=lambda key: key_occurrences[key],
                reverse=True)
        else:
            return sorted(unique_keys)

    def get_all_values_for_key_with_frequency(self, 
        key,
        lower=False):

        values = {}
        for node in self.nodes.values():
            values_occurrences = node.metadata.get_values_with_frequency(key)
            for v in values_occurrences:
                values[v.text]= values.get(v.text, 0)
                values[v.text] += values_occurrences[v]

        return values

    def get_all_values_for_key(self, 
        key,
        lower=False,
        substitute_timestamp=True):

        """
        return tuple of (value.text, value.timestamp)
        """

        values_occurrences = self.get_all_values_for_key_with_frequency(key)
        values = values_occurrences.keys()
        if self.settings['meta_browser_sort_values_by'] == 'frequency':
            return sorted(
                values,
                key=lambda value: values_occurrences[value],
                reverse=True)

        return sorted(values)

    def go_to_dynamic_definition(self, target_id):
        if target_id in self.dynamic_definitions:
            dd = self.dynamic_definitions[target_id]
            self.run_editor_method(
                'open_file_to_position',
                self.nodes[dd.source_node.id].filename,
                self.nodes[dd.source_node.id].get_file_position(dd.position))
            return self.visit_node(dd.source_node.id)        
        self.handle_info_message(
            'No dynamic definition for "%s"' % target_id
            )

    def get_by_meta(self,
        key,
        values,
        operator,
        as_nodes=False):
        
        if not isinstance(values, list):
            values = [values]
        results = set()

        if operator in ['before','after']:            
            compare_date = date_from_timestamp(values[0][1:-1])
            
            if compare_date:
                if operator == 'before':
                    results = [n for n in self.nodes.values() if default_date != n.metadata.get_date(key) < compare_date]
                if operator == 'after':
                    results = [n for n in self.nodes.values() if n.metadata.get_date(key) > compare_date != default_date ]

        if key == '_contents' and operator == '?': 
            for node in list(self.nodes.values()):
                if node.dynamic:
                    continue
                matches = []
                contents = node.stripped_contents
                lower_contents = contents.lower()           

                for v in values:
                    if v.lower() in lower_contents:
                        results.add(node.id)

        elif key == '_links_to':
            for v in values:
                results.update(self.get_links_to(v))

        elif key == '_links_from':
            for v in values:
                results.update(self.get_links_from(v))
        else:
            if key == '*':
                keys = self.get_all_keys()
            else:
                keys = [key]
            for k in keys:
                for value in values:
                    if value == '*':
                        results.update([n for n in self.nodes if 
                            self.nodes[n].metadata.get_values(
                                k,
                                convert_nodes_to_links=True)])
                        continue

                    if k in self.settings['numerical_keys']:
                        try:
                            value = float(value)
                        except ValueError:
                            value = float('inf')
 
                    use_timestamp = False
                    if isinstance(value, UrtextTimestamp):
                        use_timestamp = True

                    if k in self.settings['case_sensitive']:
                        results.update([
                            n for n in self.nodes if 
                                value in [
                                v.text for v in self.nodes[n].metadata.get_values(k) if v.text]])
                    else:
                        if isinstance(value, str):
                            value = value.lower()
                        for n in self.nodes.values():
                            found_values = n.metadata.get_values(k)
                            if use_timestamp:
                                if value in [v.timestamp for v in found_values]:
                                    results.udpate([n.id])
                            else:
                                if value in [v.text_lower for v in found_values]:
                                    results.update([n.id])

        results = list(results)
        if as_nodes:
            return [self.nodes[n] for n in results]
        return results

    def get_file_and_position(self, node_id):
        if node_id in self.nodes:
            filename = self.get_file_name(node_id)
            position = self.nodes[node_id].start_position
            return filename, position
        return None, None

    def execute(self, function, *args, **kwargs):
        if self.compiled and not self.nodes:
            return
        if self.is_async:
            return self.executor.submit(function, *args, **kwargs)
        return function(*args, **kwargs)

    def _run_hook(self, hook_name, *args):
        for ext in self.extensions.values():
            hook = getattr(ext, hook_name, None)
            if hook and callable(hook):
                hook(*args)

    """ Project Compile """

    def _compile(self, events=['-project_compiled']):
        self._verify_links_globally()
        self._add_all_sub_tags()
        for file in [f for f in self.files if not self.files[f].errors]:
            self._compile_file(file, events=events)
        self._add_all_sub_tags()

    def _compile_file(self, filename, events=[]):
        if self.files[filename].errors:
            return []
        modified_targets = []
        modified_files = []
        processed_targets = []
        for node in self.files[filename].nodes:
            for dd in self.get_dynamic_defs(target_node=node, source_node=node):
                new_targets = []
                for d in dd.targets + dd.target_ids:
                    if d in processed_targets:
                        continue
                    new_targets.append(d)
                if new_targets:
                    output = dd.process(flags=events)
                    if output not in [False, None]:
                        for target in new_targets:
                            processed_targets.append(target)
                            targeted_output = dd.post_process(
                                target,
                                output)
                            modified_target = self._direct_output(
                                targeted_output, 
                                target, 
                                dd)
                            if modified_target and modified_target not in modified_targets:
                                modified_targets.append(modified_target)

        for target in modified_targets:
            if target in self.nodes:
                self.nodes[target].dynamic = True
                if self.nodes[target].filename not in modified_files:
                    modified_files.append(self.nodes[target].filename)

        return modified_files

    def _direct_output(self, output, target, dd):
        node_link = syntax.node_link_or_pointer_c.match(target)
        if node_link:
            node_id = utils.get_id_from_link(node_link.group())
        else:
            node_id = target
        if node_id in self.nodes:
            if self._set_node_contents(node_id, output):
                return node_id
            return False

        target_file = syntax.file_link_c.match(target)
        if target_file:
            filename = utils.get_id_from_link(target_file)
            filename = os.path.join(self.entry_point, filename)
            #? TODO -- If the file is an export, need to make sure it is remembered
            # when parsed so duplicate titles can be avoided
            #self.exports[filename] = dynamic_definition
            utils.write_file_contents(filename, output)
            return filename
        virtual_target = syntax.virtual_target_match_c.match(target)
        if virtual_target:
            virtual_target = virtual_target.group()
            if virtual_target == '@self':
                if self._set_node_contents(dd.source_node.id, output):
                    return dd.source_node.id
            if virtual_target == '@clipboard':
                return self.run_editor_method('set_clipboard', output)
            if virtual_target == '@next_line':
                return self.run_editor_method('insert_at_next_line', output)
            if virtual_target == '@log':
                return self._log_item(
                    self.nodes[dd.source_node.id].filename,
                    output)
            if virtual_target == '@console':
                return self.run_editor_method('write_to_console', output)
            if virtual_target == '@popup':
                return self.run_editor_method('popup', output)
        if target in self.nodes: #fallback
            self._set_node_contents(target, output)
            return target

    """ Metadata Handling """
 
    def _add_sub_tags(self, 
        entry,
        next_node=None,
        visited_nodes=None):

        if visited_nodes == None:
            visited_nodes = []
        source_node_id = entry.from_node.id
        if next_node:
            source_node_id = next_node           

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
                    entry.meta_values,
                    self.nodes[node_to_tag],
                    tag_self=True,
                    from_node=entry.from_node,
                    tag_descendants=entry.tag_descendants)
                if node_to_tag not in entry.from_node.target_nodes:
                    entry.from_node.target_nodes.append(node_to_tag)
            
            visited_nodes.append(uid)
            
            if entry.tag_descendants:
                self._add_sub_tags(
                    entry,
                    next_node=node_to_tag, 
                    visited_nodes=visited_nodes)
        self._run_hook(
            'on_sub_tags_added',
            source_node_id,
            entry)

    def _remove_sub_tags(self, source_id):
        source_node = self.nodes[source_id]
        for target_id in source_node.target_nodes:
             if target_id in self.nodes:
                 self.nodes[target_id].metadata.clear_from_source(source_node) 

    def title(self):
        return self.settings['project_title'] 

    """ Editor Methods """

    def editor_insert_timestamp(self):
        self.run_editor_method('insert_text', self.timestamp(as_string=True))

    def editor_copy_link_to_node(self, 
        position,
        filename,
        include_project=False):

        self._parse_file(filename, try_buffer=True)

        node_id=None
        for node in self.files[filename].nodes:
            for r in node.ranges:
                if position in range(r[0],r[1]+1): # +1 in case the cursor is in the last position of the node.
                    node_id = node.id
                    break
        if node_id:
            link = self.project_list.build_contextual_link(
                node_id,
                include_project=include_project) 
            if link:
                self.run_editor_method('set_clipboard', link)
        else:
            self.handle_info_message('No Node found here')

    def run_editor_method(self, method_name, *args, **kwargs):
        if method_name in self.editor_methods:
            return self.editor_methods[method_name](*args, **kwargs)
        print('No editor method available for "%s"' % method_name)
        return False
    
    def add_directive(self, directive, folder=None):
        class newClass(directive, UrtextDirective):
            pass
        newClass.folder = folder
        for n in newClass.name:
            self.directives[n] = newClass

    def add_extension(self, extension, folder=None):
        class newClass(extension, UrtextExtension):
            pass
        newClass.folder = folder
        for n in newClass.name:
            self.extensions[n] = newClass(self)

""" 
Helpers 
"""

def to_boolean(text):
    text=text.lower()
    if text in [
        'y', 
        'yes', 
        'true',
        'on']:
        return True
    return False

def make_link(string):
    return ''.join([
        syntax.link_opening_wrapper,
        string,
        syntax.link_closing_wrapper])

def match_compact_node(selection):
    return True if syntax.compact_node_c.match(selection) else False



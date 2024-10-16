import re
import datetime
import platform
import os
import random
import time
import concurrent.futures
import threading
from urtext.file import UrtextFile, UrtextBuffer
from urtext.node import UrtextNode
from urtext.timestamp import date_from_timestamp, default_date, UrtextTimestamp
from urtext.directive import UrtextDirective
import urtext.syntax as syntax
import urtext.utils as utils
from urtext.exec import Exec

class UrtextProject:
    urtext_file = UrtextFile
    urtext_node = UrtextNode
    urtext_buffer = UrtextBuffer

    def __init__(self,
                 entry_point,
                 project_list=None,
                 editor_methods=None,
                 initial=False,
                 new_file_node_created=False):

        if editor_methods is None:
            editor_methods = {}
        self.project_list = project_list
        self.entry_point = entry_point
        self.entry_path = None
        self.project_title = self.entry_point  # default
        self.editor_methods = editor_methods
        self.time = time.time()
        self.last_compile_time = 0
        self.nodes = {}
        self.project_settings_nodes = []
        self.files = {}
        self.paths = []
        self.messages = {}
        self.virtual_outputs = {}
        self.dynamic_metadata_entries = []
        self.directives = {}
        self.project_instance_directives = {}
        self.initialized = False
        self.compiled = False
        self.excluded_files = []
        self.home_requested = False
        self.running_on_modified = None
        self.new_file_node_created = new_file_node_created
        self.initial_project = initial

    def get_setting(self,
            setting,
            _called_from_project_list=False,
            use_project_list=True):

        values = []
        for node in self.project_settings_nodes:
            values.extend(node.metadata.get_values(setting))
        if not values and not _called_from_project_list and use_project_list:
            return self.project_list.get_setting(setting, self)
        if values and values[0].is_node:
            return values
        elif setting != 'numerical_settings' and setting in self.get_setting('numerical_settings',
            _called_from_project_list=_called_from_project_list,
            use_project_list=use_project_list):
            values = [v.num() for v in values]
        return values

    def get_single_setting(self, 
            setting,
            _called_from_project_list=False,
            use_project_list=True):
        values = self.get_setting(
            setting, 
            _called_from_project_list=_called_from_project_list,
            use_project_list=use_project_list)
        if values:
            return values[0]

    def setting_is_true(self, setting):
        setting = self.get_single_setting(setting)
        if setting and setting.true():
            return True
        return False

    def get_setting_as_text(self, 
            setting,
            _called_from_project_list=False,
            use_project_list=True):
        setting = self.get_setting(setting, _called_from_project_list=_called_from_project_list)
        return [v.text for v in setting]

    def get_settings_keys(self):
        keys = []
        for n in self.project_settings_nodes:
            keys.extend(n.metadata.get_keys())
        return keys

    def get_propagated_settings(self, _called_from_project_list=False):
        propagated_settings = self.get_setting_as_text('propagate_settings', _called_from_project_list=_called_from_project_list)
        if '_all' in propagated_settings:
            return self.get_settings_keys()
        return propagated_settings

    def initialize(self):
        self.add_directive(Exec)
        for directive in self.project_list.directives.values():
            self.add_directive(directive)
        for directive in self.project_list.project_instance_directives.values():
            self.add_directive(directive)

        num_file_extensions = len(self.get_setting('file_extensions'))
        if os.path.exists(self.entry_point):
            if os.path.isdir(self.entry_point):
                self.entry_path = os.path.abspath(self.entry_point)
            elif self._include_file(self.entry_point):
                self._parse_file(self.entry_point)
                self.entry_path = os.path.abspath(os.path.dirname(self.entry_point))
            self.paths.append(os.path.abspath(self.entry_point))          
            for file in self._get_included_files():
                self._parse_file(file)
        else:
            self.run_editor_method('popup', 'Project path does not exist: %s' % self.entry_point)
            return False

        for p in self.get_settings_paths():
            if self._approve_new_path(p):
                self.paths.append(p)
                for file in self._get_included_files():
                    if file not in self.files:
                        self._parse_file(file)
                                
        num_paths = len(self.get_settings_paths())
        while len(self.get_settings_paths()) > num_paths or (
                len(self.get_setting('file_extensions')) > num_file_extensions):
            num_paths = len(self.get_settings_paths())
            num_file_extensions = len(self.get_setting('file_extensions'))
            for p in self.get_settings_paths():
                if p not in self.paths and self._approve_new_path(p):
                    self.paths.append(p)
                    for file in self._get_included_files():
                        if file not in self.files:
                            self._parse_file(file)

        if len(self.nodes) == 0 and not self.new_file_node_created:
            return False

        for node in self.nodes.values():
            node.metadata.convert_hash_keys()
            node.metadata.convert_node_links()
        self._add_all_sub_tags()
        self._mark_dynamic_nodes()
        self.initialized = True
        if self.initial_project:
            self.on_initialized()
        self.run_hook('on_initialized')
        self.handle_info_message('Compiling Urtext project from %s' % os.path.basename(self.entry_point))
        self._compile()

        other_entry_points = self.get_setting('other_entry_points')
        if other_entry_points:
            for value in other_entry_points:
                urtext_links = value.links()
                if urtext_links:
                    for path in [link.path for link in urtext_links if link.path]:
                        self.project_list._add_project(os.path.abspath(path))
                    continue
                self.project_list._add_project(os.path.abspath(utils.get_path_from_link(value.text)))

        self.compiled = True
        self.last_compile_time = time.time() - self.time
        self.time = time.time()
        self.handle_info_message('"%s" compiled' % self.title())
        return True

    def _approve_new_path(self, path):
        if path in self.project_list.get_all_paths():
            self.log_item('system', {
                'top_message':  "%s is already in another project." % path})
            return False
        return True

    def _parse_file(self, filename, try_buffer=False):
        if self._filter_filenames(filename) is None:
            self._add_to_excluded_files(filename)
            return False

        buffer = None
        existing_buffer_ids = []
            
        if self.compiled and try_buffer:
            buffer_contents = self.run_editor_method(
                'get_buffer',
                filename)
            if buffer_contents:
                buffer = self._make_buffer(filename, buffer_contents)
        else:
            buffer = self.urtext_file(filename, self)
        if buffer:
            return self._parse_buffer(buffer, existing_buffer_ids=existing_buffer_ids)

    def _parse_buffer(self, buffer, existing_buffer_ids=[]):
        if buffer.filename and buffer.filename in self.files:
            existing_buffer_ids = [n.id for n in self.files[buffer.filename].get_ordered_nodes()]            
            self.drop_file(buffer.filename)

        if not buffer.root_node:
            buffer.write_buffer_messages()
            buffer.write_buffer_contents()
            self.log_item(buffer.filename, {
                'top_message': '%s has no root node, dropping' % buffer.filename})
            return False

        self.messages[buffer.filename] = buffer.messages
        if buffer.has_errors:
            buffer.write_buffer_messages()

        changed_ids = {}
        if existing_buffer_ids:
            new_node_ids = [n.id for n in buffer.get_ordered_nodes()]
            if len(existing_buffer_ids) == len(new_node_ids):
                for index in range(0, len(existing_buffer_ids)):  # existing links are all we care about
                    if existing_buffer_ids[index] == new_node_ids[index]:
                        continue  # id stayed the same
                    else:
                        if new_node_ids[index] in existing_buffer_ids:
                            # proably only the order changed.
                            # don't have to do anything
                            continue
                        else:
                            # check each new id for similarity to the old one
                            changed_ids[existing_buffer_ids[index]] = new_node_ids[index]
                            # else:
                            # TODO try to map old to new.

        for node in buffer.nodes:
            for dd in node.dynamic_definitions:
                dd.source_node = node
                self._verify_dynamic_definition(dd)
            self._add_node(node)

        self.files[buffer.filename] = buffer
        self.run_hook('on_buffer_added', buffer)

        for entry in buffer.meta_to_node:
            keyname = entry.group(1)
            source_node = self.get_node_id_from_position(
                buffer.filename,
                entry.span()[0])
            target_node = self.get_node_id_from_position(
                buffer.filename,
                entry.span()[1] + 1)
            if source_node and target_node:
                self.nodes[source_node].metadata.add_entry(
                    keyname,
                    [self.nodes[target_node]],
                    self.nodes[source_node],
                    start_position=self.nodes[target_node].start_position,
                    end_position=self.nodes[target_node].end_position,
                    is_node=True)
                self.nodes[target_node].is_meta = True
                self.nodes[target_node].meta_key = keyname
       
        for node in buffer.nodes:

            for entry in node.metadata.entries():
                entry.from_node = node
                if entry.tag_children:
                    self._add_sub_tags(entry)
                    self.dynamic_metadata_entries.append(entry)

        if self.compiled and changed_ids:
            for old_node_id in changed_ids:
                self.run_hook('on_node_id_changed',
                            self,
                            old_node_id,
                            changed_ids[old_node_id])
            self._rewrite_changed_links(changed_ids)

        for node in buffer.nodes:
            if node.id == '(untitled)':
                print('(DEBUGGING) - should not happen, untitled node', buffer.filename)

        self._mark_dynamic_nodes()
        return buffer

    def _verify_links_globally(self):
        links = self.get_all_links()
        for filename in links:
            self._reverify_links(filename)

    def _reverify_links(self, filename):
        if filename in self.files:
            contents = self.files[filename]._get_contents()
            for node in [n for n in self.files[filename].nodes if not n.is_dynamic]:
                rewrites = {}
                for link in node.links:
                    if link.is_file:
                        if link.is_missing and link.exists():
                            rewrites[link] = ''.join([
                                syntax.file_link_opening_wrapper,
                                link.path,
                                syntax.link_closing_wrapper])
                        if not link.exists():
                            rewrites[link] = ''.join([
                                syntax.missing_file_link_opening_wrapper,
                                link.path,
                                syntax.link_closing_wrapper])
                        continue
                    if not link.node_id or link.project_name:
                        continue
                    node_id = link.node_id
                    suffix = ' >>' if link.is_pointer else ' >'
                    if node_id not in self.nodes:
                        title_only = node_id.split(syntax.resolution_identifier)[0]
                        if title_only not in self.nodes and link.node_id not in rewrites:
                            rewrites[link] = ''.join([
                                syntax.missing_node_link_opening_wrapper,
                                title_only,
                                suffix])
                    elif link.is_missing and link not in rewrites:  # node marked missing but is there
                        rewrites[link] = ''.join([
                            syntax.link_opening_wrapper,
                            link.node_id,
                            suffix])
                if rewrites:
                    for old_link in rewrites:
                        contents = contents.replace(old_link.matching_string, rewrites[old_link])
            return contents

    def _add_all_sub_tags(self):
        for entry in self.dynamic_metadata_entries:
            self._add_sub_tags(entry)

    def _rewrite_changed_links(self, changed_ids):
        for old_id in list(changed_ids.keys()):
            new_id = changed_ids[old_id]
            if new_id in self.nodes:
                for project_node in [n for n in self.nodes.values() if not n.is_dynamic]:
                    if project_node.id not in self.nodes:
                        continue
                    links_to_change = {}
                    for link in project_node.links:
                        node_id = link.node_id
                        if node_id == old_id:
                            links_to_change[node_id] = new_id
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
                                utils.make_node_link(links_to_change[node_id]), replaced_contents)
                            self.files[project_node.filename].set_buffer_contents(replaced_contents, clear_messages=False)
                            self.files[project_node.filename].write_buffer_contents()

    def _resolve_node_ids(self, buffer):
        messages = []
        allocated_ids = []

        for node in list([n for n in buffer.nodes if n.title == '(untitled)']):
            resolution = node.resolve_id(allocated_ids=allocated_ids)
            if not resolution['resolved_id']:
                message = {
                    'top_message': ''.join([
                                'Dropping (untitled) ID at position ',
                                str(node.start_position),
                                '. ',
                                resolution['reason'],
                                ' ',
                            ]),
                    'position_message': 'Dropped (untitled, cannot resolve)',
                    'position' : node.start_position
                    }
                self.log_item(buffer.filename, message)
                messages.append(message)
                buffer.nodes.remove(node)
                del node
                continue
            else:
                node.id = resolution['resolved_id']
                allocated_ids.append(node.id)
        
        # resolve duplicate titles within file/buffer
        new_file_node_ids = [file_node.id for file_node in buffer.nodes]
        nodes_to_resolve = [n for n in buffer.nodes if new_file_node_ids.count(n.id) > 1]
        for n in nodes_to_resolve:
            unresolved_id = n.id
            resolution = n.resolve_id(allocated_ids=allocated_ids)
            if not resolution['resolved_id'] or resolution['resolved_id'] in allocated_ids:
                message = {
                    'top_message' :''.join([
                                'Dropping duplicate node title "',
                                n.title,
                                '"',
                                ' at position ',
                                str(n.start_position),
                                '; duplicated in the same file.'
                            ]),
                    'position_message': 'Dropped (duplicate title in file)',
                    'position': n.start_position
                    }

                self.log_item(buffer.filename, message)
                messages.append(message)
                buffer.nodes.remove(n)
                del n
                continue
            allocated_ids.append(resolution['resolved_id'])
            n.id = resolution['resolved_id']

        # resolve duplicate titles in project
        new_file_node_ids = [file_node.id for file_node in buffer.nodes]
        allocated_ids = [n for n in self.nodes if n not in new_file_node_ids]
        for node in buffer.get_ordered_nodes():
            duplicate_titled_node = self._find_duplicate_title(node)
            if duplicate_titled_node:
                resolution = node.resolve_id(
                    allocated_ids=allocated_ids)
                if not resolution['resolved_id']:
                    message = {
                        'top_message' : ''.join([
                                'Dropping duplicate node ID "',
                                node.id,
                                '"',
                                ' already exists in file ',
                                syntax.file_link_opening_wrapper,
                                duplicate_titled_node.filename,
                                syntax.link_closing_wrapper,
                            ]),
                        'position_message': 'Dropped (node ID already exists in file)',
                        'position': node.id.start_position,
                    }
                    buffer.nodes.remove(node)
                    del node
                    self.log_item(buffer.filename, message)
                    messages.append(message)
                    continue
                node.id = resolution['resolved_id']

        if messages:
            buffer.messages = messages
            buffer.has_errors = True

    def _verify_dynamic_definition(self, new_definition):
        all_definitions = self.__get_all_dynamic_defs()

        target_ids, target_files = self._get_all_targets()
        for dd in all_definitions:
            for target_id in new_definition.target_ids():
                if target_id in target_ids:
                    new_definition.enabled = False
                    self._reject_definition(target_id, dd, new_definition)
            for target_file in new_definition.target_files():
                if target_file in target_files:
                    new_definition.enabled = False                    
                    self._reject_definition(target_file, dd, new_definition)
                # virtual_target = syntax.virtual_target_match_c.match(target_file)
                # if virtual_target:
                #     target = virtual_target.group()
                # if target == "@self":
                #     self.dynamic_definitions[definition.source_node.id] = definition
                # else:
                #     self.virtual_outputs.setdefault(target, [])
                #     self.virtual_outputs[target].append(definition)

    def _get_all_targets(self):
        target_ids = []
        target_files = []
        for d in self.__get_all_dynamic_defs():
            target_ids.extend(d.target_ids())
            target_files.extend(d.target_files())
        return target_ids, target_files

    def _verify_definition_present_if_marked(self, node):
        if node.marked_dynamic and not node.is_dynamic:
            dynamic_contents = node.contents_with_contained_nodes().strip()
            if len(dynamic_contents) > 1 and dynamic_contents[:2] != "~?":
                self._set_node_contents(node.id, dynamic_contents.replace('~', '~?', 1))

    def _reject_definition(self, target_id, good_definition, duplicate_definition):
        message = {
            'top_message': ''.join([
                '\nDynamic node ',
                utils.make_node_link(target_id),
                '\nalready has a definition in ',
                good_definition.source_node.link(),
                '\n in file ',
                syntax.file_link_opening_wrapper,
                good_definition.source_node.filename,
                syntax.link_closing_wrapper,
                '\nskipping the definition in ',
                duplicate_definition.source_node.link(),
                ])
            }
        # move this 
        # self.log_item(self.nodes[duplicate_definition.source_node.id].filename, message)

    def _add_node(self, new_node):
        new_node.project = self
        self.nodes[new_node.id] = new_node
        if self.compiled:
            new_node.metadata.convert_node_links()
        if new_node.title == 'project_settings':
            self.project_settings_nodes.append(new_node)
        self.run_hook('on_node_added', new_node)

    def get_source_node(self, filename, position):  # future
        if filename not in self.files:
            return None, None
        exported_node_id = self.get_node_id_from_position(filename, position)
        points = self.nodes[exported_node_id].export_points
        if not points:
            return None, None

        indexes = sorted(points)
        for index in range(0, len(indexes)):
            if indexes[index] <= position < indexes[index + 1]:
                node, target_position = self.nodes[exported_node_id].export_points[indexes[index]]
                offset = position - indexes[index]
                return node, target_position + offset

    def _set_node_contents(self, node_id, contents, preserve_title=False):
        """ project-aware alias for the Node _set_contents() method """
        if node_id in self.nodes:
            self._parse_buffer(self.nodes[node_id].file)
            if node_id in self.nodes:
                self.nodes[node_id]._set_contents(
                    contents,
                    preserve_title=preserve_title)
                return self.nodes[node_id].filename
        return False

    def _mark_dynamic_nodes(self):
        for dd in self.__get_all_dynamic_defs():
            for node_id in dd.target_ids():
                if node_id in self.nodes:
                    self.nodes[node_id].is_dynamic = True

    """
    Removing and renaming files
    """

    def drop_file(self, filename):
        self.drop_buffer(self.files[filename])

    def drop_buffer(self, buffer):
        self.run_hook('on_buffer_dropped', buffer.filename)
        for node in list(buffer.nodes):
            self._drop_node(node)
        if buffer.filename in self.files:
            del self.files[buffer.filename]
        if buffer.filename in self.messages:
            self.messages[buffer.filename] = []

    def _drop_node(self, node):
        if node.id in self.nodes:  # might not be if it's an incompletely parsed buffer
            self._remove_sub_tags(node.id)
            self._remove_dynamic_metadata_entries(node.id)
            if node in self.project_settings_nodes:
                self.project_settings_nodes.remove(node)
            del self.nodes[node.id]

    def delete_file(self, filename):
        """
        Deletes a file, removes it from the project,
        """
        self.run_hook('before_file_deleted', self, filename)
        self.run_editor_method('close_file', filename)
        self.drop_file(filename)
        os.remove(filename)
        if filename in self.messages:
            del self.messages[filename]
        self.run_hook('after_file_deleted', self, filename)

    def _handle_renamed(self, old_filename, new_filename):
        if new_filename != old_filename:
            self.files[new_filename] = self.files[old_filename]
            for node in self.files[new_filename].nodes:
                self.nodes[node.id].filename = new_filename
                self.files[new_filename].filename = new_filename
            del self.files[old_filename]
            self.run_hook(
                'on_file_renamed',
                old_filename,
                new_filename)

    def _filter_filenames(self, filename):
        if filename in ['urtext_files', '.git', '_versions']:
            return None
        if filename in self.get_setting_as_text('exclude_files'):
            return None
        return filename

    def new_file_node(self,
                      path=None,
                      contents=None,
                      metadata=None,
                      open_file=True,
                      ensure_timestamp_unique=True):

        contents_format = None
        if contents is None:
            contents_format = bytes(
                self.get_single_setting('new_file_node_format').text,
                "utf-8"
            ).decode("unicode_escape")
        if metadata is None:
            metadata = {}
    
        new_filename_setting = self.get_single_setting('new_filenames_template').text
        filename = self._fill_template(new_filename_setting,
            filename_safe=True,
            ensure_timestamp_unique=ensure_timestamp_unique) 
        filename += '.urtext'

        new_node_contents, node_id, cursor_pos = self._new_node(
            contents=contents,
            contents_format=contents_format,
            metadata=metadata)

        if path:
            filename = os.path.join(path, filename)
        else:
            filename = os.path.join(self.entry_path, filename)

        if os.path.isfile(filename):
            suffix = 2
            resolved_filename = filename
            while os.path.isfile(resolved_filename):
                resolved_filename = filename.replace('.urtext', ' (dup name %s).urtext' % str(suffix))
                suffix += 1
            filename = resolved_filename

        utils.write_file_contents(filename, new_node_contents)
        new_file = self.urtext_file(filename, self)
        self._parse_file(filename)

        if new_file.has_errors and 'timestamp or parent title exists in another node' in new_file.messages[0]:
            if contents is None:
                new_node_contents, node_id, cursor_pos = self._new_node(
                    contents=contents,
                    ensure_timestamp_unique=True,
                    contents_format=contents_format,
                    metadata=metadata)
            utils.write_file_contents(filename, new_node_contents)
            new_file = self.urtext_file(filename, self)
            self._parse_file(filename)
            self._resolve_node_ids(new_file)

        if filename in self.files:
            self.run_hook('on_new_file_node',
                          self.files[filename].root_node.id)
            if open_file:
                self.open_node(self.files[filename].root_node.id,
                               position=cursor_pos)
            return {
                'filename': filename,
                'root_node': self.files[filename].root_node,
                'id': self.files[filename].root_node.id,
                'cursor_pos': cursor_pos
            }

    def new_inline_node(self,
                        metadata=None,
                        contents=''):

        if metadata is None:
            metadata = {}
        contents_format = None
        new_node_contents, title, cursor_pos = self._new_node(
            contents=contents,
            contents_format=contents_format,
            metadata=metadata)

        return {
            'contents': ''.join(['{', new_node_contents, '}']),
            'cursor_pos': cursor_pos
        }

    def _new_node(self,
                  contents=None,
                  title='',
                  contents_format=None,
                  ensure_timestamp_unique=True,
                  metadata=None,
                  one_line=None):

        cursor_pos = 0
        if contents is None:
            contents = ''

        if contents_format:
            new_node_contents = self._fill_template(contents_format, ensure_timestamp_unique=True)
            if '$cursor' in new_node_contents:
                new_node_contents = new_node_contents.split('$cursor')
                cursor_pos = len(new_node_contents[0]) - 1
                new_node_contents = title + ''.join(new_node_contents)
                if cursor_pos < len(new_node_contents) - 1:
                    new_node_contents += ' '
        else:
            if one_line is None:
                one_line = self.setting_is_true('always_oneline_meta')

            if not metadata:
                metadata = {}

            device_keyname = self.get_single_setting('device_keyname')
            if device_keyname:
                metadata[device_keyname.text] = platform.node()

            new_node_contents = contents
            new_node_contents += self.urtext_node.build_metadata(metadata, one_line=one_line)

        return new_node_contents, title, cursor_pos

    def _fill_template(self,
        template_string,
        unwrap_timestamps=False,
        filename_safe=False,
        ensure_timestamp_unique=False):
    
        if '$timestamp' in template_string:
            timestamp = self.timestamp()
            if ensure_timestamp_unique and timestamp.unwrapped_string in [n.resolution for n in self.nodes.values()]:
                timestamp = self.timestamp(add_seconds=True) 
            if unwrap_timestamps:
                timestamp = timestamp.unwrapped_string
            else:
                timestamp = timestamp.wrapped_string
            template_string = template_string.replace('$timestamp', timestamp)
        template_string = template_string.replace(
            '$device_keyname',
            platform.node())
        if filename_safe:
            template_string = utils.strip_illegal_file_characters(template_string)
        return template_string
        
    def add_compact_node(self,
                         contents='',
                         metadata=None):
        if metadata is None:
            metadata = {}
        metadata_block = self.urtext_node.build_metadata(metadata, one_line=True)
        if metadata_block:
            metadata_block = ' ' + metadata_block
        return '• ' + contents.strip() + metadata_block

    def __get_all_dynamic_defs(self):
        defs = []
        for node in list(self.nodes.values()):
            defs.extend(node.dynamic_definitions)
        return defs

    def __get_all_dynamic_targets(self):
        targets = []
        for dd in self.__get_dynamic_defs():
            targets.extend(dd.target_ids())
        return targets

    def __get_dynamic_defs(self,
                           target_node=None,
                           source_node=None,
                           flags=None):        
        defs = []
        for node in [n for n in self.nodes.values() if n.dynamic_definitions]:
            for dd in node.dynamic_definitions:
                if target_node and (target_node.id in dd.target_ids()):
                    defs.append(dd)
                if source_node:
                    if dd.source_node.id == source_node.id:
                        defs.append(dd)
                for target in self.virtual_outputs:
                    if source_node and dd.source_node.id == source_node.id:
                        defs.append(dd)
                    elif not source_node:
                        defs.append(dd)
                if flags:
                    if not isinstance(flags, list):
                        flags = [flags]
                    for f in flags:
                        if dd.have_flags(f) and dd not in defs:
                            defs.append(dd)
        return defs

    def _remove_dynamic_metadata_entries(self, node_id):
        for entry in list(self.dynamic_metadata_entries):
            if entry.from_node == self.nodes[node_id]:
                self.dynamic_metadata_entries.remove(entry)

    def _remove_sub_tags(self, source_id):
        source_node = self.nodes[source_id]
        for target_id in source_node.target_nodes:
            if target_id in self.nodes:
                self.nodes[target_id].metadata.clear_from_source(source_node)

    def open_node(self, node_id, position=None):
        if node_id not in self.nodes:
            if self.compiled:
                message = node_id + ' not in current project'
            else:
                message = 'Project is still compiling'
            self.handle_info_message(message)
            return False

        node_range = (
            self.nodes[node_id].ranges[0][0],
            self.nodes[node_id].ranges[-1][1])

        if position is None:
            position = self.nodes[node_id].start_position

        self.run_editor_method(
            'open_file_to_position',
            self.nodes[node_id].filename,
            position,
            node_range=node_range)
        self.project_list.notify_node_opened()
        return self.visit_node(node_id)

    def open_home(self):
        if not self.get_home():
            if not self.compiled:
                if not self.home_requested:
                    self.handle_info_message('Project is compiling. Home will be shown when found.')
                    self.home_requested = True
                timer = threading.Timer(.5, self.open_home)
                timer.start()
                return timer
            else:
                self.home_requested = False
                self.handle_info_message(
                    'No home node for this project')
                return False
        self.home_requested = False
        home_node_id = self.get_single_setting('home')
        if home_node_id and home_node_id.text in self.nodes:
            self.open_node(home_node_id.text)
            return True
        self.handle_info_message(
                    'Home node set as "%s" but not in project' % home_node_id.text)
        return False

    def handle_info_message(self, message):
        print(message)
        self.run_editor_method('popup', message)

    def handle_error_message(self, message):
        print(message)
        self.run_editor_method('error_message', message)

    def sort_for_node_browser(self, nodes=None, as_nodes=False):
        if not nodes:
            nodes = list(self.nodes.values())
        return self._sort_nodes(
            nodes,
            self.get_setting_as_text('node_browser_sort'),
            as_nodes=as_nodes)

    def sort_for_meta_browser(self, nodes, as_nodes=False):
        meta_browser_key = self.get_single_setting('meta_browser_key')
        if meta_browser_key:
            meta_browser_key = meta_browser_key.text
            nodes = [n for n in nodes if n.metadata.get_first_value(meta_browser_key)]
            return self._sort_nodes(
                nodes,
                [meta_browser_key],
                as_nodes=as_nodes)
        return self._sort_nodes(
            nodes,
            self.get_setting_as_text('meta_browser_sort'),
            as_nodes=as_nodes)

    def _sort_nodes(self, nodes, keys, as_nodes=False):
        remaining_nodes = nodes
        sorted_nodes = []
        use_timestamp_setting = self.get_setting_as_text('use_timestamp')
        detail_key = self.get_single_setting('node_browser_detail').text
        for k in keys:
            use_timestamp = k in use_timestamp_setting
            node_group = [r for r in remaining_nodes if r.metadata.get_first_value(k) is not None]
            remaining_nodes = [r for r in remaining_nodes if r not in node_group]
            if node_group:
                if use_timestamp:
                    node_group = sorted(
                        node_group,
                        key=lambda node: node.metadata.get_first_value(k).timestamp if node.metadata.get_first_value(
                            k) else None,
                        reverse=True)
                else:
                    node_group = sorted(
                        node_group,
                        key=lambda n: n.metadata.get_first_value(k))
                for node in node_group:
                    if not detail_key:
                        detail_key = k
                    detail = node.metadata.get_first_value(detail_key)
                    if detail:
                        if detail_key in use_timestamp_setting:
                            detail = detail.timestamp.wrapped_string
                        else:
                            detail = detail.text
                    else:
                        detail = ''
                    node.display_detail = detail
                sorted_nodes.extend(node_group)
        sorted_nodes.extend([r for r in remaining_nodes if r not in sorted_nodes])
        if not as_nodes:
            return [n.id for n in sorted_nodes]
        return sorted_nodes

    def get_node_id_from_position(self, filename, position):
        if filename in self.files:
            return self.files[filename].get_node_id_from_position(position)

    def get_links_to(self, to_id, as_nodes=False, include_dynamic=True):
        links_to = [n for n in self.nodes.values() if to_id in n.links_ids()]
        if not include_dynamic:
            links_to = [n for n in links_to if not n.is_dynamic]
        if not as_nodes:
            return [n.id for n in links_to]
        return links_to

    def get_links_from(self, from_id, as_nodes=False, include_dynamic=True):
        if from_id in self.nodes:
            links = self.nodes[from_id].links_ids()
            links_from = [l for l in links if l in self.nodes]
            if not include_dynamic:
                links_from = [link for link in links_from if not self.nodes[link].is_dynamic]
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

    def handle_link(self, link):
        if link.is_node and link.node_id in self.nodes:
            if link.is_action:
                for dd in self.__get_dynamic_defs(source_node=self.nodes[link.node_id]):
                    if dd.source_node.id == link.node_id:
                        output = dd.process(link.node_id, flags=['-link_clicked'])
                        if output not in [False, None]:
                            for target in dd.targets:
                                target_output = dd.preserve_title_if_present(target) + output
                                self._direct_output(target_output, target, dd)
            else:
                return self.open_node(
                    link.node_id,
                    position=self.nodes[link.node_id].start_position + link.dest_node_position)

        elif link.is_node:
            return  self.run_editor_method('popup', 'Node cannot be found in the current project.')
        return link

    def _is_duplicate_id(self, node_id):
        return node_id in self.nodes

    def _find_duplicate_title(self, node):
        for n in list(self.nodes):
            if n.title == node.title:
                return node

    def log_item(self, filename, message):
        self.messages.setdefault(filename, [])
        if message not in self.messages[filename]:
            self.messages[filename].append(message)
        if self.setting_is_true('console_log'):
            print(str(filename) + ' : ' + message['top_message'])

    def timestamp(self, date=None, as_string=False, add_seconds=False):
        """ 
        Returns a timestamp in the format set in project_settings, or the default 
        """
        if date is None:
            date = datetime.datetime.now(
                datetime.timezone.utc
            ).astimezone()
        ts_format = self.get_single_setting('timestamp_format').text
        if add_seconds:
            if '%' in ts_format and '%S' not in ts_format:
                ts_format = ts_format.replace('%M', '%M:%S')
        if as_string:
            return ''.join([
                syntax.timestamp_opening_wrapper,
                date.strftime(ts_format),
                syntax.timestamp_closing_wrapper,
            ])
        return UrtextTimestamp(
            date.strftime(ts_format))

    def get_home(self):
        home_node_id = self.get_single_setting('home')
        if home_node_id:
            return home_node_id.text

    def get_all_meta_pairs(self):
        pairs = []
        for n in self.nodes.values():
            for k in n.metadata.get_keys().keys():
                values = n.metadata.get_values(k)
                assigner = syntax.metadata_assignment_operator
                hash_key_setting = self.get_single_setting('hash_key')
                if k == hash_key_setting.text:
                    k = '#'
                    assigner = ''
                for v in values:
                    if v.is_node:
                        pairs.append(utils.make_node_link(v.id))
                    else:
                        pairs.append(''.join([
                            k,
                            assigner,
                            v.text,  # num would need to be converted to text anyway
                        ]))

        return list(set(pairs))

    def random_node(self):
        if self.nodes:
            node_id = random.choice(list(self.nodes))
            self.open_node(node_id)
        return None

    def on_modified(self, filename, flags=[]):
        if self.compiled and filename in self._get_included_files():
            if filename in self.files:
                self._parse_file(filename)
                modified_files = self._compile_file(
                    filename,
                    flags=['-file_update'].extend(flags))
                file_obj = self.files[filename]
                verified_contents = self._reverify_links(filename)
                file_obj.set_buffer_contents(verified_contents)
                if file_obj.write_buffer_contents(run_hook=True):
                    modified_files.append(filename)
                self.run_hook(
                    'file_contents_were_modified',
                    filename)
                self.files[filename] = file_obj
                self._sync_file_list()
                if filename in self.files:
                    self.run_hook('after_on_file_modified', filename)  
                self.run_editor_method('refresh_files', modified_files)
                return modified_files

    def visit_node(self, node_id):
        self.run_hook('on_node_visited', self, node_id)
        if self.compiled:
            self.run_editor_method('status_message', ''.join([self.title(),' (compiled)']))
            return self.visit_file(self.nodes[node_id].filename)

    def visit_file(self, filename):
        return self.on_modified(filename, flags=['-file_visited'])

    def _sync_file_list(self):
        included_files = self._get_included_files()
        for filename in included_files:
            if filename not in self.files:
                self._parse_file(filename)
        for filename in [f for f in list(self.files) if f not in included_files]:
            self.log_item(
                filename,
                {'top_message': filename + ' no longer seen in project path. Dropping it from the project.'})
            self.drop_file(filename)

    def _get_included_files(self):
        files = []
        for pathname in self.paths:
            if os.path.isdir(pathname):
                files.extend([os.path.join(pathname, f) for f in os.listdir(pathname)])
            else:
                files.extend([os.path.join(os.path.dirname(pathname), f) for f in os.listdir(os.path.dirname(pathname))])
        return [f for f in files if self._include_file(f)]

    def get_settings_paths(self):
        paths = []
        if self.entry_path is not None:
            paths.append(os.path.abspath(self.entry_path))
        if os.path.isdir(self.entry_point):
            paths.append(os.path.abspath(self.entry_point))

        for node in self.get_setting('paths'):
            for n in node.children:
                pathname = n.metadata.get_first_value('path')
                if pathname:
                    path = utils.get_path_from_link(pathname.text)           
                    path = os.path.abspath(os.path.join(
                        os.path.dirname(n.filename), 
                        path))
                    if os.path.exists(path):
                        paths.append(path)
                        recurse_subfolders = n.metadata.get_first_value('recurse_subfolders')
                        if recurse_subfolders:                        
                            if path:
                                for dirpath, dirnames, filenames in os.walk(path):
                                    if '/.git' in dirpath or '/_diff' in dirpath:
                                        continue
                                    paths.append(os.path.abspath(dirpath))
        return paths

    def _include_file(self, filename):
        if filename in self.excluded_files:
            return False
        file_extensions = self.get_setting_as_text('file_extensions')
        if '.urtext' not in file_extensions or 'urtext' not in file_extensions:
            file_extensions.append('.urtext')  # for bootstrapping
        if os.path.splitext(filename)[1] in file_extensions and len(os.path.splitext(filename)) == 2:
            return True
        return False

    def _add_to_excluded_files(self, filename):
        if filename not in self.excluded_files:
            self.excluded_files.append(filename)

    def add_file(self, filename):
        """ 
        parse syncronously so we can raise an exception
        if moving files between projects.
        """
        self._parse_file(filename)
        self._compile_file(filename)

    def get_file_name(self, node_id):
        if node_id in self.nodes:
            filename = self.nodes[node_id].filename
        else:
            return None
        return filename

    def title_completions(self):
        return [
            (self.nodes[n].id,
             ''.join(utils.make_node_link(self.nodes[n].id)))
            for n in list(self.nodes)]

    def get_keys_with_frequency(self):
        key_occurrences = {}
        exclude = self.get_setting_as_text('exclude_from_star')
        exclude.extend(self.get_settings_keys())
        for node in list(self.nodes.values()):
            node_keys = node.metadata.get_keys(exclude=exclude)
            for key in node_keys:
                key_occurrences[key] = key_occurrences.get(key, 0)
                key_occurrences[key] += node_keys[key]

        return key_occurrences

    def get_all_keys(self):
        key_occurrences = self.get_keys_with_frequency()
        unique_keys = key_occurrences.keys()
        meta_browser_sort_keys_by_setting = self.get_single_setting('meta_browser_sort_keys_by')
        if meta_browser_sort_keys_by_setting and meta_browser_sort_keys_by_setting.text == 'frequency':
            return sorted(
                unique_keys,
                key=lambda key: key_occurrences[key],
                reverse=True)
        else:
            return sorted(unique_keys)

    def get_all_values_for_key_with_frequency(self, key):

        values = {}
        for node in self.nodes.values():
            values_occurrences = node.metadata.get_values_with_frequency(key)
            for v in values_occurrences:
                values[v.text] = values.get(v.text, 0)
                values[v.text] += values_occurrences[v]

        return values

    def get_all_values_for_key(self,
                               key,
                               substitute_timestamp=True):

        """
        Return tuple of (value.text, value.timestamp)
        """
        values_occurrences = self.get_all_values_for_key_with_frequency(key)
        values = values_occurrences.keys()
        meta_browser_sort_values_by_setting = self.get_single_setting('meta_browser_sort_values_by')
        if meta_browser_sort_values_by_setting and meta_browser_sort_values_by_setting.text == 'frequency':
            return sorted(
                values,
                key=lambda value: values_occurrences[value],
                reverse=True)

        return sorted(values)

    def go_to_dynamic_definition(self, target_id):
        dynamic_defs = self.__get_all_dynamic_defs()
        for dd in dynamic_defs:
            if target_id in dd.target_ids():
                self.run_editor_method(
                    'open_file_to_position',
                    self.nodes[dd.source_node.id].filename,
                    self.nodes[dd.source_node.id].get_file_position(dd.position))
                return self.visit_node(dd.source_node.id)
        self.handle_info_message('No dynamic definition for "%s"' % target_id)

    def get_by_meta(self,
                    key,
                    values,
                    operator,
                    as_nodes=False):

        if not isinstance(values, list):
            values = [values]
        results = set()

        if operator in ['before', 'after']:
            compare_date = date_from_timestamp(values[0][1:-1])

            if compare_date:
                if operator == 'before':
                    results = [n for n in self.nodes.values() if
                               default_date != n.metadata.get_date(key) < compare_date]
                if operator == 'after':
                    results = [n for n in self.nodes.values() if
                               n.metadata.get_date(key) > compare_date != default_date]

        if key == '_contents' and operator == '?':
            for node in list(self.nodes.values()):
                if node.is_dynamic:
                    continue
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
            numerical_keys_setting = self.get_setting_as_text('numerical_keys')
            case_sensitive_setting = self.get_setting_as_text('case_sensitive')
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
                    if k in numerical_keys_setting:
                        try:
                            value = float(value)
                        except ValueError:
                            value = float('inf')

                    use_timestamp = False
                    if isinstance(value, UrtextTimestamp):
                        use_timestamp = True

                    if k in case_sensitive_setting:
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
                                    results.update([n.id])
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

    def run_hook(self, hook_name, *args, **kwargs):
        for dd in self.__get_all_dynamic_defs():
            for op in dd.operations:
                hook = getattr(op, hook_name, None)
                if hook and callable(hook):
                    hook(*args, **kwargs)
        for directive in self.project_instance_directives.values():
            hook = getattr(directive, hook_name, None)
            if hook and callable(hook):
                hook(*args, **kwargs)
        self.project_list.run_hook(hook_name, *args)

    """ Project Compile """

    def _compile(self):
        num_directives = len(list(self.directives.keys()))
        num_project_directives = len(list(self.project_instance_directives.keys()))
        for dd in self.__get_all_dynamic_defs():
            self.__run_def(dd)
        if len(self.directives.keys()) > num_directives or len(self.project_instance_directives.keys()) > num_project_directives:
            return self._compile()
        for dd in self.__get_all_dynamic_defs():
            self.__run_def(dd)
        self._add_all_sub_tags()
        self._verify_links_globally()

    def _compile_file(self, filename, flags=None):
        if flags is None:
            flags = {}
        modified_files = []

        for node in self.files[filename].nodes:
            for dd in list(self.__get_dynamic_defs(target_node=node, source_node=node)):
                modified_files.extend(self.__run_def(dd))
            # HERE IS THE BUG
            self._verify_definition_present_if_marked(node)
        return modified_files

    def __run_def(self, dd, flags=None):
        modified_files = []
        if dd.is_manual():
            return modified_files
        for target in dd.targets:
            output = dd.process(target, flags=flags)
            if output not in [False, None]:
                targeted_output = dd.post_process(
                    target,
                    output)
                self._direct_output(
                    targeted_output,
                    target,
                    dd)
                if target.is_node and target.node_id in self.nodes:
                    self.nodes[target.node_id].is_dynamic = True
                    modified_files.append(self.nodes[target.node_id].filename)
                elif target.is_virtual and target.matching_string == "@self" and dd.source_node.id in self.nodes:
                    self.nodes[dd.source_node.id].is_dynamic = True
                    target.is_node = True
                    target.node_id = dd.source_node.id
                    modified_files.append(self.nodes[dd.source_node.id].filename)                    
        return modified_files

    def _direct_output(self, output, target, dd):
        if target.is_node and target.node_id in self.nodes:
            if self._set_node_contents(target.node_id, output):
                return target.node_id
            return False
        if target.is_virtual:
            if target.matching_string == '@self':
                if self._set_node_contents(dd.source_node.id, output):
                    f = self.nodes[dd.source_node.id].filename
                    return dd.source_node.id
            if target.matching_string == '@clipboard':
                return self.run_editor_method('set_clipboard', output)
            if target.matching_string == '@next_line':
                return self.run_editor_method('insert_at_next_line', output)
            if target.matching_string == '@log':
                return self.log_item(
                    self.nodes[dd.source_node.id].filename,
                    output)
            if target.matching_string == '@console':
                return self.run_editor_method('write_to_console', output)
            if target.matching_string == '@popup':
                return self.run_editor_method('popup', output)
        if target.is_file:
            utils.write_file_contents(os.path.join(self.entry_path, target.path), output)
            return target.filename
        if target.is_raw_string and target.matching_string in self.nodes:  # fallback
            if self._set_node_contents(target.matching_string, output):
                return target.matching_string
            return False

    """ Metadata Handling """

    def _add_sub_tags(self,
                      entry,
                      next_node=None,
                      visited_nodes=None):

        if visited_nodes is None:
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

            if uid not in visited_nodes and not self.nodes[node_to_tag].is_dynamic:
                self.nodes[node_to_tag].metadata.add_entry(
                    entry.keyname,
                    entry.meta_values,
                    self.nodes[node_to_tag],
                    tag_self=True,
                    from_node=entry.from_node,
                    tag_descendants=entry.tag_descendants)
                self.nodes[node_to_tag].metadata.convert_hash_keys()
                if node_to_tag not in entry.from_node.target_nodes:
                    entry.from_node.target_nodes.append(node_to_tag)

            visited_nodes.append(uid)

            if entry.tag_descendants:
                self._add_sub_tags(
                    entry,
                    next_node=node_to_tag,
                    visited_nodes=visited_nodes)
        self.run_hook(
            'on_sub_tags_added',
            source_node_id,
            entry)


    def title(self):
        title_setting = self.get_single_setting('project_title', use_project_list=False)
        if title_setting:
            return title_setting.text
        return self.entry_point

    def on_initialized(self):
        on_loaded_setting = self.get_setting_as_text('on_loaded')
        for action in on_loaded_setting:
            if action == 'open_home' and not self.project_list.node_has_been_opened():
                if self.open_home():
                    return

    def on_selected(self):
        self.run_hook('on_selected', self)

    def has_folder(self, folder):
        included_paths = self.get_settings_paths()
        if os.path.isdir(self.entry_point):
            included_paths.append(self.entry_point)
        return included_paths

    def _make_buffer(self, filename, buffer_contents):
        new_file = UrtextBuffer(self, filename, buffer_contents)
        new_file.filename = filename
        for node in new_file.nodes:
            node.filename = filename
        return new_file

    """ Editor Methods """

    def editor_insert_timestamp(self):
        self.run_editor_method('insert_text', self.timestamp(as_string=True))

    def editor_copy_link_to_node(self,
                                 position,
                                 filename,
                                 include_project=False):

        self._parse_file(filename, try_buffer=True)

        node_id = None
        for node in self.files[filename].nodes:
            for r in node.ranges:
                if position in range(r[0], r[1] + 1):  # +1 in case the cursor is in the last position of the node.
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

    def add_directive(self, directive):
        propagated_directives = self.get_setting_as_text('propagate_directives')
        propagate_all_directives = '_all' in propagated_directives

        class Directive(directive, UrtextDirective):
            pass

        if Directive.project_instance:
            global_directive = Directive(self)
            global_directive.on_added()
            self.project_instance_directives[Directive.name[0]] = (Directive(self))
            if Directive.name in propagated_directives or propagate_all_directives:
                self.project_list.add_directive(directive)
        else:
            for n in directive.name:
                self.directives[n] = directive
            self.project_list.add_directive(directive)
        return self.directives

    def get_directive(self, directive_name):
        directive_class = None
        if directive_name in self.directives:
            directive_class = self.directives[directive_name]
        elif directive_name in self.project_list.directives:
            directive_class = self.project_list.directives[directive_name]
        if not directive_class:
            return None

        class Directive(directive_class, UrtextDirective):
            pass

        return Directive

    def run_directive(self, directive_name, *args, **kwargs):
        directive = self.get_directive(directive_name)
        if not directive:
            self.handle_info_message('Directive %s is not available' % directive_name)
            return None
        op = directive(self)
        return self.project_list.execute(op.run, *args, **kwargs)

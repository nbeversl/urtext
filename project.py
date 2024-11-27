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
from urtext.call import UrtextCall
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
        self.running_on_modified = False
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
        self.calls = {}
        self.project_instance_calls = {}
        self.initialized = False
        self.compiled = False
        self.excluded_files = []
        self.home_requested = False
        self.running_on_modified = None
        self.new_file_node_created = new_file_node_created
        self.initial_project = initial
        self.visible = None

    def get_setting(self,
            setting,
            _called_from_project_list=False,
            use_project_list=True):

        values = []
        for node_id in self.project_settings_nodes:
            values.extend(self.nodes[node_id].metadata.get_values(setting))
        if not values and not _called_from_project_list and use_project_list:
            return self.project_list.get_setting(setting, self)
        if values and values[0].node():
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
        for nid in self.project_settings_nodes:
            keys.extend(self.nodes[nid].metadata.get_keys())
        return keys

    def get_propagated_settings(self, _called_from_project_list=False):
        propagated_settings = self.get_setting_as_text('propagate_settings', _called_from_project_list=_called_from_project_list)
        if '_all' in propagated_settings:
            return self.get_settings_keys()
        return propagated_settings

    def initialize(self, callback=None, initial=True, visible=True):
        self.visible = visible
        self.add_call(Exec)
        for call in self.project_list.calls.values():
            self.add_call(call)
        for call in self.project_list.project_instance_calls.values():
            self.add_call(call)

        num_file_extensions = len(self.get_setting('file_extensions'))
        if os.path.exists(self.entry_point):
            if os.path.isdir(self.entry_point) and self._approve_new_path(self.entry_point):
                self.entry_path = os.path.abspath(self.entry_point)
                self.paths.append(os.path.abspath(self.entry_point))          
            elif self._include_file(self.entry_point):
                self._parse_file(self.entry_point)
                self.entry_path = os.path.abspath(os.path.dirname(self.entry_point))
                self.paths.append(os.path.abspath(self.entry_point))
            included_files = self._get_included_files()
            if included_files and visible:
                self.handle_info_message('Initializing Urtext project from %s' % os.path.basename(self.entry_point))
            for file in included_files:
                self._parse_file(file)
        if not self.files:
            return False

        if callback:
            callback(self, initial=initial)

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
        self._add_all_sub_tags()
        self._mark_dynamic_nodes()
        self.initialized = True
        if self.initial_project:
            self.on_initialized()
        self.run_hook('on_initialized')
        self._compile()

        other_entry_points = self.get_setting('other_entry_points')
        if other_entry_points:
            for value in other_entry_points:
                urtext_links = value.links()
                if urtext_links:
                    for path in [link.path for link in urtext_links if link.path]:
                        self.project_list._init_project(os.path.abspath(path))
                    continue
                self.project_list._init_project(os.path.abspath(utils.get_path_from_link(value.text)))

        self.compiled = True
        self.last_compile_time = time.time() - self.time
        self.time = time.time()
        if visible:
            self.handle_info_message('"%s" compiled' % self.title())
        return True

    def _approve_new_path(self, path):
        if path in self.project_list.get_all_paths():
            self.log_item('system', {
                'top_message':  "%s is already in another project." % path})
            return False
        if os.path.isdir(path):
            for f in os.listdir(path):
                if self.is_project_file(f):
                    return True
        if self.is_project_file(path):
            return True
        return False

    def _parse_file(self, filename, try_buffer=False):
        if self._filter_filenames(filename) is None:
            self._add_to_excluded_files(filename)
            return False

        existing_buffer_ids = None
        if filename in self.files:
            existing_buffer_ids = [n.id for n in self.files[filename].get_ordered_nodes()]     

        if filename in self.files:
            self.drop_buffer(self.files[filename])

        buffer = None
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

    def _parse_buffer(self, buffer, existing_buffer_ids=None):
        for n in buffer.nodes:
            self._resolve_duplicate_titles(n)

        if existing_buffer_ids is None:
            if buffer.filename and buffer.filename in self.files:
                existing_buffer_ids = [n.id for n in self.files[buffer.filename].get_ordered_nodes()]     

        self.drop_buffer(buffer)
        if not buffer.root_node:
            buffer.write_buffer_messages()
            buffer.write_buffer_contents()
            self.log_item(buffer.filename, {
                'top_message': '%s has no root node, dropping' % buffer.filename})
            return False

        self.messages[buffer.filename] = buffer.messages
        if buffer.has_errors:
            buffer.write_buffer_messages()
            buffer.write_buffer_contents()
            return False

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
            if not node.errors:
                self._add_node(node)
                for frame in node.frames:
                    frame.source_node = node
                    for t in frame.targets:
                        if t.is_virtual and t.matching_string == "@self":
                            t.is_node = True
                            t.node_id = frame.source_node.id
                    self._verify_frame(frame)

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
                    self.nodes[target_node],
                    self.nodes[source_node],
                    start_position=self.nodes[target_node].start_position,
                    end_position=self.nodes[target_node].end_position)
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
                                syntax.link_closing_wrapper,
                                link.suffix])
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
                    links_to_change = {}
                    for link in project_node.links:
                        if link.node_id == old_id:
                            links_to_change[old_id] = new_id
                    if links_to_change:
                        contents = project_node.file._get_contents()
                        for node_id in list(links_to_change.keys()):
                            replaced_contents = contents
                            node_id_regex = re.escape(node_id)
                            replaced_contents = re.sub(''.join([
                                    syntax.node_link_opening_wrapper_match,
                                    node_id_regex,
                                    syntax.link_closing_wrapper
                                    ]),
                                utils.make_node_link(links_to_change[node_id]), replaced_contents)
                            project_node.file.set_buffer_contents(replaced_contents, clear_messages=False)
                            project_node.file.write_buffer_contents()
                            
    def _verify_frame(self, new_definition):
        all_frames= self.__get_all_frames()
        target_ids, target_files = self._get_all_targets()
        for frame in all_frames:
            for target_id in new_definition.target_ids():
                if target_id in target_ids:
                    new_definition.enabled = False
                    self._reject_definition(target_id, frame, new_definition)
            for target_file in new_definition.target_files():
                if target_file in target_files:
                    new_definition.enabled = False                    
                    self._reject_definition(target_file, frame, new_definition)
 
    def _get_all_targets(self):
        target_ids = []
        target_files = []
        for d in self.__get_all_frames():
            target_ids.extend(d.target_ids())
            target_files.extend(d.target_files())
        return target_ids, target_files

    def _verify_definition_present_if_marked(self, node_id):
        node = self.get_node(node_id)
        if node and node.marked_dynamic and not node.is_dynamic:
            dynamic_contents = node.contents_with_contained_nodes().strip()
            if len(dynamic_contents) > 1 and dynamic_contents[:2] != "~?":
                self._set_node_contents(node_id, dynamic_contents.replace('~', '~?', 1))
                return False
        return True

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

    def _resolve_duplicate_titles(self, node):
        duplicate_titled_nodes = self._find_duplicate_title(node)
        if duplicate_titled_nodes:
            for d in duplicate_titled_nodes:
                if d.resolution:
                    continue
                old_id = d.id
                resolution = d.resolve_id(allocated_ids=self.nodes)
                if not resolution['resolved_id']:
                    message = {
                    'top_message' : ''.join([
                            'Dropping node ID "',
                            node.id,
                            '", ',
                            resolution['reason'],
                        ]),
                    'position_message': 'ANOTHER NODE HAS THE SAME ID',
                    'position': node.start_position,
                    }
                    node.errors = True
                    self.log_item(node.filename, message)
                    node.buffer.messages.append(message)
                    return
                else:
                    d.id = resolution['resolved_id']
                    self.nodes[resolution['resolved_id']] = d
                    del self.nodes[old_id]
                    if old_id in self.project_settings_nodes:
                        self.project_settings_nodes.remove(old_id)
                        self.project_settings_nodes.append(resolution['resolved_id'])
                    self.run_hook('on_node_id_changed',
                            self,
                            old_id,
                            resolution['resolved_id'])
            resolution = node.resolve_id(allocated_ids=list(self.nodes))
            if not resolution['resolved_id']:
                message = {
                    'top_message' : ''.join([
                            'Dropping node ID "',
                            node.id,
                            '", ',
                            resolution['reason'],
                        ]),
                    'position_message': resolution['reason'],
                    'position': node.start_position,
                }
                node.errors = True
                self.log_item(node.filename, message)
                return
            else:
                node.id = resolution['resolved_id']

    def _add_node(self, new_node):
   
        new_node.project = self
        self.nodes[new_node.id] = new_node
        if new_node.title == 'project_settings':
            self.project_settings_nodes.append(new_node.id)
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
        node = self.get_node(node_id)
        if node:
            node._set_contents(contents, preserve_title=preserve_title)
            return node.file

    def _mark_dynamic_nodes(self):
        for frame in self.__get_all_frames():
            for node_id in frame.target_ids():
                node = self.get_node(node_id)
                if node:
                    node.is_dynamic = True

    """
    Removing and renaming files
    """

    def drop_buffer(self, buffer):
        self.run_hook('on_buffer_dropped', buffer.filename)
        file_nodes = [n for n in self.nodes.values() if n.filename == buffer.filename]
        for node in file_nodes:
            self._drop_node(node)
        if buffer.filename in self.files:
            del self.files[buffer.filename]
        if buffer.filename in self.messages:
            self.messages[buffer.filename] = []

    def _drop_node(self, node):
        if node.id in self.nodes:
            self._remove_dynamic_metadata_entries(node.id)
            if node.id in self.project_settings_nodes:
                self.project_settings_nodes.remove(node.id)
            self._remove_sub_tags(node.id)
            del self.nodes[node.id]
            del node

    def delete_file(self, filename):
        """
        Deletes a file, removes it from the project,
        """
        self.run_hook('before_file_deleted', self, filename)
        self.run_editor_method('close_file', filename)
        if filename in self.files:
            self.drop_buffer(self.files[filename])
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
        if filename in ['urtext_files', '.git']:
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

        new_node_contents, cursor_pos = self._new_node(
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
        buffer = self._parse_file(filename)

        if buffer.has_errors and 'timestamp or parent title exists in another node' in buffer.messages[0]:
            if contents is None:
                new_node_contents, cursor_pos = self._new_node(
                    contents=contents,
                    ensure_timestamp_unique=True,
                    contents_format=contents_format,
                    metadata=metadata)
            utils.write_file_contents(filename, new_node_contents)
            self.drop_buffer(buffer)
            new_file = self.urtext_file(filename, self)
            buffer = self._parse_file(filename)

        if filename in self.files:
            self.run_hook('on_new_file_node',
                          self.files[filename].root_node.id)
            if open_file:
                self.open_node(self.files[filename].root_node.id,
                              position=cursor_pos)
            return {
                'filename': filename,
                'root_node': self.files[filename].root_node,
                'id': buffer.root_node.id,
                'cursor_pos': cursor_pos
            }

    def new_inline_node(self,
                        metadata=None,
                        contents=''):

        if metadata is None:
            metadata = {}
        contents_format = None
        new_node_contents, cursor_pos = self._new_node(
            contents=contents,
            contents_format=contents_format,
            metadata=metadata)

        return {
            'contents': ''.join(['{', new_node_contents, '}']),
            'cursor_pos': cursor_pos
        }

    def _new_node(self,
                  contents=None,
                  contents_format=None,
                  ensure_timestamp_unique=True,
                  metadata=None):

        cursor_pos = 0
        if contents is None:
            contents = ''

        if contents_format:
            new_node_contents = self._fill_template(contents_format, ensure_timestamp_unique=True)
            if '$cursor' in new_node_contents:
                cursor_pos = len(new_node_contents.split('$cursor')[0])
                new_node_contents = new_node_contents.replace('$cursor','')
        else:
            if not metadata:
                metadata = {}
            new_node_contents = contents
            new_node_contents += self.urtext_node.build_metadata(metadata)

        return new_node_contents, cursor_pos

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
        metadata_block = self.urtext_node.build_metadata(metadata)
        if metadata_block:
            metadata_block = ' ' + metadata_block
        return '• ' + contents.strip() + metadata_block

    def __get_all_frames(self):
        defs = []
        for node in list(self.nodes.values()):
            defs.extend(node.frames)
        return defs

    def __get_all_dynamic_targets(self):
        targets = []
        for frame in self.__get_frames():
            targets.extend(frame.target_ids())
        return targets

    def __get_frames(self, target_node=None, source_node=None, flags=None):        
        frames = []
        for node in [n for n in self.nodes.values() if n.frames]:
            for frame in node.frames:
                if target_node and (target_node.id in frame.target_ids()):
                    frames.append(frame)
                if source_node:
                    if frame.source_node.id == source_node.id:
                        frames.append(frame)
                for target in self.virtual_outputs:
                    if source_node and frame.source_node.id == source_node.id:
                        frames.append(frame)
                    elif not source_node:
                        frames.append(frame)
                if flags:
                    if not isinstance(flags, list):
                        flags = [flags]
                    for f in flags:
                        if frame.have_flags(f) and frame not in frames:
                            frames.append(frame)
        return frames

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
            character=position,
            node_range=node_range)
        self.project_list.notify_node_opened()
        self.close_inactive()
        return self.visit_node(node_id)

    def open_home(self):
        home_node_id = self.get_home() 
        if not home_node_id:
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
        if home_node_id in self.nodes:
            self.open_node(home_node_id)
            return True
        self.handle_info_message('Home node set as "%s" but not in project' % home_node_id)
        return False

    def handle_info_message(self, message):
        print(message)
        self.run_editor_method('popup', message)

    def handle_error_message(self, message):
        print(message)
        self.run_editor_method('error_message', message)

    def sort_for_node_browser(self, nodes=None):
        if not nodes:
            nodes = list(self.nodes.values())
        return self._sort_nodes(
            nodes,
            self.get_setting_as_text('node_browser_sort'),
            reverse=True)

    def sort_for_meta_browser(self, nodes):
        meta_browser_key = self.get_single_setting('meta_browser_key')
        if meta_browser_key:
            meta_browser_key = meta_browser_key.text
            nodes = [n for n in nodes if n.metadata.get_first_value(meta_browser_key)]
            return self._sort_nodes(
                nodes,
                [meta_browser_key])
        return self._sort_nodes(
            nodes,
            self.get_setting_as_text('meta_browser_sort_nodes_by'))

    def _sort_nodes(self, nodes, keys, reverse=False):
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
                        reverse=reverse)
                else:
                    node_group = sorted(
                        node_group,
                        key=lambda n: n.metadata.get_first_value(k), reverse=reverse)
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
        return sorted_nodes

    def get_node_id_from_position(self, filename, position):
        if filename in self.files:
            return self.files[filename].get_node_id_from_position(position)

    def get_node(self, node_id):
        if node_id in self.nodes:
            return self.nodes[node_id]

    def get_links_to(self, to_id, include_dynamic=True):
        links_to = [n for n in self.nodes.values() if to_id in n.links_ids()]
        if not include_dynamic:
            links_to = [n for n in links_to if not n.is_dynamic]
        return links_to

    def get_links_from(self, from_id, include_dynamic=True):
        from_node = self.get_node(from_id)
        if from_node:
            links = from_node.links_ids()
            links_from = [l for l in links if l in self.nodes]
            if not include_dynamic:
                links_from = [link for link in links_from if not self.nodes[link].is_dynamic]
            return [self.nodes[n] for n in links_from]
        return []

    def get_all_links(self):
        links = {}
        for node in self.nodes.values():
            links[node.filename] = links.get(node.filename, [])
            links[node.filename].extend(node.links)
        return links

    def handle_link(self, link):
        if link.is_node:
            link_node = self.get_node(link.node_id)
            if link_node:
                if link.is_action:
                    for frame in self.__get_frames(target_node=link_node):
                        modified_buffers = self.__run_frame(frame, flags=['-link_clicked'])
                        for b in modified_buffers:
                            b.write_buffer_contents()
                else:
                    return self.open_node(
                        link.node_id,
                        position=link_node.start_position + link.dest_node_position)

        elif link.is_node:
            return  self.run_editor_method('popup', 'Node cannot be found in the current project.')
        return link

    def _find_duplicate_title(self, node):
        return [n for n in self.nodes.values() if n.title == node.title]

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
        home_node = self.get_single_setting('home')
        if home_node:
            links = home_node.links()
            if links and links[0].is_node:
                print(links[0].node_id)
                return links[0].node_id
            return home_node.text

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
                    node_as_value = v.node()
                    if node_as_value:
                        pairs.append(utils.make_node_link(node_as_value.id))
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

    def close_inactive(self):
        if self.setting_is_true('close_inactive_views'):
            self.run_editor_method('close_inactive')

    def on_modified(self, filename, flags=[]):
        modified_files = []
        if self.compiled and filename in self._get_included_files():
            if not self.running_on_modified:                
                self.running_on_modified = True
                if filename in self.files:
                    modified_files, dynamic_nodes = self._compile_file(
                        filename,
                        flags=['-file_update'] + flags)
                    file_obj = self.files[filename]
                    verified_contents = self._reverify_links(filename)
                    file_obj.set_buffer_contents(verified_contents)
                    for d in dynamic_nodes:
                        # these have to persist between parses
                        node = file_obj.get_node(d)
                        if node:
                            node.is_dynamic = True
                    if file_obj.write_buffer_contents(run_hook=True):
                        modified_files.append(filename)
                    self.run_hook('file_contents_were_modified', filename)
                    self.files[filename] = file_obj
                    self._sync_file_list()
                    if filename in self.files:
                        self.run_hook('after_on_file_modified', filename)  
                    self.run_editor_method('refresh_files', modified_files)
                self.running_on_modified = False
        self.close_inactive()
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
        for filename in [f for f in included_files if f not in self.files]:
            self._parse_file(filename)
        for filename in [f for f in list(self.files) if f not in included_files]:
            self.log_item(
                filename,
                {'top_message': filename + ' no longer seen in project path. Dropping it from the project.'})
            self.drop_buffer(self.files[filename])

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

        for value in self.get_setting('paths'):
            node_as_value = value.node()
            for n in node_as_value.children:
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
        if self.is_project_file(filename):
            return True
        return False

    def is_project_file(self, filename):
        file_extensions = self.get_setting_as_text('file_extensions')
        if '.urtext' not in file_extensions or 'urtext' not in file_extensions:
            file_extensions.append('urtext')  # for bootstrapping
        file_extensions = [e.lstrip('.') for e in file_extensions]
        if utils.get_file_extension(filename) in file_extensions:
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
            return self.nodes[node_id].filename

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

    def go_to_frame(self, target_id):
        frames = self.__get_all_frames()
        for frame in frames:
            if target_id in frame.target_ids():
                self.run_editor_method(
                    'open_file_to_position',
                    frame.source_node.filename,
                    character=self.nodes[frame.source_node.id].get_file_position(frame.position))
                return self.visit_node(frame.source_node.id)
        self.handle_info_message('No frame for "%s"' % target_id)

    def get_by_meta(self, key, values, operator):

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
            case_sensitive_setting = self.get_setting_as_text('case_sensitive_keys')
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
        return [self.nodes[n] for n in results]

    def get_file_and_position(self, node_id):
        if node_id in self.nodes:
            filename = self.get_file_name(node_id)
            position = self.nodes[node_id].start_position
            return filename, position
        return None, None

    def run_hook(self, hook_name, *args, **kwargs):
        for frame in self.__get_all_frames():
            for op in frame.operations:
                hook = getattr(op, hook_name, None)
                if hook and callable(hook):
                    hook(*args, **kwargs)
        for call in self.project_instance_calls.values():
            hook = getattr(call, hook_name, None)
            if hook and callable(hook):
                hook(*args, **kwargs)
        self.project_list.run_hook(hook_name, *args)

    """ Project Compile """

    def _compile(self):
        num_calls = len(list(self.calls.keys()))
        num_project_calls = len(list(self.project_instance_calls.keys()))
        for frame in self.__get_all_frames():
            self.__run_frame(frame)
        if len(self.calls.keys()) > num_calls or len(self.project_instance_calls.keys()) > num_project_calls:
            return self._compile()
        for frame in self.__get_all_frames():
            self.__run_frame(frame)
        self._add_all_sub_tags()
        self._verify_links_globally()

    def _compile_file(self, filename, flags=None):
        if flags is None:
            flags = []
        modified_buffers = []
        dynamic_nodes = []
        buffer = self._parse_file(filename)
        for node in buffer.nodes:
            for frame in list(self.__get_frames(target_node=node, source_node=node)):
                m_buffers, d_nodes = self.__run_frame(frame, flags=flags)
                modified_buffers.extend(m_buffers)
                dynamic_nodes.extend(d_nodes)
                for b in modified_buffers:
                    b.write_buffer_contents()
                    node_ids = []
                    while len(node_ids) < len([n for n in b.nodes if not n.errors]):
                        for node_id in [n.id for n in b.nodes if not n.errors]:
                            if node_id in node_ids:
                                continue
                            node_ids.append(node_id)
                            if self._verify_definition_present_if_marked(node_id) is False:
                                break
        return [b.filename for b in modified_buffers], dynamic_nodes

    def __run_frame(self, frame, flags=None):
        modified_buffers = []
        dynamic_nodes = []
        if frame.is_manual():
            return modified_buffers
        for target in frame.targets:
            output = frame.process(target, flags=flags)
            if output not in [False, None]:
                targeted_output = frame.post_process(target, output)
                buffer = self._direct_output(targeted_output, target, frame)
                if target.is_virtual and target.matching_string == "@self":
                    modified_buffers.append(buffer)
                if target.is_node and target.node_id in self.nodes:
                    modified_buffers.append(buffer)
                    dynamic_nodes.append(target.node_id)
        return modified_buffers, dynamic_nodes

    def _direct_output(self, output, target, frame):
        if target.is_node and target.node_id in self.nodes:
            return self._set_node_contents(target.node_id,
                ''.join([syntax.dynamic_marker, output]))            
        if target.is_virtual:
            if target.matching_string == '@self':
                return self._set_node_contents(frame.source_node.id, ''.join([syntax.dynamic_marker, output]))
            if target.matching_string == '@clipboard':
                return self.run_editor_method('set_clipboard', output)
            if target.matching_string == '@log':
                return self.log_item(
                    frame.source_node.filename, {
                        'top_message': output
                    })
            if target.matching_string == '@console':
                return self.run_editor_method('write_to_console', output)
            if target.matching_string == '@popup':
                return self.run_editor_method('popup', output)
        if target.is_file:
            return utils.write_file_contents(os.path.join(self.entry_path, target.path), output)
        if target.is_raw_string and target.matching_string in self.nodes:  # fallback
            return self._set_node_contents(target.matching_string, ''.join([syntax.dynamic_marker, output]))

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
                if self.open_home(): return

    def on_selected(self):
        self.run_hook('on_selected', self)

    def has_folder(self, folder):
        included_paths = self.get_settings_paths()
        if os.path.isdir(self.entry_point):
            included_paths.append(self.entry_point)
        return included_paths

    def _make_buffer(self, filename, buffer_contents):
        new_buffer = UrtextBuffer(self, filename, buffer_contents)
        for node in new_buffer.nodes:
            node.filename = filename
        return new_buffer

    """ Editor Methods """

    def editor_insert_timestamp(self):
        self.run_editor_method('insert_text', self.timestamp(as_string=True))

    def editor_copy_link_to_node(self,
                                 position,
                                 filename,
                                 include_project=False):

        self._parse_file(filename, try_buffer=True)
        if filename in self.files:
            node_id = None
            for node in self.files[filename].nodes:
                for r in node.ranges:
                    if position in range(r[0], r[1] + 1):  # +1 in case the cursor is in the last position of the node.
                        node_id = node.id
                        break
            if node_id:
                link = self.project_list.build_contextual_link(node_id, include_project=include_project)
                return self.run_editor_method('set_clipboard', link)
        self.handle_info_message('No Node found here')

    def run_editor_method(self, method_name, *args, **kwargs):
        if method_name in self.editor_methods:
            return self.editor_methods[method_name](*args, **kwargs)
        print('No editor method available for "%s"' % method_name)
        return False

    def add_call(self, call):
        propagated_calls = self.get_setting_as_text('propagate_calls')
        propagate_all_calls = '_all' in propagated_calls

        class call(call, UrtextCall):
            pass

        if call.project_instance:
            if call.name[0] not in self.project_instance_calls:
                global_call = call(self)
                global_call.on_added()
                self.project_instance_calls[call.name[0]] = (call(self))
                if call.name in propagated_calls or propagate_all_calls:
                    self.project_list.add_call(call)
        else:
            for n in call.name:
                self.calls[n] = call
            self.project_list.add_call(call)
        return self.calls

    def get_call(self, call_name):
        call_class = None
        if call_name in self.calls:
            call_class = self.calls[call_name]
        elif call_name in self.project_list.calls:
            call_class = self.project_list.calls[call_name]
        if not call_class:
            return None

        class call(call_class, UrtextCall):
            pass

        return call

    def run_call(self, call_name, *args, **kwargs):
        call = self.get_call(call_name)
        if not call:
            self.handle_info_message('call %s is not available' % call_name)
            return None
        op = call(self)
        return self.project_list.execute(op.run, *args, **kwargs)

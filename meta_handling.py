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

"""
Metadata
"""
import datetime
import re 

def tag_other_node(self, node_id, tag_contents):
    """adds a metadata tag to a node programmatically"""

    timestamp = self.timestamp(datetime.datetime.now())
    territory = self.nodes[node_id].ranges
    
    full_file_contents = self._full_file_contents(node_id=node_id)
    tag_position = territory[-1][1]
    if tag_position < len(full_file_contents) and full_file_contents[tag_position] == '%':
         tag_contents += '\n' # keep split markers as the first character on new lines

    new_contents = full_file_contents[:tag_position] + tag_contents + full_file_contents[tag_position:]

    self._set_file_contents(self.nodes[node_id].filename, new_contents)
    return self.on_modified(self.nodes[node_id].filename)

def consolidate_metadata(self, node_id, one_line=False):
    if node_id not in self.nodes:
        self._log_item('Node ID '+node_id+' not in project.')
        return None

    consolidated_metadata = self.nodes[node_id].consolidate_metadata(
        one_line=one_line)

    file_contents = self._full_file_contents(node_id=node_id) 
    filename = self.nodes[node_id].filename
    length = len(file_contents)
    ranges = self.nodes[node_id].ranges
    meta = re.compile(r'(\/--(?:(?!\/--).)*?--\/)',re.DOTALL)

    for single_range in ranges:

        for section in meta.finditer(file_contents[single_range[0]:single_range[1]]):
            start = section.start() + single_range[0]
            end = start + len(section.group())
            first_splice = file_contents[:start]
            second_splice = file_contents[end:]
            file_contents = first_splice
            file_contents += second_splice
            self._adjust_ranges(filename, start, len(section.group()))

    new_file_contents = file_contents[0:ranges[-1][1] - 2]
    new_file_contents += consolidated_metadata
    new_file_contents += file_contents[ranges[-1][1]:]
    self._set_file_contents(filename, new_file_contents)
    self._parse_file(filename)

def _rebuild_node_meta(self, node):
    """ Rebuilds metadata info for a single node """

    for entry in self.nodes[node].metadata.entries:
        if entry.keyname != 'title':
            if entry.keyname not in self.keynames:
                self.keynames[entry.keyname] = {}
            for value in entry.values:
                if value not in self.keynames[entry.keyname]:
                    self.keynames[entry.keyname][value] = []
                self.keynames[entry.keyname][value].append(node)

def _add_sub_tags(self, 
    source_id, # ID containing the instruction
    target_id, # ID to tag
    tag, 
    value, 
    recursive=False):
    if source_id not in self.dynamic_tags:
        self.dynamic_tags[source_id] = []
    
    children = self.nodes[target_id].tree_node.children
    for child in children:
        self.nodes[child.name].metadata.add_meta_entry(
            tag, 
            value,
            from_node=source_id)
        self.dynamic_tags[source_id].append(target_id)
        self._rebuild_node_meta(child.name)
        if recursive:
            self.add_sub_tags(
                source_id,
                child.name,
                tag,
                value,
                recursive=recursive)

metadata_functions = [ _add_sub_tags, _rebuild_node_meta, consolidate_metadata, tag_other_node]

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

def _rebuild_node_meta(self, node_id):
    """ Rebuilds metadata info for a single node """

    for entry in self.nodes[node_id].metadata.entries:

        # title becomes a node property elsewhere
        if entry.keyname != 'title':
            
            # add the key to the project if necessary
            if entry.keyname not in self.keynames:
                self.keynames[entry.keyname] = {}

            # add the values to the keyname
            for value in entry.values:
                if value not in self.keynames[entry.keyname]:
                    self.keynames[entry.keyname][value] = []
                if node_id not in self.keynames[entry.keyname][value]:
                    self.keynames[entry.keyname][value].append(node_id)

def _add_sub_tags(self, 
    source_id, # ID containing the instruction
    target_id, # ID to tag
    tag, 
    value, 
    recursive=False):
    
    self._remove_sub_tags(source_id)

    if source_id not in self.dynamic_meta:
        self.dynamic_meta[source_id] = []

    nodes_to_rebuild = []
    children = self.nodes[target_id].tree_node.children
    for child in children:
        self.nodes[child.name].metadata.add_meta_entry(
            tag, 
            value,
            from_node=source_id)
        self.dynamic_meta[source_id].append(child.name)
        if child.name not in nodes_to_rebuild:
            nodes_to_rebuild.append(child.name)
        if recursive:
            self._add_sub_tags(
                source_id,
                child.name,
                tag,
                value,
                recursive=recursive)

    for node_id in nodes_to_rebuild:
        self._rebuild_node_meta(node_id)

def _remove_sub_tags(self, source_id):

    if source_id not in self.dynamic_meta:
        return

    nodes_to_rebuild = []

    for target_id in self.dynamic_meta[source_id]:
        if target_id not in self.nodes:
            continue
        self.nodes[target_id].metadata.remove_dynamic_meta_from_source_node(source_id)                           
        if target_id not in nodes_to_rebuild:
            nodes_to_rebuild.append(target_id)

        # ALSO need to remove it from the project metadata dict.

    # rebuild meta for all the target nodes
    for node_id in nodes_to_rebuild:
        self._rebuild_node_meta(node_id)

metadata_functions = [ _add_sub_tags, _remove_sub_tags, _rebuild_node_meta, consolidate_metadata, tag_other_node]

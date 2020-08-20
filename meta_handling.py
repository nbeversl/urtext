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

entry_regex = re.compile('\w+\:\:[^\n;]+[\n;]?',re.DOTALL)


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
    for single_range in ranges:

        for section in entry_regex.finditer(file_contents[single_range[0]:single_range[1]]):
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
    """ Rebuild metadata for a single node """

    self._unbuild_node_meta(node_id)

    for entry in self.nodes[node_id].metadata._entries:

        # title becomes a node property elsewhere, skip
        if entry.keyname == 'title':
           continue 

        if entry.keyname not in self.keynames:
            self.keynames[entry.keyname] = {}

        keyname = entry.keyname.lower()

        if not entry.values and entry.dt_string:
            if entry.dt_string not in self.keynames[keyname]:
                self.keynames[keyname][entry.dt_string] = [] 
            self.keynames[keyname][entry.dt_string].append(node_id)
            continue

        # add the values to the keyname
        for value in entry.values:
                    
            if keyname in self.settings['numerical_keys']:
                try:
                    value = float(value)
                except ValueError:
                    print('cannot parse '+value+' as a numerical key')
                    continue

            if value not in self.keynames[keyname]:
                self.keynames[keyname][value] = [] 
            if node_id not in self.keynames[keyname][value]:
                self.keynames[keyname][value].append(node_id)


def _add_sub_tags(self, 
    source_id, # ID containing the metadata
    target_id,
    entry):

    nodes_to_rebuild = []   
    children = self.nodes[target_id].tree_node.children
    
    for child in children:
        
        """
        This is currently necessary because of how node pointers
        are handled in tree-building.
        FUTURE: there may be a better way to handle this.
        """
        node_to_tag = child.name.strip('ALIAS') 

        if node_to_tag in self.nodes and node_to_tag not in self.dynamic_meta[source_id]['targets']:
            self.nodes[node_to_tag].metadata.add_meta_entry(
                entry.keyname, 
                entry.values,
                from_node=source_id)
            self.dynamic_meta[source_id]['targets'].append(node_to_tag)
            if node_to_tag not in nodes_to_rebuild:
                nodes_to_rebuild.append(node_to_tag)
            if entry.recursive:
                self._add_sub_tags(source_id, node_to_tag, entry)

    for node_id in nodes_to_rebuild:
        self._rebuild_node_meta(node_id)

def _remove_sub_tags(self, source_id):
    
    if source_id not in self.dynamic_meta:
        return

    nodes_to_rebuild = []
    
    for target_id in self.dynamic_meta[source_id]['targets']:
        if target_id in self.nodes:
            self.nodes[target_id].metadata.clear_from_source(source_id)                           
            if target_id not in nodes_to_rebuild:
                nodes_to_rebuild.append(target_id)

    del self.dynamic_meta[source_id]

    # rebuild meta for all the target nodes
    for node_id in nodes_to_rebuild:
        self._rebuild_node_meta(node_id)

metadata_functions = [ _add_sub_tags, _remove_sub_tags, _rebuild_node_meta, consolidate_metadata, tag_other_node]

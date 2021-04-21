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
from .node import UrtextNode

entry_regex = re.compile('\w+\:\:[^\n;]+[\n;]?',re.DOTALL)

def tag_other_node(self,node_id, metadata={}):
    if self.is_async:
        return self.executor.submit(self._tag_other_node, node_id, metadata=metadata)
    else:
        self._tag_other_node(node_id, metadata=metadata)
        
def _tag_other_node(self, node_id, metadata={}):
    """adds a metadata tag to a node programmatically"""

    if metadata == {}:
        if len(self.settings['tag_other']) < 2:
            return None
        timestamp = self.timestamp(datetime.datetime.now())
        metadata = { self.settings['tag_other'][0] : self.settings['tag_other'][1] + ' ' + timestamp}
   
    territory = self.nodes[node_id].ranges
    metadata_contents = UrtextNode.build_metadata(metadata)
   
    full_file_contents = self.nodes[node_id].filename.get_contents()
    tag_position = territory[-1][1]

    separator = '\n'
    if self.nodes[node_id].compact:
        separator = ' '

    new_contents = ''.join([
        full_file_contents[:tag_position],
        separator,
        metadata_contents,
        separator,
        full_file_contents[tag_position:]])

    self.nodes[node_id].filename.set_file_contents(new_contents)
    return self.on_modified(self.nodes[node_id].filename)

def consolidate_metadata(self, node_id, one_line=False):

    if node_id not in self.nodes:
        self._log_item('Node ID '+node_id+' not in project.')
        return None

    consolidated_metadata = self.nodes[node_id].consolidate_metadata(
        one_line=one_line)

    file_contents = self.nodes[node_id].filename.get_contents()
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
    self.files[filename].set_file_contents(new_file_contents)
    self._parse_file(filename)

            
def _add_sub_tags(self, 
    source_id, # ID containing the metadata
    target_id,
    entry):

    to_tag = self.nodes[target_id].tree_node.children
    
    for child in children:

        """
        This is currently necessary because of how node pointers
        are handled in tree-building.
        FUTURE: there may be a better way to handle this.
        """
        node_to_tag = child.name.strip('ALIAS') 

        if source_id not in self.dynamic_meta:
            self.dynamic_meta[source_id] = { 'entries' : [] , 'targets' : []}

        if node_to_tag in self.nodes: # and node_to_tag not in self.dynamic_meta[source_id]['targets']: # bug fix.
            self.nodes[node_to_tag].metadata.add_meta_entry(
                entry.keyname, 
                entry.values,
                from_node=source_id)
            self.dynamic_meta[source_id]['targets'].append(node_to_tag)
            if entry not in self.dynamic_meta[source_id]['entries']:
                self.dynamic_meta[source_id]['entries'].append(entry)
            self.dynamic_meta[source_id]['entries'].append(entry)
            if entry.recursive:
                self._add_sub_tags(source_id, node_to_tag, entry)

def _remove_sub_tags(self, source_id):

    if source_id not in self.dynamic_meta:
        return

    for target_id in self.dynamic_meta[source_id]['targets']:
        if target_id in self.nodes:
            self.nodes[target_id].metadata.clear_from_source(source_id)                           

    del self.dynamic_meta[source_id]

metadata_functions = [ _add_sub_tags,  _tag_other_node, _remove_sub_tags, consolidate_metadata, tag_other_node]

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

from .export import UrtextExport
from .timeline import timeline
import os
import re

"""
compile method for the UrtextProject class
"""
def _compile(self, 
    skip_tags=False, 
    modified_files=[]):
    """ Main method to compile dynamic nodes from their definitions """

    for dynamic_definition in list(self.dynamic_nodes):

        source_id = dynamic_definition.source_id

        # exporting is the only the thing using target files at this moment
        if not dynamic_definition.target_id and not dynamic_definition.export:

            continue
        
        if dynamic_definition.target_id:
            target_id = dynamic_definition.target_id

            if target_id not in list(self.nodes):
                self._log_item('Dynamic node definition in >' + source_id +
                              ' points to nonexistent node >' + target_id)
                continue

            filename = self.nodes[target_id].filename

        if self.compiled and self._parse_file(filename):
            self._update(compile_project=False, modified_files=modified_files)

        points = {}

        new_node_contents = ''

        if dynamic_definition.tree:
            if dynamic_definition.tree not in self.nodes:
                continue
            new_node_contents += self.show_tree_from(dynamic_definition.tree)

        if dynamic_definition.interlinks and dynamic_definition.interlinks in self.nodes:
            new_node_contents += self.get_node_relationships(
                dynamic_definition.interlinks,
                omit=dynamic_definition.omit)

        if dynamic_definition.mirror and dynamic_definition.mirror in self.nodes:
            
            if dynamic_definition.mirror_include_all:
                # TODO prevent nodes being repeatedly mirrored inside themselves.
                start = self.nodes[dynamic_definition.mirror].ranges[0][0]
                end = self.nodes[dynamic_definition.mirror].ranges[-1][1]
                new_node_contents += self._full_file_contents(node_id=dynamic_definition.mirror)[start:end]
                new_node_contents = UrtextNode.strip_metadata(contents=new_node_contents)
                new_node_contents = UrtextNode.strip_dynamic_definitions(contents=new_node_contents)
                new_node_contents = new_node_contents.replace('{{','')
                new_node_contents = new_node_contents.replace('}}','')
            else:
                new_node_contents += self.nodes[dynamic_definition.mirror].content_only()

        
        if dynamic_definition.export: #

            exclude=[]
            if dynamic_definition.target_id:
            	exclude.append(target_id)
            exported = UrtextExport(self) 
            exported_content, points = exported.export_from(
                 dynamic_definition.export_source,
                 kind=dynamic_definition.export,
                 exclude =exclude, # prevents recurssion
                 as_single_file=True, # TOdO should be option 
                 clean_whitespace=True,
                 preformat = dynamic_definition.preformat
                )
            
            if dynamic_definition.target_file:
                with open(os.path.join(self.path, dynamic_definition.target_file), 'w',encoding='utf-8') as f:
                    f.write(exported_content)
                    f.close()
                if not dynamic_definition.target_id:
                    continue

            new_node_contents = exported_content
        

        if dynamic_definition.tag_all_key:
            if skip_tags:
                continue
            self._add_sub_tags(
                source_id,
                target_id, 
                dynamic_definition.tag_all_key, 
                dynamic_definition.tag_all_value, 
                recursive=dynamic_definition.recursive)                    
            self._compile(skip_tags=True, modified_files=modified_files)
            continue
            
        else:
 
            if dynamic_definition.include_or == 'all':
                included_nodes = set(self.all_nodes())

            elif dynamic_definition.include_or == 'indexed':
                included_nodes = set(self.indexed_nodes())
            
            else:
                # AND key/value pairs
                included_nodes = self._build_group_and(dynamic_definition.include_and)
                excluded_nodes = self._build_group_and(dynamic_definition.exclude_and)
                
                # OR key/value pairs
                included_nodes = included_nodes.union(self._build_group_or(dynamic_definition.include_or))
                excluded_nodes = excluded_nodes.union(self._build_group_or(dynamic_definition.exclude_or))

                # remove the excluded nodes
                for node_id in excluded_nodes:
                    included_nodes.discard(node_id)

            # Never include a dynamic node in itself.
            included_nodes.discard(dynamic_definition.target_id)

            """
            Assemble the final node collection into a list
            """
            included_nodes = [self.nodes[node_id] for node_id in included_nodes]
            
            """
            build timeline if specified
            """ 
            if dynamic_definition.show == 'timeline':
                new_node_contents += timeline(self, included_nodes, kind=dynamic_definition.timeline_type)

            elif dynamic_definition.search and self.ix:
                new_node_contents += self.search_term(dynamic_definition.search, exclude=[dynamic_definition.target_id])
 
            else:
                
                """ otherwise this is a list. """
                """ custom sort the nodes if a sort key is provided """
                if dynamic_definition.sort_keyname:

                    # If specified, sort by timestamp of the selected key
                    if dynamic_definition.sort_type == 'timestamp':
                        sort_func = lambda node: node.metadata.get_date(dynamic_definition.sort_keyname)

                    # ( Otherwise the sort type is alpha by string )

                    # Title is not always given by metadata so we do this manually 
                    elif dynamic_definition.sort_keyname == 'title':
                        sort_func = lambda node: node.title.lower()

                    # For all other keys, sort by key
                    else:
                        sort_func = lambda node: node.metadata.get_first_meta_value(dynamic_definition.sort_keyname)

                else:
                    """ otherwise sort them by node date by default """
                    sort_func = lambda node: node.date

                # sort them using the determined sort function
                included_nodes = sorted(
                    included_nodes,
                    key = sort_func,
                    reverse=dynamic_definition.reverse)

                """
                Truncate the list if a maximum is specified
                """            
                if dynamic_definition.max:
                    included_nodes = included_nodes[0:dynamic_definition.max]
 
                for targeted_node in included_nodes:

                    shah = '%&&&&888' #FUTURE = possibly randomize
                    item_format = dynamic_definition.show
                    item_format = bytes(item_format, "utf-8").decode("unicode_escape")
                    tokens = [
                        'TITLE',
                        'LINK',
                        'DATE',
                        'CONTENTS',
                        'META',
                    ]

                    # tokenize everything to make sure we only
                    # replace it when intended
                    for token in tokens:
                        item_format = item_format.replace(token, shah+token)
                    if shah + 'TITLE' in item_format:
                        item_format = item_format.replace(shah + 'TITLE', targeted_node.title)
                    if shah + 'LINK' in item_format:
                        item_format = item_format.replace(shah + 'LINK', '>>'+ str(targeted_node.id))
                    if shah + 'DATE' in item_format:
                        item_format = item_format.replace(shah + 'DATE', targeted_node.get_date(format_string = self.settings['timestamp_format'][0]))
                   
                    contents_syntax = re.compile(shah+'CONTENTS'+'(\(\d*\))?', re.DOTALL)      
                    contents_match = re.search(contents_syntax, item_format)

                    if contents_match:
                        suffix = ''
                        contents = targeted_node.content_only().strip('\n').strip()
                        if contents_match.group(1):
                            suffix = contents_match.group(1)
                            length_str = contents_match.group(1)[1:-1]
                            length = int(length_str)
                            if len(contents) > length:
                                contents = contents[0:length] + ' (...)'
                        item_format = item_format.replace(shah + 'CONTENTS' + suffix, contents)

                    meta_syntax = re.compile(shah+'META'+'(\(.*\))?', re.DOTALL)                   
                    meta_match = re.search(meta_syntax, item_format)
                    
                    # if META format key is present
                    #TODO refactor. This should be a method of Metadata
                    if meta_match:
                       
                        meta = ''
                        suffix = ''

                        # if tags have been specified
                        if meta_match.group(1):
                            suffix = meta_match.group(1)                           
                            keynames = meta_match.group(1)[1:-1].split(',')
                            for index in range(len(keynames)):
                                keynames[index] = keynames[index].strip().lower()
                        else: 
                            # default is to use all keynames
                            keynames = targeted_node.get_all_meta_keynames()
                        
                        for keyname in keynames:
                            values = targeted_node.metadata.get_meta_value(keyname)
                            meta += keyname + ': '
                            meta += ' '.join([value for value in values])
                            meta += '; '
                        
                        item_format = item_format.replace(shah + 'META' + suffix, meta)
                        
                    new_node_contents += item_format
                        
        """
        add metadata to dynamic node
        """

        metadata_values = { 
            'ID': [ target_id ],
            'defined in' : [ '>'+dynamic_definition.source_id ] }

        if dynamic_definition.mirror:
            metadata_values['mirrors'] = '>'+dynamic_definition.mirror

        for value in dynamic_definition.metadata:
            metadata_values[value] = dynamic_definition.metadata[value]
        built_metadata = build_metadata(metadata_values, one_line=dynamic_definition.oneline_meta)

        title = ''
        if 'title' in dynamic_definition.metadata:
            title = dynamic_definition.metadata['title'] + '\n'

        updated_node_contents = '\n' + title + new_node_contents + built_metadata
        """
        add indentation if specified
        """

        if dynamic_definition.spaces:
            updated_node_contents = indent(updated_node_contents,
                                           dynamic_definition.spaces)

        changed_file = self._set_node_contents(target_id, updated_node_contents)

        if changed_file:    
            if changed_file not in modified_files:
                modified_files.append(changed_file)
            self._parse_file(changed_file)
            modified_files = self._update(compile_project=False, modified_files=modified_files)
        self.nodes[target_id].points = points
        if dynamic_definition.tree:
            self.nodes[target_id].is_tree = True
    return modified_files


def _build_group_and(self, groups):

    final_group = set([])

    for group in groups:

        new_group = set([])

        for pair in group:
            
            key, value = pair[0], pair[1]

            if key in self.keynames:
                
                if value.lower() == 'all':
                    for value in self.keynames[key]:
                        new_group = new_group.union(set(self.keynames[key][value])) 
                elif value in self.keynames[key]:
                    new_group = new_group.union(set(self.keynames[key][value]))

        final_group = final_group.union(new_group)

    return final_group

def _build_group_or(self, group):
    final_group = set([])

    for pair in group:
        key, value = pair[0], pair[1]
        if key in self.keynames and value in self.keynames[key]:
            final_group = final_group.union(set(self.keynames[key][value]))
        
    return final_group

def build_metadata(keynames, one_line=False):
    """ Note this is a method from node.py. Could be refactored """

    if one_line:
        line_separator = '; '
    else:
        line_separator = '\n'
    new_metadata = '/-- '
    if not one_line: 
        new_metadata += line_separator
    for keyname in keynames:
        new_metadata += keyname + ': '
        if isinstance(keynames[keyname], list):
            new_metadata += ' | '.join(keynames[keyname])
        else:
            new_metadata += keynames[keyname]
        new_metadata += line_separator
    if one_line:
        new_metadata = new_metadata[:-2] + ' '

    new_metadata += '--/'
    return new_metadata 


def indent(contents, spaces=4):
    content_lines = contents.split('\n')
    for index, line in enumerate(content_lines):
        if line.strip() != '':
            content_lines[index] = ' ' * spaces + line
    return '\n'.join(content_lines)

compile_functions = [_compile, _build_group_and, _build_group_or]

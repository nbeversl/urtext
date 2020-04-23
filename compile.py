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
from .node import UrtextNode
from .timeline import timeline
import os
import re

"""
compile method for the UrtextProject class
"""
def _compile(self, 
    skip_tags=False, 
    modified_files=None):
    """ Main method to compile dynamic nodes from their definitions """

    if modified_files is None:
        modified_files = []
        
    for dynamic_definition in self.dynamic_nodes:

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
            if not dynamic_definition.export_source:
                continue 
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

            new_node_contents += exported_content
        
        if dynamic_definition.tag_all_key:
                        
            if not skip_tags:
                self._add_sub_tags(
                    source_id,
                    target_id, 
                    dynamic_definition.tag_all_key, 
                    dynamic_definition.tag_all_value, 
                    recursive=dynamic_definition.recursive)                    
                self._compile(skip_tags=True, modified_files=modified_files)
            continue
            
        else:  
           
            # allow for including other projects in the list context
            included_projects = [self]
            if dynamic_definition.include_other_projects:
                included_projects.extend(self.other_projects)

            if dynamic_definition.include_or == 'all':
                included_nodes = [self.nodes[node_id] for node_id in set(self.all_nodes()) if node_id != dynamic_definition.target_id]

            elif dynamic_definition.include_or == 'indexed':
                included_nodes = [self.nodes[node_id] for node_id in set(self.indexed_nodes()) if node_id != dynamic_definition.target_id]
            
            else:

                included_nodes = set([])
                excluded_nodes = set([])
                
                for project in included_projects:

                    # AND key/value pairs
                    included_nodes = included_nodes.union(_build_group_and(project, dynamic_definition.include_and)) 
                    excluded_nodes = excluded_nodes.union(_build_group_and(project, dynamic_definition.exclude_and))
                    
                    # OR key/value pairs
                    included_nodes = included_nodes.union(_build_group_or(project, dynamic_definition.include_or))
                    excluded_nodes = excluded_nodes.union(_build_group_or(project, dynamic_definition.exclude_or))

    
                # remove the excluded nodes
                for node in excluded_nodes:
                    included_nodes.discard(node)

                # Never include a dynamic node in itself.
                included_nodes.discard(self.nodes[dynamic_definition.target_id])
                included_nodes = list(included_nodes)
           
            """
            build timeline if specified
            """ 

            if dynamic_definition.show == 'timeline':
                new_node_contents += timeline(self, included_nodes, kind=dynamic_definition.timeline_type)

            # POSSIBLE BUG HERE
            # elif dynamic_definition.search and self.ix:
            #     new_node_contents += self.search_term(dynamic_definition.search, exclude=[dynamic_definition.target_id])
 
            else:

                """ otherwise this is a list. """
                """ custom sort the nodes if a sort key is provided """

                if dynamic_definition.sort_type == 'last_accessed':
                    sort_func = lambda node: node.last_accessed
                        
                elif dynamic_definition.sort_keyname:

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
                    key = sort_func,#
                    reverse=dynamic_definition.reverse)

                """
                Truncate the list if a maximum is specified
                """            
                if dynamic_definition.limit:
                    included_nodes = included_nodes[0:dynamic_definition.limit]
                    print(dynamic_definition.limit)
 
                for targeted_node in included_nodes:

                    shah = '%&&&&888' #FUTURE : possibly randomize -- must not be any regex operators.
                    item_format = dynamic_definition.show
                    item_format = bytes(item_format, "utf-8").decode("unicode_escape")
                    
                    # tokenize all $ format keys
                    format_key_regex = re.compile('\$[A-Za-z0-9_-]+', re.DOTALL)
                    format_keys = re.findall(format_key_regex, item_format)
                        
                    for token in format_keys:
                        item_format = item_format.replace(token, shah + token)

                    if shah + '$title' in item_format:
                        item_format = item_format.replace(shah + '$title', targeted_node.title)
                    if shah + '$link' in item_format:
                        link = ''
                        if targeted_node.parent_project not in [self.title, self.path]:
                            link += '{"'+targeted_node.parent_project+'"}'
                        else:
                            link += '>'
                        link += '>'+ str(targeted_node.id)
                        item_format = item_format.replace(shah + '$link', link)
                    if shah + '$date' in item_format:
                        item_format = item_format.replace(shah + '$date', targeted_node.get_date(format_string = self.settings['timestamp_format'][0]))
                    if shah + '$meta' in item_format:
                        item_format = item_format.replace(shah + '$meta', targeted_node.consolidate_metadata(wrapped=False))

                    # contents
                    contents_syntax = re.compile(shah+'\$contents'+'(:\d*)?', re.DOTALL)      
                    contents_match = re.search(contents_syntax, item_format)

                    if contents_match:
                        contents = targeted_node.content_only().strip('\n').strip()
                        suffix = ''
                        if contents_match.group(1):
                            suffix = contents_match.group(1)                          
                            length_str = contents_match.group(1)[1:] # strip :
                            length = int(length_str)
                            if len(contents) > length:
                                contents = contents[0:length] + ' (...)'
                        item_format = item_format.replace(shah + '$contents' + suffix, contents)

                    remaining_format_keys = re.findall( shah+'\$[A-Za-z0-9_-]+', item_format, re.DOTALL)                   
                    
                    # all other meta keys
                    for match in remaining_format_keys:
                        meta_key = match.strip(shah+'$')                   
                        values = targeted_node.metadata.get_meta_value(meta_key, substitute_timestamp=True)
                        replacement = ''
                        if values:
                            replacement = ' '.join(values)
                        item_format = item_format.replace(match, replacement);    
                                                
                    new_node_contents += item_format
                        
        # """
        # add metadata to dynamic node
        # """
        metadata_values = { 
            'ID': [ target_id ],
            'defined in' : [ '>'+dynamic_definition.source_id ] }

        if dynamic_definition.mirror:
            metadata_values['mirrors'] = '>'+dynamic_definition.mirror

        for value in dynamic_definition.metadata:
            metadata_values[value] = dynamic_definition.metadata[value]
        built_metadata = UrtextNode.build_metadata(metadata_values, one_line=dynamic_definition.oneline_meta)

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

            modified_files = self._update(
                compile_project=False, 
                modified_files=modified_files)
            
            if dynamic_definition.export:
                self.nodes[target_id].export_points = points

        self.nodes[target_id].points = points
        if dynamic_definition.tree:
            self.nodes[target_id].is_tree = True
       
    return modified_files


def _build_group_and(project, groups):

    final_group = set([])

    for group in groups:

        new_group = set([])

        for pair in group:
            
            key, value = pair[0], pair[1]

            if key in project.keynames:
                
                if value.lower() == 'all':
                    for value in project.keynames[key]:
                        new_group = new_group.union(set(project.keynames[key][value])) 

                elif value in project.keynames[key]:
                    new_group = new_group.union(set(project.keynames[key][value]))
                    
        final_group = final_group.union(new_group)

    final_group = set([project.nodes[node_id] for node_id in final_group])

    return final_group

def _build_group_or(project, group):
    final_group = set([])

    for pair in group:
        key, value = pair[0], pair[1]
        if key in project.keynames and value in project.keynames[key]:
            final_group = final_group.union(set(project.keynames[key][value]))

    final_group = [ project.nodes[node_id] for node_id in final_group ]

    return final_group

def indent(contents, spaces=4):
    content_lines = contents.split('\n')
    for index, line in enumerate(content_lines):
        if line.strip() != '':
            content_lines[index] = ' ' * spaces + line
    return '\n'.join(content_lines)

compile_functions = [_compile, ]

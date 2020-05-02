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
from. search import UrtextSearch
from .dynamic_output import DynamicOutput
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
        target_id = dynamic_definition.target_id
        if target_id in self.nodes:
            self.nodes[target_id].dynamic = True

    for dynamic_definition in self.dynamic_nodes:

        source_id = dynamic_definition.source_id
        points = {}
        new_node_contents = []
        
        if dynamic_definition.export:
            """
            Export
            """
            if not dynamic_definition.export_source:
                continue 

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
                
            new_node_contents.append(exported_content)

        if not dynamic_definition.target_id:
            continue

        target_id = dynamic_definition.target_id
        if not target_id:
            continue
        
        if target_id not in self.nodes:
            self._log_item('Dynamic node definition in >' + source_id +
                          ' points to nonexistent node >' + target_id)
            continue

        filename = self.nodes[target_id].filename    

        self._parse_file(filename)
                
        

        if dynamic_definition.search:

            search_term = dynamic_definition.search
            search = UrtextSearch(self, 
                search_term, 
                format_string=dynamic_definition.show)
            
            new_node_contents = search.initiate_search()

        elif dynamic_definition.tree:

            """
            Tree
            """

            if dynamic_definition.tree not in self.nodes:
                continue
            new_node_contents.append(self.show_tree_from(dynamic_definition.tree))

        elif dynamic_definition.interlinks and dynamic_definition.interlinks in self.nodes:

            """
            Interlinks
            """

            new_node_contents.append(self.get_node_relationships(
                dynamic_definition.interlinks,
                omit=dynamic_definition.omit))

        
            
        elif dynamic_definition.tag_all_key:
            
            """
            Tag All
            """
                        
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
            
            """
            Otherwise this is going to pull from contents of individual nodes,
            either as a timeline or as node list
            """

            # Allow for including other projects in the list context.

            included_projects = [self]
            if dynamic_definition.include_other_projects:
                included_projects.extend(self.other_projects)

            # Assemble requested nodes

            if dynamic_definition.include_all:
                included_nodes = set([self.nodes[node_id] for node_id in self.all_nodes()])

            else:
                included_nodes = []
              
                if 'indexed' in dynamic_definition.include_or:
                    included_nodes = [self.nodes[node_id] for node_id in self.indexed_nodes()]
    
                included_nodes = set(included_nodes)

                for project in included_projects:
                    included_nodes = included_nodes.union(_build_group_and(project, dynamic_definition.include_and))                     
                    included_nodes = included_nodes.union(_build_group_or(project, dynamic_definition.include_or))
                

            excluded_nodes = set([])
            for project in included_projects:

                excluded_nodes = excluded_nodes.union(_build_group_and(project, dynamic_definition.exclude_and))
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
                new_node_contents.append(timeline(self, included_nodes, kind=dynamic_definition.timeline_type))
 
            else:

                """ otherwise this is a list. """
                
                """ custom sort the nodes if a sort type is provided """

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
                    elif dynamic_definition.sort_keyname == 'index':
                        sort_func = lambda node: node.index

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
 
                for targeted_node in included_nodes:

                    next_content = DynamicOutput(dynamic_definition.show)
                   
                    if next_content.needs_title:
                        next_content.title = targeted_node.title
                   
                    if next_content.needs_link:
                        link = ''
                        if targeted_node.parent_project not in [self.title, self.path]:
                            link += '{"'+targeted_node.parent_project+'"}'
                        else:
                            link += '>'
                        link += '>'+ str(targeted_node.id)
                        next_content.link = link

                    if next_content.needs_date:
                        next_content.date = targeted_node.get_date(format_string = self.settings['timestamp_format'][0])
                    if next_content.needs_meta:
                        next_content.meta = targeted_node.consolidate_metadata(wrapped=False)
                    if next_content.needs_contents: 
                        next_content.contents = targeted_node.content_only().strip('\n').strip()
 
                    for meta_key in next_content.needs_other_format_keys:
                        values = targeted_node.metadata.get_meta_value(meta_key, substitute_timestamp=True)
                        replacement = ''
                        if values:
                            replacement = ' '.join(values)
                        next_content.other_format_keys[meta_key] = values

                    new_node_contents.append(next_content.output())
                        
        final_output = build_final_output(dynamic_definition, ''.join(new_node_contents))
        changed_file = self._set_node_contents(target_id, final_output)            

        if changed_file and changed_file not in modified_files:
                modified_files.append(changed_file)       
        
        if dynamic_definition.export:
            # must be reset since the file will have been re-parsed
            self.nodes[target_id].export_points = points           

        if dynamic_definition.tree:
            self.nodes[target_id].is_tree = True

        self.nodes[target_id].dynamic = True
       
    return modified_files

def build_final_output(dynamic_definition, contents):

    metadata_values = { 
        'ID': [ dynamic_definition.target_id ],
        'defined in' : [ '>'+dynamic_definition.source_id ] }

    built_metadata = ''
    for value in dynamic_definition.metadata:
        metadata_values[value] = dynamic_definition.metadata[value]

    built_metadata = UrtextNode.build_metadata(metadata_values, one_line=dynamic_definition.oneline_meta)

    title = ''
    if 'title' in dynamic_definition.metadata:
        title = dynamic_definition.metadata['title'] + '\n'

    final_contents = '\n' + title + contents + built_metadata

    if dynamic_definition.spaces:
        final_contents = indent(final_contents, dynamic_definition.spaces)

    return final_contents


def _build_group_and(project, groups):
    
    final_group = set([])
    new_group = set([])
    found_sets = []
    for pair in groups:

        new_group = set([])
        key, value = pair[0], pair[1]

        if key in project.keynames:

            if value.lower() == 'all':
                for value in project.keynames[key]:
                    new_group = new_group.union(set(project.keynames[key][value])) 

            elif value in project.keynames[key]:
                new_group = set(project.keynames[key][value])
        
        found_sets.append(new_group)

    for this_set in found_sets:
        new_group = new_group.intersection(this_set)

    final_group = set([project.nodes[node_id] for node_id in new_group])
    return final_group

def _build_group_or(project, group):
    final_group = set([])

    #key, value = pair[0], pair[1]

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

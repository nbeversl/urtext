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

"""
compile method for the UrtextProject class
"""
def _compile(self, skip_tags=False, modified_files=[]):
    """ Main method to compile dynamic nodes from their definitions """

    for dynamic_definition in list(self.dynamic_nodes):

        source_id = dynamic_definition.source_id

        # exporting is the only the thing using target files at this moment
        if not dynamic_definition.target_id and not dynamic_definition.export:
            continue

        if dynamic_definition.target_id:
            target_id = dynamic_definition.target_id

            if target_id not in list(self.nodes):
                self._log_item('Dynamic node definition >' + source_id +
                              ' points to nonexistent node >' + target_id)
                continue

            filename = self.nodes[target_id].filename
        
        # self._parse_file(filename)
        # self._update(compile_project=False)
        
        points = {} # temporary

        new_node_contents = ''

        if dynamic_definition.tree and dynamic_definition.tree in self.nodes:
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
                 clean_whitespace=True
                )
            
            if dynamic_definition.target_file:
                with open(os.path.join(self.path, dynamic_definition.target_file), 'w',encoding='utf-8') as f:
                    f.write(exported_content)
                    f.close()
                if not dynamic_definition.target_id:
                    continue

            new_node_contents = exported_content

        if dynamic_definition.tag_all_key and skip_tags:
            continue

        if dynamic_definition.tag_all_key and not skip_tags:
    
            self._add_sub_tags(
                source_id,
                target_id, 
                dynamic_definition.tag_all_key, 
                dynamic_definition.tag_all_value, 
                recursive=dynamic_definition.recursive)                    
            self._compile(skip_tags=True)
            continue
            

        else:
            # list of explicitly included node IDs
            included_nodes = []

            # list of explicitly excluded node IDs
            excluded_nodes = []

            # list of the nodes indicated by ALL the key/value pairs for AND inclusion
            included_nodes_and = []

            # for all AND key/value pairs in the dynamic definition   

            for and_group in dynamic_definition.include_and:

                this_and_group = []

                for pair in and_group:
                    
                    key, value = pair[0], pair[1]

                    # if the key/value pair is in the project
                    if key in self.tagnames and value in self.tagnames[key]:

                        # add its nodes to the list of possibly included nodes as its own set
                        this_and_group.append(set(self.tagnames[key][value]))
                        #included_nodes_and.append(set(self.tagnames[key][value]))

                    else:
                        # otherwise, this means no nodes result from this AND combination
                        this_and_group = []
                        break

                if this_and_group:

                    included_nodes.extend(
                        list(set.intersection(*this_and_group))
                        )

            for and_group in dynamic_definition.exclude_and:

                this_and_group = []

                for pair in and_group:
                    
                    key, value = pair[0], pair[1]

                    # if the key/value pair is in the project
                    if key in self.tagnames and value in self.tagnames[key]:

                        # add its nodes to the list of possibly included nodes as its own set
                        this_and_group.append(set(self.tagnames[key][value]))
                        #included_nodes_and.append(set(self.tagnames[key][value]))

                    else:
                        # otherwise, this means no nodes result from this AND combination
                        this_and_group = []
                        break

                if this_and_group:

                    excluded_nodes.extend(
                        list(set.intersection(*this_and_group))
                        )

            # add all the these nodes to the list of nodes to be included, avoiding duplicates
            for indiv_node_id in included_nodes_and:
                if indiv_node_id not in included_nodes:
                    included_nodes.append(indiv_node_id)

            if dynamic_definition.include_or == 'all':
                included_nodes = list(self.nodes.keys())
                included_nodes.remove(dynamic_definition.target_id)

            else:
                for item in dynamic_definition.include_or:
                    if len(item) < 2:
                        continue
                    key, value = item[0], item[1]
                    if value in self.tagnames[key]:
                        added_nodes = self.tagnames[key][value]
                        for indiv_node_id in added_nodes:
                            if indiv_node_id not in included_nodes:
                                included_nodes.append(indiv_node_id)

            for item in dynamic_definition.exclude_or:
                key, value = item[0], item[1]
                
                if key in self.tagnames and value in self.tagnames[key]:
                    excluded_nodes.extend(self.tagnames[key][value])

            for node in excluded_nodes:
                if node in included_nodes:
                    included_nodes.remove(node)
            """
            Assemble the node collection from the list
            """
            included_nodes = [self.nodes[node_id] for node_id in included_nodes]
            """
            build timeline if specified
            """
            if dynamic_definition.show == 'timeline':
                if target_id in included_nodes:
                    included_nodes.remove(target_id)
                new_node_contents += timeline(self, included_nodes, kind=dynamic_definition.timeline_type)

            else:
                """
                otherwise this is a list, so sort the nodes
                """
                if dynamic_definition.sort_tagname:

                    if dynamic_definition.sort_tagname == 'timestamp':
                        included_nodes = sorted(
                            included_nodes,
                            key = lambda node: node.date,
                            reverse=dynamic_definition.reverse)

                    elif dynamic_definition.sort_tagname == 'title':
                        included_nodes = sorted(
                            included_nodes,
                            key = lambda node: node.title.lower(),
                            reverse=dynamic_definition.reverse)

                    else:
                        included_nodes = sorted(
                            included_nodes,
                            key = lambda node: node.metadata.get_first_tag(
                                dynamic_definition.sort_tagname).lower(),
                            reverse=dynamic_definition.reverse)

                else:
                    included_nodes = sorted(
                        included_nodes,
                        key = lambda node: node.date,
                        reverse = dynamic_definition.reverse
                        )

                for targeted_node in included_nodes:

                    if dynamic_definition.show == 'title':
                         new_node_contents = ''.join([
                            new_node_contents, 
                            targeted_node.title,
                            ' >',
                            targeted_node.id,
                            '\n'
                            ]) 
                    if dynamic_definition.show == 'full_contents':
                        new_node_contents = ''.join([
                            new_node_contents,                            
                            ' - - - - - - - - - - - - - - - -\n',
                            '| ',targeted_node.title, ' >', targeted_node.id,'\n',
                            targeted_node.content_only().strip('\n').strip(),
                            '\n'
                            ])

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
            self._update(compile_project=False, update_lists=False)
        self.nodes[target_id].points = points
        
    return modified_files


def build_metadata(tags, one_line=False):
    """ Note this is a method from node.py. Could be refactored """

    if one_line:
        line_separator = '; '
    else:
        line_separator = '\n'
    new_metadata = '/-- '
    if not one_line: 
        new_metadata += line_separator
    for tag in tags:
        new_metadata += tag + ': '
        if isinstance(tags[tag], list):
            new_metadata += ' | '.join(tags[tag])
        else:
            new_metadata += tags[tag]
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

compile_functions = [_compile]
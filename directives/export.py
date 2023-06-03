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

import os
import re

if os.path.exists(os.path.join(os.path.dirname(os.path.realpath(__file__)), '../sublime.txt')):
    from Urtext.urtext.directive import UrtextDirective
    import Urtext.urtext.node
    import Urtext.urtext.syntax as syntax
else:
    from urtext.directive import UrtextDirective
    import urtext.node
    import urtext.syntax as syntax

class UrtextExport(UrtextDirective):

    name = ["EXPORT"]
    phase = 500

    def dynamic_output(self, input):
        if 'root' in self.params_dict:
            return self.export_from(
               self.params_dict['root'][0],
                )
        return ''

    def export_from(self, 
        root_node_id, 
        exclude=None, 
        ):
 
        if exclude == None:
            exclude = []

        visited_nodes = []
        points = {}
       
        exported_content, points, visited_nodes = self._add_node_content(
            root_node_id,
            exclude=exclude,
            visited_nodes=visited_nodes,
            points=points,
            )

        return exported_content

    def _add_node_content(self, 
            root_node_id,   # node to start from
            added_contents = None,
            exclude=None,
            nested=None,
            points = None,                               
            visited_nodes=None,
            ):
       
        if exclude == None:
            exclude = []
        
        if not root_node_id:
            print('Root node ID is None')
            return

        if root_node_id not in self.project.nodes:
            print('EXPORT: Root node ID ' + root_node_id +' not in the project.')
            return '','',''    

        """
        Get and set up initial values
        """
        if points == None:
            points = {}
        if added_contents == None:
            added_contents = ''
        if visited_nodes == None:
            visited_nodes = []
        if exclude == None:
            exclude = []
        if nested == None:
            nested = 0

        ranges = self.project.nodes[root_node_id].ranges
        filename = self.project.nodes[root_node_id].filename
        file_contents = self.project.files[filename]._get_file_contents()
        title = self.project.nodes[root_node_id].title

        if root_node_id in exclude or root_node_id in visited_nodes:
            return '\n' + added_contents, points, visited_nodes
        """
        Recursively add nodes, its inline nodes and node pointers, in order
        from a given starting node, keeping track of nesting level, and wrapping in markup.        
        """    
        visited_nodes.append(root_node_id)

        """ get all the node pointers and their locations"""
        locations = []
        for single_range in ranges:
            locations.extend(self.get_node_pointers_with_locations(
                file_contents[single_range[0]:single_range[1]]))
            """ locations contain tuple of (location, matched_text)"""

        """ sort node pointers in order of occurrence and remember the node_ids"""
        node_pointer_locations = {}
        for location in locations:
            node_pointer_locations[location[0]] = location[1]
            if location[1] not in visited_nodes:
                visited_nodes.append(location[1])

        range_number = 0
        for single_range in ranges:

            """ Get and add the range's contents """
            range_contents = file_contents[single_range[0]:single_range[1]]           
            range_contents = self._strip_urtext_syntax(range_contents)

            """ If first range, replace and reformat title """
            if single_range == ranges[0]:
                range_contents = re.sub(re.escape(title)+r'(\s+_)?', '', range_contents, 1)
                if range_contents:
                    range_contents = self.wrap_title(root_node_id, nested) + range_contents
                else:
                    range_contents = self.wrap_title(root_node_id, nested) + '\n'

            # range_contents = range_contents.rstrip()
            range_contents = strip_indent(range_contents)
            range_contents = indent(range_contents, nested + 1)
            range_contents = self.replace_range(range_contents, range_number, nested)   
            range_contents = self.before_replace_node_links(range_contents)
            
            if not self.project.nodes[root_node_id].is_tree or not self.have_flags('-preformat'):
                ## Only replace node links if this is not a tree
                ## or it is a tree and preformat was not selected
                range_contents = self.replace_node_links(range_contents)

            range_contents = self.after_replace_node_links(range_contents)
            """
            If this is end of the node, add a wrapper if needed
            """
            if single_range[1] == ranges[-1][1]:
                range_contents += self.closing_wrapper()
            """
            #TODO
            FUTURE: map the exported content to the source content.
            (returns node ID and exact FILE location)
            Note each point will be relative to the beginning of the 
            containing node, not the beginning of the file containing the export.
            """
            if (len(added_contents), len(added_contents) + len(range_contents) ) in points:
                del points[ (len(added_contents), len(added_contents) + len(range_contents) ) ]
            points[ (len(added_contents), len(added_contents) + len(range_contents) ) ] = ( root_node_id, single_range[0] )

            added_contents += range_contents
            
            """
            If adding subnodes, find the id of the node immediately following this range
            and add it, assuming we are including all sub-nodes.
            TODO: Add checking in here for excluded nodes
            """
            if not self.have_flags('-single_node_only') and single_range[1] < ranges[-1][1]:
                next_node = self.project.get_node_id_from_position(filename, single_range[1] + 1)
                if next_node and next_node not in visited_nodes:

                    next_nested = nested + 1

                    """ recursively add the node in the next range and its subnodes """
                    added_contents, points, visited_nodes = self._add_node_content(
                        next_node,
                        added_contents=added_contents,
                        points=points,       
                        exclude=exclude,
                        nested=next_nested,
                        visited_nodes=visited_nodes,
                        )

            range_number += 1
                   
        """ replace node pointers with their contents recursively"""

        if not self.project.nodes[root_node_id].dynamic :  
            if self.have_flags('-as_single_file'):
                added_contents, points, visited_nodes = self.replace_node_pointers(
                    nested,
                    node_pointer_locations,
                    added_contents=added_contents,
                    points=points,         
                    exclude=exclude,
                    visited_nodes=visited_nodes,
                   )
        
        return added_contents, points, visited_nodes
    
    def replace_range(self, range_contents, range_number, nested):
        return range_contents

    def is_escaped(self, escaped_regions, region):
        for e in escaped_regions:
            escaped_range = range(e.start(),e.end())
            if region[0] in escaped_range or region[1] in escaped_range:
                return True
        return False

    def after_replace_node_links(self, contents):
        return contents
        
    def get_node_pointers_with_locations(self, text, escaped_regions=[]):

        matches = []
        locations = []
        for m in syntax.node_pointer_c.finditer(text):
            if not self.is_escaped(escaped_regions, (m.start(), m.end())):
               locations.append((text.find(m.group()), m.group()))
        return locations

    def replace_node_pointers(self,     
        nested, 
        node_pointer_locations, # dict
        added_contents=None,
        points=None,                                                                 
        exclude=[],
        visited_nodes=None,
        ):
    
        if visited_nodes == None:
            visited_nodes = []
        if points == None:
            points = {}
        if added_contents == None:
            added_contents = ''

        locations = sorted(node_pointer_locations)

        for location in locations:

            match = node_pointer_locations[location]

            #TODO use regex instead
            node_id = match[2:-3]

            pointer_length = len(match)

            first_contents = added_contents.split(match)[0]
              
            remaining_contents = ''.join(added_contents.split(match)[1:])
          
            """
            Avoid recursion
            """
            if node_id in visited_nodes:
                inserted_contents = '\n' + '#' * nested + ' ! RECURSION : '+ node_id
                continue       
            
            if node_id not in self.project.nodes:                    
                visited_nodes.append(node_id)
                print('SKIPPING '+node_id)
                continue                            

            # split points here:
            points_so_far = {}
            points_after_that = {}

            length_up_to_pointer = len(first_contents)
            
            for export_range in points:
                if length_up_to_pointer in range(export_range[0], export_range[1]):
                    # need to adjust ranges here since we took out the pointer

                    points_so_far[ (export_range[0], length_up_to_pointer) ] = points[export_range]
                    points_after_that[ (length_up_to_pointer, export_range[1] - pointer_length) ] = points[export_range]
                    continue

                if length_up_to_pointer > export_range[1]:
                    points_so_far[export_range] = points[export_range]
                    continue

                if length_up_to_pointer < export_range[0]:
                    points_after_that[(export_range[0]- pointer_length, export_range[1]-pointer_length)] = points[export_range]
                    continue
                    
            added_contents, points_so_far, visited_nodes = self._add_node_content(
                node_id, 
                added_contents=first_contents,
                points=points_so_far,
                nested=nested+1,
                exclude=exclude,
                visited_nodes=visited_nodes,
                )

            length_after = len(added_contents)
            amount_added = length_after - length_up_to_pointer

            for export_range in points_after_that:
                points_so_far[ (export_range[0] + amount_added, export_range[1] + amount_added)  ] = points_after_that[export_range]

            added_contents += remaining_contents
           
            visited_nodes.append(node_id)
            
            points = points_so_far
            
        return added_contents, points, visited_nodes


    def replace_node_links(self, contents):
        """ replace node links, including titled ones, with exported versions """

        node_links = syntax.node_link_c.finditer(contents)
        for match in node_links:
            node_id = match.group(2) 
            if node_id not in self.project.nodes:                    
                contents = contents.replace(match.group(), '[ MISSING LINK : '+node_id+' ] ')
                continue

            title = self.project.nodes[node_id].title
            contents = self.replace_link(contents, title)                                    
        
        return contents

    def replace_link(self, contents, title):
        return contents

    def replace_file_links(self, contents, escaped_regions):
        to_replace = []
        for link in syntax.file_link_c.finditer(contents):
            if not self.is_escaped(escaped_regions, (link.start(), link.end())):
                to_replace.append(link)
        for link in to_replace:
            contents = contents.replace(link.group(), '['+link.group()[2:]+']('+link.group()[2:]+')')
        return contents

    def _strip_urtext_syntax(self, contents):
        contents = Urtext.urtext.node.strip_contents(contents, 
            include_backtick=False,
            reformat_and_keep_embedded_syntaxes=True).strip()           
        return contents

    def opening_wrapper(self, node_id, nested):
        return ''

    def before_replace_node_links(self, range_contents):
        return range_contents

    def closing_wrapper(self):
        return ''

    def wrap_title(self, node_id, nested):        
        title = self.project.nodes[node_id].title
        return '\n' + '\t' * nested + title

def preformat_embedded_syntaxes(text):
    #TODO update
    text = re.sub(r'%%\w+[\s|$]','```',text )
    text = re.sub(r'%%[\s|$]','```', text)
    return text

def strip_indent(text):
    return '\n'.join([line.strip() for line in text.split('\n')])

def indent(text, tabs):
    return '\n'.join(['\t' * tabs + line for line in text.split('\n')])

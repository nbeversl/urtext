
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

from urtext.node import UrtextNode
import os


def _compile(self):
    
    for dynamic_definition in self.dynamic_defs():
        if dynamic_definition.target_id in self.nodes:
            self.nodes[dynamic_definition.target_id].dynamic = True

    for dynamic_definition in self.dynamic_defs(): 
        self._process_dynamic_def(dynamic_definition)

def _compile_file(self, filename):
   
    modified = False
    filename = os.path.basename(filename)
    for node_id in self.files[filename].nodes:
        for dd in self.dynamic_defs(target=node_id):
            if self._process_dynamic_def(dd) and not modified:
                modified = filename
   
    return modified

def _process_dynamic_def(self, dynamic_definition):

    # points = {} # Future
    new_node_contents = []

    if not dynamic_definition.target_id:
        return
    if dynamic_definition.target_id not in self.nodes:
        return self._log_item('Dynamic node definition in >' + dynamic_definition.source_id +
                      ' points to nonexistent node >' + dynamic_definition.target_id)

    output = dynamic_definition.process_output()            
    final_output = build_final_output(dynamic_definition, output) 
       
    if dynamic_definition.target_id in self.nodes:
        changed_file = self._set_node_contents(dynamic_definition.target_id, final_output)            
    
    if dynamic_definition.target_id in self.nodes:

        # Dynamic nodes have blank title by default. Title can be set by header or title key.
        if not self.nodes[dynamic_definition.target_id].metadata.get_first_value('title'): #and not dynamic_definition.header:
            self.nodes[dynamic_definition.target_id].title = ''

        messages_file = self._populate_messages()
    
        return changed_file

    return None

def build_final_output(dynamic_definition, contents):

    metadata_values = {}
    if dynamic_definition.target_id:
        metadata_values['ID'] = dynamic_definition.target_id
        metadata_values['def'] = [ '>'+dynamic_definition.source_id ] 

    built_metadata = UrtextNode.build_metadata(
        metadata_values, 
        one_line = not dynamic_definition.multiline_meta)

    final_contents = ''.join([
        ' ', ## TODO: Make leading space an option.
        contents,
        built_metadata,
        ' '
        ])
    if dynamic_definition.spaces:
        final_contents = indent(final_contents, dynamic_definition.spaces)

    return final_contents

def indent(contents, spaces=4):
  
    content_lines = contents.split('\n')
    content_lines[0] = content_lines[0].strip()
    for index, line in enumerate(content_lines):
        if line.strip() != '':
            content_lines[index] = '\t' * spaces + line
    return '\n'+'\n'.join(content_lines)

compile_functions = [_compile,_process_dynamic_def, _compile_file ]

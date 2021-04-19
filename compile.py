
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

from urtext.export import UrtextExport
from urtext.node import UrtextNode
from urtext.search import UrtextSearch
from urtext.dynamic_output import DynamicOutput
import os
"""
compile method for the UrtextProject class
"""
def _compile(self):
    
    for dynamic_definition in self.dynamic_defs():
        if dynamic_definition.target_id in self.nodes:
            self.nodes[dynamic_definition.target_id].dynamic = True

    for dynamic_definition in self.dynamic_defs(): 
        self._process_dynamic_def(dynamic_definition)

def _compile_file(self, filename):
    filename = os.path.basename(filename)
    for node_id in self.files[filename].nodes:
        for dd in self.nodes[node_id].dynamic_definitions:
            self._process_dynamic_def(dd)
        for dd in self.dynamic_defs(target=node_id):
            self._process_dynamic_def(dd)

def _process_dynamic_def(self, dynamic_definition):

    points = {}
    new_node_contents = []

    if not dynamic_definition.target_id:
        return
    if dynamic_definition.target_id and dynamic_definition.target_id not in self.nodes:
        return self._log_item('Dynamic node definition in >' + dynamic_definition.source_id +
                      ' points to nonexistent node >' + dynamic_definition.target_id)

    #print(dynamic_definition.target_id)
    outcome = []
    operations = sorted(dynamic_definition.operations, key = lambda op: op.phase) 
    for operation in operations:
        #print(operation)
        outcome = operation.execute(outcome, [self], dynamic_definition.show)
      
    # if dynamic_definition.target_id:
    #     outcome.discard(dynamic_definition.target_id)           
            
    final_output = build_final_output(dynamic_definition, outcome) 
    
    # if dynamic_definition.target_id and dynamic_definition.target_id in self.h_content:
    #     if self.h_content[dynamic_definition.target_id] == hash(final_output):
    #         return

    # if dynamic_definition.exports and dynamic_definition.exports[0] in self.dynamic_memo:
    #     if self.dynamic_memo[dynamic_definition.exports[0]]['contents'] == hash(final_output):
    #         return

    # if dynamic_definition.exports:
    #     self.dynamic_memo[dynamic_definition.exports[0]] = {}
    #     self.dynamic_memo[dynamic_definition.exports[0]]['contents'] = hash(final_output)
    
    if dynamic_definition.target_id:
       
        changed_file = self._set_node_contents(dynamic_definition.target_id, final_output)                    
  
        self.nodes[dynamic_definition.target_id].dynamic = True

        # Dynamic nodes have blank title by default. Title can be set by header or title key.
        if not self.nodes[dynamic_definition.target_id].metadata.get_first_value('title'): #and not dynamic_definition.header:
            self.nodes[dynamic_definition.target_id].title = ''

        messages_file = self._populate_messages()

    # if dynamic_definition.exports:

    #     for e in dynamic_definition.exports:

    #         exported = UrtextExport(self) 
    #         exported_content = ''
    #         for node in included_nodes:
    #             node_export, points = exported.export_from(
    #                  node.id,
    #                  kind=e.output_type,
    #                  exclude=list(excluded_nodes),
    #                  as_single_file=True, # TODO should be option 
    #                  #clean_whitespace=True,
    #                  preformat=e.preformat)
                
    #             exported_content += '\n'+node_export

    #         for n in e.to_nodes:
                
    #             if n in self.nodes:
                    
    #                 metadata_values = { 
    #                     'ID': [ n ],
    #                     'def' : [ '>'+dynamic_definition.source_id ] }

    #                 built_metadata = UrtextNode.build_metadata(
    #                     metadata_values, 
    #                     one_line = True)
    #                     #not dynamic_definition.multiline_meta)

    #                 changed_file = self._set_node_contents(n, exported_content + built_metadata)                       
    #                 self.nodes[n].export_points = points           
    #                 self.nodes[n].dynamic = True

    #         for f in e.to_files:
    #             with open(os.path.join(self.path, f), 'w',encoding='utf-8') as f:
    #                 f.write(exported_content)


def build_final_output(dynamic_definition, contents):

    metadata_values = {}
    if dynamic_definition.target_id:
        metadata_values['ID'] = dynamic_definition.target_id
        metadata_values['def'] = [ '>'+dynamic_definition.source_id ] 

    built_metadata = UrtextNode.build_metadata(
        metadata_values, 
        one_line = True )
        #one_line = not dynamic_definition.multiline_meta)

   

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


from urtext.action import UrtextAction
import os
import datetime
import re

class PopNode(UrtextAction):

    name=['POP_NODE']

    def execute(self, 
        param_string, 
        filename=None,
        file_pos=0,
        col_pos=0, 
        node_id=None):
        """
        Pops a node asyncronously, making sure that if the file was saved and on_modified
        was called in the same calling function, this completes before evaluating
        the node_id from the position.

        Returns a future containing a list of modified files as the result.
        """
        if self.project.is_async:
            self.project.executor.submit(
                self._pop_node, 
                param_string, 
                os.path.basename(filename), 
                file_pos=file_pos) 
        else:
            self._pop_node(
                param_string, 
                os.path.basename(filename), 
                file_pos=file_pos)

    def _pop_node(self, 
        param_string, 
        filename, 
        file_pos=None,  
        node_id=None):
 
        if not node_id:
            node_id = self.project.get_node_id_from_position(
                filename, 
                file_pos)
 
        if not node_id:
            print('No node ID or duplicate Node ID')
            return None
        
        if self.project.nodes[node_id].root_node:
            print(node_id+ ' is already a root node.')
            return None

        start = self.project.nodes[node_id].ranges[0][0]
        end = self.project.nodes[node_id].ranges[-1][1]
        filename = self.project.nodes[node_id].filename
        file_contents = self.project.files[filename]._get_file_contents()
        
        popped_node_id = node_id

        filename = self.project.nodes[node_id].filename

        popped_node_contents = file_contents[start:end].strip()
        parent_id = self.project.nodes[node_id].tree_node.parent

        if self.project.settings['breadcrumb_key']:
            popped_node_contents += '\n'+self.project.settings['breadcrumb_key']+'::>'+parent_id.name+ ' '+self.project.timestamp(datetime.datetime.now());

        remaining_node_contents = ''.join([
            file_contents[0:start - 1],
            '\n| ',
            self.project.nodes[popped_node_id].title,
             ' >>',
            popped_node_id,
            '\n',
            file_contents[end + 1:]])
       
        with open (os.path.join(self.project.path, filename), 'w', encoding='utf-8') as f:
            f.write(remaining_node_contents)
        self.project._parse_file(filename) 

        # new file
        with open(os.path.join(self.project.path, popped_node_id+'.txt'), 'w',encoding='utf-8') as f:
            f.write(popped_node_contents)
        self.project._parse_file(popped_node_id+'.txt') 
        
class PullNode(UrtextAction):

    name=['PULL_NODE']

    def execute(self, 
        string, 
        filename, 
        file_pos=0, 
        col_pos=0):
        
        """ File must be saved in the editor first for this to work """
        if self.project.is_async:
            return self.project.executor.submit(
                self._pull_node, 
                string, 
                os.path.basename(filename), 
                file_pos=file_pos,
                col_pos=col_pos) 
        else:
            self._pull_node(
                string, 
                os.path.basename(filename), 
                file_pos=file_pos, 
                col_pos=col_pos)
    
    def _pull_node(self, 
        string, 
        destination_filename, 
        file_pos=0,
        col_pos=0):
        
        replacement_contents = None

        link = self.project.get_link(
            string,
            destination_filename,
            file_pos=file_pos,
            col_pos=col_pos)
        
        if not link or link['kind'] != 'NODE': 
            return None
        
        node_id = link['link']
        if node_id not in self.project.nodes: 
            return None

        current_node = self.project.get_node_id_from_position(destination_filename, file_pos)
        if not current_node:
            return None

        start = self.project.nodes[node_id].ranges[0][0]
        end = self.project.nodes[node_id].ranges[-1][1]
        
        source_filename = self.project.nodes[node_id].filename
        if source_filename == destination_filename:
            print('Cannot pull a node from the same file.')
            return
        contents =self.project.files[source_filename]._get_file_contents()

        replaced_file_contents = ''.join([contents[0:start-1],contents[end+1:len(contents)]])

        if self.project.nodes[node_id].root_node:
            self.project.delete_file(self.project.nodes[node_id].filename)  
        else:
            self.project.files[source_filename]._set_file_contents(replaced_file_contents)
            self.project._parse_file(self.project.nodes[node_id].filename)

        pulled_contents = contents[start:end]
        full_current_contents = self.project.files[destination_filename]._get_file_contents()

        link_location = link['link_location']
    
        wrapped_contents = ''.join(['{',pulled_contents,'}'])

        for m in re.finditer(re.escape(link['link_match']), full_current_contents):

            if m.start() < link['link_location'] < m.end():
                
                replacement_contents = ''.join([
                    full_current_contents[:m.start()],
                    wrapped_contents,
                    full_current_contents[m.end():]]
                    )
                break

        if replacement_contents:

            self.project.files[destination_filename]._set_file_contents(replacement_contents)
            self.project._parse_file(destination_filename)
            



        
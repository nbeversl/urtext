import os
import concurrent.futures
from urtext.action import UrtextAction
from ..extensions.rake import Rake
from urtext.node import strip_contents

class RakeGetAssociatedNotes(UrtextAction):
    """ 
    sorts all file-level nodes by their index, then passes
    the result to rename_file_nodes() to rename them.
    """    
    name=['RAKE_GET_ASSOC']
    
    def execute(self, 
        param_string, 
        filename=None,
        file_pos=0,
        col_pos=0, 
        node_id=None):

        return self.get_assoc_nodes(param_string, filename, file_pos)

    def get_assoc_nodes(self, string, filename, position):
        node_id = self.project.get_node_id_from_position(filename, position)
        r = Rake()
        string = strip_contents(string)
        keywords = [t[0] for t in r.run(string)]
        assoc_nodes = []
        for k in keywords:
             assoc_nodes.extend(self.project.extensions['RAKE_KEYWORDS'].get_by_keyword(k))
        assoc_nodes = list(set(assoc_nodes))
        if node_id in assoc_nodes:
            assoc_nodes.remove(node_id)
        for node_id in assoc_nodes:
            if self.project.nodes[node_id].dynamic:
                assoc_nodes.remove(node_id)
        return assoc_nodes


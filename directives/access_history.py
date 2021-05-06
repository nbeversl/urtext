from urtext.directive import UrtextDirectiveWithKeysFlags
import datetime

class AccessHistory(UrtextDirectiveWithKeysFlags):

    name = ["ACCESS_HISTORY"]
    phase = 250

    def on_node_visited(self, node_id):

        if node_id in self.dynamic_definition.included_nodes:
            
            if self.dynamic_definition.target_id in self.project.nodes:
                contents = self.project.nodes[self.dynamic_definition.target_id].contents()
                contents = ''.join([ 
                        '\n',
                        self.project.timestamp(datetime.datetime.now()), 
                        ' ', 
                        self.project.nodes[node_id].title, 
                        ' >', 
                        node_id,
                        '\n',
                        contents
                    ])
                self.project.executor.submit(self.project._set_node_contents, 
                    self.dynamic_definition.target_id, 
                    contents)
                
    def dynamic_output(self, input):
        return False









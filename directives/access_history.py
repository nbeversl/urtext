from urtext.directive import UrtextDirectiveWithKeysFlags
import datetime

class AccessHistory(UrtextDirectiveWithKeysFlags):

    name = ["ACCESS_HISTORY"]
    phase = 250

    def on_node_visited(self, node_id):
        self.dynamic_definition.process_output(max_phase=200)
        if node_id in self.dynamic_definition.included_nodes:
            if self.dynamic_definition.target_id in self.project.nodes:
                contents = self.project.nodes[self.dynamic_definition.target_id].contents()
                contents = ''.join([ 
                        '\n',
                        self.project.timestamp(self.project.default_timezone.localize(datetime.datetime.now())), 
                        ' ', 
                        self.project.nodes[node_id].title, 
                        ' >', 
                        node_id,
                        contents
                    ])
                self.project._set_node_contents(self.dynamic_definition.target_id, contents)
        else:
            print('(DEBUGGING) -- node not found for access history')

    def dynamic_output(self, input_contents):
        return False # do not change existing output.




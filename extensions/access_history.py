from urtext.extensions.extension import UrtextExtensionWithKeysFlags
import datetime

class AccessHistory(UrtextExtensionWithKeysFlags):

    name = ["ACCESS_HISTORY"]
    phase = 250
    
    def on_node_visited(self, node):
        return
        print(node)
        if self.dynamic_definition.target_id in self.project.nodes:
            contents = self.project.nodes[self.dynamic_definition.target_id].contents()
            contents = ''.join([
                    self.project.datestamp(datetime.datetime.now()) + ' ' + node.title + ' >'+node.id
                ])
            self.project._set_node_contents(contents)









from anytree import Node, RenderTree, PreOrderIter
from anytree.render import ContStyle
from urtext.dynamic_output import DynamicOutput
from urtext.timestamp import UrtextTimestamp
import datetime
from urtext.directive import UrtextDirectiveWithParamsFlags, UrtextDirectiveWithInteger

"""
Tree
"""

class Tree(UrtextDirectiveWithParamsFlags):

    name = ["TREE"]
    phase = 210
    
    def __init__(self, project):
        super().__init__(project)
        self.depth = 10

    def dynamic_output(self, start_point):
        exclude=None,
        from_root_of=False
                
        if self.have_flags('*'):
            self.depth = 999999
        
        start_point = start_point.tree_node
        if from_root_of == True:
            start_point = project.nodes[node_id].tree_node.root

        alias_nodes = self._has_aliases(start_point)

        while alias_nodes:  
            for leaf in alias_nodes:
                if leaf.name[:5] == 'ALIAS':
                    node_id = leaf.name[-3:]
                    new_tree = self.duplicate_tree(self.project.nodes[node_id].tree_node, leaf)            
                    leaf.children = new_tree.children
            alias_nodes = self._has_aliases(start_point)
     
        tree_render = ''
        
        for pre, _, this_node in RenderTree(
                start_point, 
                style=ContStyle, 
                maxlevel=self.depth):
            
            if self._tree_node_is_excluded(this_node, exclude):
                this_node.children = []
                continue

            if not this_node.name[-3:] in self.project.nodes:
                tree_render += "%s%s" % (pre, this_node.name + ' NOT IN PROJECT (DEBUGGING)\n')    
                continue

            if this_node.name[:11] == '! RECURSION':
                tree_render += "%s%s" % (pre, this_node.name + '\n')    
                continue

            if this_node.name[:5] == 'ALIAS':
                urtext_node = self.project.nodes[this_node.name[-3:]]
            else:
                urtext_node = self.project.nodes[this_node.name]
            
            # need to pass SHOW here somehow.
            next_content = DynamicOutput(  self.dynamic_definition.show, self.project.settings)
           
            if next_content.needs_title:
                next_content.title = urtext_node.title
           
            if next_content.needs_link:
                link = []
                if urtext_node.parent_project not in [self.project.title, self.project.path]:
                    link.extend(['{"',this_node.parent_project,'"}'])
                else:
                    link.append('>')
                link.append(str(urtext_node.id))
                next_content.link = ''.join(link)

            if next_content.needs_date:
                next_content.date = urtext_node.get_date(self.project.settings['node_date_keyname']).strftime(self.project.settings['timestamp_format'])

            if next_content.needs_meta:
                next_content.meta = urtext_node.consolidate_metadata(separator=':')

            if next_content.needs_contents: 
                next_content.contents = urtext_node.content_only().strip('\n').strip()

            if next_content.needs_last_accessed: 
                t = datetime.datetime.utcfromtimestamp(urtext_node.metadata.get_first_value('_last_accessed'))
                next_content.last_accessed = t.strftime(self.project.settings['timestamp_format'])

            for meta_key in next_content.needs_other_format_keys:
                
                k, ext = meta_key, ''
                if '.' in meta_key:
                    k, ext = meta_key.split('.')
                replacement = ''
                if ext in ['timestamp','timestamps']:  
                    timestamps = urtext_node.metadata.get_values(k, use_timestamp=True)
                    if timestamps:
                        if ext == 'timestamp':
                            replacement = timestamps[0].string
                        else:
                            replacement = ' | '.join([t.string for t in e.timestamps])
                else:
                    replacement = ' | '.join(urtext_node.metadata.get_values(k))
                next_content.other_format_keys[meta_key] = replacement

            tree_render += "%s%s" % (pre, next_content.output())

        return tree_render

    def on_project_init(self):        
        return
        
    
    def _tree_node_is_excluded(self, tree_node, excluded_nodes):

        if not excluded_nodes:
            return False

        node_id = tree_node.name[-3:]

        if node_id in excluded_nodes:
            return True

        if node_id not in self.project.nodes:
            return True

        for ancestor in self.project.nodes[node_id].tree_node.ancestors:
            if ancestor.name[-3:] in excluded_nodes:
                return True

        return False

    def _has_aliases(self, start_point):
        
        alias_nodes = []
        leaves = start_point.leaves  

        for leaf in leaves:
            ancestors = [a.name for a in leaf.ancestors]
            if 'ALIAS' in leaf.name and leaf.name[-3:] in self.project.nodes and self.project.nodes[leaf.name[-3:]].tree_node.children:
                if leaf.name[-3:] not in ancestors:
                    alias_nodes.append(leaf)
                else:
                    leaf.name = '! RECURSION - (from alias) : '+ self.project.nodes[leaf.name[-3:]].title + ' >'+leaf.name[-3:]

        return alias_nodes

    def duplicate_tree(self, original_node, leaf):

        new_root = Node(original_node.name)
        ancestors = [ancestor.name[-3:] for ancestor in leaf.ancestors]
        ancestors.extend([ancestor.name[-3:] for ancestor in original_node.ancestors])
        ancestors.append(leaf.name[-3:])
        ancestors.append(original_node.root.name[-3:])
        ancestors.append(original_node.name[-3:])

        # iterate immediate children only
        all_nodes = PreOrderIter(original_node, maxlevel=2)  

        for node in all_nodes: 
     
            if 'ALIAS' in node.name:            
                node_id = node.name[-3:] 
                if node_id not in ancestors:
                    if node_id in self.project.nodes:
                        new_node = Node(node.name)
                        new_node.parent = new_root
                    else:
                        new_node = Node('! (Missing Node) >'+node_id)
                        new_node.parent = new_root            
                else:
                    new_node = Node('! RECURSION (from tree duplication) : '+ self.project.nodes[node_id].title + ' >'+node_id)
                    new_node.parent = new_root  
                continue

            if node.parent == original_node:
                """ Recursively apply this function to children's children """
                new_node = self.duplicate_tree(node, leaf)
                new_node.parent = new_root

        return new_root

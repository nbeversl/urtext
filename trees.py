from anytree import Node, RenderTree, PreOrderIter
from anytree.render import ContStyle

"""
Tree building
"""
def _set_tree_elements(self, filename):
    """ Builds tree elements within the file's nodes, after the file is parsed."""

    parsed_items = self.files[filename].parsed_items
    positions = sorted(parsed_items)

    for index, position in enumerate(positions):

        node = parsed_items[position]

        #
        # If the parsed item is a tree marker to another node,
        # parse the markers, positioning it within its parent node
        #

        if node[:2] == '>>':
            inserted_node_id = node[2:]
            for other_node in [
                    node_id for node_id in self.files[filename].nodes
                    if node_id != node ]:  

                if self._is_in_node(position, other_node):
                    parent_node = other_node
                    alias_node = Node(inserted_node_id)
                    alias_node.parent = self.nodes[parent_node].tree_node
                    if alias_node not in self.alias_nodes:
                        self.alias_nodes.append(alias_node)
                    break
            continue

        if self.nodes[node].root_node:
            continue

        """
        in case this node begins the file and is an an inline node,
        set the inline node's parent as the root node manually.
        """

        if position == 0 and parsed_items[0] == '{{':
            self.nodes[node].tree_node.parent = self.nodes[root_node_id].tree_node
            continue
        """
        if this is a compact node, its parent is the node right before it.
        <Thu., Feb. 27, 2020, 08:00 AM -0500>
        This is actually not true.The node right before it could be another compact node.
        """
            
        if self.nodes[node].compact or self.nodes[node].split:               
            parent = self.get_parent(node)
            self.nodes[node].tree_node.parent = self.nodes[parent].tree_node
            continue

        """
        if this is a split node and its predecessor is already parsed,
        get the parent from the predecessor
        """
        # TODO this needs to be refactored and done more elegantly.
        if index > 0 and parsed_items[positions[index-1]][:2] not in ['>>']:
            if self.nodes[parsed_items[position]].split:
                self.nodes[parsed_items[position]].tree_node.parent = self.nodes[parsed_items[positions[index-1]]].tree_node.parent
                continue
            
        """
        Otherwise, this is either an inline node not at the beginning of the file,
        or else a root (file level) node, so:
        """
        if not self.nodes[node].root_node:
            parent = self.get_parent(node)
            self.nodes[node].tree_node.parent = self.nodes[parent].tree_node

def _build_alias_trees(self):
    """ 
    Adds copies of trees wherever there are Node Pointers (>>) 
    Must be called only when all nodes are parsed (exist) so it does not miss any
    """

    # must use EXISTING node so it appears at the right place in the tree.
    for node in self.alias_nodes:
        node_id = node.name[-3:]
        if node_id in self.nodes:
            duplicate_node = self.nodes[node_id].duplicate_tree()
            node.children = [s for s in duplicate_node.children]
        else:
            new_node = Node('MISSING NODE ' + node_id)

def _rewrite_recursion(self):

    for node in self.alias_nodes:
        all_nodes = PreOrderIter(node)
        for sub_node in all_nodes:
            if sub_node.name in [
                    ancestor.name for ancestor in sub_node.ancestors
            ]:
                sub_node.name = 'RECURSION : ' + self.nodes[sub_node.name].title + ' >'+sub_node.name
                sub_node.children = []

def _detach_excluded_tree_nodes(self, root_id, flag='tree'):

    for descendant in self.nodes[root_id.name].tree_node.descendants:

        flag = flag.lower()

        # allow for tree nodes with names that are not node IDs, 
        # such as RECURION >, etc. 
        if descendant.name not in self.nodes:
            continue 

        # Otherwise, remove it from the tree if it is flagged
        if flag == 'tree' and 'exclude_from_tree' in self.nodes[descendant.name].metadata.get_tag('flags'):
            descendant.parent = None
            continue

        # Otherwise, remove it from export if it is flagged
        if flag == 'export' and 'exclude_from_export' in self.nodes[descendant.name].metadata.get_tag('flags'):
            descendant.parent = None


def show_tree_from(self, 
                   node_id,
                   from_root_of=False):

    if node_id not in self.nodes:
        self._log_item(root_node_id + ' is not in the project')
        return None

    tree_render = ''

    start_point = self.nodes[node_id].tree_node

    if from_root_of == True:
        start_point = self.nodes[node_id].tree_node.root

    self._detach_excluded_tree_nodes(start_point)

    #no_line = AbstractStyle('    ','├── ','└── ')

    for pre, _, this_node in RenderTree(start_point,style=ContStyle ):
        if this_node.name in self.nodes:
            tree_render += "%s%s" % (pre, self.nodes[
                this_node.name].title) + ' >' + this_node.name + '\n'
        elif this_node.name[0:9] == 'RECURSION':
            tree_render += "%s%s" % (pre, this_node.name + '\n')   
        else: 
            tree_render += "%s%s" % (pre, '? (Missing Node): >' +
                                 this_node.name + '\n')
    return tree_render

trees_functions=[
    show_tree_from, 
    _detach_excluded_tree_nodes, 
    _rewrite_recursion, 
    _build_alias_trees,
    _set_tree_elements
    ]

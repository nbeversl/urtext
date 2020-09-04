from anytree import Node, RenderTree, PreOrderIter
from anytree.render import ContStyle
from .dynamic_output import DynamicOutput
import datetime

"""
Tree building
"""
def _set_tree_elements(self, filename):
    """ Builds tree elements within the file's nodes, after the file is parsed."""

    parsed_items = self.files[filename].parsed_items
    positions = sorted(parsed_items)

    for index, position in enumerate(positions):

        node = parsed_items[position]
        # parse each marker, positioning it within its parent node
        if node[:2] == '>>':
            inserted_node_id = node[2:]
            for other_node in [
                    node_id for node_id in self.files[filename].nodes
                    if node_id != node ]:  

                if self._is_in_node(position, other_node):
                    parent_node = other_node
                    alias_node = Node('ALIAS'+inserted_node_id)
                    alias_node.parent = self.nodes[parent_node].tree_node
                    if inserted_node_id not in self.alias_nodes:
                        self.alias_nodes.append(Node(inserted_node_id))
                    break
            continue

        if self.nodes[node].root_node:
            continue

        """
        in case this node begins the file and is an an inline node,
        set the inline node's parent as the root node manually.
        """

        if position == 0 and parsed_items[0] == '{':
            self.nodes[node].tree_node.parent = self.nodes[root_node_id].tree_node
            continue
        """
        if this is a compact node, its parent is the node right before it.
        <Thu., Feb. 27, 2020, 08:00 AM -0500>
        This is actually not true.The node right before it could be another compact node.
        """
            
        if self.nodes[node].compact:               
            parent = self.get_parent(node)
            if parent:
                self.nodes[node].tree_node.parent = self.nodes[parent].tree_node
            continue
            
        """
        Otherwise, this is either an inline node not at the beginning of the file,
        or else a root (file level) node, so:
        """
        if not self.nodes[node].root_node:
            parent = self.get_parent(node)
            
            # will be none if parent or root node is anonymous.
            if parent == None:
                continue
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
    """
    If alias nodes have themselves as ancestors, 
    prevent recursion.
    """

    for node in self.alias_nodes:

        """ Iterate the entire tree from this node """
        all_nodes = PreOrderIter(node) 

        for sub_node in all_nodes:
            """ 
            .name in this context is the node ID.
            In case it has already been marked as recursion,
            we always want just the last 3 characters.
            """
            alias_node_id = sub_node.name[-3:]

            if alias_node_id in [ancestor.name for ancestor in sub_node.ancestors]:
                sub_node.name = '! RECURSION : ' + self.nodes[alias_node_id].title + ' >'+alias_node_id

                """ prevent recursion by ending the tree here """
                sub_node.children = []

def _detach_excluded_tree_nodes(self, root_id, flag='tree'):

    found_nodes = []

    for descendant in self.nodes[root_id.name].tree_node.descendants:

        flag = flag.lower()

        # allow for tree nodes with names that are not node IDs, 
        if descendant.name not in self.nodes:
            continue

        # Otherwise, remove it from the tree if it is flagged
        if flag == 'tree' and 'exclude_from_tree' in self.nodes[descendant.name].metadata.get_values('flags'):
            descendant.parent = None

        # Otherwise, remove it from export if it is flagged
        if flag == 'export' and 'exclude_from_export' in self.nodes[descendant.name].metadata.get_values('flags'):
            descendant.parent = None

        found_nodes.append(descendant.name)

def show_tree_from(self, 
                   node_id,
                   dynamic_definition,
                   from_root_of=False):

    if node_id not in self.nodes:
        self._log_item(root_node_id + ' is not in the project')
        return None

    start_point = self.nodes[node_id].tree_node
    if from_root_of == True:
        start_point = self.nodes[node_id].tree_node.root

    alias_nodes = has_aliases(start_point)
    while alias_nodes:        
        for leaf in alias_nodes:
            if leaf.name[:5] == 'ALIAS':
                leaf.name = leaf.name[-3:]
                if leaf.name not in [ancestor.name for ancestor in leaf.ancestors]: 
                    if leaf.name in self.nodes:
                        new_tree = self.duplicate_tree(
                            self.nodes[leaf.name].tree_node, 
                            leaf)            
                        leaf.children = new_tree.children

        alias_nodes = has_aliases(start_point)


    self._detach_excluded_tree_nodes(start_point)

    tree_render = ''
    for pre, _, this_node in RenderTree(
            start_point, 
            style=ContStyle, 
            maxlevel=dynamic_definition.depth):
       
        if this_node.name in self.nodes:

            this_node = self.nodes[this_node.name]
            next_content = DynamicOutput(dynamic_definition.show)
            
            if next_content.needs_title:
                next_content.title = this_node.title
           
            if next_content.needs_link:
                link = []
                if this_node.parent_project not in [self.title, self.path]:
                    link.extend(['{"',this_node.parent_project,'"}'])
                else:
                    link.append('>')
                link.append(str(this_node.id))
                next_content.link = ''.join(link)

            if next_content.needs_date:
                next_content.date = this_node.get_date(format_string = self.settings['timestamp_format'][0])
  
            if next_content.needs_meta:
                next_content.meta = this_node.consolidate_metadata()

            if next_content.needs_contents: 
                next_content.contents = this_node.content_only().strip('\n').strip()

            if next_content.needs_last_accessed: 
                t = datetime.datetime.utcfromtimestamp(this_node.metadata.get_first_value('_last_accessed'))
                next_content.last_accessed = t.strftime(self.settings['timestamp_format'][0])

            for meta_key in next_content.needs_other_format_keys:
                values = this_node.metadata.get_values(meta_key, substitute_timestamp=True)
                replacement = ''
                if values and isinstance(values,list):
                    replacement = ' | '.join(values)
                next_content.other_format_keys[meta_key] = replacement
           
            tree_render += "%s%s" % (pre, next_content.output())

        
        elif this_node.name[0:11] == '! RECURSION':
            tree_render += "%s%s" % (pre, this_node.name + '\n')    

        else: 
            tree_render += "%s%s" % (pre, '? (Missing Node): >' +
                                 this_node.name + '\n')

    return tree_render

def duplicate_tree(self, original_node, leaf):

    new_root = Node(original_node.name)
    ancestors = [ancestor.name for ancestor in leaf.ancestors]
    ancestors.extend([ancestor.name for ancestor in original_node.ancestors])
    ancestors.append(leaf.name)
    ancestors.append(original_node.name)

    # iterate immediate children only
    all_nodes = PreOrderIter(original_node, maxlevel=2)  
    for node in all_nodes:

        if node == original_node:
            continue

        if node.name in ancestors:
            new_node = Node('! RECURSION (node in own ancestors): >' + node.name)
            new_node.parent = new_root
            continue
 
        if 'ALIAS' in node.name and leaf:
            node_id = node.name[-3:] 
            if node_id not in ancestors:
                if node_id in self.nodes:
                    new_node = Node(node.name)
                    new_node.parent = new_root
                else:
                    new_node = Node('! (Missing Node) >'+node_id)
                    new_node.parent = new_root            
                continue
            else:
                new_node = Node('! RECURSION 3:')
                new_node.parent = new_root         
            continue

        if node.parent == original_node:
            """ Recursively apply this function to children's children """
            new_node = self.duplicate_tree(node, leaf)
            new_node.parent = new_root

    return new_root


def has_aliases(start_point):
    alias_nodes = []
    leaves = start_point.leaves  
    for leaf in leaves:
        if 'ALIAS' in leaf.name and leaf not in alias_nodes:
            alias_nodes.append(leaf)
    return alias_nodes

trees_functions=[
    show_tree_from, 
    _detach_excluded_tree_nodes, 
    _build_alias_trees,
    _rewrite_recursion,
    _set_tree_elements,
    duplicate_tree,
    ]

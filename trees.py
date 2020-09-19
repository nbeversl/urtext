from anytree import Node, RenderTree, PreOrderIter, AsciiStyle
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

            parent_node = self.get_node_id_from_position(filename,position)      
            alias_node = Node('ALIAS'+inserted_node_id)
            alias_node.parent = self.nodes[parent_node].tree_node
            self.files[filename].alias_nodes.append(alias_node)

            continue

        """
        in case this node begins the file and is an an inline node,
        set the inline node's parent as the root node manually.
        """

        if position == 0 and parsed_items[0] == '{':
            self.nodes[node].tree_node.parent = self.nodes[root_node_id].tree_node
            continue
            
        parent = self.get_parent(node)
        if parent:
            self.nodes[node].tree_node.parent = self.nodes[parent].tree_node


def _build_alias_trees(self, file):
    """ 
    Adds copies of trees wherever there are Node Pointers (>>) 
    Must be called only when all nodes are parsed (exist) so it does not miss any
    """  
    for a in self.files[file].alias_nodes:
    
        alias_nodes = self.has_aliases(a)
        i = 0
        while alias_nodes:        
            for leaf in alias_nodes:
                if leaf.name[:5] == 'ALIAS':
                    if leaf.name not in [ancestor.name for ancestor in leaf.ancestors]: 
                        if leaf.name[-3:] in self.nodes:
                            new_tree = self.duplicate_tree(
                                self.nodes[leaf.name[-3:]].tree_node, 
                                leaf)            
                            leaf.children = new_tree.children

            alias_nodes = self.has_aliases(a)
           

    # WHAT IF IT COMES ACROSS AN ALIAS WHOSE CHILDREN HAVE NOT YET BEEN ASSIGNED?
    # HOW WOULD IT KNOW TO CONTINUE ADDING CHILDREN?
    # It has to start at the top of a tree and continue adding children until there are no more aliases.
    # that must have been what the old "while aliases" was for.

    """
    Also is this even necessary if alias trees are built at the time of rendering?
    """

    self._rewrite_recursion(file) 



def _rewrite_recursion(self, file):
    """
    If alias nodes have themselves as ancestors, 
    prevent recursion.
    """
        
    for node in self.files[file].alias_nodes:
    
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

def _tree_node_is_excluded(self, tree_node, excluded_nodes):

    node_id = tree_node.name[-3:]
    
    if node_id in excluded_nodes:
        return True

    if node_id not in self.nodes:
        return True

    for ancestor in self.nodes[node_id].tree_node.ancestors:
        if ancestor.name[-3:] in excluded_nodes:
            return True

    return False

def has_aliases(self, start_point):
    alias_nodes = []
    leaves = start_point.leaves  
    print('LEAVES')
    print(leaves)
    for leaf in leaves:
        ancestors = [a.name for a in leaf.ancestors]
        if 'ALIAS' in leaf.name and leaf.name not in ancestors and leaf.name[-3:] in self.nodes and self.nodes[leaf.name[-3:]].tree_node.children:
            alias_nodes.append(leaf)

    print('ALIAS NODES NOW')
    print(alias_nodes)
    return alias_nodes

def show_tree_from(self, 
                   node_id,
                   dynamic_definition,
                   exclude=None,
                   from_root_of=False):

    if node_id not in self.nodes:
        self._log_item(root_node_id + ' is not in the project')
        return None
   
    start_point = self.nodes[node_id].tree_node
    if from_root_of == True:
        start_point = self.nodes[node_id].tree_node.root

    alias_nodes = self.has_aliases(start_point)
    i = 1 
    while alias_nodes:  
        for leaf in alias_nodes:
            if leaf.name[:5] == 'ALIAS':
                node_id = leaf.name[-3:]
                new_tree = self.duplicate_tree(self.nodes[node_id].tree_node, leaf)            
                leaf.children = new_tree.children
        alias_nodes = self.has_aliases(start_point)
        # i +=1
        # if i > 5 :
        #     print(alias_nodes)
        #     break

    """
    FOUND ISSUE:
    The nodes only correct when the file containing their pointer(ALIAS) is updated. THis is problem the key.
    """
    tree_render = ''
    for pre, _, this_node in RenderTree(
            start_point, 
            style=ContStyle, 
            maxlevel=None):

        if self._tree_node_is_excluded(this_node, exclude):
            print('EXCLUDED')
            print(this_node)
            continue

        if this_node.name[0:11] == '! RECURSION':
            tree_render += "%s%s" % (pre, this_node.name + '\n')    
            continue

        if this_node.name[:5] == 'ALIAS':
            urtext_node = self.nodes[this_node.name[5:]]
        else:
            urtext_node = self.nodes[this_node.name]
        
        next_content = DynamicOutput(dynamic_definition.show)
       
        if next_content.needs_title:
            next_content.title = urtext_node.title
       
        if next_content.needs_link:
            link = []
            if urtext_node.parent_project not in [self.title, self.path]:
                link.extend(['{"',this_node.parent_project,'"}'])
            else:
                link.append('>')
            link.append(str(urtext_node.id))
            next_content.link = ''.join(link)

        if next_content.needs_date:
            next_content.date = urtext_node.get_date(format_string = self.settings['timestamp_format'][0])

        if next_content.needs_meta:
            next_content.meta = urtext_node.consolidate_metadata(separator=':')

        if next_content.needs_contents: 
            next_content.contents = urtext_node.content_only().strip('\n').strip()

        if next_content.needs_last_accessed: 
            t = datetime.datetime.utcfromtimestamp(urtext_node.metadata.get_first_value('_last_accessed'))
            next_content.last_accessed = t.strftime(self.settings['timestamp_format'][0])

        for meta_key in next_content.needs_other_format_keys:
            values = urtext_node.metadata.get_values(meta_key, substitute_timestamp=True)
            replacement = ''
            if values and isinstance(values,list):
                replacement = ' | '.join(values)
            next_content.other_format_keys[meta_key] = replacement

        tree_render += "%s%s" % (pre, next_content.output())

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
            # new_node = duplicate_tree(node)
            new_node.parent = new_root

    return new_root



trees_functions=[
    show_tree_from, 
    _tree_node_is_excluded, 
    _build_alias_trees,
    _rewrite_recursion,
    _set_tree_elements,
    duplicate_tree,
    has_aliases,

    ]

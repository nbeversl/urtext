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

            parent_node = self.get_node_id_from_position(filename,position)
                               
            alias_node = Node('ALIAS'+inserted_node_id)
            alias_node.parent = self.nodes[parent_node].tree_node
            self.alias_nodes.setdefault(inserted_node_id, [])
            self.alias_nodes[inserted_node_id].append(alias_node)
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
            
        parent = self.get_parent(node)
        if parent:
            self.nodes[node].tree_node.parent = self.nodes[parent].tree_node

def _build_alias_trees(self):
    """ 
    Adds copies of trees wherever there are Node Pointers (>>) 
    Must be called only when all nodes are parsed (exist) so it does not miss any
    """
    # must use EXISTING node so it appears at the right place in the tree.
  
    for node_id in self.alias_nodes:
        for a in self.alias_nodes[node_id]:
            if node_id in self.nodes:
                duplicate_node = duplicate_tree(self.nodes[node_id].tree_node)
                a.children = [c for c in duplicate_node.children]

def _rewrite_recursion(self):
    """
    If alias nodes have themselves as ancestors, 
    prevent recursion.
    """

    for node_id in self.alias_nodes:

        for node in self.alias_nodes[node_id]:
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

def _detach_excluded_tree_nodes(self, root_id, excluded_nodes):

    for descendant in self.nodes[root_id.name].tree_node.descendants:

        # allow for tree nodes with names that are not node IDs, 
        if descendant.name not in self.nodes:
            continue

        # Otherwise, remove it from the tree if it is flagged
        if descendant.name in excluded_nodes:
            descendant.parent = None

def show_tree_from(self, 
                   node_id,
                   dynamic_definition,
                   exclude=[],
                   from_root_of=False):

    if node_id not in self.nodes:
        self._log_item(root_node_id + ' is not in the project')
        return None

    
    start_point = self.nodes[node_id].tree_node
    if from_root_of == True:
        start_point = self.nodes[node_id].tree_node.root
        
    #self._detach_excluded_tree_nodes(start_point, exclude)

    tree_render = ''
    for pre, _, this_node in RenderTree(
            start_point, 
            style=ContStyle, 
            maxlevel=dynamic_definition.depth):
       
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

def duplicate_tree(original_node):
    new_root = Node(original_node.name)
    # iterate immediate children only
    all_nodes = PreOrderIter(original_node, maxlevel=2)  
    for node in all_nodes: 
        if node == original_node:
            continue        
        node_id = node.name[-3:] 
        if node_id in [ancestor.name for ancestor in node.ancestors]:
            new_node = Node('! RECURSION (node in own ancestors): >' + node.name)
            new_node.parent = new_root
            continue
        if node.parent == original_node:
            new_node = duplicate_tree(node)
            new_node.parent = new_root
    return new_root

trees_functions=[
    show_tree_from, 
    _detach_excluded_tree_nodes, 
    _build_alias_trees,
    _rewrite_recursion,
    _set_tree_elements,
    duplicate_tree,
    ]

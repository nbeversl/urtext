
import codecs
import re
import datetime
import itertools
import platform
import logging
import operator
import difflib
import json
import os
import random 
import sys
import time

from anytree import Node, RenderTree, PreOrderIter
from anytree.render import AbstractStyle

from whoosh.fields import Schema, TEXT, KEYWORD, ID, STORED
from whoosh.index import create_in, exists_in, open_dir
from whoosh.qparser import QueryParser
from whoosh.highlight import UppercaseFormatter
from whoosh.analysis import StemmingAnalyzer

from .timeline import timeline
from .node import UrtextNode
from .interlinks import Interlinks

#from .google_calendar import sync_project_to_calendar

node_id_regex = r'\b[0-9,a-z]{3}\b'
node_link_regex = r'>[0-9,a-z]{3}\b'
node_pointer_regex = r'>>[0-9,a-z]{3}\b'

if not hasattr(sys, 'argv'):
    sys.argv  = ['']

class NoProject(Exception):
    """ Raised when no Urtext nodes are in the folder """
    pass


class UrtextProject:
    """ Urtext project object """
    
    def __init__(self,
                 path,
                 make_new_files=True,
                 rename=False,
                 recursive=False,
                 import_project=False,
                 init_project=False,
                 machine_lock=None):

        self.path = path
        self.conflicting_files = []
        self.log = setup_logger('urtext_log',
                                os.path.join(self.path, 'urtext_log.txt'))
        self.make_new_files = make_new_files
        self.nodes = {}
        self.files = {}
        self.tagnames = {}
        self.zero_page = ''
        self.other_projects = []
        self.navigation = []  # Stores, in order, the path of navigation
        self.nav_index = -1  # pointer to the CURRENT position in the navigation list
        self.settings = {  # defaults
            'logfile':'urtext_log.txt',
            'timestamp_format':
                ['%a., %b. %d, %Y, %I:%M %p', '%B %-d, %Y', '%B %Y', '%m-%d-%Y'],
            'filenames': ['PREFIX', 'DATE %m-%d-%Y', 'TITLE'],
            'node_list': 'zzz.txt',
            'metadata_list': 'zzy.txt',
            'console_log':'false',
            'google_auth_token' : 'token.json',
            'google_calendar_id' : None
        }
        self.to_import = []
        self.settings_initialized = False
        self.dynamic_nodes = {}  # { target : definition, etc.}
        self.compiled = False
        self.alias_nodes = []
        
        # Whoosh
        schema = Schema(
                title=TEXT(stored=True),
                path=ID(stored=True),
                content=TEXT(stored=True, analyzer=StemmingAnalyzer()))

        index_dir = os.path.join(self.path, "index")
        
        if exists_in(os.path.join(self.path, "index"), indexname="urtext"):
            self.ix = open_dir(os.path.join(self.path, "index"),
                               indexname="urtext")
        
        filelist = os.listdir(self.path)

        if machine_lock:
            self.lock(machine_lock)
            
        for file in filelist:
            self.parse_file(file, import_project=import_project)

        for file in self.to_import:
            self.import_file(file)

        if self.nodes == {}:
            if init_project == True:
                self.log_item('Initalizing a new Urtext project in ' + path)
            else:
                raise NoProject('No Urtext nodes in this folder.')

        # needs do be done once manually on project init
        for node_id in list(self.nodes):  
            self.parse_meta_dates(node_id)

        self.compile()

        self.compiled = True
        
        self.update()

        
    def node_id_generator(self):
        chars = [
            '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'a', 'b', 'c',
            'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p',
            'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z'
        ]
        return itertools.product(chars, repeat=3)

    def update(self, compile=True, update_lists=True):
        """ 
        Main method to keep the project updated. 
        Should be called whenever file or directory content changes
        """

        # Build copies of trees wherever there are Node Pointers (>>)
        self.build_alias_trees()  

        self.rewrite_recursion()

        if compile:
            self.compile()

        if update_lists:
            self.update_node_list()
            self.update_metadata_list()

    """ 
    Parsing
    """
    def parse_file(self, 
        filename, 
        add=True, 
        import_project=False,
        re_index=False):
        """ Parse a single file into project nodes """

        filename = os.path.basename(filename)
        if self.filter_filenames(filename) == None:
            return

        full_file_contents = self.get_file_contents(filename)
        if full_file_contents == None:
            return

        # clear all node_id's defined from this file in case the file has changed
        self.remove_file(filename)

        # re-add the file to the project
        self.files[filename] = {}
        self.files[filename]['nodes'] = []
        """
        Find all node symbols in the file
        """
        symbols = {}

        for symbol in ['{{', '}}', '>>', '^']:
            loc = -2
            while loc != -1:
                loc = full_file_contents.find(symbol, loc + 2)
                symbols[loc] = symbol

        positions = sorted([key for key in symbols.keys() if key != -1])
        length = len(full_file_contents)
        
        """
        Counters and trackers
        """
        nested = 0  # tracks depth of node nesting
        nested_levels = {}
        last_start = 0  # tracks the most recently parsed position
        parsed_items = {}  # stores parsed items

        for position in positions:

            # Allow node nesting arbitrarily deep
            if nested not in nested_levels:
                nested_levels[nested] = []

            # If this opens a new node, track the ranges of the outer one.
            if symbols[position] == '{{':
                nested_levels[nested].append([last_start, position])
                nested += 1
                last_start = position + 2
                continue

            # If this points to an outside node, find which node
            if symbols[position] == '>>':
                node_pointer = full_file_contents[position:position + 5]
                if re.match(node_pointer_regex, node_pointer):
                    parsed_items[position] = node_pointer
                continue

            if symbols[position] == '^' and full_file_contents[position-1] == '\n':
                compact_node_regex = '\^[^\n]*'
                compact_node_contents = re.search(compact_node_regex, full_file_contents[position:]).group(0)
                
                compact_node = UrtextNode(os.path.join(self.path, filename), 
                    contents=compact_node_contents[1:])
                
                if compact_node.id != None and re.match(node_id_regex, compact_node.id):
                    
                    nested_levels[nested].append([last_start, position ])
                    compact_node.compact = True
                    if self.is_duplicate_id(compact_node.id, filename):
                        return

                    else:
                        self.add_node(compact_node, [[position + 2 , position+len(compact_node_contents)]])
                        parsed_items[position] = compact_node.id
                    
                    last_start = position + len(compact_node_contents) 
                    continue

            # If this closes a node:
            if symbols[position] == '}}':  # pop
                nested_levels[nested].append([last_start, position])

                # Get the node contents and construct the node
                node_contents = []
                for file_range in nested_levels[nested]:
                    node_contents.append(full_file_contents[file_range[0]:file_range[1]])

                joined_contents = ''.join(node_contents)
                new_node = UrtextNode(os.path.join(self.path, filename),
                                      contents=joined_contents)

                if new_node.id != None and re.match(node_id_regex, new_node.id):
                    if self.is_duplicate_id(new_node.id, filename):
                        return
                    else:
                        self.add_node(new_node, nested_levels[nested])
                        parsed_items[position] = new_node.id

                else:
                    error_line = full_file_contents[position -
                                                    50:position].split(
                                                        '\n')[-1]
                    error_line += full_file_contents[position:position +
                                                     50].split('\n')[0]
                    message = [
                        'Node missing ID in ', filename, '\n', error_line,
                        '\n', ' ' * len(error_line), '^'
                    ]
                    message = ''.join(message)
                    self.log_item(message)
                    return self.remove_file(filename)

                del nested_levels[nested]

                last_start = position + 2
                nested -= 1

                if nested < 0:
                    error_line = full_file_contents[position -
                                                    50:position].split('\n')[0]
                    error_line += full_file_contents[position:position +
                                                     50].split('\n')[0]
                    message = [
                        'Stray closing wrapper in ', filename, ' at position ',
                        str(position), '\n', error_line, '\n',
                        ' ' * len(error_line), '^'
                    ]
                    message = ''.join(message)
                    self.log_item(message)
                    return self.remove_file(filename)

        if nested != 0:
            error_line = full_file_contents[position -
                                            50:position].split('\n')[0]
            error_line += full_file_contents[position:position +
                                             50].split('\n')[0]
            message = [
                'Missing closing wrapper in ', filename, ' at position ',
                str(position), '\n', error_line, '\n', ' ' * len(error_line),
                '^'
            ]
            message = ''.join(message)
            self.log_item(message)
            return self.remove_file(filename)

        ### Handle the root node:
        if nested_levels == {} or nested_levels[0] == []:
            nested_levels[0] = [[0, length]]  # no inline nodes
        else:
            nested_levels[0].append([last_start + 1, length])

        root_node_contents = []
        for file_range in nested_levels[0]:
            root_node_contents.append(full_file_contents[file_range[0]:
                                                     file_range[1]])
        root_node = UrtextNode(os.path.join(self.path, filename),
                               contents=''.join(root_node_contents),
                               root=True)
        if root_node.id == None or not re.match(node_id_regex, root_node.id):
            if import_project == True:
                if filename not in self.to_import:
                    self.to_import.append(filename)
                    return self.remove_file(filename)
            else:
                self.log_item('Root node without ID: ' + filename)
                return self.remove_file(filename)

        if self.is_duplicate_id(root_node.id, filename):
            return

        self.add_node(root_node, nested_levels[0])
        root_node_id = root_node.id

        self.files[filename]['parsed_items'] = parsed_items
        """
        If this is not the initial load of the project, parse the timestamps in the file
        """
        if self.compiled == True:
            for node_id in self.files[filename]['nodes']:
                self.parse_meta_dates(node_id)
        
        self.set_tree_elements(filename)

        for node_id in self.files[filename]['nodes']:
            self.rebuild_node_tag_info(node_id)
        
        if re_index:
            self.re_search_index_file(filename)

        return filename

    """
    Tree building
    """
    def set_tree_elements(self, filename):
        """ Builds tree elements within the file, after the file is parsed."""

        parsed_items = self.files[filename]['parsed_items']
        positions = sorted(parsed_items.keys())

        for position in positions:

            node = parsed_items[position]

            #
            # If the parsed item is a tree marker to another node,
            # parse the markers, positioning it within its parent node
            #
            if node[:2] == '>>':
                inserted_node_id = node[2:]
                for other_node in [
                        node_id for node_id in self.files[filename]['nodes']
                        if node_id != node
                ]:  # Careful ...
                    if self.is_in_node(position, other_node):
                        parent_node = other_node
                        alias_node = Node(inserted_node_id)
                        alias_node.parent = self.nodes[parent_node].tree_node
                        if alias_node not in self.alias_nodes:
                            self.alias_nodes.append(alias_node)
                        break
                continue
            """
            in case this node begins the file and is an an inline node,
            set the inline node's parent as the root node manually.
            """
            if position == 0 and parsed_items[0] == '{{':
                self.nodes[node].tree_node.parent = self.nodes[
                    root_node_id].tree_node
                continue
            """
            Otherwise, this is an inline node not at the beginning of the file.
            """
            parent = self.get_parent(node)
            self.nodes[node].tree_node.parent = self.nodes[parent].tree_node

    def build_alias_trees(self):
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

    def rewrite_recursion(self):

        for node in self.alias_nodes:
            all_nodes = PreOrderIter(node)
            for sub_node in all_nodes:
                if sub_node.name in [
                        ancestor.name for ancestor in sub_node.ancestors
                ]:
                    sub_node.name = 'RECURSION >' + sub_node.name
                    sub_node.children = []

    """
    Parsing helpers
    """
    def add_node(self, new_node, ranges):
        """ Adds a node to the project object """

        if new_node.filename not in self.files:
            self.files[new_node.filename]['nodes'] = []
        """
        pass the node's dynamic definitions up into the project object
        self.dynamic_nodes = { target_id : definition }

        """
        for target_id in new_node.dynamic_definitions.keys():
            if target_id in self.dynamic_nodes:
                self.log_item('Node >' + target_id +
                              ' has duplicate definition in >' + new_node.id +
                              '. Keeping the definition in >' +
                              self.dynamic_nodes[target_id].source_id + '.')
            else:
                self.dynamic_nodes[target_id] = new_node.dynamic_definitions[
                    target_id]

        ID_tags = new_node.metadata.get_tag('ID')
        if len(ID_tags) > 1:
            self.log_item('Multiple ID tags in >' + new_node.id +
                          ', using the first one found.')

        self.nodes[new_node.id] = new_node
        self.files[new_node.filename]['nodes'].append(new_node.id)
        self.nodes[new_node.id].ranges = ranges
        if new_node.project_settings:
            self.get_settings_from(new_node)

    def parse_meta_dates(self, node_id):
        """ Parses dates (requires that timestamp_format already be set) """

        timestamp_format = self.settings['timestamp_format']
        if isinstance(timestamp_format, str):
            timestamp_format = [timestamp_format]

        for entry in self.nodes[node_id].metadata.entries:
            if entry.dtstring:
                dt_stamp = None
                for this_format in timestamp_format:
                    dt_format = '<' + this_format + '>'
                    try:
                        dt_stamp = datetime.datetime.strptime(
                            entry.dtstring, dt_format)
                    except:
                        continue
                if dt_stamp:
                    self.nodes[node_id].metadata.dt_stamp = dt_stamp
                    if entry.tag_name == 'timestamp':
                        self.nodes[node_id].date = dt_stamp
                    continue
                else:
                    self.log_item('Timestamp ' + entry.dtstring +
                                  ' not in any specified date format in >' +
                                  node_id)

    def detach_excluded_tree_nodes(self, root_id, flag='tree'):
        
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
            self.log_item(root_node_id + ' is not in the project')
            return None

        tree_render = ''

        start_point = self.nodes[node_id].tree_node

        if from_root_of == True:
            start_point = self.nodes[node_id].tree_node.root

        self.detach_excluded_tree_nodes(start_point)

        no_line = AbstractStyle('    ','├── ','└── ')


        for pre, _, this_node in RenderTree(start_point,style=no_line ):
            if this_node.name in self.nodes:
                tree_render += "%s%s" % (pre, self.nodes[
                    this_node.name].title) + ' >' + this_node.name + '\n'
            else:
                tree_render += "%s%s" % (pre, '? (Missing Node): >' +
                                         this_node.name + '\n')
        return tree_render

    def render_tree_as_html(self, 
                            node_id,
                            links_on_same_page=False,
                            from_root_of=False ):

        if node_id not in self.nodes:
            self.log_item(root_node_id + ' is not in the project')
            return None

        start_point = self.nodes[node_id].tree_node
        
        if from_root_of == True:
            start_point = self.nodes[node_id].tree_node.root

        self.detach_excluded_tree_nodes(start_point, flag='export') 

        tree_filename = node_id +'.html'

        def render_list(node, nested, visited_nodes):
            html = ''
            if node in visited_nodes:
                return html
            children = node.children
            if children:
                html += '<ul>\n'
                for child in node.children:
                    visited_nodes.append(child)
                    link = ''
                    if not links_on_same_page:
                        this_node_id = child.name
                        base_filename = self.nodes[this_node_id].filename
                        if base_filename != tree_filename:
                            this_root_node = self.get_root_node_id(base_filename)
                            link += this_root_node+'.html'
                    link += '#'+child.name
                    html += '<li><a href="' + link + '">' + self.nodes[child.name].title + '</a></li>\n'
                    html += render_list(self.nodes[child.name].tree_node, nested, visited_nodes)
                html += '</ul>\n'
            return html

        return render_list(start_point, 1, [])


    """
    Compiling dynamic nodes
    """
    def compile(self):
        """ Main method to compile dynamic nodes definitions """

        files_to_modify = {}

        for target_id in self.dynamic_nodes:
            """
            Make sure the target node exists.
            """
            source_id = self.dynamic_nodes[target_id].source_id
            if target_id not in self.nodes:
                self.log_item('Dynamic node definition >' + source_id +
                              ' points to nonexistent node >' + target_id)
                continue
            filename = self.nodes[target_id].filename
            if filename not in files_to_modify:
                files_to_modify[filename] = []
            files_to_modify[filename].append(target_id)

        # rebuild the text for each file all at once
        for file in files_to_modify:

            """
            Get current file contents
            """
            with open(os.path.join(self.path, file), "r",
                      encoding='utf-8') as theFile:
                old_file_contents = theFile.read()
                theFile.close()

            updated_file_contents = old_file_contents
            re_parsed_files = []

            for target_id in files_to_modify[file]:
                    
                old_node_contents = self.nodes[target_id].contents()
                dynamic_definition = self.dynamic_nodes[target_id]

                contents = ''

                if dynamic_definition.tree and dynamic_definition.tree in self.nodes:
                    contents += self.show_tree_from(dynamic_definition.tree)

                else:
                    included_nodes = []
                    excluded_nodes = []

                    included_nodes_and = []
                    for item in dynamic_definition.include_and:
                        key, value = item[0], item[1]
                        if value in self.tagnames[key]:
                            included_nodes_and.append(set(self.tagnames[key][value]))
                            
                    if len(included_nodes_and) > 1:
                        included_nodes_and = list(set(included_nodes_and[0]).intersection(*included_nodes_and))
                    else:
                        included_nodes_and = list(included_nodes_and)
                        
                    for e in included_nodes_and:
                        included_nodes.append(e)

                    for indiv_node in included_nodes:
                        if indiv_node not in included_nodes:
                            included_nodes.append(indiv_node)
                    for item in dynamic_definition.include_or:
                        key, value = item[0], item[1]
                        if value in self.tagnames[key]:
                            added_nodes = self.tagnames[key][value]
                            for indiv_node in added_nodes:
                                if indiv_node not in included_nodes:
                                    included_nodes.append(indiv_node)
        
                    for item in dynamic_definition.exclude_or:
                        key, value = item[0], item[1]
                        if value in self.tagnames[key]:
                            excluded_nodes.extend(self.tagnames[key][value])

                    for node in excluded_nodes:
                        if node in included_nodes:
                            included_nodes.remove(node)
                    """
                    Assemble the node collection from the list
                    """
                    included_nodes = [
                        self.nodes[node_id] for node_id in included_nodes
                    ]
                    """
                    build timeline if specified
                    """
                    if dynamic_definition.show == 'timeline':
                        contents += urtext.timeline.timeline(
                            self, included_nodes)

                    else:
                        """
                        otherwise this is a list, so sort the nodes
                        """
                        if dynamic_definition.sort_tagname != None:
                            included_nodes = sorted(
                                included_nodes,
                                key=lambda node: node.metadata.get_tag(
                                    dynamic_definition.sort_tagname))
                        else:
                            included_nodes = sorted(included_nodes,
                                                    key=lambda node: node.date)

                        for targeted_node in included_nodes:
                            if dynamic_definition.show == 'title':
                                show_contents = targeted_node.title
                            if dynamic_definition.show == 'full_contents':
                                show_contents = targeted_node.content_only(
                                ).strip('\n').strip()
                            contents += '- '+show_contents + ' >' + targeted_node.id + '\n'
                """
                add metadata to dynamic node
                """

                metadata_values = { 
                    'ID': [ target_id ],
                    'kind' : [ 'dynamic' ],
                    'defined in' : [ '>'+dynamic_definition.source_id ] }

                for value in dynamic_definition.metadata:
                    metadata_values[value] = dynamic_definition.metadata[value]
                built_metadata = build_metadata(metadata_values, one_line=dynamic_definition.oneline_meta)

                updated_node_contents = contents + built_metadata

                """
                add indentation if specified
                """

                if dynamic_definition.spaces:
                    updated_node_contents = indent(updated_node_contents,
                                                   dynamic_definition.spaces)

                updated_file_contents = updated_file_contents.replace(
                    old_node_contents, updated_node_contents)
            
            """
            Update this file if it has changed
            """
            if updated_file_contents != old_file_contents:

                with open(os.path.join(self.path, file), "w",
                          encoding='utf-8') as theFile:
                    theFile.write(updated_file_contents)
                    theFile.close()
                self.parse_file(os.path.join(self.path, file))
        
        self.update(compile=False)

    """
    Refreshers
    """
    def update_node_list(self):

        """ Refreshes the Node List file """
        if 'zzz' in self.nodes:
            node_list_file = self.nodes['zzz'].filename
        else:
            node_list_file = self.settings['node_list']
        with open(os.path.join(self.path, node_list_file),
                  'w',
                  encoding='utf-8') as theFile:
            theFile.write(self.list_nodes())
            metadata = '/--\nID:zzz\ntitle: Node List\n--/'
            theFile.write(metadata)
            theFile.close()

    def update_metadata_list(self):
        """ Refreshes the Metadata List file """

        root = Node('Metadata Keys')
        for key in [
                k for k in self.tagnames
                if k.lower() not in ['defined in', 'id', 'timestamp', 'index']
        ]:
            s = Node(key)
            s.parent = root
            for value in self.tagnames[key]:
                t = Node(value)
                t.parent = s
                if value in self.tagnames[key]:
                    for node_id in self.tagnames[key][value]:
                        n = Node(self.nodes[node_id].title + ' >' +
                                 node_id)
                        n.parent = t
        if 'zzy' in self.nodes:
            metadata_file = self.nodes['zzy'].filename
        else:
            metadata_file = self.settings['metadata_list']
            
        with open(os.path.join(self.path, metadata_file),
                  'w',
                  encoding='utf-8') as theFile:
            for pre, _, node in RenderTree(root):
                theFile.write("%s%s\n" % (pre, node.name))
            metadata = '/--\nID:zzy\ntitle: Metadata List\n--/'
            theFile.write(metadata)
            theFile.close()

    """
    Metadata
    """
    def tag_other_node(self, node_id, tag_contents):
        """adds a metadata tag to a node programmatically"""

        # might also need to add in checking for Sublime (only) to make sure the file
        # is not open and unsaved.
        timestamp = self.timestamp(datetime.datetime.now())
        territory = self.nodes[node_id].ranges
        with open(os.path.join(self.path, self.nodes[node_id].filename),
                  'r', encoding='utf-8') as theFile:
            full_file_contents = theFile.read()
            theFile.close()
        tag_position = territory[-1][1]
        new_contents = full_file_contents[:tag_position] + tag_contents + full_file_contents[
                                              tag_position:]
        with open(os.path.join(self.path, self.nodes[node_id].filename),
                  'w', encoding='utf-8') as theFile:
            theFile.write(new_contents)
            theFile.close()
        self.parse_file(os.path.join(self.path, self.nodes[node_id].filename))

    def consolidate_metadata(self, node_id, one_line=False):
        
        def adjust_ranges(filename, position, length):
            for node_id in self.files[os.path.basename(filename)]['nodes']:
                for index in range(len(self.nodes[node_id].ranges)):
                    this_range = self.nodes[node_id].ranges[index]
                    if position >= this_range[0]:
                        self.nodes[node_id].ranges[index][0] -= length
                        self.nodes[node_id].ranges[index][1] -= length

        consolidated_metadata = self.nodes[node_id].consolidate_metadata(
            one_line=one_line)

        filename = self.nodes[node_id].filename
        with open(os.path.join(self.path, filename), 'r',
                  encoding='utf-8') as theFile:
            file_contents = theFile.read()
            theFile.close()

        length = len(file_contents)
        ranges = self.nodes[node_id].ranges
        meta = re.compile(r'(\/--(?:(?!\/--).)*?--\/)',
                          re.DOTALL)  # \/--((?!\/--).)*--\/
        for single_range in ranges:

            for section in meta.finditer(
                    file_contents[single_range[0]:single_range[1]]):
                start = section.start() + single_range[0]
                end = start + len(section.group())
                first_splice = file_contents[:start]
                second_splice = file_contents[end:]
                file_contents = first_splice
                file_contents += second_splice
                adjust_ranges(filename, start, len(section.group()))

        new_file_contents = file_contents[0:ranges[-1][1] - 2]
        new_file_contents += consolidated_metadata
        new_file_contents += file_contents[ranges[-1][1]:]
        with open(os.path.join(self.path, filename), 'w',
                  encoding='utf-8') as theFile:
            theFile.write(new_file_contents)
            theFile.close()
        return consolidated_metadata

    def build_tag_info(self):
        """ Rebuilds metadata for the entire project """

        self.tagnames = {}
        for node in self.nodes:
            self.rebuild_node_tag_info(node)

    def rebuild_node_tag_info(self, node):
        """ Rebuilds metadata info for a single node """

        for entry in self.nodes[node].metadata.entries:
            if entry.tag_name.lower() != 'title':
                if entry.tag_name not in self.tagnames:
                    self.tagnames[entry.tag_name] = {}
                if not isinstance(entry.value, list):
                    entryvalues = [entry.value]
                else:
                    entryvalues = entry.value
                for value in entryvalues:
                    if value not in self.tagnames[entry.tag_name]:
                        self.tagnames[entry.tag_name][value] = []
                    self.tagnames[entry.tag_name][value].append(node)

    def import_file(self, filename):
        with open(
                os.path.join(self.path, filename),
                'r',
                encoding='utf-8',
        ) as theFile:
            full_file_contents = theFile.read()
            theFile.close()

        date = creation_date(os.path.join(self.path, filename))
        now = datetime.datetime.now()
        contents = '\n\n'
        contents += "/-- ID:" + self.next_index() + '\n'
        contents += 'timestamp:' + self.timestamp(date) + '\n'
        contents += 'imported:' + self.timestamp(now) + '\n'
        contents += " --/"

        full_file_contents += contents

        with open(
                os.path.join(self.path, filename),
                'w',
                encoding='utf-8',
        ) as theFile:
            full_file_contents = theFile.write(full_file_contents)
            theFile.close()

        return self.parse_file(filename)

    def get_node_relationships(self, node_id):
        return Interlinks(self, node_id).render

    """
    Removing and renaming files
    """
    def remove_file(self, filename):
        """ removes the file from the project object """

        filename = os.path.basename(filename)
        if filename in self.files:
            for node_id in self.files[filename]['nodes']:
                for target_id in list(self.dynamic_nodes):
                    if self.dynamic_nodes[target_id].source_id == node_id:
                        del self.dynamic_nodes[target_id]

                # REFACTOR
                # delete it from the self.tagnames array -- duplicated from delete_file()
                for tagname in list(self.tagnames):
                    for value in list(self.tagnames[tagname]):
                        if value in self.tagnames[
                                tagname]:  # in case it's been removed
                            if node_id in self.tagnames[tagname][value]:
                                self.tagnames[tagname][value].remove(node_id)
                            if len(self.tagnames[tagname][value]) == 0:
                                del self.tagnames[tagname][value]
                del self.nodes[node_id]
            del self.files[filename]
        return None

    def handle_renamed(self, old_filename, new_filename):
        new_filename = os.path.basename(new_filename)
        old_filename = os.path.basename(old_filename)
        self.files[new_filename] = self.files[old_filename]
        for node_id in self.files[new_filename]['nodes']:
            self.nodes[node_id].filename = new_filename
            self.nodes[node_id].full_path = os.path.join(
                self.path, new_filename)
        if new_filename != old_filename:
            del self.files[old_filename]

    """ 
    Methods for filtering files to skip 
    """
    def filter_filenames(self, filename):
        """ Filters out files to skip altogether """
        """ Omit system files """
        if filename[0] == '.':
            return None
        
        if not filename.endswith('.txt'):
            # FUTURE:
            # save and check these in an optional list of other extensions 
            # set from project_settings 
            return None
        """ Omit the log file """
        skip_files = [self.settings['logfile']]
        if filename in skip_files:
            return

        return filename

    def get_file_contents(self, filename):
        """ returns the file contents, filtering out Unicode Errors, directories, other errors """

        try:
            with open(
                    os.path.join(self.path, filename),
                    'r',
                    encoding='utf-8',
            ) as theFile:
                full_file_contents = theFile.read()
                theFile.close()
            return full_file_contents.encode('utf-8').decode('utf-8')

        except IsADirectoryError:
            return None
        except UnicodeDecodeError:
            self.log_item('UnicodeDecode Error: ' + filename)
            return None
        except:
            self.log_item('Urtext not including ' + filename)
            return None

        

    def new_file_node(self, date=None, metadata = {}):
        """ add a new FILE-level node programatically """

        if date == None:
            date = datetime.datetime.now()
        node_id = self.next_index()
        contents = "\n\n\n"
        contents += "/-- ID:" + node_id + '\n'
        contents += 'Timestamp:' + self.timestamp(date) + '\n'
        for key in metadata:
            contents += key + ": " + metadata[key] + '\n'
        contents += "--/"

        filename = node_id + '.txt'

        with open(os.path.join(self.path, filename), "w") as theFile:
            theFile.write(contents)
            theFile.close()

        self.files[filename] = {}
        self.files[filename]['nodes'] = [node_id]
        self.nodes[node_id] = UrtextNode(os.path.join(self.path, filename),
                                         contents)
        return { 
                'filename':filename, 
                'id':node_id
                }
 
    def add_inline_node(self, 
            date=None, 
            contents='', 
            metadata={},
            one_line=False ):

        if contents == '':
            contents = ' '
 
        separator = '\n'
        newline = '\n'
        if one_line:
            separator = '; '
            newline = ''
 
        node_id = self.next_index()
        if date == None:
            date = datetime.datetime.now()
 
        new_node_contents = "{{ " + contents 
        new_node_contents += newline + "/-- ID:" + node_id + separator
        new_node_contents += 'timestamp:' + self.timestamp(date) + separator
        for key in metadata:
            new_node_contents += key + ": " + metadata[key] + newline
        new_node_contents += "--/ }}"
 
        return new_node_contents

    """ 
    Reindexing (renaming) Files 
    """
    def reindex_files(self):
        # Indexes all file-level nodes in the project

        # Calculate the zero-padded digit length of the file prefix:
        prefix = 0
        remaining_root_nodes = list(self.root_nodes())
        indexed_nodes = list(self.indexed_nodes())
        for node_id in indexed_nodes:
            if node_id in remaining_root_nodes:
                self.nodes[node_id].prefix = prefix
                remaining_root_nodes.remove(node_id)
                prefix += 1

        unindexed_root_nodes = [
            self.nodes[node_id] for node_id in remaining_root_nodes
        ]
        date_sorted_nodes = sorted(unindexed_root_nodes,
                                   key=lambda r: r.date,
                                   reverse=True)

        for node in date_sorted_nodes:
            node.prefix = prefix
            prefix += 1
        return self.rename_file_nodes(list(self.files), reindex=True)

    def rename_file_nodes(self, filenames, reindex=False):

        if isinstance(filenames, str):
            filenames = [filenames]
        used_names = []

        indexed_nodes = list(self.indexed_nodes())
        filename_template = list(self.settings['filenames'])
        renamed_files = {}
        date_template = None

        for index in range(0, len(filename_template)):
            if 'DATE' in filename_template[index]:
                date_template = filename_template[index].replace('DATE',
                                                                 '').strip()
                filename_template[index] = 'DATE'

        for filename in filenames:
            old_filename = os.path.basename(filename)
            root_node_id = self.get_root_node_id(old_filename)
            root_node = self.nodes[root_node_id]

            new_filename = ' - '.join(filename_template)
            new_filename = new_filename.replace('TITLE', root_node.title)
            if root_node_id not in indexed_nodes and date_template != None:
                new_filename = new_filename.replace(
                    'DATE',
                    datetime.datetime.strftime(root_node.date, date_template))
            else:
                new_filename = new_filename.replace('DATE -', '')
            if reindex == True:
                padded_prefix = '{number:0{width}d}'.format(
                    width=self.prefix_length(), number=int(root_node.prefix))
                new_filename = new_filename.replace('PREFIX', padded_prefix)
            else:
                old_prefix = old_filename.split('-')[0].strip()
                new_filename = new_filename.replace('PREFIX', old_prefix)
            new_filename = new_filename.replace('/', '-')
            new_filename = new_filename.replace('.', ' ')
            new_filename = new_filename.replace('’', "'")
            new_filename = new_filename.replace(':', "-")
            new_filename += '.txt'
            if new_filename not in used_names:
                renamed_files[old_filename] = new_filename
                used_names.append(new_filename)

            else:
                self.log_item('Renaming ' + old_filename +
                              ' results in duplicate filename: ' +
                              new_filename)

        for filename in renamed_files:
            old_filename = filename
            new_filename = renamed_files[old_filename]
            self.log_item('renaming ' + old_filename + ' to ' + new_filename)
            os.rename(os.path.join(self.path, old_filename),
                      os.path.join(self.path, new_filename))
            self.handle_renamed(old_filename, new_filename)

        return renamed_files

    def prefix_length(self):
        """ Determines the prefix length for indexing files (requires an already-compiled project) """

        prefix_length = 0
        num_files = len(self.files)
        while num_files > 1:
            prefix_length += 1
            num_files /= 10
        return prefix_length

    """
    Project Navigation
    """

    def nav_advance(self):
        if not self.check_nav_history():
            return None

        # return if the index is already at the end
        if self.nav_index == len(self.navigation) - 1:
            self.log_item('index is at the end.')
            return None
        
        self.nav_index += 1
        print (self.navigation[self.nav_index])
        return self.navigation[self.nav_index]


    def nav_new(self, node_id):

        # don't re-remember consecutive duplicate links
        if self.nav_index > -1 and node_id == self.navigation[self.nav_index]:
            return

        # add the newly opened file as the new "HEAD"
        del self.navigation[self.nav_index+1:]
        self.navigation.append(node_id)
        self.nav_index += 1

    def nav_reverse(self):

        if self.nav_index == 0:
            self.log_item('index is already at the beginning.')
            return None


        if not self.check_nav_history():
            return None

        last_node = self.navigation[self.nav_index - 1]
        self.nav_index -= 1
        print(last_node)
        return last_node


    def check_nav_history(self):

        if len(self.navigation) == -1:
            self.log_item('There is no nav history')
            return None

        return True

    """ 
    Cataloguing Nodes
    """
    def list_nodes(self):
        """returns a list of all nodes in the project, in plain text"""
        output = ''
        for node_id in list(self.indexed_nodes()):
            title = self.nodes[node_id].title
            output += title + ' >' + node_id + '\n-\n'
        for node_id in list(self.unindexed_nodes()):
            title = self.nodes[node_id].title
            output += title + ' >' + node_id + '\n-\n'
        return output

    def unindexed_nodes(self):
        """ 
        returns an array of node IDs of unindexed nodes, 
        in reverse order (most recent) by date 
        """
        unindexed_nodes = []
        for node_id in list(self.nodes):
            if self.nodes[node_id].metadata.get_tag('index') == []:
                unindexed_nodes.append(node_id)
                
        sorted_unindexed_nodes = sorted(
            unindexed_nodes,
            key=lambda node_id: self.nodes[node_id].date,
            reverse=True)
        return sorted_unindexed_nodes

    def indexed_nodes(self):
        """ returns an array of node IDs of indexed nodes, in indexed order """

        indexed_nodes_list = []
        node_list = list(self.nodes)
        for node in node_list:
            if self.nodes[node].metadata.get_tag('index') != []:
                indexed_nodes_list.append([
                    node,
                    int((self.nodes[node].metadata.get_tag('index')[0]))
                ])
        sorted_indexed_nodes = sorted(indexed_nodes_list,
                                      key=lambda item: item[1])
        for i in range(len(sorted_indexed_nodes)):
            sorted_indexed_nodes[i] = sorted_indexed_nodes[i][0]
        return sorted_indexed_nodes

    def root_nodes(self):
        """
        Returns the IDs of all the root (file level) nodes
        """
        root_nodes = []
        for node_id in self.nodes:
            if self.nodes[node_id].root_node == True:
                root_nodes.append(node_id)
        return root_nodes

    """ 
    Full Text search implementation using Whoosh (unfinished) 
    These methods are currently unused
    """
    def rebuild_search_index(self):
        
        self.ix = create_in(os.path.join(self.path, "index"),
                            schema=self.schema,
                            indexname="urtext")

        self.writer = self.ix.writer()

        for filename in self.files:
            self.re_search_index_file(filename, single=False)
                                
        self.writer.commit()

    def re_search_index_file(self, filename, single=True):
        
        if not self.ix:
            return

        if single:
            self.writer = self.ix.writer()

        for node_id in self.files[filename]['nodes']:
            self.writer.add_document(title=self.nodes[node_id].title,
                                path=node_id,
                                content=self.nodes[node_id].contents())
        if single:
            self.writer.commit()

    def search(self, string):

        final_results = ''
        with self.ix.searcher() as searcher:
            query = QueryParser("content", self.ix.schema).parse(string)
            results = searcher.search(query, limit=1000)
            results.formatter = UppercaseFormatter()
            final_results += 'TOTAL RESULTS: ' + str(len(results)) + '\n\n'
            for result in results:
                final_results += '\n\n---- in >' + result['path'] + '\n\n'
                test = self.nodes[result['path']].contents()
                final_results += result.highlights("content")

        return final_results

    """ 
    Other Features, Utilities
    """
    def export_project( self , jekyll=False, style_titles=True ):
        for filename in list(self.files):
            export_filename = self.get_root_node_id(filename)+'.html'
            self.export(filename, 
                export_filename, 
                kind='HTML',
                as_single_file=False,
                style_titles=style_titles,
                strip_urtext_syntax=False,
                jekyll=jekyll)

    def export( self, 
                filename, 
                to_filename, 
                kind='HTML',
                as_single_file=False,
                style_titles=True,
                strip_urtext_syntax=True,
                jekyll=False,
                jekyll_post=False):
        

        def opening_wrapper(kind, nested):
            wrappers = { 
                'HTML':     '<div class="urtext_nested_'+str(nested)+'">',
                'Markdown': ''
                }
            return wrappers[kind]

        def closing_wrapper(kind):
            wrappers = { 
                'HTML': '</div>',
                'Markdown': ''
                }
            return wrappers[kind]

        def wrap_title(kind, node_id, nested):
            title = self.nodes[node_id].title
            if kind == 'Markdown':
                return '\n' + '#' * nested + ' ' + title + '\n'
            if kind == 'HTML':
                return '<h'+str(nested)+'>' + title + '</h'+str(nested)+'>\n'
            
        root_node_id = self.get_root_node_id(filename)
        
        def s(  root_node_id, 
                nested, 
                visited_nodes, 
                strip_urtext_syntax=strip_urtext_syntax, 
                style_titles=style_titles):

            if root_node_id in visited_nodes:
                return '\n' + '#' * nested + ' RECURSION : '+ root_node_id                
            else:
                visited_nodes.append(root_node_id)

            exported_contents = ''

            ranges =  self.nodes[root_node_id].ranges
            filename = self.nodes[root_node_id].filename
            
            with open(os.path.join(self.path, filename),'r',encoding="utf-8") as f:
                file_contents = f.read()
                f.close()
            
            title = self.nodes[root_node_id].title
            if style_titles:                 
                exported_contents += wrap_title(kind, root_node_id, nested)

            title_removed = True
            if len(self.nodes[root_node_id].metadata.get_tag('title')) == 0: 
                title_removed = False
            
            exported_contents += opening_wrapper(kind, nested)        
            exported_contents += '<a name="'+ root_node_id + '"></a>'

            
            for single_range in ranges:

                added_contents = '' 
                
                if kind == 'HTML':
                    
                    if single_range == ranges[0] and not strip_urtext_syntax:
                        added_contents += '<span class="urtext-open-brackets">&#123;&#123;</span>'

                    added_contents += file_contents[single_range[0]:single_range[1]]

                    lines = [line.strip() for line in added_contents.split('\n') if line.strip() != '']
                    added_contents = ''

                    index = 0
                    while index < len(lines):
                        line = lines[index]
                        if line[0] == '-':
                            added_contents += '<ul class="urtext-list">'
                            while index < len(lines) - 1:
                                added_contents += '<li>'+line[1:]+'</li>'
                                index += 1
                                line = lines[index]
                                if line[0] != '-':
                                    break
                            added_contents += '</ul>'

                        added_contents += '<div class="urtext_line">' + line.strip()
                        if single_range == ranges[-1] and line == lines[-1] and not strip_urtext_syntax:
                            added_contents += '<span class="urtext-close-brackets">&#125;&#125;</span>'                
                        added_contents += '</div>\n'     
                        index += 1

                
                if style_titles and not title_removed and title in added_contents:
                    added_contents = added_contents.replace(title,'',1)
                    title_removed = True

                elif kind == 'HTML':
                    heading_tag = 'h'+str(nested)
                    added_contents = added_contents.replace(  title,
                                                              '<'+heading_tag+'>'+title+'</'+heading_tag+'>',
                                                              1)

                    for match in re.findall(node_link_regex, exported_contents):
                        node_id = match[1:]
                        if node_id not in self.nodes:
                            # probably another use of >, technically a syntax error
                            # TODO write better error catching here
                            continue
                        filename = self.nodes[root_node_id].filename
                        if node_id in self.files[filename]:
                            link = '#'+node_id
                        else: 
                            base_filename = self.nodes[node_id].filename
                            this_root_node = self.get_root_node_id(base_filename)
                            link = this_root_node+'.html#'+ node_id
                        exported_contents = exported_contents.replace(match, 
                                        '<a href="'+link+'">'+match+'</a>')
                    
                if as_single_file:
                    while re.findall(node_pointer_regex, added_contents):
                        for match in re.findall(node_pointer_regex, added_contents):
                            inserted_contents = s(match[2:5], nested + 1, visited_nodes)
                            if inserted_contents == None:
                                inserted_contents = ''
                            added_contents = added_contents.replace(match, inserted_contents)

                exported_contents += added_contents
                if single_range != ranges[-1]:
                    next_node = self.get_node_id_from_position(filename, single_range[1]+1)
                    if next_node in self.dynamic_nodes and self.dynamic_nodes[next_node].tree:
                        exported_contents += self.render_tree_as_html(self.dynamic_nodes[next_node].tree)
                    else:
                        exported_contents += s(next_node, nested + 1 ,visited_nodes)
                
            exported_contents += closing_wrapper(kind)

            return exported_contents 

         

        visited_nodes = []
        final_exported_contents = s(root_node_id, 1, visited_nodes)
        
        

        if strip_urtext_syntax:
            # strip metadata
            final_exported_contents = re.sub(r'(\/--(?:(?!\/--).)*?--\/)',
                                       '',
                                       final_exported_contents,
                                       flags=re.DOTALL)
        if kind == 'HTML': 
            final_exported_contents = final_exported_contents.replace('/--','<span class="urtext-metadata">/--')
            final_exported_contents = final_exported_contents.replace('--/','--/</span>')

        
        if jekyll:

                post_or_page = 'page'
                if jekyll_post:
                    post_or_page = 'post'

                header = '\n'.join([
                '---',
                'layout: '+ post_or_page,
                'title:  "'+ self.nodes[root_node_id].title +'"',
                'date:   2019-08-21 10:44:41 -0500',
                'categories: '+ ' '.join(self.nodes[root_node_id].metadata.get_tag('categories')),
                '---'
                ]) + '\n'

                final_exported_contents = header + final_exported_contents


        
        with open(os.path.join(self.path, to_filename), 'w', encoding='utf-8') as f:
            f.write(final_exported_contents)
    
    def get_parent(self, child_node_id):
        """ Given a node ID, returns its parent, if any """

        filename = self.nodes[child_node_id].filename
        start = self.nodes[child_node_id].ranges[0][0]
        distance_back = 2 
        if self.nodes[child_node_id].compact:
            distance_back = 1
        for other_node in [
                other_id for other_id in self.files[filename]['nodes']
                if other_id != child_node_id
                ]:
            
            if self.is_in_node(start - distance_back, other_node):
                return other_node
        return None

    def is_in_node(self, position, node_id):
        """ Given a position, and node_id, returns whether the position is in the node """
        for this_range in self.nodes[node_id].ranges:
            if position > this_range[0] - 2 and position < this_range[1] + 2:
                return True
        return False

    def get_node_id_from_position(self, filename, position):
        """ Given a position, returns the Node ID it's in """

        for node_id in self.files[os.path.basename(filename)]['nodes']:
            if self.is_in_node(position, node_id):
                return node_id
        return None

    def get_link(self, string, position=None):
        """ Given a line of text passed from an editorm, returns finds a node or web link """

        url_scheme = re.compile('http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\), ]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')
        if re.search(url_scheme, string):
            url = re.search(url_scheme, string).group(0)
            return ['HTTP', url]

        link = None
        # first try looking where the cursor is positioned
        if position:
            for index in range(0, 3):
                if re.search(node_link_regex,
                             string[position - index:position - index + 5]):
                    link = re.search(
                        node_link_regex,
                        string[position - index:position - index + 5]).group(0)

        # next try looking ahead:
        if not link:
            after_cursor = string[position:]
            if re.search(node_link_regex, after_cursor):
                link = re.search(node_link_regex, after_cursor).group(0)

        if not link:
            before_cursor = string[:position]
            if re.search(node_link_regex, before_cursor):
                link = re.search(node_link_regex, before_cursor).group(0)

        if not link:
            return None

        node_id = link.split(':')[0].strip('>')
        if node_id.strip() in self.nodes:
            file_position = self.nodes[node_id].ranges[0][0]
            return ['NODE', node_id, file_position]
        else:
            self.log_item('Node ' + node_id + ' is not in the project')
            return None
        self.log_item('No node ID found on this line.')
        return None

    def build_timeline(self, nodes):
        """ Given a list of nodes, returns a timeline """

        return timeline(self, nodes)

    def is_duplicate_id(self, node_id, filename):
        if node_id in self.nodes:
            self.log_item('Duplicate node ID ' + node_id + ' in ' + filename +
                          ' -- already used in ' +
                          self.nodes[node_id].filename + ' (>' + node_id + ')')
            self.remove_file(filename)
            return True
        return False

    def log_item(self, item):
        self.log.info(item + '\n')
        #if self.settings['console_log'].lower() == 'true':          
        print(item)
        pass
        
    def timestamp(self, date):
        """ Given a datetime object, returns a timestamp in the format set in project_settings, or the default """

        timestamp_format = '<' + self.settings['timestamp_format'][0] + '>'
        return date.strftime(timestamp_format)

    def get_settings_from(self, node):
        for entry in node.metadata.entries:
            self.settings[entry.tag_name.lower()] = entry.value

    def get_file_name(self, node_id):
        if node_id in self.nodes:
            return self.nodes[node_id].filename
        return None

    def next_index(self):
        index = random.choice(list(self.node_id_generator()))
        while ''.join(index) in self.nodes:
            index = random.choice(list(self.node_id_generator()))
        return ''.join(index)

    def get_root_node_id(self, filename):
        """
        Given a filename, returns the root Node's ID
        """
        for node_id in self.files[filename]['nodes']:
            if self.nodes[node_id].root_node == True:
                return node_id
        return None

    def get_all_files(self):

        all_files = []
        for node in self.nodes:
            all_files.append(self.nodes[node].filename)
        return all_files
    """
    Sync to Google Calendar
    """
    def get_google_auth_token(self):
        return os.path.join(self.path, self.settings['google_auth_token'])

    def get_google_credentials(self):
        return os.path.join(self.path, 'credentials.json')

    def get_service_account_private_key(self):
        return os.path.join(self.path, self.settings['google_service_account_private_key'])
    def sync_to_google_calendar(self):
        google_calendar_id = self.settings['google_calendar_id']
        if not google_calendar_id:
            return
        sync_project_to_calendar(self, google_calendar_id)

    """
    Folder Locking
    """
    def check_lock(self, machine):
        lock = self.get_current_lock()
        if lock == machine:
            return True
        if not lock:
            return self.lock(machine)
        print('compiling locked by '+lock)
        return False

    def get_current_lock(self):
        lock_file = os.path.join(self.path,'.lock')
        try:
            with open(lock_file, 'r') as f:
                contents = f.read()
                f.close()
            return contents
        except:
            return None

    def lock(self, machine):
        lock_file = os.path.join(self.path,'.lock')
        with open (lock_file, 'w', encoding='utf-8') as f:
            f.write(machine)
            f.close()
        return True

""" 
Helpers 
"""
def build_metadata(tags, one_line=False):
    """ Note this is a method from node.py. Could be refactored """

    if one_line:
        line_separator = '; '
    else:
        line_separator = '\n'
    new_metadata = '\n/-- '
    if not one_line: 
        new_metadata += line_separator
    for tag in tags:
        new_metadata += tag + ': '
        if isinstance(tags[tag], list):
            new_metadata += ' | '.join(tags[tag])
        else:
            new_metadata += tags[tag]
        new_metadata += line_separator
    if one_line:
        new_metadata = new_metadata[:-2] + ' '

    new_metadata += '--/'
    return new_metadata 

def indent(contents, spaces=4):
    content_lines = contents.split('\n')
    for index in range(len(content_lines)):
        if content_lines[index].strip() != '':
            content_lines[index] = ' ' * spaces + content_lines[index]
    return '\n'.join(content_lines)


def setup_logger(name, log_file, level=logging.INFO):
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
    if not os.path.exists(log_file):
        with open(log_file, 'w', encoding='utf-8') as theFile:
            theFile.close()
    logger = logging.getLogger(name)
    handler = logging.FileHandler(log_file, mode='a')
    handler.setFormatter(formatter)
    logger.setLevel(level)
    logger.addHandler(handler)
    return logger


def creation_date(path_to_file):
    """
    Try to get the date that a file was created, falling back to when it was
    last modified if that isn't possible.
    See http://stackoverflow.com/a/39501288/1709587 for explanation.
    """
    if platform.system() == 'Windows':
        return datetime.datetime.fromtimestamp(os.path.getctime(path_to_file))
    else:
        stat = os.stat(path_to_file)
        try:
            return datetime.datetime.fromtimestamp(stat.st_birthtime)
        except AttributeError:
            # We're probably on Linux. No easy way to get creation dates here,
            # so we'll settle for when its content was last modified.
            return datetime.datetime.fromtimestamp(stat.st_mtime)

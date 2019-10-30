# -*- coding: utf-8 -*-
import re
import datetime
import itertools
import platform
import logging
import json
import os
import random
import time
from time import strftime
from pytz import timezone
import pytz
import getpass

from anytree import Node, RenderTree, PreOrderIter
from anytree.render import AbstractStyle

from whoosh.fields import Schema, TEXT, KEYWORD, ID, STORED
from whoosh.index import create_in, exists_in, open_dir
from whoosh.qparser import QueryParser
from whoosh.highlight import UppercaseFormatter
from whoosh.analysis import StemmingAnalyzer

from .timeline import timeline
from .file import UrtextFile
from .interlinks import Interlinks

#from .google_calendar import sync_project_to_calendar
node_id_regex = r'\b[0-9,a-z]{3}\b'
node_pointer_regex = r'>>[0-9,a-z]{3}\b'
node_link_regex = r'>[0-9,a-z]{3}\b'

class UrtextProject:
    """ Urtext project object """
    
    def __init__(self,
                 path,
                 rename=False,
                 recursive=False,
                 import_project=False,
                 init_project=False):

        self.path = path
        self.conflicting_files = []
        self.log = setup_logger('urtext_log',
                                os.path.join(self.path, 'urtext_log.txt'))
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
            'google_calendar_id' : None,
            'timezone' : 'US/Eastern' 
        }
        self.to_import = []
        self.settings_initialized = False
        self.dynamic_nodes = {}  # { target : definition, etc.}
        self.compiled = False
        self.alias_nodes = []
        self.ix = None
 
        # Whoosh
        self.schema = Schema(
                title=TEXT(stored=True),
                path=ID(stored=True),
                content=TEXT(stored=True, analyzer=StemmingAnalyzer()))

        index_dir = os.path.join(self.path, "index")
        
        if exists_in(os.path.join(self.path, "index"), indexname="urtext"):
            self.ix = open_dir(os.path.join(self.path, "index"),
                               indexname="urtext")
        
        filelist = os.listdir(self.path)

        self.machine_name = getpass.getuser()
        self.lock()
        
        for file in filelist:
            if self.filter_filenames(file) == None:
                continue
            self.parse_file(file, import_project=import_project)

        for file in self.to_import:
            self.import_file(file)

        if self.nodes == {}:
            if init_project == True:
                self.log_item('Initalizing a new Urtext project in ' + path)
            else:
                raise NoProject('No Urtext nodes in this folder.')

        # must be done once manually on project init
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

        if compile == True:
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

        if self.filter_filenames(filename) == None:
            return

        # clear all node_id's defined from this file in case the file has changed
        self.remove_file(filename)

        """
        Find all node symbols in the file
        """
        new_file = UrtextFile(os.path.join(self.path, filename))
        self.files[new_file.basename] = new_file
        for node_id in new_file.nodes:
            if self.is_duplicate_id(node_id, filename):
                self.remove_file(new_file.basename)
                return
            self.add_node(new_file.nodes[node_id])
        
        """
        If this is not the initial load of the project, parse the timestamps in the file
        """
        if self.compiled == True:
            for node_id in new_file.nodes:
                self.parse_meta_dates(node_id)
        
        self.set_tree_elements(new_file.basename)

        for node_id in new_file.nodes:
            self.rebuild_node_tag_info(node_id)
        
        #if re_index:
        #    self.re_search_index_file(filename)

        return filename

    """
    Tree building
    """
    def set_tree_elements(self, filename):
        """ Builds tree elements within the file, after the file is parsed."""

        parsed_items = self.files[filename].parsed_items
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
                        node_id for node_id in self.files[filename].nodes
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
                self.nodes[node].tree_node.parent = self.nodes[root_node_id].tree_node
                continue
            """
            Otherwise, this is either an inline node not at the beginning of the file,
            or else a root (file level) node, so:
            """
            if not self.nodes[node].root_node:
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
    def add_node(self, new_node):
        """ Adds a node to the project object """

        for target_id in new_node.dynamic_definitions.keys():
            if target_id in self.dynamic_nodes:
                self.log_item('Node >' + target_id +
                              ' has duplicate definition in >' + new_node.id +
                              '. Keeping the definition in >' +
                              self.dynamic_nodes[target_id].source_id + '.')
            else:
                self.dynamic_nodes[target_id] = new_node.dynamic_definitions[target_id]

        ID_tags = new_node.metadata.get_tag('ID')
        if len(ID_tags) > 1:
            self.log_item('Multiple ID tags in >' + new_node.id +
                          ', using the first one found.')
            print('ERROR LOGGING, ID_tags:')
            print(ID_tags)


        self.nodes[new_node.id] = new_node
        if new_node.project_settings:
            self.get_settings_from(new_node)

    def parse_meta_dates(self, node_id):
        """ Parses dates (requires that timestamp_format already be set) """

        timestamp_format = self.settings['timestamp_format']
        default_timezone = timezone(self.settings['timezone'])

        if isinstance(timestamp_format, str):
            timestamp_format = [timestamp_format]

        for entry in self.nodes[node_id].metadata.entries:
            if entry.dtstring:
                dt_stamp = None
                for this_format in timestamp_format:
                    dt_format = '<' + this_format + '>'
                    try:
                        dt_stamp = datetime.datetime.strptime(entry.dtstring, dt_format)
                    except:
                        continue
                if dt_stamp:
                    if dt_stamp.tzinfo == None:
                        dt_stamp = default_timezone.localize(dt_stamp) 
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
                            
                            # Will need to be changed to handle multiple root nodes
                            this_root_node = self.get_root_node_id(base_filename)
                            ###
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

        for target_id in list(self.dynamic_nodes):
            """
            Make sure the target node exists.
            """

            source_id = self.dynamic_nodes[target_id].source_id
            if target_id not in self.nodes:
                self.log_item('Dynamic node definition >' + source_id +
                              ' points to nonexistent node >' + target_id)
                continue

            # these should no longer be necessary with machine lock
            # self.parse_file(self.nodes[target_id].filename)
            # self.update(compile=False, update_lists=False)
            
            dynamic_definition = self.dynamic_nodes[target_id]

            new_node_contents = ''

            if dynamic_definition.tree and dynamic_definition.tree in self.nodes:
                new_node_contents += self.show_tree_from(dynamic_definition.tree)

            else:
                # list of explicitly included node IDs
                included_nodes = []

                # list of explicitly excluded node IDs
                excluded_nodes = []

                # list of the nodes indicated by ALL the key/value pairs for AND inclusion
                included_nodes_and = []

                # for all AND key/value pairs in the dynamic definition                 
                for item in dynamic_definition.include_and:
                    key, value = item[0], item[1]

                    # if the key/value pair is in the project
                    if key in self.tagnames and value in self.tagnames[key]:

                        # add its nodes to the list of possibly included nodes as its own set
                        included_nodes_and.append(set(self.tagnames[key][value]))

                    else:
                        # otherwise, this means no nodes result from this AND combination
                        included_nodes_and = []
                        break

                # If more than one actual set results from this:
                if len(included_nodes_and) > 1:

                    # reduce the list to the intersection of all sets
                    included_nodes_and = list(set(included_nodes_and[0]).intersection(*included_nodes_and))

                elif len(included_nodes_and) > 0:
                    # otherwise, the list of included nodes is just the single set, if it exists
                    included_nodes_and = list(included_nodes_and[0])
                    
                # add all the these nodes to the list of nodes to be included, avoiding duplicates
                for indiv_node_id in included_nodes_and:
                    if indiv_node_id not in included_nodes:
                        included_nodes.append(indiv_node_id)

                for item in dynamic_definition.include_or:
                    key, value = item[0], item[1]
                    if value in self.tagnames[key]:
                        added_nodes = self.tagnames[key][value]
                        for indiv_node_id in added_nodes:
                            if indiv_node_id not in included_nodes:
                                included_nodes.append(indiv_node_id)
    
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
                included_nodes = [self.nodes[node_id] for node_id in included_nodes]
                """
                build timeline if specified
                """
                if dynamic_definition.show == 'timeline':
                    new_node_contents += timeline(self, included_nodes)

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
                            show_contents = targeted_node.content_only().strip('\n').strip()
                        new_node_contents += '- '+show_contents + ' >' + targeted_node.id + '\n'
            """
            add metadata to dynamic node
            """

            metadata_values = { 
                'ID': [ target_id ],
                'defined in' : [ '>'+dynamic_definition.source_id ] }

            for value in dynamic_definition.metadata:
                metadata_values[value] = dynamic_definition.metadata[value]
            built_metadata = build_metadata(metadata_values, one_line=dynamic_definition.oneline_meta)

            title = ''
            if 'title' in dynamic_definition.metadata:
                title = dynamic_definition.metadata['title'] + '\n'

            updated_node_contents = '\n' + title + new_node_contents + built_metadata

            """
            add indentation if specified
            """

            if dynamic_definition.spaces:
                updated_node_contents = indent(updated_node_contents,
                                               dynamic_definition.spaces)

            self.set_node_contents(target_id, updated_node_contents)
        
        self.update(compile=False)

    def set_node_contents(self, node_id, contents):
        """ project-aware alias for the Node set_content() method """

        if self.nodes[node_id].set_content(contents):
            self.parse_file(self.nodes[node_id].filename)

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
        for key in sorted([
                k for k in self.tagnames
                if k.lower() not in ['defined in', 'id', 'timestamp', 'index']
        ]):
            s = Node(key)
            s.parent = root
            for value in sorted(self.tagnames[key]):
                t = Node(value)
                t.parent = s
                if value in self.tagnames[key]:
                    for node_id in sorted(self.tagnames[key][value]):
                        if node_id in self.nodes:
                            n = Node(self.nodes[node_id].title + ' >' +
                                     node_id)
                            n.parent = t
                        else: # debugging
                            print(node_id+ ' WAS LOST (DEBUGGING)')
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
        
        full_file_contents = self.full_file_contents(node_id=node_id)
        tag_position = territory[-1][1]
        new_contents = full_file_contents[:tag_position] + tag_contents + full_file_contents[tag_position:]

        self.set_file_contents(self.nodes[node_id].filename, new_contents)
        self.parse_file(os.path.join(self.path, self.nodes[node_id].filename))

    def adjust_ranges(self, filename, from_position, amount):
        """ 
        adjust the ranges of all nodes in the given file 
        a given amount, from a given position
        """
        for node_id in self.files[os.path.basename(filename)].nodes:
            number_ranges = len(self.nodes[node_id].ranges)
            for index in range(number_ranges):
                this_range = self.nodes[node_id].ranges[index]
                if from_position >= this_range[0]:
                    self.nodes[node_id].ranges[index][0] -= amount
                    self.nodes[node_id].ranges[index][1] -= amount

    def full_file_contents(self, filename='', node_id=''):
        if node_id:
            filename = self.nodes[node_id].filename
        if not filename:
            return
        with open(os.path.join(self.path, filename), 'r',
                  encoding='utf-8') as theFile:
            file_contents = theFile.read()
            theFile.close()
        return file_contents

    def set_file_contents(self, filename, contents):
        with open(os.path.join(self.path, filename),
                  'w', encoding='utf-8') as theFile:
            theFile.write(contents)
            theFile.close()
        return

    def consolidate_metadata(self, node_id, one_line=False):
        if node_id not in self.nodes:
            self.log_item('Node ID '+node_id+' not in project.')
            return None

        consolidated_metadata = self.nodes[node_id].consolidate_metadata(
            one_line=one_line)

        file_contents = self.full_file_contents(node_id=node_id) 
        filename = self.nodes[node_id].filename
        length = len(file_contents)
        ranges = self.nodes[node_id].ranges
        meta = re.compile(r'(\/--(?:(?!\/--).)*?--\/)',re.DOTALL)

        for single_range in ranges:

            for section in meta.finditer(file_contents[single_range[0]:single_range[1]]):
                start = section.start() + single_range[0]
                end = start + len(section.group())
                first_splice = file_contents[:start]
                second_splice = file_contents[end:]
                file_contents = first_splice
                file_contents += second_splice
                self.adjust_ranges(filename, start, len(section.group()))

        new_file_contents = file_contents[0:ranges[-1][1] - 2]
        new_file_contents += consolidated_metadata
        new_file_contents += file_contents[ranges[-1][1]:]
        self.set_file_contents(filename, new_file_contents)
        self.parse_file(filename)

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

        self.set_file_contents(filename,full_file_contents)

        return self.parse_file(filename)

    def get_node_relationships(self, node_id):
        return Interlinks(self, node_id).render

    """
    Removing and renaming files
    """
    def remove_file(self, filename):
        """ removes the file from the project object """

        if filename in self.files:
            for node_id in self.files[filename].nodes:
                for target_id in list(self.dynamic_nodes):
                    if self.dynamic_nodes[target_id].source_id == node_id:
                        del self.dynamic_nodes[target_id]

                # REFACTOR
                # delete it from the self.tagnames array -- duplicated from delete_file()
                for tagname in list(self.tagnames):
                    for value in list(self.tagnames[tagname]):
                        if value in self.tagnames[tagname]:  
                            # in case it's been removed
                            if node_id in self.tagnames[tagname][value]:
                                self.tagnames[tagname][value].remove(node_id)
                            if len(self.tagnames[tagname][value]) == 0:
                                del self.tagnames[tagname][value]
                if node_id in self.nodes:
                    del self.nodes[node_id]
            del self.files[filename]
        return None

    def handle_renamed(self, old_filename, new_filename):
        new_filename = os.path.basename(new_filename)
        old_filename = os.path.basename(old_filename)
        self.files[new_filename] = self.files[old_filename]
        for node_id in self.files[new_filename].nodes:
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
    
    def new_file_node(self, date=None, metadata = {}, node_id=None):
        """ add a new FILE-level node programatically """

        if date == None:
            date = datetime.datetime.now()

        if not node_id:
            node_id = self.next_index()            
        contents = "\n\n\n"
        contents += "/-- ID:" + node_id + '\n'
        contents += 'Timestamp:' + self.timestamp(date) + '\n'
        for key in metadata:
            contents += key + ": " + metadata[key] + '\n'
        contents += "--/"

        filename = node_id + '.txt'

        self.set_file_contents( filename, contents )  
        self.parse_file(filename)
        return { 
                'filename':filename, 
                'id':node_id
                }
 
    def add_inline_node(self, 
            date=None, 
            contents='', 
            metadata={},
            one_line=False ):

        if date == None:
            date = datetime.datetime.now()
            
        if contents == '':
            contents = ' '
 
        node_id = self.next_index()       
        metadata['id']=self.next_index()
        metadata['timestamp'] = self.timestamp(date)
        new_node_contents = "{{ " + contents 
        metadata_block = build_metadata(metadata, one_line=one_line)
        new_node_contents += metadata_block + " }}"
 
        return new_node_contents

    def add_compact_node(self, 
            date=None, 
            contents='', 
            metadata={},
        ):
        if date == None:
            date = datetime.datetime.now()
        metadata['id']=self.next_index()
        metadata['timestamp'] = self.timestamp(date)
        metadata_block = build_metadata(metadata, one_line=True)
        return '^ '+contents + metadata_block

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

            ## WILL NEED TO BE CHANGED TO HANDLE MULTIPLE ROOT NODES

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

        for node_id in self.files[filename].nodes:
            self.writer.add_document(title=self.nodes[node_id].title,
                                path=node_id,
                                content=self.nodes[node_id].contents())
        if single:
            self.writer.commit()

    def search(self, string):

        final_results = ''
        shown_nodes = []
        with self.ix.searcher() as searcher:
            query = QueryParser("content", self.ix.schema).parse(string)
            results = searcher.search(query, limit=1000)
            results.formatter = UppercaseFormatter()
            final_results += 'Total Results: ' + str(len(results)) + '\n\n'
            final_results +='\n----------------------------------\n'
            for result in results:
                node_id = result['path']
                if node_id in self.nodes:
                    if node_id not in shown_nodes:
                        final_results += ''.join([
                            self.nodes[node_id].title,' >', node_id, '\n',
                            result.highlights("content"),
                            '\n----------------------------------\n'])
                        shown_nodes.append(node_id)
                else:
                    final_results += node_id + ' ( No longer in the project. Update the search index. )\n\n'

        return final_results

    """ 
    Other Features, Utilities
    """
    def export_project( self , jekyll=False, style_titles=True ):
        for filename in list(self.files):
            # will have to be changed to handle multiple root nodes
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
        
        # will have to be changed to handle multiple root nodes
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
            
            file_contents = self.full_file_contents(filename)
            
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
                other_id for other_id in self.files[filename].nodes
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

        for node_id in self.files[os.path.basename(filename)].nodes:
            if self.is_in_node(position, node_id):
                return node_id
        return None

    def get_link(self, string, position=0):
        """ Given a line of text passed from an editor, returns finds a node or web link """
        url_scheme = re.compile('http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\), ]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')

        if re.search(url_scheme, string[position:]):
            url = re.search(url_scheme, string).group(0)
            return ['HTTP', url]

        link = None
        # first try looking around where the cursor is positioned
        for index in range(0, 3):
            if re.search(node_link_regex,
                         string[position - index:position - index + 5]):
                link = re.search(
                    node_link_regex,
                    string[position - index:position - index + 5]).group(0)
                break

        # next try looking ahead:
        if not link:
            after_cursor = string[position:]
            if re.search(node_link_regex, after_cursor):
                link = re.search(node_link_regex, after_cursor).group(0)

        # then behind:
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
            return True
        return False

    def log_item(self, item):
        self.log.info(item + '\n')
        #if self.settings['console_log'].lower() == 'true':          
        print(item)
        pass
        
    def timestamp(self, date):
        """ Given a datetime object, returns a timestamp in the format set in project_settings, or the default """

        default_timezone = timezone(self.settings['timezone'])
        if date.tzinfo == None:
            date = timezone(self.settings['timezone']).localize(date)             

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
        for node_id in self.files[filename].nodes:
            for root_node in self.files[filename].root_nodes:
                if self.is_in_node(root_node, self.nodes[node_id].ranges[0][0]):
                    return root_node
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
    def check_lock(self):
        lock = self.get_current_lock()
        if lock == self.machine_name:
            return True
        if not lock:
            return self.lock()
        print('compiling locked by '+lock)
        return False

    def get_current_lock(self):
        lock_file = os.path.join(self.path,'lock')
        with open(lock_file, 'r', encoding='utf-8') as f:
            contents = f.read()
            f.close()
        return contents

    def lock(self):
        lock_file = os.path.join(self.path,'lock')
        with open (lock_file, 'w', encoding='utf-8') as f:
            f.write(self.machine_name)
            f.close()
        return True

    def pop_node(self, position=None, filename=None, node_id=None):
        if not node_id:
            node_id = self.get_node_id_from_position(filename, position)
        if not node_id:
            return
        if self.nodes[node_id].root_node:
            print(node_id + ' is already a root node.')
            return

        start = self.nodes[node_id].ranges[0][0]
        end = self.nodes[node_id].ranges[-1][1]

        file_contents = self.full_file_contents(node_id=node_id)
        popped_node_id = node_id
        root_node_id = self.get_root_node_id(self.nodes[node_id].filename)

        popped_node_contents = file_contents[start:end].strip()
        
        remaining_node_contents = ''.join([
            file_contents[0:start - 2],
            '\n',
            '>>',
            popped_node_id,
            '\n',
            file_contents[end + 2:]])

        self.nodes[root_node_id].set_content(remaining_node_contents)
        with open(os.path.join(self.path, popped_node_id+'.txt'), 'w',encoding='utf-8') as f:
            f.write(popped_node_contents)
            f.close()

        self.parse_file(popped_node_id+'.txt')
        self.parse_file(self.nodes[node_id].filename)
        
        return start - 2 # returns where to put the cursor at the new marker

    def titles(self):
        title_list = {}
        for node_id in self.nodes:
            title_list[self.nodes[node_id].title] = node_id
        return title_list

    def complete_tag(self, fragment):
        fragment = fragment.lower().strip()
        length = len(fragment)
        for tag in self.tagnames['tags'].keys():
            if fragment == tag[:length].lower():
                return tag
        return u''

    """
    Methods used with watchdog
    """

    def on_created(self, filename):
        if not self.check_lock():
            return False
        if os.path.isdir(filename):
            return True
        filename = os.path.basename(filename)
        if filename in self.files:
          return True
        self.parse_file(filename, re_index=True)
        self.log_item(filename +' modified. Updating the project object')
        self.update()
        return True

    def on_modified(self, filename):
        if not self.check_lock():
          return False
        filename = os.path.basename(filename)
        do_not_update = [
            'index', 
            os.path.basename(self.path),
            self.settings['logfile'],
            ]

        for node_id in ['zzz','zzy']:
            if node_id in self.nodes:
               do_not_update.append(self.nodes[node_id].filename)

        if filename in do_not_update or '.git' in filename:
            return True
        self.log_item('MODIFIED ' + filename +' - Updating the project object')
        self.parse_file(filename, re_index=True)
        self.update()
        return True

    def on_deleted(self, filename):
      """ this method should be removed, since deleting files should be done explicitly from Urtext """
      pass
      
      # if not self.check_lock():
      #     return False
        
      # filename = os.path.basename(filename)
      # self.log_item('Watchdog saw file deleted: '+filename)
      # self.remove_file(filename)
      # self.update()
      # return True

    def on_moved(self, filename):
        if not self.check_lock():            
            return False
        old_filename = os.path.basename(filename)
        new_filename = os.path.basename(filename)
        if old_filename in self.files:
            self.log.info('RENAMED ' + old_filename + ' to ' +
                                    new_filename)
            self.handle_renamed(old_filename, new_filename)
        return True



class NoProject(Exception):
    """ no Urtext nodes are in the folder """
    pass


""" 
Helpers 
"""
def build_metadata(tags, one_line=False):
    """ Note this is a method from node.py. Could be refactored """

    if one_line:
        line_separator = '; '
    else:
        line_separator = '\n'
    new_metadata = '/-- '
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

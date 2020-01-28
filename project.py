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
import pickle
from time import strftime
from pytz import timezone
import pytz
import concurrent.futures
from anytree import Node, RenderTree, PreOrderIter
from anytree.render import AbstractStyle

from whoosh.fields import Schema, TEXT, KEYWORD, ID, STORED
from whoosh.index import create_in, exists_in, open_dir
from whoosh.qparser import QueryParser
from whoosh.highlight import UppercaseFormatter
from whoosh.analysis import StemmingAnalyzer
from whoosh.writing import AsyncWriter

from .timeline import timeline
from .file import UrtextFile
from .interlinks import Interlinks
from .node import UrtextNode 
from .export import UrtextExport

#from .google_calendar import sync_project_to_calendar
node_id_regex = r'\b[0-9,a-z]{3}\b'
node_pointer_regex = r'>>[0-9,a-z]{3}\b'
node_link_regex = r'>[0-9,a-z]{3}\b'
title_marker_regex = r'\|.*?>{1,2}[0-9,a-z]{3}\b'

class UrtextProject:
    """ Urtext project object """
    
    def __init__(self,
                 path,
                 rename=False,
                 recursive=False,
                 import_project=False,
                 init_project=False,
                 watchdog=False):

        self.path = path
        if not os.path.exists(os.path.join(self.path, "urtext_log.txt")):
            with open(os.path.join(self.path, "urtext_log.txt"), "w") as f:
                f.write('URTEXT LOG')
                f.close()
        self.log = setup_logger('urtext_log',
                                os.path.join(self.path, 'urtext_log.txt'))

        self.nodes = {}
        self.files = {}
        self.tagnames = {}
        self.zero_page = ''
        self.other_projects = []
        self.navigation = []  # Stores, in order, the path of navigation
        self.nav_index = -1  # pointer to the CURRENT position in the navigation list
        self.to_import = []
        self.settings_initialized = False
        self.dynamic_nodes = {}  # { target : definition, etc.}
        self.dynamic_tags = {} # source_id : [ target_id, ... ]
        self.compiled = False
        self.alias_nodes = []
        self.ix = None
        self.loaded = False
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.settings = {  # defaults
            'logfile':'urtext_log.txt',
            'home': None,
            'timestamp_format':
                ['%a., %b. %d, %Y, %I:%M %p', '%B %-d, %Y', '%B %Y', '%m-%d-%Y'],
            'filenames': ['PREFIX', 'DATE %m-%d-%Y', 'TITLE'],
            'console_log':'false',
            'google_auth_token' : 'token.json',
            'google_calendar_id' : None,
            'timezone' : ['UTC'] 
        }
        self.default_timezone = None
        self.title = self.path # default
        # Whoosh
        self.schema = Schema(
                title=TEXT(stored=True),
                path=ID(stored=True),
                content=TEXT(stored=True, analyzer=StemmingAnalyzer()))

        index_dir = os.path.join(self.path, "index")
        
        if exists_in(os.path.join(self.path, "index"), indexname="urtext"):
            self.ix = open_dir(os.path.join(self.path, "index"), indexname="urtext")

        # if os.path.exists(os.path.join(self.path, "save.p")):
        #     self.log_item('Loading project from pickle')
        #     saved_state = pickle.load(open( os.path.join(self.path, "save.p"), "rb" ) )
           
        #     self.nodes = saved_state.nodes
        #     self.files = saved_state.files
        #     self.tagnames = saved_state.tagnames
        #     self.settings = saved_state.settings
        #     self.dynamic_nodes = saved_state.dynamic_nodes
        #     self.alias_nodes = saved_state.alias_nodes
                
        #     self.executor.submit(self._initialize_project, import_project=import_project, init_project=init_project) 
        
        self._initialize_project(import_project=import_project, init_project=init_project)
        self.loaded = True
    
    def _initialize_project(self, 
        import_project=False, 
        init_project=False):

        # Files

        filelist = os.listdir(self.path)
        
        for file in filelist:
            if self.filter_filenames(file) == None:
                continue            
            self._parse_file(file)
        
        if import_project:
            for file in self.to_import:
                self.import_file(file)

        if self.nodes == {}:
            if init_project == True:
                self.log_item('Initalizing a new Urtext project in ' + self.path)
            else:
                raise NoProject('No Urtext nodes in this folder.')

        self.default_timezone = timezone(self.settings['timezone'][0])
        # must be done once manually on project init
        for node_id in list(self.nodes):  
            self.parse_meta_dates(node_id)

        self.compile()
        
        self.build_alias_trees()  
        self.rewrite_recursion()                
        self.update_node_list()
        self.update_metadata_list()

        self.compiled = True
        
        self._update()

    def node_id_generator(self):
        chars = [
            '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'a', 'b', 'c',
            'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p',
            'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z'
        ]
        return itertools.product(chars, repeat=3)

    def _update(self, 
        compile_project=True, 
        update_lists=True,
        modified_files=[]):

        """ 
        Main method to keep the project updated. 
        Should be called whenever file or directory content changes
        """

        # Build copies of trees wherever there are Node Pointers (>>)
        self.build_alias_trees()  

        self.rewrite_recursion()

        if compile_project:
            modified_files = self.compile(modified_files=modified_files)
                
        self.update_node_list()
        self.update_metadata_list()

        pickle = PickledUrtextProject(self)
        
        return modified_files

    def _parse_file(self, 
        filename,
        re_index=False,
        ):
    
        if self.filter_filenames(os.path.basename(filename)) == None:
            return

        # clear all node_id's defined from this file in case the file has changed
        if os.path.basename(filename) in self.files:
            self.remove_file(os.path.basename(filename))

        """
        Parse the file
        """
        new_file = UrtextFile(os.path.join(self.path, filename))
        if not new_file.nodes: 
            self.to_import.append(filename)
            return

        """
        re-add the filename and all its nodes to the project
        """
        
        self.files[new_file.basename] = new_file
        for node_id in new_file.nodes:
            if self.is_duplicate_id(node_id, filename):
                self.remove_file(new_file.basename)
                return
            self.add_node(new_file.nodes[node_id])
        
        """
        If this is not the initial load of the project, parse the timestamps in the file
        """
        if self.compiled:
            for node_id in new_file.nodes:
                self.parse_meta_dates(node_id)
        
        self.set_tree_elements(new_file.basename)

        for node_id in new_file.nodes:
            self.rebuild_node_tag_info(node_id)

        if re_index:
            self.re_search_index_file(filename)

        return filename

    def rewrite_titles(self,filename):
        
        original_contents = self.full_file_contents(filename=filename)
        new_contents = original_contents
        matches = re.findall(title_marker_regex, new_contents)
        if matches:
            for match in matches:
                node_id = match[-3:]
                if node_id in self.nodes:
                    title = self.nodes[node_id].title
                else:
                    title = ' ? '
                bracket = '>'
                if re.search(node_pointer_regex, match):
                    bracket += '>'
                new_contents = new_contents.replace(match, '| '+title+' '+bracket+node_id)
        if new_contents != original_contents:
            return new_contents 

        return False

    """
    Tree building
    """
    def set_tree_elements(self, filename):
        """ Builds tree elements within the file's nodes, after the file is parsed."""

        parsed_items = self.files[filename].parsed_items
        positions = sorted(parsed_items.keys())

        for index in range(len(positions)):

            position = positions[index]

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

                    if self.is_in_node(position, other_node):
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
    
    def _add_sub_tags(self, 
        source_id, # ID containing the instruction
        target_id, # ID to tag
        tag, 
        value, 
        recursive=False):

        if source_id not in self.dynamic_tags:
            self.dynamic_tags[source_id] = []

        children = self.nodes[target_id].tree_node.children
        for child in children:
            self.nodes[child.name].metadata.set_tag(
                tag, 
                value, 
                from_node=source_id)
            self.dynamic_tags[source_id].append(target_id)
            self.rebuild_node_tag_info(child.name)
            if recursive:
                self.add_sub_tags(
                    source_id,
                    child.name,
                    tag,
                    value,
                    recursive=recursive)

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

        if len(new_node.metadata.get_tag('ID')) > 1:
            self.log_item('Multiple ID tags in >' + new_node.id +
                          ', using the first one found.')
        
        self.nodes[new_node.id] = new_node
        if new_node.project_settings:
            self.get_settings_from(new_node)

    def parse_meta_dates(self, node_id):
        """ Parses dates (requires that timestamp_format already be set) """

        for entry in self.nodes[node_id].metadata.entries:
            if entry.dtstring:
                dt_stamp = self.date_from_timestamp(entry.dtstring) 
                if dt_stamp:
                    self.nodes[node_id].metadata.dt_stamp = dt_stamp
                    if entry.tag_name == 'timestamp':
                        self.nodes[node_id].date = dt_stamp
                else:
                    self.log_item('Timestamp ' + entry.dtstring +
                                  ' not in any specified date format in >' +
                                  node_id)

    def date_from_timestamp(self, datestamp_string):
        dt_stamp = None
        for this_format in self.settings['timestamp_format']:
            try:
                dt_stamp = datetime.datetime.strptime(datestamp_string, '<' + this_format + '>')
                if dt_stamp.tzinfo == None:
                    dt_stamp = self.default_timezone.localize(dt_stamp) 
                return dt_stamp                
            except:
                continue
        return None


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

    """
    Compiling dynamic nodes
    """
    def compile(self, skip_tags=False, modified_files=[]):
        """ Main method to compile dynamic nodes from their definitions """

        for target_id in list(self.dynamic_nodes):

            source_id = self.dynamic_nodes[target_id].source_id
            if target_id not in self.nodes:
                self.log_item('Dynamic node definition >' + source_id +
                              ' points to nonexistent node >' + target_id)
                continue

            filename = self.nodes[target_id].filename
            self._parse_file(filename)
            self._update(compile_project=False)

            if target_id not in self.dynamic_nodes:
                print('dynamic node list has changed ,skipping '+target_id)
                continue

            dynamic_definition = self.dynamic_nodes[target_id]

            new_node_contents = ''

            if dynamic_definition.tree and dynamic_definition.tree in self.nodes:
                new_node_contents += self.show_tree_from(dynamic_definition.tree)

            if dynamic_definition.interlinks and dynamic_definition.interlinks in self.nodes:
                new_node_contents += self.get_node_relationships(
                    dynamic_definition.interlinks,
                    omit=dynamic_definition.omit)

            if dynamic_definition.mirror and dynamic_definition.mirror in self.nodes:
                if dynamic_definition.mirror_include_all:
                    # TODO prevent nodes being repeatedly mirrored inside themselves.
                    start = self.nodes[dynamic_definition.mirror].ranges[0][0]
                    end = self.nodes[dynamic_definition.mirror].ranges[-1][1]
                    new_node_contents += self.full_file_contents(node_id=dynamic_definition.mirror)[start:end]
                    new_node_contents = UrtextNode.strip_metadata(contents=new_node_contents)
                    new_node_contents = UrtextNode.strip_dynamic_definitions(contents=new_node_contents)
                    new_node_contents = new_node_contents.replace('{{','')
                    new_node_contents = new_node_contents.replace('}}','')
                else:
                    new_node_contents += self.nodes[dynamic_definition.mirror].content_only()

            if dynamic_definition.export:
                
                exported = UrtextExport(self) 
                exported_content = exported.export_from(
                     dynamic_definition.export_source,
                     kind=dynamic_definition.export
                    )

                if dynamic_definition.export_to == 'file':
                    with open(os.path.join(self.path, dynamic_definition.destination), 'w', encoding ='utf-8') as f:
                        f.write(exported_content)
                        f.close()

                if dynamic_definition.export_to == 'node' and dynamic_definition.destination in self.nodes:
                    new_node_contents = exported_content

            if dynamic_definition.tag_all_key and skip_tags:
                continue

            if dynamic_definition.tag_all_key and not skip_tags:
        
                self._add_sub_tags(
                    source_id,
                    target_id, 
                    dynamic_definition.tag_all_key, 
                    dynamic_definition.tag_all_value, 
                    recursive=dynamic_definition.recursive)                    
                self.compile(skip_tags=True)
                continue
                

            else:
                # list of explicitly included node IDs
                included_nodes = []

                # list of explicitly excluded node IDs
                excluded_nodes = []

                # list of the nodes indicated by ALL the key/value pairs for AND inclusion
                included_nodes_and = []

                # for all AND key/value pairs in the dynamic definition   

                for and_group in dynamic_definition.include_and:

                    this_and_group = []

                    for pair in and_group:
                        
                        key, value = pair[0], pair[1]

                        # if the key/value pair is in the project
                        if key in self.tagnames and value in self.tagnames[key]:

                            # add its nodes to the list of possibly included nodes as its own set
                            this_and_group.append(set(self.tagnames[key][value]))
                            #included_nodes_and.append(set(self.tagnames[key][value]))

                        else:
                            # otherwise, this means no nodes result from this AND combination
                            this_and_group = []
                            break
 
                    if this_and_group:
 
                        included_nodes.extend(
                            list(set.intersection(*this_and_group))
                            )

                for and_group in dynamic_definition.exclude_and:

                    this_and_group = []

                    for pair in and_group:
                        
                        key, value = pair[0], pair[1]

                        # if the key/value pair is in the project
                        if key in self.tagnames and value in self.tagnames[key]:

                            # add its nodes to the list of possibly included nodes as its own set
                            this_and_group.append(set(self.tagnames[key][value]))
                            #included_nodes_and.append(set(self.tagnames[key][value]))

                        else:
                            # otherwise, this means no nodes result from this AND combination
                            this_and_group = []
                            break
 
                    if this_and_group:
 
                        excluded_nodes.extend(
                            list(set.intersection(*this_and_group))
                            )

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
                    
                    if key in self.tagnames and value in self.tagnames[key]:
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
                    if dynamic_definition.sort_tagname:

                        if dynamic_definition.sort_tagname == 'timestamp':
                            included_nodes = sorted(
                                included_nodes,
                                key = lambda node: node.date,
                                reverse=dynamic_definition.reverse)

                        elif dynamic_definition.sort_tagname == 'title':
                            included_nodes = sorted(
                                included_nodes,
                                key = lambda node: node.title.lower(),
                                reverse=dynamic_definition.reverse)

                        else:
                            included_nodes = sorted(
                                included_nodes,
                                key = lambda node: node.metadata.get_first_tag(
                                    dynamic_definition.sort_tagname).lower(),
                                reverse=dynamic_definition.reverse)

                    else:
                        included_nodes = sorted(
                            included_nodes,
                            key = lambda node: node.date,
                            reverse = dynamic_definition.reverse
                            )

                    for targeted_node in included_nodes:

                        if dynamic_definition.show == 'title':
                             new_node_contents += ''.join([ 
                                targeted_node.title,
                                ' >',
                                targeted_node.id,
                                '\n'
                                ]) 
                        if dynamic_definition.show == 'full_contents':
                            new_node_contents += '| '+targeted_node.title + ' >'+targeted_node.id + '\n'
                            new_node_contents += ' - - - - - - - - - - - - - - - -\n'
                            new_node_contents += targeted_node.content_only().strip('\n').strip() + '\n'
            """
            add metadata to dynamic node
            """

            metadata_values = { 
                'ID': [ target_id ],
                'defined in' : [ '>'+dynamic_definition.source_id ] }

            if dynamic_definition.mirror:
                metadata_values['mirrors'] = '>'+dynamic_definition.mirror

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

            changed_file = self.set_node_contents(target_id, updated_node_contents)
            if changed_file:
                if changed_file not in modified_files:
                    modified_files.append(changed_file)
                self._parse_file(changed_file)
                self._update(compile_project=False)
     
        return modified_files

    def export_nodes(self, node_list, args):
        if isinstance(node_list, str):
            node_list = [node_list]
        pass

    def export_file (self, filename, args):
        pass

    def export_from_root_node(self, root_node_id):
        export = UrtextExport(self)
        #contents = export.from_root_id(root_node_id)
        contents = export.export_from(
            root_node_id, 
            kind='plaintext',
            as_single_file=True)
        return contents
    
    def export_project(self, args):
        pass 

    def set_node_contents(self, node_id, contents):
        """ project-aware alias for the Node set_content() method """
        content_changed = self.nodes[node_id].set_content(contents)
        if content_changed:
            self._parse_file(self.nodes[node_id].filename)
            return self.nodes[node_id].filename
        return False

    """
    Refreshers
    """
    def update_node_list(self):
        """ Refreshes the Node List file, if it exists """
        if 'zzz' in self.nodes:
            node_list_file = self.nodes['zzz'].filename
            contents = self.list_nodes() + '/--\nid:zzz\ntitle: Node List\n--/'
            self.set_node_contents('zzz', contents)

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
            contents = ''           
            for pre, _, node in RenderTree(root):
                contents += "%s%s\n" % (pre, node.name)
            contents += '/--\nid:zzy\ntitle: Metadata List\n--/'
            self.set_node_contents('zzy', contents)
    """
    Metadata
    """
    def tag_other_node(self, node_id, tag_contents):
        """adds a metadata tag to a node programmatically"""

        timestamp = self.timestamp(datetime.datetime.now())
        territory = self.nodes[node_id].ranges
        
        full_file_contents = self.full_file_contents(node_id=node_id)
        tag_position = territory[-1][1]
        if tag_position < len(full_file_contents) and full_file_contents[tag_position] == '%':
             tag_contents += '\n' # keep split markers as the first character on new lines

        new_contents = full_file_contents[:tag_position] + tag_contents + full_file_contents[tag_position:]

        self.set_file_contents(self.nodes[node_id].filename, new_contents)
        return self.on_modified(os.path.join(self.path, self.nodes[node_id].filename))

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
        self._parse_file(filename)

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
                for value in entry.values:
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

        return self._parse_file(filename)

    def get_node_relationships(self, 
        node_id, 
        omit=[]):

        return Interlinks(self, 
            node_id, 
            omit=omit).render_tree()

    """
    Removing and renaming files
    """
    def remove_file(self, filename):
    
        if filename in self.files:
            for node_id in self.files[filename].nodes:
                for target_id in list(self.dynamic_nodes):
                    if self.dynamic_nodes[target_id].source_id == node_id:
                        del self.dynamic_nodes[target_id]

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
                if node_id in self.dynamic_tags:
                    for target_id in self.dynamic_tags[node_id]:
                        if target_id in self.nodes:
                            self.nodes[target_id].metadata.remove_dynamic_tags_from_node(node_id)

            del self.files[filename]

        return None

    def delete_file(self, filename):
    	  
        self.remove_file(os.path.basename(filename))
        os.remove(os.path.join(self.path, filename))
        future = self.executor.submit(self._update) 

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
        if 'urtext_log' in filename:
            return None
        if not filename.endswith('.txt'):
            # FUTURE:
            # save and check these in an optional list of other extensions 
            # set from project_settings 
            return None
        """ Omit the log file """
        skip_files = [self.settings['logfile'][0]]
        if filename in skip_files:
            return None

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
        self._parse_file(filename)
        return { 
                'filename':filename, 
                'id':node_id
                }
 
    def add_inline_node(self, 
            date=None, 
            contents='', 
            metadata={},
            one_line=False,
            include_timestamp=False):
            
        if contents == '':
            contents = ' '
        
        node_id = self.next_index()
        metadata['id']=node_id
        if include_timestamp:
            if date == None:
                date = datetime.datetime.now()
            metadata['timestamp'] = self.timestamp(date)
        new_node_contents = "{{ " + contents 
        metadata_block = build_metadata(metadata, one_line=one_line)
        new_node_contents += metadata_block + " }}"
        metadata={}
        return (new_node_contents, node_id)

    def insert_interlinks(self, node_id, one_line=True):
        new_node = self.add_inline_node()
        insertion = new_node[0]
        new_node_id = new_node[1]
        dynamic_def =   '[[ id:'+ new_node_id +'; '
        dynamic_def +=  'interlinks:'+node_id
        dynamic_def += ' ]]'

        return '\n'.join([insertion, dynamic_def])

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
        """ 
        sorts all file-level nodes by their index, then passes
        the result to rename_file_nodes() to rename them.
        """

        # Calculate the required zero-padded digit length for the file prefix:
        prefix = 0
        
        # this should actually just be the first root node, not all root nodes.
        remaining_primary_root_nodes = list(self.root_nodes(primary=True))

        indexed_nodes = list(self.indexed_nodes())
        for node_id in indexed_nodes:
            if node_id in remaining_primary_root_nodes:
                self.nodes[node_id].prefix = prefix
                remaining_primary_root_nodes.remove(node_id)
                prefix += 1

        unindexed_root_nodes = [self.nodes[node_id] for node_id in remaining_primary_root_nodes]
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

            ## Name each file from the first root_node
            root_node_id = self.files[old_filename].root_nodes[0]
            root_node = self.nodes[root_node_id]

            # start with the filename template, replace each element
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
        return last_node

    def nav_current(self):
        if not self.check_nav_history():
            return None
        if self.nav_index in self.navigation:
            return self.navigation[self.nav_index]
        return None

    def check_nav_history(self):

        if len(self.navigation) == -1:
            self.log_item('There is no nav history')
            return None

        return True

    """ 
    Cataloguing Nodes
    """

    def list_nodes(self):
            
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

        #self.update_lock.acquire()
        indexed_nodes_list = []
        for node_id in list(self.nodes):
            if self.nodes[node_id].metadata.get_tag('index') != []:
                indexed_nodes_list.append([
                    node_id,
                    int((self.nodes[node_id].metadata.get_first_tag('index')))
                ])
        sorted_indexed_nodes = sorted(indexed_nodes_list,
                                      key=lambda item: item[1])
        for i in range(len(sorted_indexed_nodes)):
            sorted_indexed_nodes[i] = sorted_indexed_nodes[i][0]
        #self.update_lock.release()   
        return sorted_indexed_nodes

    def root_nodes(self, primary=False):
        """
        Returns the IDs of all the root (file level) nodes
        """
        root_nodes = []        
        for filename in self.files:
            if not primary:
                root_nodes.extend(self.files[filename].root_nodes)
            else:
                root_nodes.append(self.files[filename].root_nodes[0])
        return root_nodes
    

    def rebuild_search_index(self):
        
        self.ix = create_in(os.path.join(self.path, "index"),
                            schema=self.schema,
                            indexname="urtext")

        self.writer = AsyncWriter(self.ix)

        for filename in self.files:
            self.re_search_index_file(filename, single=False)
                                
        self.writer.commit()

    def re_search_index_file(self, filename, single=True):
        
        if not self.ix:
            return

        if single:
            self.writer = AsyncWriter(self.ix)

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

    
    
    def get_parent(self, child_node_id):
        """ Given a node ID, returns its parent, if any """
        
        filename = self.nodes[child_node_id].filename
        start_of_node = self.nodes[child_node_id].ranges[0][0]
        distance_back = 1
        
        parent_node = self.get_node_id_from_position(filename, start_of_node - distance_back)
        while not parent_node and distance_back < start_of_node:
            distance_back += 1
            parent_node = self.get_node_id_from_position(filename, start_of_node - distance_back)

        while self.nodes[child_node_id].split and not self.nodes[child_node_id].compact and self.nodes[parent_node].split :
            if self.nodes[parent_node].root_node:
                break
            parent_node = self.get_parent(parent_node)

        return parent_node

    def is_in_node(self, position, node_id):
        """ Given a position, and node_id, returns whether the position is in the node """
        for this_range in self.nodes[node_id].ranges:
           
            if position >= this_range[0] and position <= this_range[1]:
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
            return ('HTTP', url)
        link = None
        # first try looking around where the cursor is positioned
        for index in range(0, 4):
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
            return ('NODE', node_id, file_position)
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

        if date.tzinfo == None:
            date = self.default_timezone.localize(date)             
        timestamp_format = '<' + self.settings['timestamp_format'][0] + '>'
        return date.strftime(timestamp_format)

    def get_settings_from(self, node):
        for entry in node.metadata.entries:
            self.settings[entry.tag_name.lower()] = entry.values
        if 'project_title' in self.settings:
            self.title = self.settings['project_title'][0]
        self.default_timezone = timezone(self.settings['timezone'][0])

    def get_home(self):
        if self.settings['home']:
            return self.settings['home'][0]
        return None

    def get_file_name(self, node_id):
        if node_id in self.nodes:
            return self.nodes[node_id].filename
        return None

    def next_index(self):
        index = random.choice(list(self.node_id_generator()))
        while ''.join(index) in self.nodes:
            index = random.choice(list(self.node_id_generator()))
        return ''.join(index)

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

    def pop_node(self, position=None, filename=None, node_id=None):
        if not node_id:
            node_id = self.get_node_id_from_position(filename, position)
        if not node_id:
            return
        if self.nodes[node_id].root_node:
            print(node_id + ' is already a root node.')
            return None

        start = self.nodes[node_id].ranges[0][0]
        end = self.nodes[node_id].ranges[-1][1]

        file_contents = self.full_file_contents(node_id=node_id)
        
        popped_node_id = node_id

        filename = self.nodes[node_id].filename
        popped_node_contents = file_contents[start:end].strip()
        
        if self.nodes[node_id].split:
            popped_node_contents = popped_node_contents[1:] # strip the '%'

        if self.nodes[node_id].compact:
            # Strip whitspace + '^'
            popped_node_contents = popped_node_contents.lstrip()
            popped_node_contents = popped_node_contents[1:]

        remaining_node_contents = ''.join([
            file_contents[0:start - 2],
            '\n',
            '>>',
            popped_node_id,
            '\n',
            file_contents[end + 2:]])

        with open (os.path.join(self.path, filename), 'w', encoding='utf-8') as f:
            f.write(remaining_node_contents)
            f.close()

        self._parse_file(filename)

        with open(os.path.join(self.path, popped_node_id+'.txt'), 'w',encoding='utf-8') as f:
            f.write(popped_node_contents)
            f.close()

        self._parse_file(popped_node_id+'.txt')
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

    def random_node(self):
        node_id = random.choice(list(self.nodes))
        return node_id


    """
    Methods used with watchdog
    """

    def on_created(self, filename):
        unlocked, lock_name = self.check_lock()
        if not unlocked:
            return (False, lock_name)
        if os.path.isdir(filename):
            return (True,'')
        filename = os.path.basename(filename)
        if filename in self.files:
            return (True,'')
        self._parse_file(filename, re_index=True)
        self.log_item(filename +' modified. Updating the project object')
        self.update()
        return (True,'')

    def on_modified(self, 
            filename,
            watchdog=False):
    
        if watchdog:
            unlocked, lock_name = self.check_lock()
            if not unlocked:
                return (False, lock_name)
        do_not_update = [
            'index', 
            os.path.basename(self.path),
            self.settings['logfile'],
            ]

        for node_id in ['zzz','zzy']:
            if node_id in self.nodes:
               do_not_update.append(self.nodes[node_id].filename)
        filename = os.path.basename(filename)
        if filename in do_not_update or '.git' in filename:
            return (True,'')
        
        self.log_item('MODIFIED ' + filename +' - Updating the project object')
        return self.executor.submit(self.file_update, filename)
         
        
    def file_update(self, filename):
        rewritten_contents = self.rewrite_titles(filename)
        modified_files = []
        if rewritten_contents:
            self.set_file_contents(filename, rewritten_contents)
            modified_files.append(filename)     
        self._parse_file(filename, re_index=True)        
        return self._update(modified_files=modified_files)

    def on_moved(self, filename):
        unlocked, lock_name = self.check_lock()
        if not unlocked:
            return (False, lock_name)
        old_filename = os.path.basename(filename)
        new_filename = os.path.basename(filename)
        if old_filename in self.files:
            self.log.info('RENAMED ' + old_filename + ' to ' +
                                    new_filename)
            self.handle_renamed(old_filename, new_filename)
        return (True,'')

class NoProject(Exception):
    """ no Urtext nodes are in the folder """
    pass

class PickledUrtextProject:

    def __init__(self, project):
        
        self.nodes = project.nodes
        self.files = project.files
        self.tagnames = project.tagnames
        self.settings = project.settings
        self.dynamic_nodes = project.dynamic_nodes
        self.alias_nodes = project.alias_nodes
        pickle.dump( self, open( os.path.join(project.path, "save.p"), "wb" ) )

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

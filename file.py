# -*- coding: utf-8 -*-
"""
This file is part of Urtext.

Urtext is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Urtext is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Urtext.  If not, see <https://www.gnu.org/licenses/>.

"""
import os
import re
from .node import UrtextNode
from . import node
from whoosh.writing import AsyncWriter
import concurrent.futures
from concurrent.futures import ALL_COMPLETED
import hashlib

node_id_regex =         r'\b[0-9,a-z]{3}\b'
node_link_regex =       r'>[0-9,a-z]{3}\b'
node_pointer_regex =    r'>>[0-9,a-z]{3}\b'
compact_node_regex =    '\^[^\n]*'

compiled_symbols = [re.compile(symbol) for symbol in  [
    '{{', # inline node opening wrapper
    '}}', # inline node closing wrapper
    '>>', # node pointer
    '[\n$]',    # line ending (closes compact node)
    ]]

# additional symbols using MULTILINE flag
compiled_symbols.extend( [re.compile(symbol, re.M) for symbol in [
    '^[^\S\n]*\^',  # compact node opening wrapper
    '^\%[^%]'       # split node marker
    ] ])

# number of positions to advance parsing for of each possible symbol
symbol_length = {   
    '^[^\S\n]*\^':  0, # compact node opening wrapper
    '{{' :          2, # inline opening wrapper
    '}}' :          2, # inline closing wrapper
    '>>' :          2, # node pointer
    '[\n$]' :       0, # compact node closing
    '^\%[^%]' :     0,  # split node opening
    'EOF':          0,
}

class UrtextFile:

    def __init__(self, filename, previous_hash=None, search_index=None):
        
        self.nodes = {}
        self.root_nodes = []
        self.filename = filename
        self.anonymous_nodes = []
        self.basename = os.path.basename(filename)        
        self.parsed_items = {}
        self.search_index_updates = []
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=10)
        self.search_index = search_index
        self.changed = True
        self.is_parseable = True
        
        contents = self.get_file_contents()        
        self.hash = self.hash_contents(contents)
        if self.hash == previous_hash:
            self.changed = False
            pass
        else:
            if self.search_index:
                self.search_index.refresh()
                self.writer = AsyncWriter(self.search_index)
            self.lex_and_parse(contents, search_index=self.search_index)
        
    def lex_and_parse(self, contents, search_index=None):
        if not contents:
            return
        self.file_length = len(contents)        
        self.lex(contents)
        self.parse(contents, search_index=search_index)

    def hash_contents(self, contents):
        r = bytearray(contents,'utf-8')
        md5 = hashlib.md5()
        md5.update(r)
        return md5.digest()

    def lex(self, contents):
        """ populate a dict syntax symbols """
        self.symbols = {}

        for compiled_symbol in compiled_symbols:
            locations = compiled_symbol.finditer(contents)
            for loc in locations:
                start = loc.span()[0]
                self.symbols[start] = compiled_symbol.pattern

        self.positions = sorted([key for key in self.symbols if key != -1])

    def parse(self, contents, search_index=None):

        """
        Counters and trackers
        """
        nested = 0  # tracks depth of node nesting
        nested_levels = {} # store node nesting into layers
        last_position = 0  # tracks the most recently parsed position in the file
        compact_node_open = False
        split = False
        last_node_was_split = False

        """
        Trim leading symbols that are newlines or node pointers
        """

        if self.positions:
            while self.positions and self.symbols[self.positions[0]] in [ '[\n$]', '>>' ]:
                self.positions.pop(0)

        if self.positions:
            nested_levels[0] = [ [0, self.positions[0] + symbol_length[self.symbols[self.positions[0]]] ] ]

        self.positions.append(len(contents))
        self.symbols[len(contents)] = 'EOF'

        for index in range(0, len(self.positions)):

            position = self.positions[index]
            
            # Allow node nesting arbitrarily deep
            nested_levels[nested] = [] if nested not in nested_levels else nested_levels[nested]
            
            """
            If this opens a new node
            """
            if self.symbols[position] == '{{':

                # begin tracking the ranges of the next outer one
                if [last_position, position + 2] not in nested_levels[nested]:
                    nested_levels[nested].append([last_position, position + 2])

                # add another level of depth
                nested += 1 

                # move the parsing pointer forward 2
                last_position = position + 2
                continue

            """
            If this points to an outside node, find which node
            """
            if self.symbols[position] == '>>':
                
                # Find the contents of the pointer 
                node_pointer = contents[position:position + 5]
                
                # If it matches a node regex, add it to the parsed items
                if re.match(node_pointer_regex, node_pointer):
                    self.parsed_items[position] = node_pointer

                continue

            """
            If the symbol opens a compact node
            """
            if self.symbols[position] == '^[^\S\n]*\^': 
                # TODO - FIGURE OUT WHY ADDING + 1 to these positions to correct the 
                # parsing causes exporting to skip entire regions
                if [last_position, position  ] not in nested_levels[nested] and position  > last_position:
                    nested_levels[nested].append([last_position, position ])
                nested += 1 
                last_position = position + 1
                compact_node_open = True
                continue    

            """
            Node closing symbols :  }}, %, newline, EOF
            """
            if self.symbols[position] in ['}}', '^\%(?!%)', '[\n$]', 'EOF']:  # pop
                
                compact, root = False, False

                if self.symbols[position] == '[\n$]':
                    if compact_node_open:
                        compact = True
                        compact_node_open = False   
                    else:
                        continue

                if [last_position, position] not in nested_levels[nested]: # avoid duplicates
                    nested_levels[nested].append([last_position, position ])
                
                # determine whether this is a node made by a split marker (%)
                start_position = nested_levels[nested][0][0]
                end_position = nested_levels[nested][-1][1]         
                if start_position >= 0 and contents[start_position] == '%':
                    split = True
                if end_position < len(contents) and contents[end_position] == '%':
                    split = True
                
                # file level nodes are root nodes, with multiples permitted  
                if nested == 0 or self.symbols[position] == 'EOF':
                    # use most recent value; if previous closed node is split, this is split.
                    split = last_node_was_split 
                    root = True
                    if nested != 0:
                        #TODO -- if a compact node closes the file, this error will be thrown.
                        self.log_error('Missing closing wrapper', position)
                        return None

                # Build the node contents and construct the node
                node_contents = ''.join([  
                        contents[file_range[0]:file_range[1]] 
                            for file_range in nested_levels[nested] 
                        ])
       
                new_node = node.create_urtext_node(
                    self.filename, 
                    contents=node_contents,
                    root=root,
                    split=split,
                    compact=compact,
                    )
                
                if not self.add_node(new_node, nested_levels[nested], node_contents):
                    if root:
                        return self.log_error('Root node without ID', 0)
                    if compact:
                        print ('Compact Node symbol without ID at %s in %s. Continuing to add the file.' % (position,self.filename))     
                    else:
                        return self.log_error('Node missing ID', position)
 
                del nested_levels[nested]
                last_position = position + symbol_length[self.symbols[position]]

                if split: # split nodes
                    last_node_was_split = True
                    continue

                last_node_was_split = False
                # reduce the nesting level only for compact, inline nodes
                if not root:
                    nested -= 1                       
                if nested < 0:
                    return self.log_error('Stray closing wrapper', position)  
                
        if len(self.root_nodes) == 0:
            return self.log_error('No root nodes found', 0)
            
        if self.search_index:
            self.executor.submit(self.commit_writer)
    
    def commit_writer(self):
         concurrent.futures.wait(
            self.search_index_updates, 
            timeout=None, 
            return_when=ALL_COMPLETED) 
         self.writer.commit()
         print('Search index updated. ' + self.filename+'\n')

    def add_node(self, new_node, ranges, contents):
        if new_node.id != None and re.match(node_id_regex, new_node.id):
            self.nodes[new_node.id] = new_node
            self.nodes[new_node.id].ranges = ranges
            if new_node.root_node:
                self.root_nodes.append(new_node.id) 
            self.update_search_index(new_node, contents)
            self.parsed_items[ranges[0][0]] = new_node.id
            return True
        return False

    def get_file_contents(self):
        """ returns the file contents, filtering out Unicode Errors, directories, other errors """

        try:
            with open(
                    self.filename,
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

    def update_search_index(self, new_node, node_contents):
        if self.search_index:
            stripped_contents = UrtextNode.strip_metadata(contents=node_contents)
            stripped_contents = UrtextNode.strip_dynamic_definitions(contents=stripped_contents)
            self.search_index_updates.append(
                self.executor.submit( 
                    self.writer.update_document, 
                    title=new_node.title,
                    path=new_node.id,
                    content=stripped_contents)
                )


    def log_error(self, message, position):

        self.is_parseable = False
        self.nodes = {}
        self.parsed_items = {}
        self.root_nodes = []
        self.file_length = 0
        
        print(''.join([ 
                message, ' in ', self.filename, ' at position ',
            str(position)]))

        return None

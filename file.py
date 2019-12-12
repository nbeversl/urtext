
import os
import re
from .node import UrtextNode
from . import node

node_id_regex = r'\b[0-9,a-z]{3}\b'
node_link_regex = r'>[0-9,a-z]{3}\b'
node_pointer_regex = r'>>[0-9,a-z]{3}\b'
compact_node_regex = '\^[^\n]*'

compiled_symbols = [re.compile(symbol) for symbol in  [
    '{{', # inline node opening wrapper
    '}}', # inline node closing wrapper
    '>>', # node pointer
    '\n',
    ] ]
compiled_symbols.extend( [re.compile(symbol, re.M) for symbol in [
    '^[ ]*\^',           # compact node opening wrapper
    '^\%(?!%)'          # split node marker
    ] ])

symbol_length = {
    '^[ ]*\^':1,
    '{{' : 2,
    '}}' : 2,
    '>>' : 2,
    '\n' : 1,
    '^\%(?!%)' : 1
}

class UrtextFile:

    def __init__(self, filename):
        
        self.nodes = {}
        self.root_nodes = []
        self.filename = filename
        self.basename = os.path.basename(filename)        
        self.parsed_items = {}
        self.lex_and_parse()

    def lex_and_parse(self):
        contents = self.get_file_contents()
        if not contents:
            return
        self.file_length = len(contents)
        self.lex(contents)
        self.parse(contents)

    def lex(self, contents):
        """ locate syntax symbols """
        self.symbols = {}

        for compiled_symbol in compiled_symbols:
            locations = compiled_symbol.finditer(contents)
            for loc in locations:
                start = loc.span()[0]
                self.symbols[start] = compiled_symbol.pattern

        self.positions = sorted([key for key in self.symbols.keys() if key != -1])

    def parse(self, contents):

        """
        Counters and trackers
        """
        nested = 0  # tracks depth of node nesting
        nested_levels = {}
        last_position = 0  # tracks the most recently parsed position in the file
        compact_node_open = False
        split = False
        
        """
        If there are node syntax symbols in the file,
        find the first non-newline symbol. Newlines are significant
        only if a compact node is open.
        """
        if self.positions:

            non_newline_symbol = 0
            while self.symbols[self.positions[non_newline_symbol]] == '\n':
                non_newline_symbol += 1
                if non_newline_symbol == len(self.positions):
                    break
            if non_newline_symbol < len(self.positions):
                nested_levels[0] = [
                    [0, self.positions[non_newline_symbol] + symbol_length[self.symbols[self.positions[non_newline_symbol]]
                    ]]
                    ]
                           
        for index in range(non_newline_symbol, len(self.positions)):

            position = self.positions[index]

            # Allow node nesting arbitrarily deep
            nested_levels[nested] = [] if nested not in nested_levels else nested_levels[nested]
            
            # If this opens a new node
            if self.symbols[position] == '{{':

                # begin tracking the ranges of the next outer one
                if [last_position, position + 2] not in nested_levels[nested]:
                    nested_levels[nested].append([last_position, position + 2])

                # add another level of depth
                nested += 1 

                # move the parsing pointer forward
                last_position = position + 2
                continue

            # If this points to an outside node, find which node
            if self.symbols[position] == '>>':
                
                # Find the contents of the pointer 
                node_pointer = contents[position:position + 5]
                
                # If it matches a node regex, add it to the parsed items
                if re.match(node_pointer_regex, node_pointer):
                    self.parsed_items[position] = node_pointer

                continue

            if self.symbols[position] == '^[ ]*\^':
                if [last_position, position + 1] not in nested_levels[nested]:
                    nested_levels[nested].append([last_position, position + 1])
                nested += 1 
                last_position = position + 1
                compact_node_open = True
                continue
                
            if self.symbols[position] == '\n' and compact_node_open:
                # TODO: this could be refactored with what is below
                
                if [last_position, position] not in nested_levels[nested]: # avoid duplicates
                    nested_levels[nested].append([last_position, position])

                compact_node = node.create_urtext_node(
                    self.filename, 
                    contents=''.join([  
                        contents[file_range[0]:file_range[1]] 
                            for file_range in nested_levels[nested] 
                        ])[1:].strip(), # omit the leading/training whitespace and the '^' character itself:
                    compact = True)

                compact_node_open = False
                
                if not self.add_node(
                    compact_node, # node
                    nested_levels[nested] # ranges
                    ):
                    print ('Compact Node symbol without ID at %s in %s. Continuing to add the file.' % (position,self.filename))
                
                else:
                    self.parsed_items[nested_levels[nested][0][0]] = compact_node.id
                
                del nested_levels[nested]
                nested -= 1
                last_position = position + 1
                if nested < 0:
                    return self.log_error('Stray closing wrapper', position)  
                continue

            # If this closes a node:
            if self.symbols[position] in ['}}', '^\%(?!%)']:  # pop

                # TODO why is this if necessary?
                if [last_position, position] not in nested_levels[nested]: # avoid duplicates
                    nested_levels[nested].append([last_position, position])
            
                # file level nodes are root nodes, with multiples permitted
                root = True if nested == 0 else False

                split = False

                # determine whether this is a node made by a split marker (%)
                start_position = nested_levels[nested][0][0]
                end_position = nested_levels[nested][-1][1]

                # TODO this method of checking for split node may be problematic?? 
                # Will an inline node ever get falsely called a split node?
                if contents[start_position-1] == '%' or contents[end_position+1] == '%':
                    split = True
                                
                node_contents = ''.join([  
                        contents[file_range[0]:file_range[1]] 
                            for file_range in nested_levels[nested] 
                        ])

                # Get the node contents and construct the node
                new_node = node.create_urtext_node(
                    self.filename, 
                    contents=node_contents,
                    root=root,
                    split=split)
                
                if not self.add_node(new_node, nested_levels[nested]):
                    return self.log_error('Node missing ID', position)

                self.parsed_items[nested_levels[nested][0][0]] = new_node.id

                del nested_levels[nested]

                if self.symbols[position] == '^\%(?!%)':
                    last_position = position + 1  # overwrite from above
                    continue
                
                last_position = position + 2

                nested -= 1

                if nested < 0:
                    return self.log_error('Stray closing wrapper', position)  
                
        if nested != 0:
            self.log_error('Missing closing wrapper', position)
            return None

        ### handle last (lowest) remaining node at the file level
        
        if nested_levels == {} or nested_levels[0] == [] and last_position > 0:
            # everything else in the file is part of another node.
            nested_levels[0] = [[last_position+1, self.file_length]]
               
        elif nested_levels == {} or nested_levels[0] == []:
            # everything else in the file is other nodes.
            nested_levels[0] = [[0, self.file_length]]  
        
        elif [last_position + 1, self.file_length] not in nested_levels[0]:
            nested_levels[0].append([last_position + 1, self.file_length])

        node_contents = ''.join([contents[file_range[0]: file_range[1]] for file_range in nested_levels[0]])
        root_node = node.create_urtext_node(
            self.filename,
            contents=node_contents,
            root=True,
            split=split # use most recent value; if previous closed node is split, this is split.
            )
       
        if not self.add_node(root_node, nested_levels[0]):                
            return self.log_error('Root node without ID', 0)
        
        if len(self.root_nodes) == 0:
            print('NO ROOT NODES')
            print(self.filename)

    def add_node(self, new_node, ranges):
      
        if new_node.id != None and re.match(node_id_regex, new_node.id):
            self.nodes[new_node.id] = new_node
            self.nodes[new_node.id].ranges = ranges
            if new_node.root_node:
                self.root_nodes.append(new_node.id) 
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
        except:
            print('Urtext not including ' + self.filename)
            return None

    def log_error(self, message, position):
 
        self.nodes = {}
        self.parsed_items = {}
        self.root_nodes = []
        self.file_length = 0
        
        print(''.join([ 
                message, ' in ', self.filename, ' at position ',
            str(position)]))

        return None
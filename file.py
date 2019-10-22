import os
import re
from .node import UrtextNode

node_id_regex = r'\b[0-9,a-z]{3}\b'
node_link_regex = r'>[0-9,a-z]{3}\b'
node_pointer_regex = r'>>[0-9,a-z]{3}\b'
compact_node_regex = '\^[^\n]*'

class UrtextFile:

    def __init__(self, filename):
        
        self.nodes = {}
        self.root_nodes = {}
        self.filename = filename
        self.basename = os.path.basename(filename)        
        self.compiled_symbols = [re.compile(symbol) for symbol in ['{{', '}}', '>>', '^\s*\^', '%%'] ]
        self.parsed_items = {}
        self.length = None
        self.full_file_contents = self.get_file_contents()
        self.length = len(self.full_file_contents)
        self.parse()
        self.lex()
       
    def parse(self):
        """ locate syntax symbols """
        self.symbols = {}

        for compiled_symbol in self.compiled_symbols:
            symbol = compiled_symbol.pattern
            locations = compiled_symbol.finditer(self.full_file_contents)
            for loc in locations:
                start = loc.span()[0]
                self.symbols[start] = symbol

        self.positions = sorted([key for key in self.symbols.keys() if key != -1])
                
    def lex(self):

        """
        Counters and trackers
        """
        nested = 0  # tracks depth of node nesting
        nested_levels = {}
        last_start = 0  # tracks the most recently parsed position

        if self.positions:
            nested_levels[0] = [[0, self.positions[0]]]

        for position in self.positions:

            # Allow node nesting arbitrarily deep
            nested_levels[nested] = [] if nested not in nested_levels else nested_levels[nested]

            # If this opens a new node, track the ranges of the outer one.
            if self.symbols[position] == '{{':
                nested_levels[nested].append([last_start, position])
                nested += 1
                last_start = position + 2
                continue

            # If this points to an outside node, find which node
            if self.symbols[position] == '>>':
                node_pointer = self.full_file_contents[position:position + 5]
                if re.match(node_pointer_regex, node_pointer):
                    self.parsed_items[position] = node_pointer
                continue

            if self.symbols[position] == '^\s*\^':
                compact_node_contents = re.search(compact_node_regex, self.full_file_contents[position:]).group(0)
                compact_node = UrtextNode(self.filename, 
                    contents=compact_node_contents[1:], # omit the '^ character itself'
                    compact = True)

                if not self.add_node(compact_node, [[position + 2 , position+len(compact_node_contents)]]):
                    return self.log_error('Compact Node problem', position)
                    
                nested_levels[nested].append([last_start, position ]) 
                self.parsed_items[position] = compact_node.id
                last_start = position + len(compact_node_contents) 
                continue

            # If this closes a node:
            if self.symbols[position] in ['}}','%%']:  # pop
                nested_levels[nested].append([last_start, position])

                root = True if nested == 0 else False
                
                # Get the node contents and construct the node
                new_node = UrtextNode(
                    self.filename, 
                    contents=''.join([  
                        self.full_file_contents[file_range[0]:file_range[1]] 
                            for file_range in nested_levels[nested] 
                        ]),
                    root=root)

                if not self.add_node(new_node, nested_levels[nested]):
                    return self.log_error('Node missing ID', position)

                self.parsed_items[position] = new_node.id
                del nested_levels[nested]

                last_start = position + 2

                if self.symbols[position] == '%%':
                    nested_levels[nested] = [] if nested not in nested_levels else nested_levels[nested]
                    nested_levels[nested].append([last_start, position])
                    continue

                nested -= 1

                if nested < 0:
                    return self.log_error('Stray closing wrapper', position)  

        if nested != 0:
            self.log_error('Missing closing wrapper', position)
            return None

        ### Handle the root node:
        if nested_levels == {} or nested_levels[0] == []:
            nested_levels[0] = [[0, self.length]]  
        else:
            nested_levels[0].append([last_start + 1, self.length])

        root_node = UrtextNode(self.filename,
                               contents=''.join([
                                    self.full_file_contents[file_range[0]: file_range[1]] for file_range in nested_levels[0]]),
                               root=True)

        if not self.add_node(root_node, nested_levels[0]):
            print('Root node without ID: ' + self.filename)
            return None

        self.root_node_id = root_node.id
    

    def add_node(self, new_node, ranges):
        if new_node.id != None and re.match(node_id_regex, new_node.id):
            self.nodes[new_node.id] = new_node
            self.nodes[new_node.id].ranges = ranges
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
        error_line = self.full_file_contents[position - 50:position].split('\n')[0]
        error_line += self.full_file_contents[position:position + 50].split('\n')[0]

        print(''.join([ 
                message, ' in ', self.filename, ' at position ',
            str(position), '\n', error_line, '\n', ' ' * len(error_line), '^']))

        return None
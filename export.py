""" 
Export

These should be re-tested. 
"""
import os
import re
from .node import UrtextNode

node_link_regex = r'[^>]>[0-9,a-z]{3}\b'
OPENING_BRACKETS = '<span class="urtext-open-brackets">&#123;&#123;</span>'
node_pointer_regex = r'>>[0-9,a-z]{3}\b'
titled_link_regex = r'\|.*?[^>]>[0-9,a-z]{3}\b'
titled_node_pointer_regex =r'\|.*?>>[0-9,a-z]{3}\b'
"""
Required abilities:

"""
class UrtextExport:

    def __init__(self, project):
        self.project = project
        self.extensions  = {
            'plaintext':'.txt',
            'html' : '.html',
            'markdown' :'.md'
        }
   
    def _strip_urtext_syntax(self, contents):
        contents = UrtextNode.strip_contents(contents)
        contents = contents.replace('{{','')
        contents = contents.replace('}}','')
        contents = re.sub(r'^\%', '', contents, flags=re.MULTILINE)
        return contents        
 
    def _opening_wrapper(self, kind, node_id, nested):
        wrappers = { 
            'html': '<div class="urtext_nested_'+str(nested)+'"><a name="'+ node_id + '"></a>',
            'markdown': '',
            'plaintext': ''
            }
        return wrappers[kind]

    def _closing_wrapper(self, kind):
        wrappers = { 
            'html': '</div>',
            'markdown': '',
            'plaintext': ''
            }
        return wrappers[kind]

    def _wrap_title(self, kind, node_id, nested):
        title = self.project.nodes[node_id].title
        if title.strip() == '':
            print('NO TITLE HERE')
            print(node_id)
        wrappers = {
            'markdown': '#' * nested + ' ' + title +'\n',
            'html' : '<h'+str(nested)+'>' + title + '</h'+str(nested)+'>\n',
            'plaintext' : title,
        }
        return wrappers[kind]


    def export_from(self, 
        root_node_id, 
        as_single_file=False,
        strip_urtext_syntax=True,
        style_titles=True,
        exclude=[], 
        clean_whitespace=False,
        kind='plaintext'
        ):

        """
        Public method to export a tree of nodes from a given root node
        """
        self.visited_nodes = []
        self.mapped_positions = {}
        self.final_content = ''

        """
        Bootstrap _add_node_content() with a root node ID and then 
        return contents, recursively if specified.
        """
        exported_content, points = self._add_node_content(
            root_node_id,
            as_single_file=as_single_file,
            strip_urtext_syntax=strip_urtext_syntax,
            style_titles=style_titles,
            exclude=exclude,
            kind=kind,
            clean_whitespace=clean_whitespace
            )

        return exported_content, points

    def _add_node_content(self, 
            root_node_id,                               # node to start from
            added_contents ='',
            points = {},
            as_single_file=False,                       # Recursively add contents from node pointers?
            strip_urtext_syntax=True,                   # for HTML, strip Urtext syntax?
            style_titles=True,                          # style titles ????
            exclude=[],                                 # specify any nodes to exclude
            kind='plaintext',                           # format
            nested=0,                                   # nested level (private)
            single_node_only=False,                      # stop at this node, no inline nodes
            clean_whitespace=False,
            ):         
        """
        Recursively add nodes, its inline nodes and node pointers, in order
        from a given starting node, keeping track of nesting level, and wrapping in markup.        
        """    
       
        """
        Get and set up initial values
        """
        ranges = self.project.nodes[root_node_id].ranges
        filename = self.project.nodes[root_node_id].filename
        file_contents = self.project.full_file_contents(filename)        
        title = self.project.nodes[root_node_id].title
        split = self.project.nodes[root_node_id].split
        
        if points == {}:
            points = {0:root_node_id}

        for single_range in ranges:
            
            points[len(added_contents)] = ( root_node_id, single_range[0] ) # returns node ID and exact FILE location

            """
            If this is the node's first range:
            """
            if single_range == ranges[0]:

                if kind == 'html' and not strip_urtext_syntax:

                    # add Urtext styled {{ wrapper
                    added_contents += OPENING_BRACKETS

            """
            Get and add the range's contents
            """
            range_contents = file_contents[single_range[0]:single_range[1]]
            range_contents = self._strip_urtext_syntax(range_contents)
            
            if kind == 'html':
                """
                Insert special HTML wrappers
                """
                lines = [line.strip() for line in range_contents.split('\n') if line.strip() != '']
                index = 0
                while index < len(lines):
                    line = lines[index]

                    """
                    Insert HTML <ul><li><li></ul> tags for lists
                    """
                    if line[0] == '-':
                        range_contents += '<ul class="urtext-list">'
                        while index < len(lines) - 1:
                            range_contents += '<li>'+line[1:]+'</li>'
                            index += 1
                            line = lines[index]
                            if line[0] != '-':
                                break
                        range_contentss += '</ul>'

                    """
                    For non-list items, wrap them in a <div>
                    """
                    range_contents += '<div class="urtext_line">' + line.strip()
                    if range_contents == ranges[-1] and line == lines[-1] and not strip_urtext_syntax:
                        range_contents += '<span class="urtext-close-brackets">&#125;&#125;</span>'                
                    range_contents += '</div>\n'     
                    index += 1           
            
            """
            Wrap the title if this is the first range in the node.
            Remove duplicate titles if there is no title key.
            """  
            if single_range == ranges[0]:
                
                if not self.project.nodes[root_node_id].metadata.get_tag('title') and title in range_contents: 
                    range_contents = range_contents.replace(title.strip(),'',1)

                added_contents += self._wrap_title(kind, root_node_id, nested)

            """
            Add the range contents only after the title, if any.
            """

            added_contents += range_contents

            if single_range != ranges[0] and kind == 'html':    
 
                """
                Otherwise, only for HTML, wrap all important elements
                """
        
                heading_tag = 'h'+str(nested)
                added_contents = added_contents.replace(  
                    title,
                    '<'+heading_tag+'>'+title+'</'+heading_tag+'>',
                    1)

            added_contents = self.replace_node_links(added_contents, kind)

            if clean_whitespace:
                added_contents = added_contents.strip('\n ')
                added_contents = '\n' + added_contents + '\n'

            """
            For this single range of text, replace node pointers with their contents,
            which cals this function recursively.
            """
            if as_single_file:

                added_contents, points = self.replace_node_pointers(
                    nested,
                    kind,
                    added_contents=added_contents,
                    points=points,
                    as_single_file=True,
                    strip_urtext_syntax=strip_urtext_syntax,
                    style_titles=style_titles,
                    exclude=exclude,
                    clean_whitespace=clean_whitespace
                    )

            """
            If this is end of the node, mark it complete
            """
            if single_range[1] == ranges[-1][1]:
                added_contents += self._closing_wrapper(kind)
               
            """
            If we are adding subnodes, find the node_id of the node immediately following this range
            and add it, assuming we are including all sub-nodes.
            TODO: Add checking in here for excluded nodes
            """
        
            if not single_node_only and single_range[1] < ranges[-1][1]:

                # get the node in the space immediately following this RANGE
                next_node = self.project.get_node_id_from_position(filename, single_range[1] + 1)

                if next_node and next_node not in self.visited_nodes:

                    """ for HTML, if this is a dynamic node and contains a tree, add the tree"""
                    if kind == 'html' and next_node in self.project.dynamic_nodes and self.project.dynamic_nodes[next_node].tree:
                        exported_contents += self._render_tree_as_html(self.project.dynamic_nodes[next_node].tree)

                    else:

                        next_nested = nested

                        if not split:
                            next_nested+=1

                        """
                        recursively add the node in the next range and its subnodes
                        """
                        added_contents, points = self._add_node_content(
                            next_node,
                            added_contents=added_contents,
                            points=points,       
                            as_single_file=as_single_file,
                            strip_urtext_syntax=strip_urtext_syntax,
                            style_titles=style_titles,
                            exclude=exclude,
                            kind=kind,
                            nested=next_nested,
                            clean_whitespace=clean_whitespace,
                            )
        
        return added_contents, points

    def replace_node_pointers(self,     
        nested, 
        kind,
        added_contents='',
        points={},
        as_single_file=False,                       
        strip_urtext_syntax=True,                   
        style_titles=True,                          
        exclude=[],
        clean_whitespace=False):

        patterns = [titled_node_pointer_regex, node_pointer_regex]
        matches = []
        lex = {}
        for pattern in patterns:
            matches.extend(re.findall(pattern, added_contents))
        for match in matches:
            location = added_contents.find(match)
            lex[location] = match
        locations = sorted(lex.keys())

        for location in locations:

            match = lex[location]
            node_id = match[-3:]

            added_contents = added_contents.split(match)[0]
            remaining_contents = ''.join(added_contents.split(match)[1:])
            
            """
            Avoid recursion
            """
            if node_id in self.visited_nodes:
                inserted_contents = '\n' + '#' * nested + ' <><><>< RECURSION : '+ node_id + ' ><><><>' 
                continue       
            
            self.visited_nodes.append(node_id)

            if node_id not in self.project.nodes:
                print('NODE MARKER >>'+node_id+' not in project, skipping')
                continue                            

            added_contents, points = self._add_node_content(
                node_id, 
                added_contents=added_contents,
                points=points,
                nested=nested+1,
                as_single_file=True,
                kind=kind,
                strip_urtext_syntax=strip_urtext_syntax,
                style_titles=style_titles,
                clean_whitespace=clean_whitespace,
                )

            # POSSIBLY may need to add here:
            # points [ len(added_contents) ] = whatever the sending ID was??? ]
            added_contents += remaining_contents

        return added_contents, points


    def replace_node_links(self, contents, kind):
        """ replace node links, including titled ones, with exported versions """

        patterns = [titled_link_regex,  node_link_regex]

        for pattern in patterns:

            node_links = re.findall(pattern, contents)

            for match in node_links:

                node_link = re.search(node_link_regex, match)            

                node_id = node_link.group(0)[-3:]

                if node_id not in self.project.nodes:
                    
                    print('Skipping node ID '+node_id+', not in project')
                    continue

                title = self.project.nodes[node_id].title

                if kind == 'html':

                    filename = self.project.nodes[root_node_id].filename
                    
                    if node_id in self.project.files[filename].nodes:
                        link = '#'+node_id

                    else: 
                        base_filename = self.project.nodes[node_id].filename
                        this_root_node = self.project.files[base_filename].root_nodes[0]
                        link = this_root_node+'.html#'+ node_id
                
                    contents = contents.replace(match, '<a href="'+link+'">'+title+'</a>')

                if kind in ['plaintext','markdown']:

                    contents = contents.replace(match, '"'+title+'"') # TODO - make quote wrapper optional
        
        return contents

    def other_stuff():
        """
        older code, not currently being used??
        """

        root_node_id = project.files[filename].root_nodes[0]
        
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
                'title:  "'+ project.nodes[root_node_id].title +'"',
                'date:   2019-08-21 10:44:41 -0500',
                'categories: '+ ' '.join(project.nodes[root_node_id].metadata.get_tag('categories')),
                '---'
                ]) + '\n'

                final_exported_contents = header + final_exported_contents


        with open(os.path.join(project.path, to_filename), 'w', encoding='utf-8') as f:
            f.write(final_exported_contents)

    def export_project( self, project , jekyll=False, style_titles=True ):
        """
        Export an entire project
        """
        for filename in self.project.files:
            
            # Name file by the first root node
            export_filename = project.files[filename].root_nodes[0]+'.html'

        pass
        #TODO :complete


    def _render_tree_as_html(   self, node_id,
                                links_on_same_page=False,
                                from_root_of=False ):

        if node_id not in self.project.nodes:
            project.log_item(root_node_id + ' is not in the project')
            return None

        start_point = self.project.nodes[node_id].tree_node
        
        if from_root_of == True:
            start_point = self.project.nodes[node_id].tree_node.root

        # revisit whether this does what we actually want it to.
        self.project.detach_excluded_tree_nodes(start_point, flag='export') 

        tree_filename = node_id +'.html'

        def render_list(node, nested, visited_nodes):
            html = ''
            if node in visited_nodes:
                return html
            children = node.children
            if children:
                html += '<ul>\n'
                for child in node.children:
                    if child.name not in self.project.nodes:
                        print(child.name + ' not in the project. skipping')
                        continue
                    visited_nodes.append(child)
                    link = ''
                    if not links_on_same_page:
                        this_node_id = child.name
                        
                        base_filename = self.project.nodes[this_node_id].filename
                        if base_filename != tree_filename:
                            
                            # Will need to be changed to handle multiple root nodes
                            this_root_node = self.project.files[base_filename].root_nodes[0]
                            ###
                            link += this_root_node+'.html'
                        else:
                            print(this_node_id + ' not in the project. Not exporting')
                    link += '#'+child.name
                    html += '<li><a href="' + link + '">' + self.project.nodes[child.name].title + '</a></li>\n'
                    html += render_list(self.project.nodes[child.name].tree_node, nested, visited_nodes)
                html += '</ul>\n'
            return html

        return render_list(start_point, 1, [])

    """ Older stuff - not sure it's needed"""

    def node(self, node_id, kind):
        """ export a single node to a file (why?) """
        
        if kind == 'plaintext':
            contents = self.project.nodes[node_id].content_only()
            filename = self.project.nodes[node_id].title
            if not filename:
                filename = self.project.nodes[node_id].metadata.get_tag('filename')[0]
            if not filename:
                filename = node_id
            filename = filename.strip()

        if self.extensions[kind] not in filename:
            filename += self.extensions[kind]

        with open(os.path.join(self.project.path, filename), 'w', encoding="utf-8") as f:
            f.write(contents)
            f.close()

    def _add_content(self, from_file=None, exclude=[], from_node_id=None):
        
        if from_node_id:
            start = self.project.nodes[from_node_id].ranges[0][0]
            end = self.project.nodes[from_node_id].ranges[-1][1]
        elif from_file:
            start = 0
            end = self.project.files[from_file].file_length
        if not from_file:
            file_name = self.project.nodes[from_node_id].filename
        else:
            file_name = from_file

        contents_from_file = ''
        full_file_contents = self.project.full_file_contents(file_name)[start:end]
        contents_from_file = full_file_contents
        exclude_ranges = []
        for node_id in exclude:
            if node_id in self.project.files[file_name]:
                for this_range in self.project.nodes[node_id].ranges:
                    exclude_ranges.append(this_range)
        exclude_ranges = sorted(exclude_ranges, key = lambda range: range[0] )
        for this_range in exclude_ranges:
            cut_content = full_file_contents[this_range[0], this_range[1]]
            contents_from_file = contents_from_file.replace(cut_content,'')
        return contents_from_file 


def merge_two_dicts(x, y):
    z = x.copy()   # start with x's keys and values
    z.update(y)    # modifies z with y's keys and values & returns None
    return z

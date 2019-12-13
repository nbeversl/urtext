""" 
Export

These should be re-tested. 
"""
import os
import re
from .node import UrtextNode

node_link_regex = r'>[0-9,a-z]{3}\b'
OPENING_BRACKETS = '<span class="urtext-open-brackets">&#123;&#123;</span>'

        
        

class UrtextExport:

    def __init__(self, project):
        self.project = project
        self.extensions  = {
            'plaintext':'.txt',
            'html' : '.html',
            'markdown' :'.md'
        }



    def node(self, node_id, kind):

        kind = kind.lower()

        if kind == 'plaintext':
            contents = self.project.nodes[node_id].content_only()
 
            filename = self.project.nodes[node_id].title
            if not filename:
                filename = self.project.nodes[node_id].metadata.get_tag('filename')[0]
            if not filename:
                filename = self.project.nodes[node_id]
            filename = filename.strip()

        if self.extensions[kind] not in filename:
            filename += self.extensions[kind]

        with open(os.path.join(self.project.path, filename), 'w', encoding="utf-8") as f:
            f.write(contents)
            f.close()

    def from_root_id(self, 
        root_node_id, 
        exclude=[], 
        kind='plaintext'):
        
        if isinstance(exclude,str):
            exclude = [exclude]

        kind = kind.lower()

        if kind == 'plaintext':
            contents = ''

        filename = self.project.nodes[root_node_id].filename
        contents = self._add_content(exclude=exclude, from_node_id=root_node_id)

        visited_nodes = []
        node_links = re.findall('>>[0-9,a-z]{3}', contents)
        while node_links:

            for match in node_links:
                node_id = match[2:]
                if node_id not in visited_nodes:
                    visited_nodes.append(node_id)
                    if node_id in self.project.nodes:                    
                        new_contents = self._add_content(exclude=exclude, from_node_id=node_id)
                        contents = contents.replace(match, new_contents, 1)    
                else:
                     contents = contents.replace(match, 'RECURSION!!', 1)
            node_links = re.findall('>>[0-9,a-z]{3}', contents)
        


        return self._strip_urtext_syntax(contents)

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

    def _strip_urtext_syntax(self, contents):
        contents = UrtextNode.strip_contents(contents)
        contents = contents.replace('{{','')
        contents = contents.replace('}}','')
        contents = re.sub(r'^\%', '', contents, re.DOTALL)
        return contents        

    
    def _opening_wrapper(self, kind, nested):
        kind = kind.lower()
        wrappers = { 
            'HTML': '<div class="urtext_nested_'+str(nested)+'">',
            'Markdown': '',
            'plaintext': ''

            }
        return wrappers[kind]

    def _closing_wrapper(self, kind):
        kind = kind.lower()
        wrappers = { 
            'html': '</div>',
            'markdown': '',
            'plaintext': ''
            }
        return wrappers[kind]

    def _wrap_title(self, kind, node_id, nested):
        title = self.project.nodes[node_id].title
        wrappers = {
            'markdown': '\n' + '#' * nested + ' ' + title + '\n',
            'html' : '<h'+str(nested)+'>' + title + '</h'+str(nested)+'>\n',
            'plaintext' : title,
        }
        return wrappers[kind]


    def older_export_from(self, 
        root_node_id, 
        as_single_file=False,
        strip_urtext_syntax=True,
        style_titles=True,
        exclude=[], 
        kind='plaintext'
        ):

        """
        Public method to export a tree of nodes from a given root node
        """
        self.visited_nodes = []
        exported_content = self._add_node_content(
            root_node_id,
            as_single_file=as_single_file,
            strip_urtext_syntax=strip_urtext_syntax,
            style_titles=style_titles,
            exclude=exclude,
            kind=kind,
            )

        return exported_content

    def _add_node_content(self, 
            root_node_id,                               # node to start from
            as_single_file=False,                       # single file or separate files?
            strip_urtext_syntax=True,                   # for HTML, strip Urtext syntax?
            style_titles=True,                          # style titles ????
            exclude=[],
            kind='plaintext',
            nested=1,                                   # nested level (private)
            ):         
        """
        Recursively add nested nodes / node pointers from a given starting node,
        keeping track of nesting level, and wrapping in markup.
        """    

        """
        Avoid recursion
        """

        if root_node_id in self.visited_nodes:
            return '\n' + '#' * nested + ' <><><>< RECURSION : '+ root_node_id + ' ><><><>'                
        else:
            self.visited_nodes.append(root_node_id)

        """
        Get initial values
        """
        exported_contents = ''    
        ranges = self.project.nodes[root_node_id].ranges
        filename = self.project.nodes[root_node_id].filename
        file_contents = self.project.full_file_contents(filename)        
        title = self.project.nodes[root_node_id].title

        """
        Wrap the title if specified
        """
        if style_titles:                 
            exported_contents += self._wrap_title(kind, root_node_id, nested)
        
        """
        Insert opening node wrapper
        """

        exported_contents += self._opening_wrapper(kind, nested)        

        if kind == 'html':
            exported_contents += '<a name="'+ root_node_id + '"></a>'

        """
        For all ranges of the node,

        """

        for single_range in ranges:

            # accumulate contents to add to exported_contents
            added_contents = '' 
                
            """
            If this is the node's first range, add Urtext styled {{ wrapper
            """
            if kind == 'html' and single_range == ranges[0] and not strip_urtext_syntax:
                added_contents += OPENING_BRACKETS

            """
            Add the node's contents
            """
            range_contents = file_contents[single_range[0]:single_range[1]]
            range_contents = self._strip_urtext_syntax(range_contents)
            added_contents += range_contents

            if kind == 'html':
                """
                Separate added contents in to separate lines
                """
                lines = [line.strip() for line in added_contents.split('\n') if line.strip() != '']
                index = 0
                while index < len(lines):
                    line = lines[index]

                    """
                    Insert HTML <ul><li><li></ul> tags for lists
                    """

                    if line[0] == '-':
                        added_contents += '<ul class="urtext-list">'
                        while index < len(lines) - 1:
                            added_contents += '<li>'+line[1:]+'</li>'
                            index += 1
                            line = lines[index]
                            if line[0] != '-':
                                break
                        added_contents += '</ul>'

                    """
                    For non-list items, wrap them in a <div>
                    """
                    added_contents += '<div class="urtext_line">' + line.strip()
                    if single_range == ranges[-1] and line == lines[-1] and not strip_urtext_syntax:
                        added_contents += '<span class="urtext-close-brackets">&#125;&#125;</span>'                
                    added_contents += '</div>\n'     
                    index += 1

            """
            Remove duplicate titles if there is no title key.
            """
            if style_titles and not self.project.nodes[root_node_id].metadata.get_tag('title') and title in added_contents: 
                added_contents = added_contents.replace(title,'',1)
           
            elif kind == 'html':    
 
                """
                Otherwise, only for HTML, wrap all important elements
                """
        
                heading_tag = 'h'+str(nested)
                added_contents = added_contents.replace(  
                    title,
                    '<'+heading_tag+'>'+title+'</'+heading_tag+'>',
                    1)

                for match in re.findall(node_link_regex, exported_contents):
                    node_id = match[1:]
                    if node_id not in project.nodes:
                        print('Skipping node ID '+node_id+', not in project')
                        continue
                    filename = project.nodes[root_node_id].filename
                    if node_id in project.files[filename].nodes:
                        link = '#'+node_id
                    else: 
                        base_filename = project.nodes[node_id].filename
                        # WILL HAVE TO BE CHANGED TO HANDLE MULTIPLE ROOT NODES
                        this_root_node = project.files[base_filename].root_nodes[0]
                        ##
                        link = this_root_node+'.html#'+ node_id
                    
                    exported_contents = exported_contents.replace(match, 
                                    '<a href="'+link+'">'+match+'</a>')
                
            if as_single_file:
                
                while re.findall(node_pointer_regex, added_contents):
                    for match in re.findall(node_pointer_regex, added_contents):
                        inserted_contents = self._add_node_content(
                            match[2:5], 
                            nested + 1,
                            as_single_file=as_single_file,
                            strip_urtext_syntax=strip_urtext_syntax,
                            style_titles=style_titles
                            )
                        added_contents = added_contents.replace(match, inserted_contents)

            exported_contents += added_contents

            """
            If this is not the last range in the file,
            find the node_id of the node immediately following this range
            and add it, assuming we are including all sub-nodes.
            TODO: Add checking in here for excluded nodes
            """
            if single_range != ranges[-1]:
                next_node = self.project.get_node_id_from_position(filename, single_range[1]+1)

                if next_node in self.project.dynamic_nodes and self.roject.dynamic_nodes[next_node].tree:
                    exported_contents += self._render_tree_as_html(self.project.dynamic_nodes[next_node].tree)

                else:
                    exported_contents += self._add_node_content(
                        next_node,                        
                        as_single_file=as_single_file,
                        strip_urtext_syntax=strip_urtext_syntax,
                        style_titles=style_titles,
                        exclude=exclude,
                        kind=kind,
                        nested=nested + 1,)
                        
        exported_contents += self._closing_wrapper(kind)

        return exported_contents 

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

    def export_project( project , jekyll=False, style_titles=True ):
        """
        Export an entire project
        """
        for filename in self.project.files:
            
            # Name file by the first root node
            export_filename = project.files[filename].root_nodes[0]+'.html'

        pass
        #TODO :complete


    def _render_tree_as_html(   node_id,
                                links_on_same_page=False,
                                from_root_of=False ):

        if node_id not in self.project.nodes:
            project.log_item(root_node_id + ' is not in the project')
            return None

        start_point = project.nodes[node_id].tree_node
        
        if from_root_of == True:
            start_point = project.nodes[node_id].tree_node.root

        # revisit whether this does what we actually want it to.
        project.detach_excluded_tree_nodes(start_point, flag='export') 

        tree_filename = node_id +'.html'

        def render_list(node, nested, visited_nodes):
            html = ''
            if node in visited_nodes:
                return html
            children = node.children
            if children:
                html += '<ul>\n'
                for child in node.children:
                    if child.name not in project.nodes:
                        print(child.name + ' not in the project. skipping')
                        continue
                    visited_nodes.append(child)
                    link = ''
                    if not links_on_same_page:
                        this_node_id = child.name
                        
                        base_filename = project.nodes[this_node_id].filename
                        if base_filename != tree_filename:
                            
                            # Will need to be changed to handle multiple root nodes
                            this_root_node = project.files[base_filename].root_nodes[0]
                            ###
                            link += this_root_node+'.html'
                        else:
                            print(this_node_id + ' not in the project. Not exporting')
                    link += '#'+child.name
                    html += '<li><a href="' + link + '">' + project.nodes[child.name].title + '</a></li>\n'
                    html += render_list(project.nodes[child.name].tree_node, nested, visited_nodes)
                html += '</ul>\n'
            return html

        return render_list(start_point, 1, [])


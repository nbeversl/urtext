""" 
Export

These should be re-tested. 
"""
def export_project( project , jekyll=False, style_titles=True ):
    for filename in list(project.files):
        # Name file by the first root node
        export_filename = project.files[filename].root_nodes[0]+'.html'
        export(project,
            filename, 
            export_filename, 
            kind='HTML',
            as_single_file=False,
            style_titles=style_titles,
            strip_urtext_syntax=False,
            jekyll=jekyll)

def export( project, 
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
        title = project.nodes[node_id].title
        if kind == 'Markdown':
            return '\n' + '#' * nested + ' ' + title + '\n'
        if kind == 'HTML':
            return '<h'+str(nested)+'>' + title + '</h'+str(nested)+'>\n'
    
    # name by the first root node
    root_node_id = project.files[filename].root_nodes[0]
 
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

        ranges =  project.nodes[root_node_id].ranges
        filename = project.nodes[root_node_id].filename
        
        file_contents = project.full_file_contents(filename)
        
        title = project.nodes[root_node_id].title
        if style_titles:                 
            exported_contents += wrap_title(kind, root_node_id, nested)

        title_removed = True
        if len(project.nodes[root_node_id].metadata.get_tag('title')) == 0: 
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
                    if node_id not in project.nodes:
                        # probably another use of >, technically a syntax error
                        # TODO write better error catching here
                        continue
                    filename = project.nodes[root_node_id].filename
                    if node_id in project.files[filename]:
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
                        inserted_contents = s(match[2:5], nested + 1, visited_nodes)
                        if inserted_contents == None:
                            inserted_contents = ''
                        added_contents = added_contents.replace(match, inserted_contents)

            exported_contents += added_contents
            if single_range != ranges[-1]:
                next_node = project.get_node_id_from_position(filename, single_range[1]+1)
                if next_node in project.dynamic_nodes and project.dynamic_nodes[next_node].tree:
                    exported_contents += project.render_tree_as_html(project.dynamic_nodes[next_node].tree)
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
            'title:  "'+ project.nodes[root_node_id].title +'"',
            'date:   2019-08-21 10:44:41 -0500',
            'categories: '+ ' '.join(project.nodes[root_node_id].metadata.get_tag('categories')),
            '---'
            ]) + '\n'

            final_exported_contents = header + final_exported_contents


    with open(os.path.join(project.path, to_filename), 'w', encoding='utf-8') as f:
        f.write(final_exported_contents)

def render_tree_as_html(project, 
                            node_id,
                            links_on_same_page=False,
                            from_root_of=False ):

    if node_id not in self.nodes:
        self.log_item(root_node_id + ' is not in the project')
        return None

    start_point = self.nodes[node_id].tree_node
    
    if from_root_of == True:
        start_point = self.nodes[node_id].tree_node.root

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
                visited_nodes.append(child)
                link = ''
                if not links_on_same_page:
                    this_node_id = child.name
                    base_filename = self.nodes[this_node_id].filename
                    if base_filename != tree_filename:
                        
                        # Will need to be changed to handle multiple root nodes
                        this_root_node = self.files[base_filename].root_nodes[0]
                        ###


                        link += this_root_node+'.html'
                link += '#'+child.name
                html += '<li><a href="' + link + '">' + self.nodes[child.name].title + '</a></li>\n'
                html += render_list(self.nodes[child.name].tree_node, nested, visited_nodes)
            html += '</ul>\n'
        return html

    return render_list(start_point, 1, [])


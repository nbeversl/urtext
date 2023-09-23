""" Metadata Handling """

def tag_other_node(self, 
    full_line, 
    cursor, 
    metadata={}):
    
    return self.execute(
        self._tag_other_node,
        full_line,
        cursor,
        metadata=metadata)
    
def _tag_other_node(
    self, 
    full_line, 
    cursor, 
    metadata={}):
    
    link = self.parse_link(full_line, col_pos=cursor)
    if not link: return

    if metadata == {}:
        if len(self.settings['tag_other']) < 2: return None
        metadata = { self.settings['tag_other'][0] : self.settings['tag_other'][1] + ' ' + self.timestamp().wrapped_string }
    territory = self.nodes[link['node_id']].ranges
    metadata_contents = UrtextNode.build_metadata(metadata)

    filename = self.nodes[link['node_id']].filename
    full_file_contents = self.files[filename]._get_file_contents()
    tag_position = territory[-1][1]

    separator = '\n'
    if self.nodes[link['node_id']].compact:
        separator = ' '

    new_contents = ''.join([
        full_file_contents[:tag_position],
        separator,
        metadata_contents,
        separator,
        full_file_contents[tag_position:]])
    self.files[filename]._set_file_contents(new_contents)
    return self._on_modified(filename)
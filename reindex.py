import os
import datetime

""" 
Reindexing (renaming) Files 
"""
def reindex_files(self):
    """ 
    sorts all file-level nodes by their index, then passes
    the result to rename_file_nodes() to rename them.
    """    
    self._sync_file_list()
    files = self.all_files() 
    if self.is_async:
        return self.executor.submit(self._rename_file_nodes, files, reindex=True)
    return self._rename_file_nodes(files, reindex=True)

def rename_file_nodes(self, filename, reindex=False):
    if self.is_async:
        future = self.executor.submit(self._rename_file_nodes, filename, reindex=reindex)
        renamed_files = future.result()
        return renamed_files
    else:
        return self._rename_file_nodes(filename, reindex=reindex)

def _prefix_length(self):
        """ Determines the prefix length for indexing files (requires an already-compiled project) """
        prefix_length = 1
        num_files = len(self.files)
        while num_files > 0:
            prefix_length += 1
            num_files -= 10
        return prefix_length

def _rename_file_nodes(self, filenames, reindex=False):
    """ Rename a file or list of files by metadata """

    if isinstance(filenames, str):
        filenames = [filenames]

    used_names = []
    existing_files = os.listdir()
    renamed_files = {}
    date_template = self.settings['filename_datestamp_format']
    prefix = 0
    prefix_length = self._prefix_length()
    for filename in filenames:
        old_filename = os.path.basename(filename)
        if old_filename not in self.files:
            return {}

        if not self.files[old_filename].root_nodes:
            self._log_item('DEBUGGING (reindex.py): No root nodes in '+old_filename)
            continue

        ## Name each file from the first root_node
        root_node_id = self.files[old_filename].root_nodes[0]
        root_node = self.nodes[root_node_id]
        filename_template = list(self.settings['filenames'])
        for i in range(0,len(filename_template)):
            
            if filename_template[i] == 'PREFIX' and reindex == True:
                padded_prefix = '{number:0{width}d}'.format(
                    width = prefix_length, 
                    number = prefix)
                filename_template[i] = padded_prefix
            else:                
                filename_template[i] = ' '.join(root_node.metadata.get_values(filename_template[i]))
 
        prefix += 1

        # start with the filename template, replace each element
        new_filename = ' - '.join(filename_template)      
        new_filename = new_filename.replace('’', "'")
        new_filename = new_filename.strip('-').strip();
        new_filename += '.txt'
        new_filename = strip_illegal_characters(new_filename)
        new_filename = new_filename[:255]

        if new_filename in used_names:
            new_filename = new_filename.replace('.txt',' - '+root_node.id+'.txt')

        # renamed_files retains full file paths
        renamed_files[os.path.join(self.path, old_filename)] = os.path.join(self.path, new_filename)
        used_names.append(new_filename)

        # add history files
        old_history_file = old_filename.replace('.txt','.diff')
        if os.path.exists(os.path.join(self.path, 'history', old_history_file)  ):
            new_history_file = new_filename.replace('.txt','.diff')
            renamed_files[os.path.join(self.path, 'history', old_history_file)] = os.path.join(self.path, 'history', new_history_file)
            
    for filename in renamed_files:
        old_filename = filename
        new_filename = renamed_files[old_filename]

        self._log_item('renaming ' + old_filename + ' to ' + new_filename)

        os.rename(old_filename, new_filename)

        if old_filename[-4:].lower() == '.txt': # skip history files
            self._handle_renamed(old_filename, new_filename)

    """
    Returns a list of renamed files with full paths
    """    
    return renamed_files

def strip_illegal_characters(filename):
    for c in ['<', '>', ':', '"', '/', '\\', '|', '?','*']:
        filename = filename.replace(c,' ')
    return filename


reindex_functions = [ rename_file_nodes, _rename_file_nodes, reindex_files, _prefix_length ]

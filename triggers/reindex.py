import os
import concurrent.futures
from urtext.triggers.trigger import UrtextTrigger

class ReindexFiles(UrtextTrigger):
    """ 
    sorts all file-level nodes by their index, then passes
    the result to rename_file_nodes() to rename them.
    """    
    name='REINDEX'
    
    def execute(self, project):
        project._sync_file_list()
        files = project.all_files() 
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=50)
        executor.submit(self.rename_file_nodes, project, files, reindex=True)
     
    def rename_file_nodes(self, project, filenames, reindex=False):
        """ Rename a file or list of files by metadata """

        if isinstance(filenames, str):
            filenames = [filenames]
            
        used_names = []
        existing_files = os.listdir(project.path)
        renamed_files = {}
        date_template = project.settings['filename_datestamp_format']
        prefix = 0
        prefix_length = len(str(len(project.files)))
        for filename in filenames:

            old_filename = os.path.basename(filename)
            if old_filename not in project.files:
                return {}

            if not project.files[old_filename].root_nodes:
                project._log_item('DEBUGGING (reindex.py): No root nodes in '+old_filename)
                continue

            ## Name each file from the first root_node
            root_node_id = project.files[old_filename].root_nodes[0]
            root_node = project.nodes[root_node_id]
            filename_template = list(project.settings['filenames'])
            for i in range(0,len(filename_template)):
                
                if filename_template[i] == 'PREFIX' and reindex == True:
                    padded_prefix = '{number:0{width}d}'.format(
                        width = prefix_length, 
                        number = prefix)
                    filename_template[i] = padded_prefix
                    
                elif filename_template[i].lower() == 'title':
                    filename_template[i] = root_node.title
                elif filename_template[i].lower() in project.settings['use_timestamp']:
                    timestamp = root_node.metadata.get_first_value(filename_template[i], use_timestamp=True)
                    if timestamp:
                        filename_template[i] = timestamp.strftime(date_template)
                    else:
                        filename_template[i] = ''
                else:
                    filename_template[i] = ' '.join([str(s) for s in root_node.metadata.get_values(filename_template[i])])
     
            # start with the filename template, replace each element
            new_filename = ' - '.join(filename_template)      
            new_filename = new_filename.replace('’', "'")
            new_filename = new_filename.strip().strip('-').strip();
            new_filename = strip_illegal_characters(new_filename)
            new_filename = new_filename[:255]
            new_filename += '.txt'

            if new_filename in used_names:
                new_filename = new_filename.replace('.txt',' - '+root_node.id+'.txt')

            # renamed_files retains full file paths
            renamed_files[os.path.join(project.path, old_filename)] = os.path.join(project.path, new_filename)
            used_names.append(new_filename)

            # add history files
            old_history_file = old_filename.replace('.txt','.diff')
            if os.path.exists(os.path.join(project.path, 'history', old_history_file) ):
                new_history_file = new_filename.replace('.txt','.diff')
                renamed_files[os.path.join(project.path, 'history', old_history_file)] = os.path.join(project.path, 'history', new_history_file)

            prefix += 1
            
        for filename in renamed_files:
            old_filename = filename
            new_filename = renamed_files[old_filename]
            os.rename(old_filename, new_filename)

            if old_filename[-4:].lower() == '.txt': # skip history files
                project._handle_renamed(old_filename, new_filename)

        return renamed_files

def strip_illegal_characters(filename):
    for c in ['<', '>', ':', '"', '/', '\\', '|', '?','*']:
        filename = filename.replace(c,' ')
    return filename
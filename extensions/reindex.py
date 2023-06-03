import os
if os.path.exists(os.path.join(os.path.dirname(os.path.realpath(__file__)), '../sublime.txt')):
    from Urtext.urtext.extension import UrtextExtension
else:
    from urtext.extension import UrtextExtension

class ReindexFiles(UrtextExtension):
    """ 
    sorts all file-level nodes by their index, then passes
    the result to rename_file_nodes() to rename them.
    """    
    name=['REINDEX']        
    
    def rename_all_files(self):
        return self.rename_file_nodes(self.project.all_files(), reindex=True)

    def rename_file_nodes(self, filenames, reindex=False):
        """ Rename a file or list of files by metadata """

        if isinstance(filenames, str):
            filenames = [filenames]
       
        used_names = []
        renamed_files = {}
        for old_filename in filenames:
            
            if old_filename not in self.project.files:
                print('%s not found in project files' % old_filename)
                continue
            if not self.project.files[old_filename].root_node:
                print('%s is an empty file, nothing to use for filenaming' % old_filename)
                continue

            root_node = self.project.files[old_filename].root_node
            filename_template = list(self.project.settings['filenames'])
            
            for i in range(0,len(filename_template)):
                
                if filename_template[i].lower() == 'title':
                    filename_length = int(self.project.settings['filename_title_length'])
                    if filename_length > 255:
                        filename_length = 255
                    title = root_node.title
                    filename_template[i] = title[:filename_length]
                
                elif filename_template[i].lower() in self.project.settings['use_timestamp']:
                    timestamp = root_node.metadata.get_first_value(filename_template[i], use_timestamp=True)
                    if timestamp:
                        filename_template[i] = timestamp.strftime(self.project.settings['filename_datestamp_format'])
                    else:
                        filename_template[i] = ''                
                else:
                    filename_template[i] = ' '.join([str(s) for s in root_node.metadata.get_values(filename_template[i])])

            if filename_template in [ [], [''] ]:
                return print('New filename(s) could not be made. Check project_settings')

            filename_template = [p.strip() for p in filename_template if p.strip()]
            new_basename = ' - '.join(filename_template)      
            new_basename = new_basename.replace('’', "'")
            new_basename = new_basename.strip().strip('-').strip();
            new_basename = strip_illegal_characters(new_basename)
            new_basename = new_basename[:248].strip()

            test_filename = os.path.join(
                os.path.dirname(old_filename), 
                new_basename + '.urtext')

            if test_filename == old_filename:
                continue

            # avoid overwriting existing files
            unique_file_suffix = 1
            while test_filename in used_names or os.path.exists(test_filename):
                unique_file_suffix += 1
                test_filename = os.path.join(
                    os.path.dirname(old_filename), 
                    new_basename + ' ' + str(unique_file_suffix) + '.urtext')
                if test_filename == old_filename:
                    break

            if test_filename == old_filename:
                continue

            new_filename = test_filename
            renamed_files[old_filename] = new_filename
            used_names.append(new_filename)

        for old_filename in renamed_files:
            new_filename = renamed_files[old_filename]
            os.rename(old_filename, new_filename)
            self.project._handle_renamed(old_filename, new_filename)

        return renamed_files

class RenameSingleFile(ReindexFiles):

    name=['RENAME_SINGLE_FILE']

    def rename_single_file(self, filename):
        return self.rename_file_nodes(filename, reindex=True) 

def strip_illegal_characters(filename):
    for c in ['<', '>', ':', '"', '/', '\\', '|', '?','*', '.', ';']:
        filename = filename.replace(c,' ')
    return filename
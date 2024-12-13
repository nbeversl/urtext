from urtext.buffer import UrtextBuffer
import urtext.syntax as syntax
import urtext.utils as utils

class UrtextFile(UrtextBuffer):
   
    def __init__(self, filename, project):
        self.filename = filename
        super().__init__(project, filename, self._read_contents())

    def _get_contents(self):
        if not self.contents:
            self.contents = self._read_contents()
        return self.contents

    def _read_contents(self):
        """ returns the file contents, filtering out Unicode Errors, directories, other errors """
        try:
            with open(self.filename, 'r', encoding='utf-8') as theFile:
                full_file_contents = theFile.read()
        except IsADirectoryError:
            return None
        except UnicodeDecodeError:
            self._log_error(''.join([
                'UnicodeDecode Error: ',
                syntax.file_link_opening_wrapper,
                self.filename,
                syntax.link_closing_wrapper]), 0)
            return None
        except TimeoutError:
            return print('Timed out reading %s' % self.filename)
        except FileNotFoundError:
            return print('Cannot read file from storage %s' % self.filename)
        return full_file_contents

    def write_buffer_contents(self, run_hook=False):
        if run_hook: # for last modification only
            self.project.run_hook('on_write_file_contents', self)
        existing_contents = self._read_contents()
        if existing_contents == self.contents:
            return False
        if self.filename:
            utils.write_file_contents(self.filename, self.contents)
            buffer_setting = self.project.get_single_setting('use_buffer')
            if buffer_setting and buffer_setting.true():
                self.project.run_editor_method('set_buffer', self.filename, self.contents)
            else:
                self.project.run_editor_method('refresh_files', self.filename)
            self.project._parse_file(self.filename)
        elif self.identifier:
            self.project.run_editor_method('set_buffer', None, self.contents, identifier=self.identifier)
            self.project._parse_buffer(self)
        return True

    def contents_did_change(self):
        current_contents = self.contents
        disk_contents = self._read_contents()
        if current_contents != disk_contents:
            return True
        return False

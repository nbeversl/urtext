# -*- coding: utf-8 -*-
"""
This file is part of Urtext.

Urtext is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Urtext is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Urtext.  If not, see <https://www.gnu.org/licenses/>.

"""
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
import os

class UrtextWatcher (FileSystemEventHandler):

  def __init__(self,
               project,
               make_new_files=True,
               rename=False,
               recursive=False,
               import_project=False,
               init_project=False):

    self.project = project


  # def on_created(self, event):

  #   if event.is_directory:
  #       return None
  #   filename = event.src_path
    
  #   # if filter(filename) == None:
  #   #   return
  #   if filename in self.project.files:
  #     # This is not really a new file.
  #     return None
  #   # if self.project.parse_file(filename) == None:
  #   #     self.project.log_item(filename + ' not added.')
  #   #     return
  #   # self.project.log_item(filename +
  #   #                         ' modified. Updating the project object')
  #   # self.project.update()
      

  def on_created(self, event):
      filename = os.path.basename(event.src_path)
      if os.path.isdir(filename):
          return True
      filename = os.path.basename(filename)
      if filename in self.project.files:
        return True
      print(filename + ' found by on_created() -- DEBUGGING')
      self.project.add_file(filename)

      return True


  # def on_deleted(self, event):
  #   if not self.project.check_lock(machine):
  #     return

  #   if filter(event.src_path) == None:
  #       return
  #   filename = os.path.basename(event.src_path)
  #   self.project.log_item('Watchdog saw file deleted: '+filename)
  #   self.project.remove_file(filename)
  #   self.project.update()
   
  # def on_moved(self, event):
  #     if not self.project.check_lock(machine):
  #       return

  #     if filter(event.src_path) == None:
  #       return
  #     old_filename = os.path.basename(event.src_path)
  #     new_filename = os.path.basename(event.dest_path)
  #     if old_filename in _UrtextProject.files:
  #         self.project.log.info('RENAMED ' + old_filename + ' to ' +
  #                                 new_filename)
  #         self.project.handle_renamed(old_filename, new_filename)


  def on_modified(self, event):
      filename = os.path.basename(event.src_path)
      if os.path.isdir(filename):
          return True
      # do_not_update = [
      #     'index', 
      #     os.path.basename(self.project.path),
      #     # self.project.settings['logfile'],
      #     ]
      if filename not in self.project.files:
        return False
      file_changed = self.project._file_changed(filename)
      if file_changed:
        self.project.on_modified(filename)
      return True

 

  # def on_moved(self, filename):
  #     old_filename = os.path.basename(filename)
  #     new_filename = os.path.basename(filename)
  #     if old_filename in self.files:
  #         self.log.info('RENAMED ' + old_filename + ' to ' +
  #                                 new_filename)
  #         self.handle_renamed(old_filename, new_filename)
  #     return True
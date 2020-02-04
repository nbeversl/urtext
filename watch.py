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
from .project import UrtextProject
from watchdog.observers import Observer

class UrtextWatcher (FileSystemEventHandler):

  def __init__(self,
               path,
               make_new_files=True,
               rename=False,
               recursive=False,
               import_project=False,
               init_project=False):

    self.project = _UrtextProject
    observer = Observer()
    eventhandler = UrtextWatcher()
    observer.schedule(event_handler, path, recursive=True)
    observer.start()

  def on_created(self, event):

    if not self.project.check_lock('THIS MACHINE'):
      return

    if event.is_directory:
        return None
    filename = event.src_path
    if filter(filename) == None:
      return
    if filename in _UrtextProject.files:
      # This is not really a new file.
      return None
    if _UrtextProject.parse_file(filename) == None:
        _UrtextProject.log_item(filename + ' not added.')
        return
    _UrtextProject.log_item(filename +
                            ' modified. Updating the project object')
    _UrtextProject.update()
      
    """
    def on_modified(self, event):
      # this was moved to a sublime_plugin.EventListener
       
    """
  def on_deleted(self, event):
    if not self.project.check_lock(machine):
      return

    if filter(event.src_path) == None:
        return
    filename = os.path.basename(event.src_path)
    _UrtextProject.log_item('Watchdog saw file deleted: '+filename)
    _UrtextProject.remove_file(filename)
    _UrtextProject.update()
   
  def on_moved(self, event):
      if not self.project.check_lock(machine):
        return

      if filter(event.src_path) == None:
        return
      old_filename = os.path.basename(event.src_path)
      new_filename = os.path.basename(event.dest_path)
      if old_filename in _UrtextProject.files:
          _UrtextProject.log.info('RENAMED ' + old_filename + ' to ' +
                                  new_filename)
          _UrtextProject.handle_renamed(old_filename, new_filename)


    
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
import os

class UrtextWatcher (FileSystemEventHandler):

  def __init__(self, project):
      self.project = project

  def on_created(self, event):

    if event.is_directory:
        return None
    filename = event.src_path
    
    if os.path.basename(filename) in self.project.files:
      return None
    self.project._log_item('Watchdog saw new file, adding '+filename)
    self.project.add_file(filename)
    
  def on_deleted(self, event):
    if event.is_directory:
        return None
    filename = os.path.basename(event.src_path)
    self.project._log_item('Watchdog saw file deleted, removing '+filename)
    self.project.remove_file(filename)

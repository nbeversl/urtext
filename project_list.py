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

from .project import UrtextProject, node_id_regex, NoProject
import re
import os

class ProjectList():

    def __init__(self, base_path):
        self.projects = []
        self.base_path = base_path
        self._add_folder(base_path)
        self.current_project = None
        if self.projects:
            self.current_project = self.projects[0]
        

    def _add_folder(self, folder, import_project=False):
        """ recursively add folders """
        try:
            if os.path.basename(folder) not in ['index','img','files']:
                project = UrtextProject(folder)
                self.projects.append(UrtextProject(folder))
                print('Added Urtext project '+project.title)
                print('from '+folder)
        except NoProject:
            if import_project:
                self.import_project(folder)
            else:
                print('No project found in '+folder)
        sub_dirs = next(os.walk(folder))[1]
        for subdir in sub_dirs:
            if subdir not in ['.git','.DS_Store','/']:
                self._add_folder(os.path.join(folder, subdir))

    def get_link(self, string, position=0):
        project_link_r = re.compile(r'{\"(.*?)\"}>([0-9,a-z]{3})\b')
        match = project_link_r.search(string)
        if match:
            other_project = match.group(1)
            node_id = match.group(2)
            if self.set_current_project_by_title(other_project):
                print('Urtext project switched to ' + other_project)

        # from here, could just pass in the node ID instead of the full string
        return self.current_project.get_link(string, position=position)

    def on_modified(self, filename):
        project = self._get_project_from_path(os.path.dirname(filename))
        if project:
            project.on_modified(filename)
        if project != self.current_project:
            print('Switching projects to '+project.title)
            self.current_project = project

    def _get_project_from_path(self, path):
        for project in self.projects:
            if path == project.path:
                return project
        return None

    def set_current_project_by_title(self, title):
        for project in self.projects:
            if project.title == title:
                self.current_project = project
                return True
        return False

    def nav_current(self):
        nav = self.current_project.get_home()
        if not nav:
            nav = self.current_project.nav_current()
        if not nav:
            return None
        return nav

    def set_current_project_from_path(self, path):
        for project in self.projects:
            if project.path == path:
                self.current_project = project
                return True
        return False

    def project_titles(self):
        titles = []
        for project in self.projects:
            titles.append(project.title)
        return titles
    
    def import_project(self, path):
        project = UrtextProject(path, import_project=True)
        print('Imported project '+project.title)
        self.projects.append(project)
        self.set_current_project_from_path(path)

    def get_current_project(self, path):
        for project in self.projects:
            if project.path == path:
                return project
        return None

    def init_new_project(self, path):
        if path in self.project_titles():
            print('Path already in use.')
            return None
        if not os.path.exists(path):
            os.makedirs(path)
        project = UrtextProject(path, init_project=True)
        if project:
            self.projects.append(project)
            self.set_current_project_from_path(path)
        return None

    def get_node_link(self, string):

        node_string = re.compile(node_id_regex + '(\:\d{0,20})?')
        if re.search(node_string, string):
            node_and_position = re.search(node_string, string).group(0)
            node_id = node_and_position.split(':')[0].strip()
            for project in self.projects:
                for node in project.nodes:
                    if node == node_id:
                        return {
                            'project_path': project.path,
                            'filename': project.nodes[node].filename
                        }
        return None

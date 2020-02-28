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
        self.navigation = []
        self.nav_index = -1
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
        project_link_r = re.compile(r'{\"(.*?)\"}(>([0-9,a-z]{3})\b)')
        project_name = project_link_r.search(string)
        if project_name:
            other_project = project_name.group(1)
            self.set_current_project(other_project)
            if len(project_name.groups()) == 2:
                node_id = project_name.group(3)
            else:
                node_id = self.nav_current()
            self.current_project.nav_new(node_id)
            if node_id:
                return ('NODE', 
                    node_id, 
                    self.current_project.nodes[node_id].ranges[0][0])
            return None

        # from here, could just pass in the node ID instead of the full string
        link = self.current_project.get_link(string, position=position)
        self.current_project.nav_new(link[1])
        return link

    def on_modified(self, filename):
        if self.set_current_project(os.path.dirname(filename)):
            return self.current_project.on_modified(filename)            
        return None
        
    def _get_project_from_path(self, path):
        for project in self.projects:
            if path == project.path:
                return project
        return None

    def _get_project_from_title(self, title):
        for project in self.projects:
            if title == project.title:
                return project
        return None

    def get_project(self, title_or_path):
        project = None
        project = self._get_project_from_title(title_or_path) 
        if not project:
            project = self._get_project_from_path(title_or_path) 
        return project

    def set_current_project(self, title_or_path):
        project = None
        project = self._get_project_from_title(title_or_path) 
        if not project:
            project = self._get_project_from_path(title_or_path)
        if project and project != self.current_project:
           self.current_project = project
           return print('Urtext project switched to ' + self.current_project.title)
        return project

    def nav_current(self):
        node_id = self.current_project.nav_current()        
        if not node_id:
            node_id = self.current_project.get_home()
        if not node_id:
            node_id = self.current_project.random_node()
        if not node_id:
            return None
        return node_id

    def project_titles(self):
        titles = []
        for project in self.projects:
            titles.append(project.title)
        return titles
    
    def import_project(self, path):
        project = UrtextProject(path, import_project=True)
        print('Imported project '+project.title)
        self.projects.append(project)
        self.set_current_project(path)

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
            self.set_current_project(path)
        return None

    def move_file(self, filename, to_project):
        to_project = self.get_project(to_project)
        if not to_project:
            return None
        filename = os.path.basename(filename)
        self.current_project.remove_file(filename)
        os.rename(
            os.path.join( self.current_project.path, filename),
            os.path.join( to_project.path, filename)
            )        
        to_project.add_file(filename)
        return True
        
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

    def replace_links(self, old_project_path_or_title, new_project_path_or_title, node_id):
        old_project = self.get_project(old_project_path_or_title)
        new_project = self.get_project(new_project_path_or_title)
        old_project.replace_links(node_id, new_project=new_project.title)
    
    def titles(self):
        title_list = {}
        for project in self.projects:
            for node_id in project.nodes:
                title_list[project.nodes[node_id].title] = (project.title, node_id)
        return title_list

    """
    Project List Navigation
    """

    def nav_advance(self):
        if not self.check_nav_history():
            return None

        # return if the index is already at the end
        if self.nav_index == len(self.navigation) - 1:
            print('index is at the end.')
            return None
        
        self.nav_index += 1
        project, node_id = self.navigation[self.nav_index]
        self.get_project(project).nav_advance()
        self.set_current_project(project)
        return node_id

    def nav_new(self, node_id, project=None):
        if not project:
            project = self.current_project

        # don't re-remember consecutive duplicate links
        if self.nav_index > -1 and node_id == self.navigation[self.nav_index]:
            return

        # add the newly opened file as the new "HEAD"
        del self.navigation[self.nav_index+1:]
        self.navigation.append((project.title, node_id))
        self.current_project.nav_new(node_id)
        self.nav_index += 1

    def nav_reverse(self):
        if not self.check_nav_history():
            return None

        if self.nav_index == 0:
            print('index is already at the beginning.')
            return None

        project, last_node = self.navigation[self.nav_index - 1]
        self.get_project(project).nav_reverse()
        self.set_current_project(project)
        self.nav_index -= 1
        return last_node

    def check_nav_history(self):

        if len(self.navigation) == 0:
            print('There is no nav history')
            return None

        return True



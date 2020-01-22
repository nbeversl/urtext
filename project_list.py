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
        

    def _add_folder(self, folder):
        """ recursively add folders to the list"""
        try:
            project = UrtextProject(folder)
            self.projects.append(UrtextProject(folder))
            print('Added Urtext project '+project.title)
            print('from '+folder)
        except NoProject:
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
                print('PROJECT CHANGED TO ' + other_project)

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

    def get_current_project(self, path):
        for project in self.projects:
            if project.path == path:
                return project
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

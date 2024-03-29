import os
import re

if os.path.exists(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'sublime.txt')):
    from .project import UrtextProject
    import Urtext.urtext.syntax as syntax
    from Urtext.urtext.link import UrtextLink
else:
    from urtext.project import UrtextProject
    import urtext.syntax as syntax
    from urtext.link import UrtextLink

class ProjectList():

    def __init__(self, 
        entry_point,
        editor_methods=None):
   
        if editor_methods == None:
            editor_methods = {} 
        self.entry_point = entry_point
        self.projects = []
        self.extensions = {}
        self.current_project = None
        self.editor_methods = editor_methods
        self.add_project(entry_point)            
        for project in self.projects:
            project.compile()

    def add_project(self, path, new_file_node_created=False):
        """ recursively add folders """
        if os.path.exists(path):
            paths = []
            for p in self.projects:
                paths.extend([entry['path'] for entry in p.settings['paths']])
            if path not in paths:
                project = UrtextProject(path, 
                    project_list=self,
                    editor_methods=self.editor_methods,
                    new_file_node_created=new_file_node_created)
                project.initialize()
                if project.title() not in [p.title() for p in self.projects]:
                    self.projects.append(project)
        else:
            print('No path %s' % path )

    def handle_link(self, 
        string, 
        filename, 
        col_pos=0):

        """
        Given a line of text, looks for a link to a node or project
        with node, sets the current project to the containing project,
        and returns the link information. Does not update navigation,
        this should be done by the calling method.
        """
        if not string.strip():
            return
        link = UrtextLink(string, filename, col_pos=col_pos)
        if not link.is_usable:
            return self.handle_unusable_link(link, '')

        """ If a project name has been specified, locate the project and node """
        if link.project_name:
            if not self.set_current_project(link.project_name):
                self.current_project.run_editor_method('popup',
                    'Project is not available.')
                return None

        elif filename:
            self.set_current_project(os.path.dirname(filename))

        if self.current_project and link.is_node:
            return self.current_project.handle_link(
                link,
                filename,
                col_pos=col_pos)

        if link.is_file:
            if os.path.exists(link.path):
                return self.run_editor_method(
                    'open_external_file', 
                    link.path)            
            elif self.current_project: # try as relative path
                return self.run_editor_method(
                    'open_external_file', 
                    os.path.join(self.current_project.entry_path, link.path))
        
        if link.is_http:
            return self.run_editor_method('open_http_link', link.url)

    def handle_unusable_link(self, urtext_link, message):
        if self.current_project and not self.current_project.compiled:
            message = "Project is still compiling"
        else:
            message = "No link"
        return self.run_editor_method('popup', message)

    def on_modified(self, filename):
        project = self._get_project_from_path(
            os.path.dirname(filename))
        if project:
            self.current_project = project
            project.on_modified(filename)

    def _get_project_from_path(self, path):
        if not os.path.isdir(path):
            path = os.path.dirname(path)
        for project in self.projects:
            if path in [entry['path'] for entry in project.settings['paths']]:
                return project

    def _get_project_from_title(self, title):
        for project in self.projects:
            if title == project.title():
                return project

    def get_project(self, title_or_path):
        project = self._get_project_from_title(title_or_path) 
        if not project:
            project = self._get_project_from_path(title_or_path) 
        return project

    def set_current_project(self, title_or_path):
        project = self.get_project(title_or_path) 
        if not project:
            return
        if ( not self.current_project ) or ( 
            project.title() != self.current_project.title() ) :
            self.current_project = project
            self.current_project.run_editor_method('popup',
                'Switched to project: %s ' % self.current_project.title())
        return self.current_project

    def build_contextual_link(self, 
        node_id,
        project_title=None, 
        pointer=False,
        include_project=False):

        if node_id:
            if project_title == None:
                project = self.current_project
            else:
                project = self.get_project(project_title)
            link = ''.join([
                syntax.link_opening_wrapper,
                node_id,
                syntax.link_closing_wrapper])
            if pointer:
                link = link.replace(
                    syntax.link_closing_wrapper, 
                    syntax.pointer_closing_wrapper)
            if include_project or project != self.current_project:
                link = ''.join([
                    syntax.other_project_link_prefix,
                    '"',
                    project.title(),
                    '"',
                    link])
            return link
        
    def project_titles(self):
        titles = []
        for project in self.projects:
            titles.append(project.title())
        return titles

    def get_project_title_from_link(self, target):
        match = syntax.project_link_c.search(target)
        if match:
            return match.group(1).strip()
        return target

    def get_project_from_link(self, target):
        project_name = self.get_project_title_from_link(target)
        project = self.get_project(project_name)
        return project if project else None

    def get_current_project(self, path):
        for project in self.projects:
            if project.path in project.settings['paths']:
                return project
        return None

    def visit_file(self, filename):
        self.set_current_project(filename)
        if self.current_project:
            return self.current_project.visit_file(filename)

    def visit_node(self, filename, node_id):
        self.set_current_project(filename)
        if self.current_project:
            return self.current_project.visit_node(node_id)

    def new_project_in_path(self, path):
        if os.path.exists(path):
            new_project = UrtextProject(path, project_list=self)
            self.set_current_project(path)
        else:
            print('%s does not exist' % path) 

    def move_file(self, 
        old_filename, 
        source_project_name_or_path,
        destination_project_name_or_path,
        replace_links=True):

        """
        Move a file from one project to another, checking for
        node ID duplication in the new project location, and 
        optionally replacing links to every affected node.
        """
        source_project = self.get_project(
            source_project_name_or_path)
        destination_project = self.get_project(
            destination_project_name_or_path)

        if not destination_project:
            print('Destination project `'+ destination_project_name_or_path +'` was not found.')
            return None

        if old_filename not in source_project.files:
            print('File '+ old_filename +' not included in the current project.')
            return None

        moved_nodes = list(source_project.files[old_filename].nodes)        
        source_project.drop_file(old_filename)
        new_filename = os.path.join(
            destination_project.settings['paths'][0]['path'],
            os.path.basename(old_filename))
        os.rename(old_filename, new_filename)
        """
        add_file() will raise an exception if the file makes
        duplicate nodes in the destination project
        """
        try:
            changed_ids = destination_project.add_file(new_filename) 
        except Exception:
            return None

        if replace_links:
            for moved_node in moved_nodes:
                nodes_with_links = source_project.get_links_to(moved_node.id, as_nodes=True)
                for node_with_link in nodes_with_links:
                    node_with_link.replace_links(
                        moved_node.id,
                        new_project=destination_project.title())

        source_project._run_hook('on_file_moved_to_other_project',
            old_filename,
            new_filename)

        self.run_editor_method('retarget_view', old_filename, new_filename)

        return changed_ids

    def get_all_meta_pairs(self):
        meta_values = []
        for project in self.projects:
            meta_pairs = project.get_all_meta_pairs()
            for pair in meta_pairs:
                if pair not in meta_values:
                    meta_values.append(pair)
        return meta_values

    def replace_links(self,
        old_project_path_or_title,
        new_project_path_or_title,
        node_id):
        old_project = self.get_project(old_project_path_or_title)
        new_project = self.get_project(new_project_path_or_title)
        old_project.replace_links(
            node_id,
            new_project=new_project.title())
    
    def titles(self):
        title_list = {}
        for project in self.projects:
            for node_id in project.nodes:
                title_list[project.nodes[node_id].title] = (project.title(), node_id)
        return title_list

    def is_in_export(self, filename, position):
        if not self.current_project:
            return None
        return self.current_project.is_in_export(filename, position)

    def editor_insert_link_to_node(self, node, project_title=None):
        if project_title == None:
            project_title = self.current_project.title
        if project_title:
            link = self.build_contextual_link(
                node.id,
                project_title=project_title)
            self.current_project.run_editor_method('insert_text', link)

    def delete_file(self, file_name, project=None):
        if not project:
            project = self.current_project
        project.delete_file(file_name)

    def run_editor_method(self, method_name, *args, **kwargs):
        if method_name in self.editor_methods:
            return self.editor_methods[method_name](*args, **kwargs)
        print('No editor method available for "%s"' % method_name)
        return False

    def can_use_extension(self, feature_name):
        if self.current_project and feature_name in self.current_project.extensions:
            return True
        print('%s not available' % feature_name)
        return False


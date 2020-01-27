# -*- coding: utf-8 -*-
import re
import os

parent_dir = os.path.dirname(__file__)
node_id_regex = r'\b[0-9,a-z]{3}\b'


class UrtextDynamicDefinition:
    """ Urtext Dynamic Definition """
    def __init__(self, contents):

        self.spaces = 0
        self.target_id = None
        self.include_or = []
        self.include_and = []
        self.exclude_or = []
        self.exclude_and = []
        self.tree = None
        self.sort_tagname = None
        self.metadata = {}
        self.show = 'full_contents'
        self.oneline_meta = False
        self.interlinks = None
        self.omit=[]
        self.mirror = None
        self.mirror_include_all = None
        self.export = None
        self.tag_all_key = None
        self.tag_all_value = None
        self.recursive = False
        self.reverse = False

        entries = re.split(';|\n', contents)

        for entry in entries:
            
            if entry.strip().lower() == 'oneline_meta':
                self.oneline_meta = True
                continue

            atoms = [
                atom.strip() for atom in entry.split(':') if atom.strip() != ''
            ]
            """
            skip entries without values
            """
            if len(atoms) < 2:
                continue
            """
            add metadata to target node
            """
            if atoms[0].lower() == 'metadata' and len(atoms) > 2:
                self.metadata[atoms[1]] = ':'.join(
                    atoms[2:]) 
                continue
            """
            use case-insensitive values for the rest
            """
            atoms = [atom.lower() for atom in atoms]
            """
            indentation
            """
            if atoms[0].lower() == 'mirror':
                self.mirror = atoms[1]
                if len(atoms) > 2 and atoms[2].lower() == 'include':
                    self.mirror_include_all = True
                continue

            if atoms[0].lower() == 'indent':
                self.spaces = int(atoms[1])
                continue

            if atoms[0].lower() == 'tree':
                self.tree = atoms[1]
                continue

            if atoms[0].lower() == 'interlinks':
                self.interlinks = atoms[1]
                continue

            if atoms[0].lower() == 'omit':
                self.omit = atoms[1:]
                continue


            if atoms[0].lower() == 'sort':
                self.sort_tagname = atoms[1]
                if len(atoms) > 2 and atoms[2].lower() == 'reverse':
                    self.reverse = True
                continue

            if atoms[0].lower() == 'export':
                if len(atoms) < 5 :
                    continue

                export_format = atoms[1]
                from_node = atoms[2]
                node_or_file = atoms[3]
                destination = atoms[4]

                if export_format.lower() not in ['markdown','html','plaintext']:
                    continue
                if node_or_file.lower() not in ['node','file']:
                    continue

                self.export = export_format
                self.export_to = node_or_file
                self.export_source = from_node
                self.destination = destination
                continue
            """
            Tag all subnodes
            """
            if atoms[0].lower() == 'tag_all' and len(atoms) > 2:
                self.tag_all_key = atoms[1]
                self.tag_all_value = atoms[2]
                if len(atoms) > 3 and atoms[3] == 'r':
                    self.recursive = True

            """
            target node ID
            """
            if atoms[0].lower() == 'id':
                self.target_id = re.search(node_id_regex, atoms[1]).group(0)
                continue
            """
            show contents, title
            """
            if atoms[0].lower() == 'show':
                if atoms[1].lower() == 'title':
                    self.show = 'title'
                if atoms[1].lower() == 'timeline':
                    self.show = 'timeline'
                continue
            """
            exclude/include meta
            """
            if atoms[0].lower() == 'include':
                if atoms[1].lower() == 'all':
                    self.include_or = 'all'
                    continue

                if atoms[1].lower() == 'metadata' and len(atoms) > 3:
                    
                    if atoms[2].lower() == 'and':
                        and_group = []
                        key = atoms[3]
                        values = atoms[4:]
                        for value in values:
                            and_group.append((key,value)) 
                        self.include_and.append(and_group)
                        
                    elif atoms[2].lower() == 'or':
                        key = atoms[3]
                        values = atoms[4:]
                        for value in values:
                            self.include_or.append((key,value))
                    else:
                        key = atoms[2]
                        values = atoms[3:]
                        for value in values:
                            self.include_or.append((key,value))
                    continue

            if atoms[0].lower() == 'exclude':
                if atoms[1].lower() == 'metadata' and len(atoms) > 3:
                    
                    if atoms[2].lower() == 'and':
                        and_group = []
                        key = atoms[3]
                        values = atoms[4:]
                        for value in values:
                            and_group.append((key,value)) 
                        self.exclude_and.append(and_group)
                        
                    elif atoms[2].lower() == 'or':
                        key = atoms[3]
                        values = atoms[4:]
                        for value in values:
                            self.exclude_or.append((key,value))

                    else:
                        key = atoms[2]
                        values = atoms[3:]
                        for value in values:
                            self.exclude_or.append((key,value))
                    continue

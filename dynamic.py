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
            if atoms[0] == 'metadata' and len(atoms) > 2:
                self.metadata[atoms[1]] = ':'.join(
                    atoms[2:]) 
                continue
            """
            use case-insensitive values for the rest
            """
            atoms = [atom.lower() for atom in atoms]
            """
            inndentation
            """
            if atoms[0] == 'indent':
                self.spaces = int(atoms[1])
                continue

            if atoms[0] == 'tree':
                self.tree = atoms[1]
                continue

            if atoms[0] == 'sort':
                self.sort_tagname = atoms[1]
                continue

            """
            target node ID
            """
            if atoms[0] == 'id':
                self.target_id = re.search(node_id_regex, atoms[1]).group(0)
                continue
            """
            show contents, title
            """
            if atoms[0] == 'show':
                if atoms[1] == 'title':
                    self.show = 'title'
                if atoms[1] == 'timeline':
                    self.show = 'timeline'
                continue
            """
            exclude/include meta
            """
            if atoms[0] == 'include':
                if atoms[1] == 'all':
                    self.include_or = 'all'
                    continue

                if atoms[1] == 'metadata' and len(atoms) > 3:
                    
                    if atoms[2] == 'and':
                        and_group = []
                        key = atoms[3]
                        values = atoms[4:]
                        for value in values:
                            and_group.append((key,value)) 
                        self.include_and.append(and_group)
                        
                    elif atoms[2] == 'or':
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

            if atoms[0] == 'exclude':
                if atoms[1] == 'metadata' and len(atoms) > 3:
                    
                    if atoms[2] == 'and':
                        and_group = []
                        key = atoms[3]
                        values = atoms[4:]
                        for value in values:
                            and_group.append((key,value)) 
                        self.exclude_and.append(and_group)
                        
                    elif atoms[2] == 'or':
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

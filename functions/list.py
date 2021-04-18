from .function import UrtextFunctionWithParamsFlags
from .tree import Tree

class NodeList(UrtextFunctionWithParamsFlags):

    name = ["LIST"]    
    phase = 200
    def execute(self, node_list, projects, m_format):
        contents = []
        for n in node_list:
            added_contents = Tree('-infinite').execute(n, projects[0], m_format)
            contents.append(added_contents)
        return '\n'.join(contents)

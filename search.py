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
from whoosh.writing import AsyncWriter
def rebuild_search_index(self):
    
    self.ix = create_in(os.path.join(self.path, "index"),
                        schema=self.schema,
                        indexname="urtext")

    self.writer = AsyncWriter(self.ix)

    for filename in self.files:
        self.re_search_index_file(filename, single=False)
                            
    self.writer.commit()

def re_search_index_file(self, filename, single=True):
    
    if not self.ix:
        return

    if single:
        self.writer = AsyncWriter(self.ix)

    for node_id in self.files[filename].nodes:
        self.writer.add_document(title=self.nodes[node_id].title,
                            path=node_id,
                            content=self.nodes[node_id].contents())
    if single:
        self.writer.commit()

def search(self, string):

    final_results = ''
    shown_nodes = []

    with self.ix.searcher() as searcher:
        query = QueryParser("content", self.ix.schema).parse(string)
        results = searcher.search(query, limit=1000)
        results.formatter = UppercaseFormatter()
        final_results += 'Total Results: ' + str(len(results)) + '\n\n'
        final_results +='\n----------------------------------\n'
        for result in results:
            node_id = result['path']
            if node_id in self.nodes:
                if node_id not in shown_nodes:
                    final_results += ''.join([
                        self.nodes[node_id].title,' >', node_id, '\n',
                        result.highlights("content"),
                        '\n----------------------------------\n'])
                    shown_nodes.append(node_id)
            else:
                final_results += node_id + ' ( No longer in the project. Update the search index. )\n\n'

    return final_results

search_functions = [ rebuild_search_index, re_search_index_file, search]
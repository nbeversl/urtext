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
from whoosh.qparser import QueryParser
from whoosh.highlight import UppercaseFormatter

def rebuild_search_index(self):
    
    writer = AsyncWriter(self.ix)

    for node_id in self.nodes:
        node = self.nodes[node_id]
        try:
            writer.update_document(title=node.title,
                            path=node.id,
                            content=node.content_only())
        except:
            print('ERROR in '+node_id)

    writer.commit()
    
def search(self, string):

    final_results = ''
    shown_nodes = []

    with self.ix.searcher() as searcher:
        qp = QueryParser("content", self.ix.schema)
        query = qp.parse(string)
        results = searcher.search(query, limit=1000)
        results.formatter = UppercaseFormatter()
        final_results += 'Total Results: ' + str(len(results)) + '\n\n'
        final_results +='\n----------------------------------\n'
        for result in results:
            node_id = result['path']
            if node_id in self.nodes and node_id not in shown_nodes:
                final_results += ''.join([
                    self.nodes[node_id].title,' >', node_id, '\n',
                    result.highlights("content"),
                    '\n----------------------------------\n'])
                shown_nodes.append(node_id)
            else:
                final_results += node_id + ' ( No longer in the project. Update the search index. )\n\n'

    return final_results

def search_term(self, string, exclude=[]):
    
    with self.ix.searcher() as searcher:
        qp = QueryParser("content", self.ix.schema)
        query = qp.parse(string)
        results = searcher.search(query, limit=1000)
        results.formatter = UppercaseFormatter()
        final_results = ''
        for result in results:
            node_id = result['path']
            if node_id in exclude:
                continue
            final_results += self.nodes[node_id].title + ' >'+node_id +'\n - - - - - - - - - - - - - - - -\n\n' + result.highlights("content").strip('\t').strip() +'\r\r'
        return final_results

search_functions = [ rebuild_search_index, search, search_term ]
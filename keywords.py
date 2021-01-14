#from project_list import ProjectList
#from gensim.summarization import keywords
from python_rake import Rake
#from rake import RakeImpl
import time
from sklearn.feature_extraction.text import TfidfVectorizer
import numpy as np

path = '/Users/n_beversluis/Library/Mobile Documents/iCloud~com~omz-software~Pythonista3/Documents/archive'
project_list = ProjectList(path) 

nate = '/Users/n_beversluis/Library/Mobile Documents/iCloud~com~omz-software~Pythonista3/Documents/archive/nate-big-project'
project_list.set_current_project(nate)

while not project_list.current_project.compiled:
    time.sleep(1)
# r = Rake()
# for n in project_list.current_project.nodes:
#     text = project_list.current_project.nodes[n].content_only()
#     a=r.extract_keywords_from_text(text)
#     b=r.get_ranked_phrases()
#     c=r.get_ranked_phrases_with_scores()  
#     print('RANKED PHRASES WITH SCORES')
#     for i in c:
#         print(i[0])
#         print(i[1])
#     print('----------------------------------------------------')

corpus = [project_list.current_project.nodes[n].content_only() for n in project_list.current_project.nodes]
tfidf = TfidfVectorizer().fit_transform(corpus)
# no need to normalize, since Vectorizer will return normalized tf-idf
pairwise_similarity = tfidf * tfidf.T

arr = pairwise_similarity.toarray()
np.fill_diagonal(arr, np.nan)
for c in corpus:
    print(c)
    print('MOST SIMILAR TO:')
    input_idx = corpus.index(c)
    result_idx = np.nanargmax(arr[input_idx])
    print(corpus[result_idx])
    print('----------------------------------------------------')
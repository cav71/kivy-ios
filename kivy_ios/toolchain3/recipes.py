import contextlib
import collections
import pathlib
import typing
import collections

from pathlib import Path
from typing import Optional, List, Tuple, Generator, Union
from types import ModuleType

from kivy_ios.toolchain import Recipe
from . import util


class DependencyError(Exception):
    pass


class DependencyMissing(DependencyError):
    pass


def find_recipes(path: Path) -> List[Recipe]:
    recipes = []
    for p in path.glob("*"):
        if not (p / "__init__.py").exists():
            continue
        mod = util.loadr(p.name, p / "__init__.py")
        if not mod:
            continue
        recipes.append(mod)
    return recipes


def tree(root:str, recipes: Recipe, what: Optional[str]=None) -> Generator[Union[Tuple[int, str, List[str]], Tuple[int, str, List[str], List[str]]], None, None]:
    queue = collections.deque()
    levels = collections.defaultdict(int)
    parents = collections.defaultdict(list)
    children = collections.defaultdict(list)
    queue.append(root)
    equivalence = { "python": "python3" }
    equivalence = { }
    assert "python" not in recipes
    class Dummy:
        def __init__(self):
            self.depends = []
    recipes["python"] = Dummy()
    while queue:
        node = queue.popleft()
        node = equivalence.get(node, node)
        
        if node not in recipes:
            raise DependencyMissing(f"cannot find [{node}] in dependency list for [{parents[node]}]")
        subs = recipes[node].depends
        for sub in subs:
            sub = equivalence.get(sub, sub)
            parents[sub].append(node)
            children[node].append(sub)
            levels[sub] = levels[node] + 1
        if not what or what == "both":
            yield levels[node], node, parents.get(node, None), children.get(node, None)
        elif what == "children":
            yield levels[node], node, children.get(node, None)
        elif what == "parents":
            yield levels[node], node, parents.get(node, None)
        else:
            raise RuntimeError(f"invalid what {what} parameter")
        queue.extend(recipes[node].depends)
        
    
        
# import collections
# import networkx as nx
# import matplotlib.pyplot as plt
# graph = nx.DiGraph()
# 


# mod = loadr("kivy_ios.recipes.kivy")
# seen = set()
# queue = collections.deque()
# queue.append(mod.name)
# 
# while queue:
#     node = queue.popleft()
#     if node not in seen:
#         mod = loadr(f"kivy_ios.recipes.{node}")
#         queue.extend(mod.depends)
#         for d in mod.depends:
#             print(f"{d} -> {node}")
#             graph.add_edge(node, d)
#         seen.add(node)
# #nx.write_graphml(graph, "out.graphml") # with_labels=True, font_weight='bold')
# #plt.show()
# from rich.tree import Tree
# from rich import print
# nodes = {}
# tree = Tree("kivy")
# 
# for parent, node in nx.bfs_tree(graph, "kivy").edges():
#     nodes[parent] = nodes.get(parent, tree.add(parent))
#     nodes[parent].add(node)
#     print(node)
#     
# print(tree)



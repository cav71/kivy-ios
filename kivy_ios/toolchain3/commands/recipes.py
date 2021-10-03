import click


def recipes(ctx):
    from ..recipes import find_recipes
    recipes = find_recipes(ctx.recipesdir)
    for recipe in recipes:
        doc = "  " + recipe.__doc__.replace("\n", "  \n")
        print(f"""
{recipe.name}
  from: {recipe.recipe_dir}
{doc}
""".strip())


@click.argument("target")
def dependencies(ctx, target):
    from itertools import groupby
    from ..recipes import find_recipes, tree

    recipes = { r.name: r for r in find_recipes(ctx.recipesdir)}
    if target not in recipes:
        raise click.UsageError(f"target {target} not found in recipes")

    from rich.tree import Tree

    root = Tree("Dependencies")
    nodes = {}
    #breakpoint()
    for level, node, children in tree(target, recipes, what="children"):
        print(level, node, children)
        if not level:
            nodes[node] = root.add(node)
        parent = nodes[node]
        for child in children or []:
            #assert child not in nodes, "circular dependency"
            nodes[child] = parent.add(child)
    from rich import print as xprint
    xprint(root)
    

    #walk = groupby(sorted(tree(target, recipes), key=lambda x: -x[0]), key=lambda y: y[0])
    #for level, node, parents in sorted(tree(target, recipes), key=lambda x: -x[0]):
    #    print(level, node, parents)
    #for level, group in walk:
    #    print(level)
    #    for g in group:
    #        print("", g)


import typing

import attr
import click
import rich
from kivy_ios.toolchain3 import context


@click.group()
@click.pass_context
@context.context_args
def main(ctx):
    pass

from .commands.info import info
info = main.command()(click.pass_obj(info))

from .commands.recipes import recipes, dependencies
recipes = main.command()(click.pass_obj(recipes))
dependencies = main.command()(click.pass_obj(dependencies))

from .commands.build import build
build = main.command()(click.pass_obj(build))

if __name__ == "__main__":
    main()


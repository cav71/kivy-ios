import kivy_ios.toolchain3.sdk

def info(ctx):
    "show current configuration"
    from typing import Sequence
    from attr import fields
    from rich.console import Console
    from rich.text import Text
    from rich.table import Table

    text = Text()
    pre = [
        "basedir",
        "recipesdir",
        "workdir", 
        "builddir",
        "cachedir",
        "prefix",
    ]
    post = [
        "env"
    ]
    fields = pre + list(set(f.name for f in fields(ctx.__class__)) - set(pre) - set(post)) + post

    table = Table(title="Context config")
    table.add_column("name")
    table.add_column("value(s)")
    
    for field in fields:
        value = getattr(ctx, field)
        lines = []
        if isinstance(value, Sequence):
            if value:
                for item in value or [ "no-items" ]:
                    lines.append(f"{item}")
            else:
                lines.append("[]")
        else:
            lines.append(str(value))
        table.add_row(f"[bold red]{field}", "\n".join(lines))

    console = Console()
    console.print(table)

    table = Table(title="SDKs - available")
    table.add_column("key")   
    table.add_column("name")   
    for name, sdk in kivy_ios.toolchain3.sdk.sdks().items():
        table.add_row(name, sdk["displayName"]) 
    console.print(table)


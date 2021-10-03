import click
import jinja2
import attr

import kivy_ios.toolchain3.sdk
from kivy_ios.toolchain3 import util


class BuildUnit:
    version = "2.5.5"
    sources = [
        f"https://download.savannah.gnu.org/releases/freetype/freetype-old/freetype-{version}.tar.bz2"
    ]
    def __init__(self, name):
        self.name = name

    def download(self, ctx):
        from kivy_ios.toolchain3.downloader import download
        destdir = ctx.cachedir / "downloads"
        destdir.mkdir(parents=True, exist_ok=True)
        result = []
        for source in self.sources:
            if isinstance(source, str):
                source, subdir = source, util.rstrips(source.rpartition("/")[2], { ".tar.bz2", ".tgz" })
            else:
                source, subdir = source
            result.append((download(source, destdir.resolve()), subdir))
        return result

    def run(self, ctx, sdk, arch):
        env = kivy_ios.toolchain3.sdk.load_macos_sdk_env(sdk, arch)

        subs = [ "-arch", arch, "-pipe", "-no-cpp-precomp", "-O3", ]
        env.gnuflags.cflags.extend(subs)
        env.gnuflags.cxxflags.extend(subs)

        for field in attr.fields(env.gnuflags.__class__):
            setattr(env.gnuflags, field.name,
                getattr(ctx.gnuflags, field.name) + getattr(env.gnuflags, field.name))

        builddir = ctx.builddir / self.name
        builddir.mkdir(parents=True, exist_ok=True)
        environment = jinja2.Environment(
            loader=jinja2.FileSystemLoader(searchpath=ctx.basedir / "templates")
        )
        tarballs = dict(self.download(ctx))

        script = builddir / "run-me.sh"
        with script.open("w") as fp:
            tmpl = environment.get_template("gnudance.tmpl")
            fp.write(tmpl.render(ctx=ctx, env=env, 
                builddir=builddir,
                tarballs=tarballs))
        script.chmod(0o700)


@click.argument("sdk")
@click.argument("arch", type=click.Choice(["x86_64", "arm64"], case_sensitive=False))
@click.argument("packages", nargs=-1)
def build(ctx, sdk, arch, packages):
    "build a recipe"
    sdks = kivy_ios.toolchain3.sdk.sdks()
    if sdk not in sdks:
        raise click.BadParameter(f"unknown sdk {sdk}")
    bu = BuildUnit(packages[0])
    bu.download(ctx)
    bu.run(ctx, sdks[sdk], arch)
    

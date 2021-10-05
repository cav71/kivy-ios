from kivy_ios.toolchain import Recipe, sh
from os.path import join


sh = sh.child(__name__)


class FreetypeRecipe(Recipe):
    version = "2.5.5"
    url = "https://download.savannah.gnu.org/releases/freetype/freetype-old/freetype-{version}.tar.bz2"
    library = "objs/.libs/libfreetype.a"
    include_dir = ["include", ("builds/unix/ftconfig.h", "config/ftconfig.h")]
    include_per_arch = True

    def build_arch(self, arch):
        build_env = arch.get_env()
        #configure = self.sh.Command(join(self.build_dir, "configure"))
        breakpoint()
        self.sh.configure(
                "CC={}".format(build_env["CC"]),
                "LD={}".format(build_env["LD"]),
                "CFLAGS={}".format(build_env["CFLAGS"]),
                "LDFLAGS={}".format(build_env["LDFLAGS"]),
                "--prefix=/",
                "--host={}".format(arch.triple),
                "--without-png",
                "--without-bzip2",
                "--without-fsspec",
                "--without-harfbuzz",
                "--without-old-mac-fonts",
                "--enable-static=yes",
                "--enable-shared=no")
        self.sh.make("clean")
        self.sh.make(self.ctx.concurrent_make)


recipe = FreetypeRecipe()

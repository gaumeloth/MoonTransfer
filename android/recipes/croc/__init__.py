from os.path import join
from shutil import which

import sh

from pythonforandroid.recipe import Recipe
from pythonforandroid.toolchain import current_directory, shprint
from pythonforandroid.util import ensure_dir


class CrocRecipe(Recipe):
    version = "11.0.1"
    url = "https://github.com/schollz/croc/archive/refs/tags/v{version}.tar.gz"
    sha512sum = (
        "fc316adff9c977d38031d49a87f9e6df2da1596e2279d8890cfc81d5c63f2f57"
        "ed082117b5e26eba8b9f6b7c80355746563be11b8a460ef4ae089666f3030b26"
    )
    built_libraries = {"libcroc.so": "."}

    def get_recipe_env(self, arch=None, with_flags_in_cc=True):
        env = super().get_recipe_env(arch, with_flags_in_cc=False)
        go_arch = {"arm64-v8a": "arm64"}.get(arch.arch)
        if go_arch is None:
            raise ValueError(f"Unsupported croc Android architecture: {arch.arch}")

        # Go does not consume p4a's CFLAGS when selecting the cgo compiler.
        env["CC"] = arch.get_clang_exe(with_target=True)
        env["CXX"] = arch.get_clang_exe(with_target=True, plus_plus=True)

        cache_root = join(self.ctx.build_dir, "go-cache")
        module_cache = join(self.ctx.build_dir, "go-mod-cache")
        ensure_dir(cache_root)
        ensure_dir(module_cache)
        env.update(
            {
                # Android's system DNS resolver is only available to Go via cgo.
                "CGO_ENABLED": "1",
                "GOCACHE": cache_root,
                "GOMODCACHE": module_cache,
                "GOOS": "android",
                "GOARCH": go_arch,
                "GOARM64": "v8.0",
                "GOTOOLCHAIN": "local",
            }
        )
        return env

    def build_arch(self, arch):
        go = which("go")
        if go is None:
            raise RuntimeError("Go is required to build croc for Android.")

        env = self.get_recipe_env(arch)
        with current_directory(self.get_build_dir(arch.arch)):
            shprint(
                sh.Command(go),
                "build",
                "-mod=readonly",
                "-trimpath",
                "-buildvcs=false",
                "-ldflags=-s -w -buildid=",
                "-o",
                "libcroc.so",
                ".",
                _env=env,
            )


recipe = CrocRecipe()

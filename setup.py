"""Bundle the authoritative root platform runner and platforms into wheels."""
from pathlib import Path
from shutil import copy2, copytree, rmtree
from setuptools import setup
from setuptools.command.build_py import build_py


class BuildWithPlatforms(build_py):
    def run(self):
        super().run()
        source = Path(__file__).resolve().parent / 'platforms'
        target = Path(self.build_lib) / 'browser_workspace_app' / 'platforms'
        if target.exists():
            rmtree(target)
        copytree(source, target, ignore=lambda _dir, names: {n for n in names if n == '__pycache__' or n.endswith(('.pyc', '.pyo'))})
        copy2(Path(__file__).resolve().parent / 'platform_runner.py', Path(self.build_lib) / 'browser_workspace_app' / 'platform_runner.py')


setup(cmdclass={'build_py': BuildWithPlatforms})

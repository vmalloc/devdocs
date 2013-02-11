#! /usr/bin/python
import os
import subprocess

root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
tarfile = os.path.join(root_dir, "__webapp.tar")

def _is_dir_newer(directory, filename):
    file_mtime = os.stat(filename).st_mtime
    for dirname, _, filenames in os.walk(directory):
        for filename in filenames:
            if filename.endswith(".pyc"):
                continue
            if os.stat(os.path.join(dirname, filename)).st_mtime > file_mtime:
                return True
    return False

def _tar():
    if 0 != subprocess.call("tar cvf __webapp.tar webapp", shell=True, cwd=root_dir):
        raise Exception("Tar failed")

if __name__ == '__main__':
    if not os.path.exists(tarfile) or _is_dir_newer(os.path.join(root_dir, "webapp"), tarfile):
        _tar()

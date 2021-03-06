#! /usr/bin/python
# -*- mode: python -*-
from contextlib import contextmanager
import glob
import itertools
import logbook
import os
import re
import stat
import shutil
import subprocess
import tempfile
from raven import Client
from rq_queues import default_queue, retry_queue
from sentry_dsn import SENTRY_DSN

sentry = Client(SENTRY_DSN)

_logger = logbook.Logger(__name__)

def unzip_docs(filename, dest, package_name, version):
    directory = os.path.dirname(filename)
    sphinx_dir = os.path.join(directory, "sphinx", "html")
    if not os.path.isdir(sphinx_dir):
        os.makedirs(sphinx_dir)
    subprocess.check_call(["tar", "xzf", filename, "-C", sphinx_dir])
    os.unlink(filename)

    _write_metadata(directory, package_name=package_name, version=version)
    _move_to_dest(directory, os.path.join(dest, package_name))


def build_docs(repo, dest, pypi=None, retries_left=5):
    try:
        temp_dest = tempfile.mkdtemp()
        with _ensuring_virtualenv() as env:
            with _temporary_checkout(repo, env, pypi) as temp_checkout:
                temp_checkout.write_metadata(temp_dest)
                temp_checkout.generate_sphinx(os.path.join(temp_dest, "sphinx"))
                temp_checkout.generate_dash(os.path.join(temp_dest, "dash"))
                temp_checkout.write_metadata(temp_dest)
                _move_to_dest(temp_dest, os.path.join(dest, temp_checkout.get_package_name()))
            return 0
    except:
        _logger.error("Exception while building docs", exc_info=True)
        retries_left -= 1
        if retries_left <= 0:
            sentry.captureException()
        else:
            retry_queue.enqueue_call(
                retry_build_docs,
                args=(repo, dest, pypi, retries_left),
            )
def retry_build_docs(*args):
    """
    Meant to be called from cron job. Should only push the rebuild job again to the main (default) queue
    """
    default_queue.enqueue_call(build_docs, args=args)

def _temporary_checkout(repo, env, pypi):
    directory = os.path.join(tempfile.mkdtemp(), "src")
    _execute_assert_success("git clone {} {}".format(repo, directory))
    return Checkout(directory, env, pypi)

@contextmanager
def _ensuring_virtualenv():
    virtualenv_path = "/tmp/virtualenvs/builder"
    _execute_assert_success("virtualenv {}".format(virtualenv_path))
    try:
        for package in ["doc2dash", "Sphinx==1.1.3"]:
            _execute_assert_success("{0}/bin/pip install --use-wheel --find-links /opt/devdocs/wheels {1}".format(virtualenv_path, package))
        yield virtualenv_path
    finally:
        shutil.rmtree(virtualenv_path)

class Checkout(object):
    def __init__(self, path, venv, pypi):
        super(Checkout, self).__init__()
        self._path = path
        self._venv = venv
        self._package_name = self._version = self._description = None
        self._fetch_metadata()
        self._install(pypi)

    def get_package_name(self):
        return self._package_name

    def _fetch_metadata(self):
        _execute_in_venv(self._venv, "python setup.py sdist", cwd=self._path)
        [pkg_info_filename] = glob.glob("{}/*.egg-info/PKG-INFO".format(self._path))
        with open(pkg_info_filename) as pkg_info_file:
            metadata = {}
            for metadata_entry in pkg_info_file:
                key, value = metadata_entry.split(":", 1)
                metadata[key.strip()] = value.strip()
        self._package_name = metadata["Name"]
        self._description = metadata["Description"]
        self._version = _execute_assert_success(
            "git describe --tags",
            cwd=self._path, stdout=subprocess.PIPE).stdout.read().strip()
        _logger.info("Processing %s (version %s)", self._package_name, self._version)

    def _install(self, pypi):
        command = "pip install --use-wheel --find-links /opt/devdocs/wheels"
        if pypi:
            command += " -i {0}".format(pypi)
        command += " -e {0}".format(self._path)
        _execute_in_venv(self._venv, command, cwd=self._path)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def generate_sphinx(self, dest_dir):
        _execute_in_venv(
            self._venv,
            "python setup.py build_sphinx --version {version} --release {version} -E -a --build-dir {dest}".format(dest=dest_dir, version=self._version),
            cwd=self._path
        )

    def generate_dash(self, dest_dir):
        temp_path = tempfile.mkdtemp()
        try:
            temp_sphinx_dir = os.path.join(tempfile.mkdtemp(), "sphinx")
            with self._patched_repository_context():
                self.generate_sphinx(temp_sphinx_dir)
                _execute_in_venv(self._venv, "doc2dash {temp_sphinx_dir}/html -i {icon} -n {self._package_name} --destination {dest}/".format(
                    icon=_get_icon_path(),
                    self=self,
                    temp_sphinx_dir=temp_sphinx_dir,
                    dest=dest_dir,
                    ))
            _execute_assert_success("tar -czvf {0}.tgz {0}.docset".format(self._package_name), cwd=dest_dir)
            shutil.rmtree(os.path.join(dest_dir, "{0}.docset".format(self._package_name)))
        finally:
            shutil.rmtree(temp_path)

    @contextmanager
    def _patched_repository_context(self):
        try:
            self._patch_repo()
            yield
        finally:
            _execute_assert_success("git reset --hard", cwd=self._path)

    def _patch_repo(self):
        config_filename = os.path.join(self._path, "doc", "conf.py")
        with open(config_filename) as f:
            config = f.read()
        config_dict = {"__file__" : config_filename}
        exec(config, config_dict)
        html_options = config_dict.get("html_theme_options", {})
        html_options["nosidebar"] = True
        re.sub(r"#?html_theme_options\s+=\s+\{[^\}]*\}", "html_theme_options={!r}".format(html_options), config)
        with open(config_filename, "w") as f:
            f.write(config)

    def write_metadata(self, dest_dir):
        _write_metadata(dest_dir, package_name=self._package_name, version=self._version, description=self._description)

def _get_icon_path():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "docs_icon.png"))

def _fix_permissions(directory):
    _fix_permissions_single_file(directory)
    for path, dirnames, filenames in os.walk(directory):
        for name in itertools.chain(dirnames, filenames):
            full_path = os.path.join(path, name)
            _fix_permissions_single_file(full_path)
def _fix_permissions_single_file(path):
    mode = os.stat(path).st_mode | stat.S_IRGRP | stat.S_IROTH
    if os.path.isdir(path):
        mode |= stat.S_IXGRP | stat.S_IXOTH
    os.chmod(path, mode)

def _move_to_dest(src, dest):
    _logger.debug("move: {} --> {}", src, dest)
    deleted = dest + ".deleted"
    if os.path.exists(dest):
        os.rename(dest, deleted)
    os.rename(src, dest)
    _fix_permissions(dest)
    if os.path.exists(deleted):
        shutil.rmtree(deleted)

def _execute_assert_success(cmd, *args, **kwargs):
    _logger.debug("exec: {}", cmd)
    p = subprocess.Popen(cmd, shell=True,
                         *args, **kwargs)
    if 0 != p.wait():
        raise ExecutionError("Command failed: cmd: {!r}".format(cmd))
    return p

def _execute_in_venv(venv, cmd, *args, **kwargs):
    _execute_assert_success("bash -c 'source {}/bin/activate && {}'".format(venv, cmd), *args, **kwargs)

class ExecutionError(Exception):
    pass

def _write_metadata(dest, package_name, version, description=None):
    metadata_dir = os.path.join(dest, "metadata")
    if not os.path.isdir(metadata_dir):
        os.makedirs(metadata_dir)
    for field, value in (("package_name", package_name), ("version", version), ("description", description)):
        if value is None:
            continue
        with open(os.path.join(metadata_dir, field), "w") as f:
            f.write(value)

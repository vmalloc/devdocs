import httplib
from flask import (
    Flask,
    abort,
    make_response,
    render_template,
    request,
    send_from_directory,
    url_for,
    )
from werkzeug import secure_filename
import os
from tempfile import mkdtemp
from urlobject import URLObject
from builder import build_docs, unzip_docs
from raven.contrib.flask import Sentry
from sentry_dsn import SENTRY_DSN
from rq_queues import default_queue

# Tell RQ what Redis connection to use

app = Flask(__name__)
app.config["DOCS_ROOT"] = "/opt/devdocs/docs"
app.config["DEBUG"] = True

sentry = Sentry(app, dsn=SENTRY_DSN)

if not os.path.exists(app.config["DOCS_ROOT"]):
    os.makedirs(app.config["DOCS_ROOT"])

@app.route("/")
def index():
    return render_template("index.html", projects=get_projects())

@app.route("/build", methods=["POST"])
def build():
    default_queue.enqueue_call(
        build_docs,
        args=(request.values["url"], app.config["DOCS_ROOT"], request.values.get("pypi_url", None)))
    return "Queued"

@app.route("/upload/<package_name>/<version_name>", methods=["POST"])
def upload(package_name, version_name):
    if len(request.files) != 1:
        return make_response(("File upload requires one file", httplib.BAD_REQUEST, {}))
    [(_, uploaded_file)] = request.files.items()
    filename = secure_filename(uploaded_file.filename)
    directory = mkdtemp()
    local_filename = os.path.join(directory, filename)
    uploaded_file.save(local_filename)
    default_queue.enqueue_call(
        unzip_docs, args=(local_filename, app.config["DOCS_ROOT"], package_name, version_name)
    )
    return "Queued"

@app.route("/dash/<package_name>.xml")
def generate_docset_xml(package_name):
    version_filename = os.path.join(app.config["DOCS_ROOT"], package_name, "metadata", "version")
    if not os.path.isfile(version_filename):
        abort(httplib.NOT_FOUND)
    with open(version_filename) as version_file:
        version = version_file.read().strip()
    docset_url = URLObject(request.base_url).\
                 with_path(url_for("get_docset", package_name=package_name, filename=package_name + ".tgz"))
    return """<entry>
<version>{version}</version>
<url>{url}</url>
</entry>""".format(version=version, url=docset_url)

@app.route("/dash/<package_name>/<path:filename>")
def get_docset(package_name, filename):
    return send_from_directory(os.path.join(app.config["DOCS_ROOT"], package_name, "dash"), filename)


@app.route("/sphinx/<package_name>/")
@app.route("/sphinx/<package_name>/<path:filename>")
def serve_sphinx(package_name, filename="index.html"):
    return send_from_directory(
        os.path.join(app.config["DOCS_ROOT"], package_name, "sphinx", "html"),
        filename
    )

def get_projects():
    for project_name in os.listdir(app.config["DOCS_ROOT"]):
        project_root = os.path.join(app.config["DOCS_ROOT"], project_name)
        project = {}
        for attr in ["package_name", "version"]:
            with open(os.path.join(project_root, "metadata", attr)) as attr_file:
                project[attr] = attr_file.read().strip()
            project["has_dash"] = os.path.isdir(os.path.join(project_root, "dash"))
        yield project

if __name__ == "__main__":
    app.run(debug=True, port=8080)

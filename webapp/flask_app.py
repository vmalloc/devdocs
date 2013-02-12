import httplib
from flask import (
    Flask,
    abort,
    render_template,
    request,
    send_from_directory,
    url_for,
    )
import os
from rq import Connection, Queue
from redis import Redis
from urlobject import URLObject
from builder import build_docs

# Tell RQ what Redis connection to use
redis_conn = Redis()
async_queue = Queue(connection=redis_conn)

app = Flask(__name__)
app.config["DOCS_ROOT"] = "/opt/devdocs/docs"
app.config["DEBUG"] = True
app.config["JOB_TIMEOUT"] = 60 * 60

if not os.path.exists(app.config["DOCS_ROOT"]):
    os.makedirs(app.config["DOCS_ROOT"])

@app.route("/")
def index():
    return render_template("index.html", projects=get_projects())

@app.route("/build", methods=["POST"])
def build():
    async_queue.enqueue_call(
        build_docs,
        args=(request.values["url"], app.config["DOCS_ROOT"], request.values.get("pypi_url", None)),
        timeout=app.config["JOB_TIMEOUT"])
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
        project = {}
        for attr in ["package_name", "version"]:
            with open(os.path.join(app.config["DOCS_ROOT"], project_name, "metadata", attr)) as attr_file:
                project[attr] = attr_file.read().strip()
        yield project

if __name__ == "__main__":
    app.run(debug=True)

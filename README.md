# Overview
This is a small deployable webapp to index Sphinx-based docs and expose them as [Dash](http://kapeli.com/ )  docsets.

# Install
Deployment requires [Ansible](http://ansible.cc/ ) to be installed.

To test via vagrant, just run `vagrant up`. The webserver will be available via http://127.0.0.1:8080. You will need 

To install to a server, create an inventory file (for instance, in `./inventory`), which looks like the following:

	[webservers]
	my.deployment.server
	
And then run ansible-playbook to deploy:

	ansible-playbook -u root  -i ./inventory ./ansible/deploy.yml

# Usage
To build a doc from a git repository, post the following:

	curl http://my.deployment.server/build -F url=git://your.git.server/repo

Alternatively you can upload a .tgz file containing your already-built HTML directory:

    cutl http://my.deployment.server/upload/PROJET_NAME/PROJECT_VERSION -F file=@myfile.tgz

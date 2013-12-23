default: test

testserver: env
	.env/bin/python webapp/flask_app.py

deploy:
	.env/bin/ansible-playbook -i ansible/inventory ansible/deploy.yml

clean:
	rm -rf .env
	find . -name "*.pyc" -delete

env: .env/.up-to-date

.PHONY: env

.env/.up-to-date: webapp/pip_requirements.txt
	virtualenv .env
	.env/bin/pip install -r webapp/pip_requirements.txt
	touch .env/.up-to-date

deploy: __webapp.tar env
	.env/bin/ansible-playbook -i ansible/inventory ansible/deploy.yml

vagrant_up:
	vagrant up
.PHONY: vagrant_up

__webapp.tar:
	python ansible/build_tar.py
.PHONY: __webapp.tar

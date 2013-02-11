from fabric.api import *

def deploy_to_vagrant():
    local("vagrant up")
    local("ansible-playbook -u root --private-key $HOME/.vagrant.d/insecure_private_key -i 127.0.0.1:2222, ./deploy.yml")
